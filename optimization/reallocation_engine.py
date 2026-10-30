"""Allocation lifecycle: run → validate → publish version → update offer statuses → notify.

Also the authorised-withdrawal workflow (release seat, re-optimise with minimal disruption,
fill the vacancy with the next qualifying applicant under the configured policy) and capacity changes.
Nothing here renders UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from database import db_manager as db
from optimization.cp_sat_model import DEFAULT_MU, SolveResult, solve_initial, solve_reassign
from optimization.metrics import run_metrics
from optimization.problem import ProblemData
from optimization.validator import ValidationReport, compare, validate
from services import notification_service as ns


@dataclass
class PublishResult:
    solve: SolveResult
    validation: Optional[ValidationReport]
    run_id: Optional[int]
    problem: ProblemData
    comparison: dict = field(default_factory=dict)
    offers: Dict[str, int] = field(default_factory=dict)
    notified: List[int] = field(default_factory=list)
    message: str = ""

    @property
    def published(self) -> bool:
        return self.run_id is not None


def _policy(conn) -> dict:
    s = db.get_settings(conn)
    try:
        mu = max(1, int(float(s.get("reallocation_mu", "1000"))))
    except ValueError:
        mu = 1000
    return {"objective_mode": s["objective_mode"], "lock_confirmed": s["lock_confirmed_seats"] == "1", "mu": mu}


def _update_offers(conn, problem: ProblemData, assignment: Dict[int, int], previous: Dict[int, int]) -> Dict[str, int]:
    """Provisional for newly seated / moved, confirmed stays confirmed if unchanged, waitlisted if applied but unseated."""
    counts = {"provisional": 0, "confirmed": 0, "waitlisted": 0, "none": 0}
    rows = conn.execute("SELECT id, offer_status, status, application_status FROM applicants").fetchall()
    for r in rows:
        aid = r["id"]
        if r["status"] != "active" or r["application_status"] != "applied":
            new = "none"
        elif aid in assignment:
            new = "confirmed" if (r["offer_status"] == "confirmed" and previous.get(aid) == assignment[aid]) else "provisional"
        else:
            new = "waitlisted"
        if new != r["offer_status"]:
            conn.execute("UPDATE applicants SET offer_status = ? WHERE id = ?", (new, aid))
        counts[new] += 1
    conn.commit()
    return counts


def _notify_changes(conn, problem: ProblemData, previous: Dict[int, int], assignment: Dict[int, int], run_id: int, first_publish: bool) -> List[int]:
    notified = []
    labels = {p.id: f"{p.code} — {p.name}" for p in problem.programs}
    for a in problem.active_applicant_ids:
        before, after = previous.get(a), assignment.get(a)
        if after is not None and before is None:
            ns.notify(conn, a, "provisional_offer", {"program": labels[after]}, dedupe=f"offer:{run_id}")
        elif after is not None and before != after:
            ns.notify(conn, a, "reallocated", {"program": labels[after]}, dedupe=f"realloc:{run_id}")
        elif after is None and (before is not None or first_publish):
            ns.notify(conn, a, "waitlisted", {}, dedupe=f"wait:{run_id}")
        else:
            continue
        notified.append(a)
    return notified


def publish(conn, solve: SolveResult, problem: ProblemData, *, mode: str, notes: str, locked: Optional[Dict[int, int]] = None) -> PublishResult:
    """Validate independently; persist as a new version only if valid; then update offers and notify."""
    if not solve.has_solution:
        return PublishResult(solve, None, None, problem, message=f"Not published: solver status {solve.status}. " + " ".join(solve.notes))
    rep = validate(problem, solve.assignment, locked=locked)
    if not rep.ok:
        return PublishResult(solve, rep, None, problem, message="Not published: independent validator found violations.")
    parent = db.get_current_run(conn)
    previous = dict(problem.previous)
    run_id = db.save_run(conn, mode=mode, solver_status=solve.status, assignment=solve.assignment, problem=problem,
                         objective=solve.objective, best_bound=solve.best_bound, wall_time_s=solve.wall_time_s,
                         reassigned_count=solve.reassigned_count, parent_run_id=parent["id"] if parent else None, notes=notes)
    offers = _update_offers(conn, problem, solve.assignment, previous)
    notified = _notify_changes(conn, problem, previous, solve.assignment, run_id, first_publish=parent is None)
    comparison = compare(problem, previous, solve.assignment)
    return PublishResult(solve, rep, run_id, problem, comparison, offers, notified, message=f"Published as version #{run_id} ({solve.status}).")


def run_initial(conn, time_limit_s: float = 20.0, notes: str = "Initial allocation") -> PublishResult:
    pol = _policy(conn)
    problem = db.build_problem(conn, previous={})
    res = solve_initial(problem, time_limit_s=time_limit_s, objective_mode=pol["objective_mode"])
    return publish(conn, res, problem, mode="initial", notes=f"{notes} · policy {pol['objective_mode']}")


def run_reallocation(conn, reason: str, mu: Optional[int] = None, time_limit_s: float = 20.0) -> PublishResult:
    """Minimal-disruption re-optimisation against the current version. Confirmed seats are locked by policy."""
    pol = _policy(conn)
    mu = pol["mu"] if mu is None else mu
    problem = db.build_problem(conn)                      # previous = current published allocation
    locked = db.confirmed_assignment_map(conn) if pol["lock_confirmed"] else {}
    locked = {a: p for a, p in locked.items() if problem.is_eligible(a, p) and problem.capacity.get(p, 0) > 0}
    res = solve_reassign(problem, mu=mu, time_limit_s=time_limit_s, locked=list(locked), objective_mode=pol["objective_mode"])
    out = publish(conn, res, problem, mode="reassign", notes=f"Reallocation · {reason} · policy {pol['objective_mode']}", locked=locked)
    if out.published:
        db.log_audit(conn, "system", "reallocation", {"reason": reason, "run_id": out.run_id, "moved": out.comparison.get("moved_count"),
                                                      "newly_seated": len(out.comparison.get("newly_seated", []))})
    return out


def process_withdrawal(conn, withdrawal_id: int, approve: bool, actor: str = "admin") -> PublishResult | None:
    """Authorised withdrawal: mark withdrawn (record kept), release the seat, re-run, fill vacancy, notify."""
    w = db.get_withdrawal(conn, withdrawal_id)
    if w is None or w["status"] != "requested":
        raise ValueError("withdrawal is not pending")
    aid = w["applicant_id"]
    if not approve:
        db.decide_withdrawal(conn, withdrawal_id, False, actor)
        ns.notify(conn, aid, "withdrawal_requested", {"body": "rejected"}, dedupe=f"wd_rejected:{withdrawal_id}")
        return None
    released = db.get_current_assignment_map(conn).get(aid)
    db.withdraw_applicant(conn, aid, reason=f"authorised withdrawal #{withdrawal_id} by {actor}")
    db.set_offer_status(conn, aid, "none", actor=actor)
    ns.notify(conn, aid, "withdrawal_confirmed", {}, dedupe=f"wd_confirmed:{withdrawal_id}")
    out = None
    if db.get_current_run(conn) is not None:
        out = run_reallocation(conn, reason=f"withdrawal #{withdrawal_id} of {db.app_id(aid)}")
    db.decide_withdrawal(conn, withdrawal_id, True, actor, released_program_id=released, run_id_after=out.run_id if out and out.published else None)
    return out


def change_capacity(conn, program_id: int, new_capacity: int, reason: str, reallocate: bool = True) -> PublishResult | None:
    db.update_capacity(conn, program_id, new_capacity, reason)
    if reallocate and db.get_current_run(conn) is not None:
        return run_reallocation(conn, reason=f"capacity change on program {program_id}: {reason}")
    return None


def confirm_offer(conn, applicant_id: int, actor: str = "student") -> bool:
    row = conn.execute("SELECT offer_status, status FROM applicants WHERE id = ?", (applicant_id,)).fetchone()
    if not row or row["status"] != "active" or row["offer_status"] not in ("provisional", "confirmed"):
        return False
    if row["offer_status"] == "confirmed":
        return True
    db.set_offer_status(conn, applicant_id, "confirmed", actor=actor)
    seat = db.current_assignment_for(conn, applicant_id)
    ns.notify(conn, applicant_id, "admission_confirmed", {"program": f"{seat['code']} — {seat['program_name']}" if seat else ""}, dedupe=f"confirm:{applicant_id}")
    return True


def technical_summary(conn, run_id: Optional[int] = None) -> dict:
    run = db.get_run(conn, run_id) if run_id else db.get_current_run(conn)
    if run is None:
        return {}
    problem = db.build_problem(conn, previous={})
    assignment = {r["applicant_id"]: r["program_id"] for r in conn.execute(
        "SELECT applicant_id, program_id FROM assignments WHERE run_id = ? AND program_id IS NOT NULL", (run["id"],))}
    m = run_metrics(problem, assignment)
    m.update({"run_id": run["id"], "mode": run["mode"], "solver_status": run["solver_status"], "wall_time_s": run["wall_time_s"],
              "policy": run["policy_json"], "created_at": run["created_at"], "notes": run["notes"], "reassigned": run["reassigned_count"]})
    return m


def vacancy_report(conn) -> list:
    """For every program with vacant seats: who on the waitlist could take one, and if nobody, why."""
    run = db.get_current_run(conn)
    if run is None:
        return []
    problem = db.build_problem(conn)
    assignment = dict(problem.previous)
    from collections import Counter
    used = Counter(assignment.values())
    waitlist = [a for a in problem.active_applicant_ids if a not in assignment]
    report = []
    for p in problem.programs:
        vacant = p.capacity - used.get(p.id, 0)
        if vacant <= 0:
            continue
        ranked = [a for a in waitlist if (a, p.id) in problem.pref_rank]
        eligible = [a for a in ranked if problem.is_eligible(a, p.id)]
        if eligible:
            why = f"{len(eligible)} waitlisted applicant(s) qualify; run a reallocation to seat them."
        elif ranked:
            why = f"{len(ranked)} waitlisted applicant(s) ranked it but none meets the eligibility floor (score ≥ {p.min_score}" + (f", track {p.required_track}" if p.required_track else "") + ")."
        else:
            why = "no waitlisted applicant ranked this program; seated applicants are not moved under the minimal-disruption policy."
        report.append({"program": p.code, "name": p.name, "capacity": p.capacity, "allocated": used.get(p.id, 0), "vacant": vacant,
                       "eligible_waitlisted": len(eligible), "explanation": why})
    return report
