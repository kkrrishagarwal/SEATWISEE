"""Counterfactual appeal engine: "what if we grant applicant S their requested program T?"

1. Take the baseline allocation (previous) as the thing to protect.
2. Re-solve in reassign mode with x[S, T] == 1 forced.
3. Report the ripple: who moved, where, preference deltas, constraint compliance, solver status.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from optimization.cp_sat_model import DEFAULT_MU, MODE_REASSIGN, AllocationModel, SolveResult
from optimization.problem import ProblemData
from optimization.validator import ValidationReport, compare, validate


@dataclass
class RippleRow:
    applicant_id: int
    name: str
    before_program: Optional[int]
    after_program: Optional[int]
    before_rank: Optional[int]
    after_rank: Optional[int]
    points_delta: int
    kind: str  # "appellant" | "displaced" | "relocated" | "newly_seated" | "lost_seat"


@dataclass
class CounterfactualResult:
    applicant_id: int
    target_program_id: int
    solve: SolveResult
    feasible: bool
    baseline: Dict[int, int]
    alternative: Dict[int, int]
    ripple: List[RippleRow] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    validation: Optional[ValidationReport] = None
    pre_check_reasons: List[str] = field(default_factory=list)
    recommendation: str = ""

    @property
    def displaced_count(self) -> int:
        return sum(1 for r in self.ripple if r.kind != "appellant")

    @property
    def preference_delta(self) -> int:
        return int(self.metrics.get("points_delta", 0))

    def to_dict(self) -> dict:
        return {
            "applicant_id": self.applicant_id,
            "target_program_id": self.target_program_id,
            "status": self.solve.status,
            "feasible": self.feasible,
            "displaced_count": self.displaced_count,
            "preference_delta": self.preference_delta,
            "metrics": {k: v for k, v in self.metrics.items() if k != "moved"},
            "ripple": [r.__dict__ for r in self.ripple],
            "pre_check_reasons": self.pre_check_reasons,
            "validation_ok": self.validation.ok if self.validation else None,
            "recommendation": self.recommendation,
            "solver_notes": self.solve.notes,
        }


def evaluate_appeal(
    problem: ProblemData,
    applicant_id: int,
    target_program_id: int,
    mu: int = DEFAULT_MU,
    time_limit_s: float = 20.0,
) -> CounterfactualResult:
    """Clone the state, force the request, re-solve, and quantify the ripple effect."""
    p = copy.deepcopy(problem)                     # never mutate the live state
    baseline = dict(p.previous)

    pre = p.ineligibility_reasons(applicant_id, target_program_id)
    if baseline.get(applicant_id) == target_program_id:
        pre.append("applicant already holds the requested program in the baseline allocation")

    model = AllocationModel(p, mode=MODE_REASSIGN, mu=mu, forced={applicant_id: target_program_id}, time_limit_s=time_limit_s)
    solve = model.solve()
    feasible = solve.has_solution

    result = CounterfactualResult(
        applicant_id=applicant_id, target_program_id=target_program_id, solve=solve, feasible=feasible,
        baseline=baseline, alternative=solve.assignment if feasible else {}, pre_check_reasons=pre,
    )

    if feasible:
        alt = solve.assignment
        result.metrics = compare(p, baseline, alt)
        result.validation = validate(p, alt, forced={applicant_id: target_program_id})
        for aid, (b, a) in sorted(result.metrics["moved"].items()):
            appl = p.applicant(aid)
            br, ar = p.pref_rank.get((aid, b)) if b else None, p.pref_rank.get((aid, a)) if a else None
            if aid == applicant_id:
                kind = "appellant"
            elif b is not None and a is None:
                kind = "lost_seat"
            elif b is None and a is not None:
                kind = "newly_seated"
            elif b == target_program_id:
                kind = "displaced"
            else:
                kind = "relocated"
            result.ripple.append(RippleRow(aid, appl.name, b, a, br, ar, p.points(aid, a) - p.points(aid, b), kind))
        others = result.displaced_count
        delta = result.preference_delta
        if others == 0:
            result.recommendation = "GRANT: a free seat exists; nobody else is affected."
        elif delta >= 0:
            result.recommendation = f"GRANT (low cost): {others} other applicant(s) move but total preference satisfaction does not fall."
        elif any(r.kind == "lost_seat" for r in result.ripple):
            result.recommendation = f"REJECT (high cost): granting this removes a seat from {sum(1 for r in result.ripple if r.kind=='lost_seat')} applicant(s) entirely."
        else:
            result.recommendation = f"REVIEW: {others} applicant(s) displaced, total preference score drops by {-delta} points."
    else:
        if solve.status == "INFEASIBLE":
            why = "; ".join(pre) if pre else "; ".join(solve.notes)
            result.recommendation = f"CANNOT GRANT (proven infeasible): {why}"
        else:
            result.recommendation = "UNRESOLVED: the solver timed out before proving feasibility or infeasibility. Retry with a longer limit."
    return result
