"""Google OR-Tools CP-SAT allocation engine. No Streamlit, no SQL: ProblemData in, SolveResult out.

Decision variable  x[i, j] in {0, 1}  : applicant i is seated in program j.

Hard constraints
  (1) sum_j x[i, j] <= 1                 one seat per applicant
  (2) sum_i x[i, j] <= capacity[j]       never exceed capacity
  (3) x[i, j] <= eligibility[i, j]       prerequisites + ranked + active
  (+) optional forced assignments / forbidden pairs for counterfactuals

Objective (all integer, lexicographic by scaling)
  Mode A (initial)   : maximise SCALE * sum_ij points(rank_ij) * x[i, j]  +  sum_ij merit_i * x[i, j]
                       The merit term (0..100 per seated applicant, earlier applicants get a +1 bonus
                       via a timestamp rank) is a deterministic tie-breaker: SCALE exceeds the largest
                       possible merit sum, so it can never override a preference-point difference.
  Mode B (reassign)  : maximise preference - mu * displacement
                       displacement = #applicants not keeping their previous seat
                                    = sum_i (1 - x[i, prev_i])   (per-applicant |x - prev|)
                       With mu > max points (100) this is lexicographic: every lost seat
                       costs more than any preference gain can repay.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from ortools.sat.python import cp_model

from optimization.problem import ProblemData, points_for_rank

MODE_INITIAL = "initial"
MODE_REASSIGN = "reassign"
DEFAULT_MU = 1000  # displacement penalty; > 100 makes stability lexicographically dominant
MERIT_WEIGHT = 1000            # merit (0..100) * MERIT_WEIGHT  +  earliness (0..999): merit dominates timestamp
TIE_BREAK_MAX = 100 * MERIT_WEIGHT + 999


def _scale(n_applicants: int) -> int:
    """Smallest power of ten strictly larger than the max total tie-break bonus."""
    bound = n_applicants * TIE_BREAK_MAX
    scale = 10
    while scale <= bound:
        scale *= 10
    return scale

STATUS_NAMES = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "MODEL_INVALID",
    cp_model.UNKNOWN: "UNKNOWN",
}

STATUS_EXPLANATIONS = {
    "OPTIMAL": "Solver proved this allocation is optimal for the declared objective.",
    "FEASIBLE": "A valid allocation was found but optimality was NOT proven within the time limit.",
    "INFEASIBLE": "Solver proved that no allocation satisfies all hard constraints.",
    "UNKNOWN": "Unresolved: the solver hit its time limit before finding or refuting a solution.",
    "MODEL_INVALID": "The model itself is malformed (programming error).",
}


@dataclass
class SolveResult:
    status: str
    mode: str
    assignment: Dict[int, int] = field(default_factory=dict)       # applicant -> program
    objective: Optional[float] = None
    best_bound: Optional[float] = None
    wall_time_s: float = 0.0
    preference_score: int = 0
    assigned_count: int = 0
    unassigned: List[int] = field(default_factory=list)
    changed: Dict[int, Tuple[Optional[int], Optional[int]]] = field(default_factory=dict)  # aid -> (before, after)
    kept: List[int] = field(default_factory=list)
    rank_histogram: Dict[int, int] = field(default_factory=dict)
    mu: int = 0
    num_branches: int = 0
    num_conflicts: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def has_solution(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")

    @property
    def is_proven_optimal(self) -> bool:
        return self.status == "OPTIMAL"

    @property
    def reassigned_count(self) -> int:
        return len(self.changed)

    @property
    def explanation(self) -> str:
        return STATUS_EXPLANATIONS.get(self.status, self.status)

    def summary(self) -> dict:
        return {
            "status": self.status,
            "mode": self.mode,
            "objective": self.objective,
            "best_bound": self.best_bound,
            "wall_time_s": round(self.wall_time_s, 3),
            "preference_score": self.preference_score,
            "assigned": self.assigned_count,
            "unassigned": len(self.unassigned),
            "reassigned": self.reassigned_count,
            "kept": len(self.kept),
            "rank_histogram": self.rank_histogram,
        }


def _diff(previous: Dict[int, int], new: Dict[int, int], applicant_ids: Iterable[int]):
    changed, kept = {}, []
    for aid in applicant_ids:
        b, a = previous.get(aid), new.get(aid)
        if b != a:
            changed[aid] = (b, a)
        elif a is not None:
            kept.append(aid)
    return changed, kept


class AllocationModel:
    """Builds and solves the CP-SAT model. Instantiate once per solve."""

    def __init__(
        self,
        problem: ProblemData,
        mode: str = MODE_INITIAL,
        mu: int = DEFAULT_MU,
        forced: Optional[Dict[int, int]] = None,      # applicant -> program that MUST hold
        forbidden: Optional[Iterable[Tuple[int, int]]] = None,
        locked: Optional[Iterable[int]] = None,       # applicants whose previous seat is frozen
        time_limit_s: float = 20.0,
        workers: int = 1,                             # single worker + fixed seed => reproducible solutions
        tie_break: bool = True,
    ):
        self.tie_break = tie_break
        self.p = problem
        self.mode = mode
        self.mu = mu if mode == MODE_REASSIGN else 0
        self.forced = dict(forced or {})
        self.forbidden = set(forbidden or [])
        self.locked = set(locked or [])
        self.time_limit_s = time_limit_s
        self.workers = workers
        self.model = cp_model.CpModel()
        self.x: Dict[Tuple[int, int], cp_model.IntVar] = {}
        self._build()

    # ----------------------------------------------------------------- model
    def _build(self) -> None:
        p, m = self.p, self.model
        elig = p.eligibility()
        A, P = p.applicant_ids, p.program_ids

        for i in A:
            for j in P:
                self.x[i, j] = m.NewBoolVar(f"x_{i}_{j}")
                if not elig[i, j] or (i, j) in self.forbidden:
                    m.Add(self.x[i, j] == 0)               # (3) eligibility

        for i in A:                                         # (1) one seat max
            m.Add(sum(self.x[i, j] for j in P) <= 1)

        for j in P:                                         # (2) capacity
            m.Add(sum(self.x[i, j] for i in A) <= p.capacity[j])

        for i, j in self.forced.items():                    # counterfactual force
            m.Add(self.x[i, j] == 1)

        for i in self.locked:                               # frozen seats
            if i in p.previous:
                m.Add(self.x[i, p.previous[i]] == 1)

        self.scale = _scale(len(A))
        pref_terms = [
            self.scale * points_for_rank(p.pref_rank[i, j]) * self.x[i, j]
            for (i, j) in p.pref_rank
            if (i, j) in self.x
        ]
        # Deterministic tie-break (lexicographic below preference points):
        #   merit score * MERIT_WEIGHT  +  earliness bonus (999 for the first application, decreasing)
        tie_terms = []
        if self.tie_break:
            order = sorted(A, key=lambda i: (p.applicant(i).applied_at or "9999", i))
            early_bonus = {i: max(0, 999 - rank) for rank, i in enumerate(order)}
            tie_terms = [
                (min(100, max(0, p.applicant(i).score)) * MERIT_WEIGHT + early_bonus[i]) * self.x[i, j]
                for (i, j) in p.pref_rank
                if (i, j) in self.x
            ]
        objective = sum(pref_terms) + sum(tie_terms)

        if self.mode == MODE_REASSIGN and self.mu > 0:
            # Displacement = number of applicants who do NOT keep their previous seat:
            #     sum_{i with prev_i} (1 - x[i, prev_i])
            # This is the per-applicant form of sum |x - prev|. The raw pairwise form charges a
            # relocation twice (leave + arrive) but an eviction once, so the solver would rather
            # evict than relocate. Charging per applicant removes that perverse incentive; the
            # preference term then makes relocation strictly better than eviction.
            disp_terms = []
            for i in A:
                prev_j = p.previous.get(i)
                if prev_j is not None and (i, prev_j) in self.x:
                    disp_terms.append(1 - self.x[i, prev_j])
            self.displacement = sum(disp_terms)
            objective = objective - self.scale * self.mu * self.displacement
        else:
            self.displacement = None

        m.Maximize(objective)

    # ----------------------------------------------------------------- solve
    def solve(self) -> SolveResult:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_s
        solver.parameters.num_search_workers = self.workers
        solver.parameters.random_seed = 7
        t0 = time.perf_counter()
        raw = solver.Solve(self.model)
        wall = time.perf_counter() - t0
        status = STATUS_NAMES.get(raw, "UNKNOWN")

        res = SolveResult(status=status, mode=self.mode, wall_time_s=wall, mu=self.mu,
                          num_branches=solver.NumBranches(), num_conflicts=solver.NumConflicts())
        if status in ("OPTIMAL", "FEASIBLE"):
            # Report in preference-point units (tie-break term is < 1 point by construction).
            res.objective = solver.ObjectiveValue() / self.scale
            res.best_bound = solver.BestObjectiveBound() / self.scale
            assignment = {}
            for (i, j), var in self.x.items():
                if solver.Value(var) == 1:
                    assignment[i] = j
            res.assignment = assignment
            res.assigned_count = len(assignment)
            res.preference_score = self.p.total_points(assignment)
            res.unassigned = [i for i in self.p.active_applicant_ids if i not in assignment]
            res.changed, res.kept = _diff(self.p.previous, assignment, self.p.applicant_ids)
            hist: Dict[int, int] = {}
            for i, j in assignment.items():
                r = self.p.pref_rank.get((i, j), 0)
                hist[r] = hist.get(r, 0) + 1
            res.rank_histogram = dict(sorted(hist.items()))
            if status == "FEASIBLE":
                res.notes.append("Optimality gap: objective %.2f vs bound %.2f (preference-point units)" % (res.objective, res.best_bound))
        elif status == "INFEASIBLE":
            res.notes.extend(self._diagnose_infeasibility())
        elif status == "UNKNOWN":
            res.notes.append("Increase the time limit or reduce the problem size and retry.")
        return res

    # ----------------------------------------------------------------- diagnostics
    def _diagnose_infeasibility(self) -> List[str]:
        """Cheap structural checks that explain the most common infeasibility causes."""
        notes = []
        p = self.p
        for i, j in self.forced.items():
            reasons = p.ineligibility_reasons(i, j)
            if reasons:
                notes.append(f"Forced assignment of applicant {i} to program {j} is ineligible: " + "; ".join(reasons))
            if p.capacity[j] <= 0:
                notes.append(f"Program {j} has zero capacity, so the forced assignment cannot hold.")
            if (i, j) in self.forbidden:
                notes.append(f"Pair ({i}, {j}) is both forced and forbidden.")
        from collections import Counter
        demand = Counter(self.forced.values())
        for i in self.locked:
            if i in p.previous:
                demand[p.previous[i]] += 1
        for j, d in demand.items():
            if d > p.capacity[j]:
                notes.append(f"{d} seats are forced/locked into program {j} but its capacity is {p.capacity[j]}.")
        if not notes:
            notes.append("No single-cause explanation found; the forced and locked constraints conflict jointly.")
        return notes


# ------------------------------------------------------------------ convenience wrappers
def solve_initial(problem: ProblemData, time_limit_s: float = 20.0) -> SolveResult:
    return AllocationModel(problem, mode=MODE_INITIAL, time_limit_s=time_limit_s).solve()


def solve_reassign(problem: ProblemData, mu: int = DEFAULT_MU, time_limit_s: float = 20.0) -> SolveResult:
    """Capacity shock / withdrawal: preserve `problem.previous` as far as mathematically possible."""
    return AllocationModel(problem, mode=MODE_REASSIGN, mu=mu, time_limit_s=time_limit_s).solve()
