"""Plain-language metrics derived from a run (no solver internals)."""
from __future__ import annotations

from collections import Counter
from typing import Dict

from optimization.problem import ProblemData


def run_metrics(problem: ProblemData, assignment: Dict[int, int]) -> dict:
    active = problem.active_applicant_ids
    used = Counter(assignment.values())
    seats = sum(problem.capacity.values())
    ranks = Counter(problem.pref_rank.get((a, p), 0) for a, p in assignment.items())
    first = ranks.get(1, 0)
    top3 = sum(v for k, v in ranks.items() if 1 <= k <= 3)
    per_program = [{
        "code": p.code, "name": p.name, "capacity": p.capacity, "allocated": used.get(p.id, 0),
        "vacant": max(0, p.capacity - used.get(p.id, 0)),
        "utilisation": round(used.get(p.id, 0) / p.capacity, 3) if p.capacity else 0.0,
    } for p in problem.programs]
    return {
        "active_applicants": len(active), "seated": len(assignment), "unassigned": len(active) - len(assignment),
        "total_seats": seats, "vacant_seats": seats - len(assignment),
        "fill_rate": round(len(assignment) / seats, 3) if seats else 0.0,
        "first_choice_rate": round(first / len(assignment), 3) if assignment else 0.0,
        "top3_rate": round(top3 / len(assignment), 3) if assignment else 0.0,
        "rank_histogram": dict(sorted(ranks.items())),
        "preference_points": problem.total_points(assignment),
        "per_program": per_program,
    }
