"""SQLite persistence layer: schema bootstrap, seeding, CRUD, pandas bridges.

The optimisation code never touches SQL; this module converts rows <-> ProblemData.
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from optimization.problem import Applicant, Program, ProblemData

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = os.environ.get("SEATWISEE_DB", str(ROOT / "seatwisee.db"))

TRACKS = ["Engineering", "Science", "Commerce", "Arts"]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan",
    "Ananya", "Diya", "Aadhya", "Saanvi", "Myra", "Kiara", "Anika", "Navya", "Riya", "Ira",
    "Kabir", "Dev", "Yash", "Rahul", "Nikhil", "Priya", "Sneha", "Pooja", "Meera", "Tanvi",
]
LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Agarwal", "Singh", "Patel", "Reddy", "Nair", "Iyer", "Das",
    "Khan", "Mehta", "Joshi", "Chopra", "Bose", "Rao", "Mishra", "Kulkarni", "Pillai", "Yadav",
]

PROGRAM_CATALOG: List[Tuple[str, str, int, int, Optional[str]]] = [
    # code, name, capacity, min_score, required_track
    ("CSE", "Computer Science & AI", 30, 70, "Engineering"),
    ("ECE", "Electronics & Communication", 22, 60, "Engineering"),
    ("MECH", "Mechanical Engineering", 20, 50, "Engineering"),
    ("DATA", "Data Science Bootcamp", 18, 65, None),
    ("BIO", "Biotechnology", 15, 55, "Science"),
    ("PHY", "Applied Physics", 12, 60, "Science"),
    ("FIN", "Finance & Analytics", 20, 55, "Commerce"),
    ("MKT", "Marketing & Brand Strategy", 18, 40, "Commerce"),
    ("DES", "Design & Visual Arts", 15, 35, "Arts"),
    ("MGMT", "Management Foundations", 20, 45, None),
]


# --------------------------------------------------------------------------- connection
def get_conn(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    init_db(conn)
    tables = [
        "audit_log", "appeals", "capacity_changes", "assignments",
        "allocation_runs", "preferences", "applicants", "programs",
    ]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")
    conn.execute("DELETE FROM sqlite_sequence")
    conn.commit()
    init_db(conn)


def is_seeded(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT COUNT(*) FROM programs").fetchone()[0] > 0


# --------------------------------------------------------------------------- audit
def log_audit(conn: sqlite3.Connection, actor: str, action: str, details: Optional[dict | str] = None) -> None:
    payload = json.dumps(details, default=str) if isinstance(details, dict) else details
    conn.execute(
        "INSERT INTO audit_log (actor, action, details) VALUES (?, ?, ?)", (actor, action, payload)
    )
    conn.commit()


def load_audit(conn: sqlite3.Connection, limit: int = 200) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT id, ts, actor, action, details FROM audit_log ORDER BY id DESC LIMIT ?", conn, params=(limit,)
    )


# --------------------------------------------------------------------------- seeding
def seed_demo(conn: sqlite3.Connection, n_applicants: int = 200, seed: int = 42) -> None:
    """Populate 10 programs and `n_applicants` synthetic applicants with ranked preferences."""
    rng = random.Random(seed)
    init_db(conn)
    cur = conn.cursor()
    for code, name, cap, min_score, track in PROGRAM_CATALOG:
        cur.execute(
            "INSERT INTO programs (code, name, capacity, min_score, required_track) VALUES (?,?,?,?,?)",
            (code, name, cap, min_score, track),
        )
    programs = {row["code"]: dict(row) for row in cur.execute("SELECT * FROM programs")}

    for i in range(1, n_applicants + 1):
        track = rng.choices(TRACKS, weights=[0.42, 0.2, 0.23, 0.15])[0]
        score = max(30, min(100, int(rng.gauss(68, 14))))
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        email = f"applicant{i:03d}@seatwisee.demo"
        cur.execute(
            "INSERT INTO applicants (name, email, score, track) VALUES (?,?,?,?)",
            (name, email, score, track),
        )
        aid = cur.lastrowid

        # Applicants mostly rank programs they are plausibly eligible for, with some reach picks.
        eligible = [
            p for p in programs.values()
            if (p["required_track"] in (None, track)) and score >= p["min_score"]
        ]
        reach = [p for p in programs.values() if p not in eligible]
        rng.shuffle(eligible)
        rng.shuffle(reach)
        n_prefs = rng.choice([3, 4, 4, 5, 5])
        chosen = eligible[:n_prefs]
        if len(chosen) < n_prefs:
            chosen += reach[: n_prefs - len(chosen)]
        elif rng.random() < 0.25 and reach:
            chosen[rng.randrange(len(chosen))] = reach[0]
        for rank, p in enumerate(chosen, start=1):
            cur.execute(
                "INSERT INTO preferences (applicant_id, program_id, rank) VALUES (?,?,?)",
                (aid, p["id"], rank),
            )
    conn.commit()
    log_audit(conn, "system", "seed", {"applicants": n_applicants, "programs": len(PROGRAM_CATALOG), "seed": seed})


# --------------------------------------------------------------------------- reads
def load_programs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM programs ORDER BY id", conn)


def load_applicants(conn: sqlite3.Connection, active_only: bool = False) -> pd.DataFrame:
    q = "SELECT * FROM applicants"
    if active_only:
        q += " WHERE status = 'active'"
    return pd.read_sql_query(q + " ORDER BY id", conn)


def load_preferences(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT pr.applicant_id, pr.program_id, pr.rank, p.code FROM preferences pr "
        "JOIN programs p ON p.id = pr.program_id ORDER BY pr.applicant_id, pr.rank",
        conn,
    )


def get_current_run(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM allocation_runs WHERE is_current = 1 ORDER BY id DESC LIMIT 1").fetchone()


def get_run(conn: sqlite3.Connection, run_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM allocation_runs WHERE id = ?", (run_id,)).fetchone()


def load_runs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM allocation_runs ORDER BY id DESC", conn)


def load_assignments(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT a.applicant_id, ap.name, ap.email, ap.score, ap.track,
               a.program_id, p.code AS program_code, p.name AS program_name,
               a.rank_obtained, a.previous_program_id, pp.code AS previous_code
        FROM assignments a
        JOIN applicants ap ON ap.id = a.applicant_id
        LEFT JOIN programs p ON p.id = a.program_id
        LEFT JOIN programs pp ON pp.id = a.previous_program_id
        WHERE a.run_id = ?
        ORDER BY a.applicant_id
        """,
        conn,
        params=(run_id,),
    )


