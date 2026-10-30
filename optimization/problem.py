"""Pure data container shared by the DB layer, the solver, the validator and the UI.

Nothing in here imports OR-Tools or Streamlit, so every other module can depend on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Points awarded for landing an applicant in their k-th ranked program.
PREFERENCE_POINTS: Dict[int, int] = {1: 100, 2: 50, 3: 20, 4: 10, 5: 5}
DEFAULT_POINTS_BEYOND_TABLE = 1


def points_for_rank(rank: Optional[int]) -> int:
    if rank is None:
        return 0
    return PREFERENCE_POINTS.get(rank, DEFAULT_POINTS_BEYOND_TABLE)


@dataclass
class Applicant:
    id: int
    name: str
    score: int
    track: str
    status: str = "active"
    email: str = ""


@dataclass
class Program:
    id: int
    code: str
    name: str
    capacity: int
    min_score: int = 0
    required_track: Optional[str] = None


@dataclass
class ProblemData:
    """Everything the CP-SAT model needs, already resolved into plain dicts."""

    applicants: List[Applicant]
    programs: List[Program]
    # (applicant_id, program_id) -> rank (1 = top choice). Only ranked pairs exist.
    pref_rank: Dict[Tuple[int, int], int] = field(default_factory=dict)
    # Existing assignment to preserve (applicant_id -> program_id). Missing = unassigned.
    previous: Dict[int, int] = field(default_factory=dict)

    # ---- derived helpers -------------------------------------------------
    @property
    def applicant_ids(self) -> List[int]:
        return [a.id for a in self.applicants]

    @property
    def active_applicant_ids(self) -> List[int]:
        return [a.id for a in self.applicants if a.status == "active"]

    @property
    def program_ids(self) -> List[int]:
        return [p.id for p in self.programs]

    @property
    def capacity(self) -> Dict[int, int]:
        return {p.id: p.capacity for p in self.programs}

    def applicant(self, aid: int) -> Applicant:
        return next(a for a in self.applicants if a.id == aid)

    def program(self, pid: int) -> Program:
        return next(p for p in self.programs if p.id == pid)

    def is_eligible(self, aid: int, pid: int) -> bool:
        """Hard eligibility: applicant ranked the program, meets its score floor and track."""
        if (aid, pid) not in self.pref_rank:
            return False
        a, p = self.applicant(aid), self.program(pid)
        if a.status != "active":
            return False
        if a.score < p.min_score:
            return False
        if p.required_track and a.track != p.required_track:
            return False
        return True

    def ineligibility_reasons(self, aid: int, pid: int) -> List[str]:
        """Human-readable reasons an applicant cannot take a program (empty = eligible)."""
        reasons: List[str] = []
        a, p = self.applicant(aid), self.program(pid)
        if a.status != "active":
            reasons.append(f"applicant status is '{a.status}'")
        if (aid, pid) not in self.pref_rank:
            reasons.append("program is not in the applicant's ranked preferences")
        if a.score < p.min_score:
            reasons.append(f"score {a.score} is below the program minimum {p.min_score}")
        if p.required_track and a.track != p.required_track:
            reasons.append(f"track '{a.track}' does not match required track '{p.required_track}'")
        return reasons

    def eligibility(self) -> Dict[Tuple[int, int], bool]:
        return {
            (a, p): self.is_eligible(a, p)
            for a in self.applicant_ids
            for p in self.program_ids
        }

    def points(self, aid: int, pid: Optional[int]) -> int:
        if pid is None:
            return 0
        return points_for_rank(self.pref_rank.get((aid, pid)))

    def total_points(self, assignment: Dict[int, int]) -> int:
        return sum(self.points(a, p) for a, p in assignment.items())
