"""Independent rule checker. Pure Python, zero OR-Tools, zero trust in the solver.

Given a ProblemData and a proposed assignment, re-derives every declared rule and lists violations.
Used after every solve and inside the tests so solver bugs cannot be silently persisted.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from optimization.problem import ProblemData


@dataclass
class Violation:
    rule: str
    applicant_id: Optional[int]
    program_id: Optional[int]
    message: str


@dataclass
class ValidationReport:
    violations: List[Violation] = field(default_factory=list)
    checks_run: List[str] = field(default_factory=list)
    seats_used: Dict[int, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_rows(self) -> List[dict]:
        return [v.__dict__ for v in self.violations]


def validate(problem: ProblemData, assignment: Dict[int, int], forced: Optional[Dict[int, int]] = None) -> ValidationReport:
    rep = ValidationReport()
    cap = problem.capacity
    program_ids = set(problem.program_ids)
    applicant_ids = set(problem.applicant_ids)

    # Rule 0: referential integrity
    rep.checks_run.append("known_ids")
    for a, p in assignment.items():
        if a not in applicant_ids:
            rep.violations.append(Violation("known_ids", a, p, f"unknown applicant id {a}"))
        if p not in program_ids:
            rep.violations.append(Violation("known_ids", a, p, f"unknown program id {p}"))

    # Rule 1: one seat per applicant (dict keys guarantee this, but check for duplicate values per applicant)
    rep.checks_run.append("one_seat_per_applicant")
    seen = Counter(assignment.keys())
    for a, n in seen.items():
        if n > 1:
            rep.violations.append(Violation("one_seat_per_applicant", a, None, f"applicant {a} holds {n} seats"))

    # Rule 2: capacity
    rep.checks_run.append("capacity")
    used = Counter(assignment.values())
    rep.seats_used = {p: used.get(p, 0) for p in problem.program_ids}
    for p, n in used.items():
        if p in cap and n > cap[p]:
            rep.violations.append(Violation("capacity", None, p, f"program {p} seats {n} applicants but capacity is {cap[p]}"))

    # Rule 3: eligibility (score floor, track, ranked, active)
    rep.checks_run.append("eligibility")
    for a, p in assignment.items():
        if a in applicant_ids and p in program_ids and not problem.is_eligible(a, p):
            reasons = "; ".join(problem.ineligibility_reasons(a, p))
            rep.violations.append(Violation("eligibility", a, p, f"applicant {a} not eligible for program {p}: {reasons}"))

    # Rule 4: withdrawn applicants must hold no seat
    rep.checks_run.append("withdrawn_unassigned")
    for a in problem.applicants:
        if a.status != "active" and a.id in assignment:
            rep.violations.append(Violation("withdrawn_unassigned", a.id, assignment[a.id], f"withdrawn applicant {a.id} still seated"))

    # Rule 5: forced placements honoured (counterfactual contract)
    if forced:
        rep.checks_run.append("forced_honoured")
        for a, p in forced.items():
            if assignment.get(a) != p:
                rep.violations.append(Violation("forced_honoured", a, p, f"forced placement of {a} into {p} not present"))

    return rep


def compare(problem: ProblemData, before: Dict[int, int], after: Dict[int, int]) -> dict:
    """Side-by-side metrics used by the dashboards and the PDF report."""
    moved = {a: (before.get(a), after.get(a)) for a in set(before) | set(after) if before.get(a) != after.get(a)}
    return {
        "before_assigned": len(before),
        "after_assigned": len(after),
        "before_points": problem.total_points(before),
        "after_points": problem.total_points(after),
        "points_delta": problem.total_points(after) - problem.total_points(before),
        "moved_count": len(moved),
        "moved": moved,
        "kept_count": sum(1 for a in before if after.get(a) == before[a]),
        "newly_seated": [a for a in after if a not in before],
        "lost_seat": [a for a in before if a not in after],
    }