def get_current_assignment_map(conn: sqlite3.Connection) -> Dict[int, int]:
    run = get_current_run(conn)
    if run is None:
        return {}
    rows = conn.execute(
        "SELECT applicant_id, program_id FROM assignments WHERE run_id = ? AND program_id IS NOT NULL",
        (run["id"],),
    ).fetchall()
    return {r["applicant_id"]: r["program_id"] for r in rows}


def build_problem(conn: sqlite3.Connection, previous: Optional[Dict[int, int]] = None) -> ProblemData:
    """Assemble a ProblemData from the DB. `previous` defaults to the current persisted allocation."""
    applicants = [
        Applicant(id=r["id"], name=r["name"], score=r["score"], track=r["track"], status=r["status"], email=r["email"])
        for r in conn.execute("SELECT * FROM applicants ORDER BY id")
    ]
    programs = [
        Program(id=r["id"], code=r["code"], name=r["name"], capacity=r["capacity"],
                min_score=r["min_score"], required_track=r["required_track"])
        for r in conn.execute("SELECT * FROM programs ORDER BY id")
    ]
    pref_rank = {
        (r["applicant_id"], r["program_id"]): r["rank"]
        for r in conn.execute("SELECT applicant_id, program_id, rank FROM preferences")
    }
    if previous is None:
        previous = get_current_assignment_map(conn)
    return ProblemData(applicants=applicants, programs=programs, pref_rank=pref_rank, previous=dict(previous))


