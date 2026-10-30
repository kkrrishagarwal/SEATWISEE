"""Application-level workflows that combine DB + engine: eligibility verification, student appeals, admin decisions."""
from __future__ import annotations

import json
from typing import Optional

from database import db_manager as db
from optimization.counterfactual import CounterfactualResult, evaluate_appeal
from optimization.reallocation_engine import publish
from services import notification_service as ns

TRACKING_STAGES = ["Application Submitted", "Under Review", "Eligibility Verified", "Allocation Completed", "Provisional Offer", "Admission Confirmed"]


def verify_eligibility(conn, applicant_id: int) -> str:
    """'eligible' if the applicant qualifies for at least one ranked program, else 'ineligible'."""
    problem = db.build_problem(conn, previous={})
    if applicant_id not in problem.applicant_ids:
        return "pending"
    ok = any(problem.is_eligible(applicant_id, pid) for (a, pid) in problem.pref_rank if a == applicant_id)
    status = "eligible" if ok else "ineligible"
    conn.execute("UPDATE applicants SET eligibility_status = ? WHERE id = ?", (status, applicant_id))
    conn.commit()
    return status


def verify_all_eligibility(conn) -> dict:
    problem = db.build_problem(conn, previous={})
    counts = {"eligible": 0, "ineligible": 0}
    for a in problem.applicant_ids:
        ok = any(problem.is_eligible(a, pid) for (x, pid) in problem.pref_rank if x == a)
        status = "eligible" if ok else "ineligible"
        conn.execute("UPDATE applicants SET eligibility_status = ? WHERE id = ?", (status, a))
        counts[status] += 1
    conn.commit()
    db.log_audit(conn, "admin", "eligibility_verified_all", counts)
    return counts


def tracking(conn, row) -> list:
    """Stages relevant to this student, each (label, done)."""
    seat = db.current_assignment_for(conn, row["id"])
    applied = row["application_status"] == "applied"
    elig = row["eligibility_status"]
    stages = [("Application Submitted", applied)]
    if applied:
        stages.append(("Under Review", True))
        stages.append(("Eligibility Verified", elig == "eligible"))
        if elig == "ineligible":
            stages.append(("Not eligible for ranked programs", True))
            return stages
        stages.append(("Allocation Completed", seat is not None))
        if seat is not None and seat["program_id"]:
            stages.append(("Provisional Offer", row["offer_status"] in ("provisional", "confirmed")))
            stages.append(("Admission Confirmed", row["offer_status"] == "confirmed"))
        elif seat is not None:
            stages.append(("Waitlisted", True))
    return stages


# ---------------------------------------------------------------- appeals
def submit_student_appeal(conn, applicant_id: int, requested_program_id: int, reason: str) -> int:
    open_appeal = conn.execute("SELECT id FROM appeals WHERE applicant_id = ? AND decision = 'submitted'", (applicant_id,)).fetchone()
    if open_appeal:
        raise ValueError("you already have an appeal awaiting evaluation")
    run = db.get_current_run(conn)
    current = db.get_current_assignment_map(conn).get(applicant_id)
    cur = conn.execute(
        "INSERT INTO appeals (applicant_id, requested_program_id, baseline_run_id, decision, reason, source, current_program_id) VALUES (?,?,?,?,?,?,?)",
        (applicant_id, requested_program_id, run["id"] if run else None, "submitted", reason.strip()[:1000], "student", current))
    conn.commit()
    prog = conn.execute("SELECT code, name FROM programs WHERE id = ?", (requested_program_id,)).fetchone()
    db.log_audit(conn, "student", "appeal_submitted", {"appeal_id": cur.lastrowid, "applicant_id": applicant_id, "program_id": requested_program_id})
    ns.notify(conn, applicant_id, "appeal_submitted", {"program": f"{prog['code']} — {prog['name']}"}, dedupe=f"appeal_sub:{cur.lastrowid}")
    return cur.lastrowid


def evaluate_existing_appeal(conn, appeal_id: int) -> CounterfactualResult:
    ap = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
    problem = db.build_problem(conn)
    settings = db.get_settings(conn)
    locked = db.confirmed_assignment_map(conn) if settings["lock_confirmed_seats"] == "1" else {}
    locked.pop(ap["applicant_id"], None)
    cf = evaluate_appeal(problem, ap["applicant_id"], ap["requested_program_id"], locked=locked)
    conn.execute("UPDATE appeals SET solver_status=?, feasible=?, displaced_count=?, preference_delta=?, result_json=?, decision='evaluated' WHERE id=?",
                 (cf.solve.status, int(cf.feasible), cf.displaced_count, cf.preference_delta, json.dumps(cf.to_dict(), default=str), appeal_id))
    conn.commit()
    db.log_audit(conn, "admin", "appeal_evaluated", {"appeal_id": appeal_id, "status": cf.solve.status, "feasible": cf.feasible, "displaced": cf.displaced_count})
    return cf


def decide_appeal(conn, appeal_id: int, accept: bool, actor: str = "admin") -> Optional[int]:
    """Admin decision. Accepting publishes the evaluated alternative as a new validated version."""
    ap = conn.execute("SELECT * FROM appeals WHERE id = ?", (appeal_id,)).fetchone()
    prog = conn.execute("SELECT code, name FROM programs WHERE id = ?", (ap["requested_program_id"],)).fetchone()
    run_id = None
    if accept:
        problem = db.build_problem(conn)
        settings = db.get_settings(conn)
        locked = db.confirmed_assignment_map(conn) if settings["lock_confirmed_seats"] == "1" else {}
        locked.pop(ap["applicant_id"], None)
        cf = evaluate_appeal(problem, ap["applicant_id"], ap["requested_program_id"], locked=locked)
        if not cf.feasible:
            raise ValueError("the requested assignment is not feasible; it cannot be accepted")
        out = publish(conn, cf.solve, problem, mode="appeal", notes=f"Appeal #{appeal_id} accepted by {actor}", locked=locked)
        if not out.published:
            raise ValueError(out.message)
        run_id = out.run_id
    conn.execute("UPDATE appeals SET decision = ?, decided_at = datetime('now') WHERE id = ?", ("accepted" if accept else "rejected", appeal_id))
    conn.commit()
    db.log_audit(conn, actor, "appeal_" + ("accepted" if accept else "rejected"), {"appeal_id": appeal_id, "run_id": run_id})
    ns.notify(conn, ap["applicant_id"], "appeal_evaluated", {"program": f"{prog['code']} — {prog['name']}", "decision": "accepted" if accept else "rejected"},
              dedupe=f"appeal_dec:{appeal_id}")
    return run_id


def load_appeals_full(conn):
    import pandas as pd
    return pd.read_sql_query(
        """SELECT ap.id, ap.created_at, ap.source, a.id AS applicant_id, a.name AS applicant, a.email, p.code AS requested,
                  cp.code AS current_program, ap.reason, ap.solver_status, ap.feasible, ap.displaced_count, ap.preference_delta, ap.decision, ap.decided_at
           FROM appeals ap JOIN applicants a ON a.id = ap.applicant_id JOIN programs p ON p.id = ap.requested_program_id
           LEFT JOIN programs cp ON cp.id = ap.current_program_id ORDER BY ap.id DESC""", conn)