# --------------------------------------------------------------------------- writes
def save_run(
    conn: sqlite3.Connection,
    *,
    mode: str,
    solver_status: str,
    assignment: Dict[int, int],
    problem: ProblemData,
    objective: Optional[float],
    best_bound: Optional[float],
    wall_time_s: float,
    reassigned_count: int,
    parent_run_id: Optional[int],
    notes: str = "",
    make_current: bool = True,
) -> int:
    """Persist a solver result as a new run version. Returns run id."""
    pref_score = problem.total_points(assignment)
    cur = conn.cursor()
    if make_current:
        cur.execute("UPDATE allocation_runs SET is_current = 0")
    cur.execute(
        """INSERT INTO allocation_runs
           (mode, solver_status, objective, best_bound, wall_time_s, preference_score,
            assigned_count, reassigned_count, parent_run_id, is_current, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (mode, solver_status, objective, best_bound, wall_time_s, pref_score,
         len(assignment), reassigned_count, parent_run_id, 1 if make_current else 0, notes),
    )
    run_id = cur.lastrowid
    rows = []
    for a in problem.applicants:
        pid = assignment.get(a.id)
        rows.append((run_id, a.id, pid, problem.pref_rank.get((a.id, pid)) if pid else None, problem.previous.get(a.id)))
    cur.executemany(
        "INSERT INTO assignments (run_id, applicant_id, program_id, rank_obtained, previous_program_id) VALUES (?,?,?,?,?)",
        rows,
    )
    conn.commit()
    log_audit(conn, "admin", f"run:{mode}", {
        "run_id": run_id, "status": solver_status, "assigned": len(assignment),
        "reassigned": reassigned_count, "preference_score": pref_score, "parent": parent_run_id,
    })
    return run_id


def update_capacity(conn: sqlite3.Connection, program_id: int, new_capacity: int, reason: str = "") -> Tuple[int, int]:
    old = conn.execute("SELECT capacity FROM programs WHERE id = ?", (program_id,)).fetchone()[0]
    conn.execute("UPDATE programs SET capacity = ? WHERE id = ?", (new_capacity, program_id))
    conn.execute(
        "INSERT INTO capacity_changes (program_id, old_capacity, new_capacity, reason) VALUES (?,?,?,?)",
        (program_id, old, new_capacity, reason),
    )
    conn.commit()
    log_audit(conn, "admin", "capacity_change", {"program_id": program_id, "old": old, "new": new_capacity, "reason": reason})
    return old, new_capacity


def withdraw_applicant(conn: sqlite3.Connection, applicant_id: int, reason: str = "") -> None:
    conn.execute("UPDATE applicants SET status = 'withdrawn' WHERE id = ?", (applicant_id,))
    conn.commit()
    log_audit(conn, "admin", "withdraw", {"applicant_id": applicant_id, "reason": reason})


def reinstate_applicant(conn: sqlite3.Connection, applicant_id: int) -> None:
    conn.execute("UPDATE applicants SET status = 'active' WHERE id = ?", (applicant_id,))
    conn.commit()
    log_audit(conn, "admin", "reinstate", {"applicant_id": applicant_id})


def add_applicant(
    conn: sqlite3.Connection, *, name: str, email: str, score: int, track: str, ranked_program_ids: Sequence[int]
) -> int:
    cur = conn.cursor()
    cur.execute("INSERT INTO applicants (name, email, score, track) VALUES (?,?,?,?)", (name, email.lower().strip(), score, track))
    aid = cur.lastrowid
    for rank, pid in enumerate(ranked_program_ids, start=1):
        cur.execute("INSERT INTO preferences (applicant_id, program_id, rank) VALUES (?,?,?)", (aid, pid, rank))
    conn.commit()
    log_audit(conn, "public", "register", {"applicant_id": aid, "email": email, "prefs": list(ranked_program_ids)})
    return aid


def find_applicant_by_email(conn: sqlite3.Connection, email: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM applicants WHERE lower(email) = ?", (email.lower().strip(),)).fetchone()


def current_assignment_for(conn: sqlite3.Connection, applicant_id: int) -> Optional[sqlite3.Row]:
    run = get_current_run(conn)
    if run is None:
        return None
    return conn.execute(
        """SELECT a.*, p.code, p.name AS program_name FROM assignments a
           LEFT JOIN programs p ON p.id = a.program_id
           WHERE a.run_id = ? AND a.applicant_id = ?""",
        (run["id"], applicant_id),
    ).fetchone()


def record_appeal(
    conn: sqlite3.Connection, *, applicant_id: int, requested_program_id: int, baseline_run_id: Optional[int],
    solver_status: str, feasible: bool, displaced_count: int, preference_delta: int, result: dict,
) -> int:
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO appeals (applicant_id, requested_program_id, baseline_run_id, solver_status, feasible,
                                displaced_count, preference_delta, result_json)
           VALUES (?,?,?,?,?,?,?,?)""",
        (applicant_id, requested_program_id, baseline_run_id, solver_status, int(feasible),
         displaced_count, preference_delta, json.dumps(result, default=str)),
    )
    conn.commit()
    log_audit(conn, "admin", "appeal_evaluated", {
        "appeal_id": cur.lastrowid, "applicant_id": applicant_id, "program_id": requested_program_id,
        "status": solver_status, "feasible": feasible, "displaced": displaced_count, "pref_delta": preference_delta,
    })
    return cur.lastrowid


def set_appeal_decision(conn: sqlite3.Connection, appeal_id: int, decision: str) -> None:
    conn.execute("UPDATE appeals SET decision = ? WHERE id = ?", (decision, appeal_id))
    conn.commit()
    log_audit(conn, "admin", f"appeal_{decision}", {"appeal_id": appeal_id})


def load_appeals(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT ap.id, ap.created_at, a.name AS applicant, p.code AS requested, ap.solver_status, ap.feasible,
                  ap.displaced_count, ap.preference_delta, ap.decision
           FROM appeals ap JOIN applicants a ON a.id = ap.applicant_id JOIN programs p ON p.id = ap.requested_program_id
           ORDER BY ap.id DESC""",
        conn,
    )


def load_capacity_changes(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT c.id, c.created_at, p.code, c.old_capacity, c.new_capacity, c.reason
           FROM capacity_changes c JOIN programs p ON p.id = c.program_id ORDER BY c.id DESC""",
        conn,
    )


def ensure_seeded(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = get_conn(db_path)
    init_db(conn)
    if not is_seeded(conn):
        seed_demo(conn)
    return conn


if __name__ == "__main__":  # python -m database.db_manager  -> (re)seed
    c = get_conn()
    reset_db(c)
    seed_demo(c)
    print(f"Seeded {c.execute('SELECT COUNT(*) FROM applicants').fetchone()[0]} applicants and "
          f"{c.execute('SELECT COUNT(*) FROM programs').fetchone()[0]} programs into {DEFAULT_DB_PATH}")
