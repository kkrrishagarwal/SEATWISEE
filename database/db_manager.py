"""SQLite persistence layer: schema bootstrap, seeding, CRUD, pandas bridges.

The optimisation code never touches SQL; this module converts rows <-> ProblemData.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from optimization.problem import Applicant, Program, ProblemData

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = os.environ.get("SEATWISEE_DB", str(ROOT / "seatwisee.db"))
UPLOAD_DIR = Path(os.environ.get("SEATWISEE_UPLOADS", str(ROOT / "uploads")))
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
DOC_KINDS = {"marksheet": "12thMarksheet", "scorecard": "EntranceScorecard"}

DEFAULT_FORM_FIELDS = [
    # key, label, type, required, options
    ("category", "Category", "select", 1, ["General", "OBC", "SC", "ST", "EWS"]),
    ("city", "City", "text", 1, None),
    ("phone", "Phone number", "text", 1, None),
    ("gap_years", "Gap years after 12th", "number", 0, None),
]
CITIES = ["Delhi", "Mumbai", "Bengaluru", "Hyderabad", "Pune", "Kolkata", "Jaipur", "Lucknow", "Bhopal", "Chennai"]

# CMS defaults: section_key -> (label shown to the admin, default text)
DEFAULT_SITE_CONTENT = {
    "institute_name": ("Institute name", "Syntaxis Institute of Technology"),
    "hero_title": ("Hero title", "Empowering the Next Generation of Innovators."),
    "hero_subtitle": ("Hero subtitle", "A research-driven campus where engineering, data science and management converge. Fair, transparent seat allocation powered by the SEATWISEE constraint engine."),
    "announcements": ("Announcements", "Admissions 2026 are open. Rank up to five programs and upload your 12th marksheet and entrance scorecard. Allocation results will be published by the admissions office."),
    "about_us": ("About us", "Seats are allocated by a constraint-programming engine (Google OR-Tools CP-SAT) that maximises preference satisfaction while respecting eligibility and capacity. Every decision is explainable and independently validated."),
    "contact_info": ("Contact info", "Admissions Office · admissions@seatwisee.demo · +91 120 456 7890 · Mon–Sat 9:00–17:30 IST"),
}

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

PROGRAM_DETAILS: Dict[str, Tuple[str, str, str]] = {
    # code: (department, duration, description)
    "CSE": ("School of Computing", "4 years", "Systems, algorithms and software engineering with an AI specialisation and a capstone shipped to real users."),
    "ECE": ("School of Engineering", "4 years", "Signal processing, embedded systems and communication networks with hardware labs from the first semester."),
    "MECH": ("School of Engineering", "4 years", "Design, manufacturing and thermal sciences with a modern CNC and robotics workshop."),
    "DATA": ("School of Computing", "1 year", "Intensive data science bootcamp: statistics, machine learning and MLOps on real datasets."),
    "BIO": ("School of Sciences", "3 years", "Molecular biology, genetics and bioprocess engineering in wet-lab and computational tracks."),
    "PHY": ("School of Sciences", "3 years", "Applied physics with photonics, materials and instrumentation electives."),
    "FIN": ("School of Business", "3 years", "Finance and analytics with live trading-room simulations and fintech projects."),
    "MKT": ("School of Business", "3 years", "Marketing and brand strategy with agency placements and digital campaign studios."),
    "DES": ("School of Design", "3 years", "Visual communication, UX and product design in studio-based learning."),
    "MGMT": ("School of Business", "3 years", "Management foundations: operations, people and strategy with startup consulting projects."),
}

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
    _migrate(conn)
    seed_site_content(conn)      # idempotent: fills only missing keys, never overwrites admin edits
    seed_settings(conn)
    ensure_admin_user(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after the first release to databases created before them."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(applicants)")}
    wanted = {
        "form_data": "TEXT", "marksheet_path": "TEXT", "scorecard_path": "TEXT",
        "applied_at": "TEXT NOT NULL DEFAULT (datetime('now'))",
        # pre-existing rows all carry full applications, so they migrate as 'applied'
        "application_status": "TEXT NOT NULL DEFAULT 'applied'",
        "password_hash": "TEXT", "phone": "TEXT", "address": "TEXT",
    }
    for col, ddl in wanted.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE applicants ADD COLUMN {col} {ddl}")
    extra = {
        "applicants": {"offer_status": "TEXT NOT NULL DEFAULT 'none'", "eligibility_status": "TEXT NOT NULL DEFAULT 'pending'"},
        "programs": {"description": "TEXT", "duration": "TEXT", "department": "TEXT", "is_open": "INTEGER NOT NULL DEFAULT 1", "image_key": "TEXT"},
        "appeals": {"reason": "TEXT", "source": "TEXT NOT NULL DEFAULT 'admin'", "current_program_id": "INTEGER", "decided_at": "TEXT"},
        "allocation_runs": {"policy_json": "TEXT", "published": "INTEGER NOT NULL DEFAULT 1"},
    }
    for table, columns in extra.items():
        have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in columns.items():
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    # backfill descriptive program fields for databases seeded before they existed
    for r in conn.execute("SELECT id, code FROM programs WHERE department IS NULL OR department = ''").fetchall():
        dept, dur, desc = PROGRAM_DETAILS.get(r["code"], ("Academics", "", ""))
        conn.execute("UPDATE programs SET department = ?, duration = ?, description = COALESCE(description, ?), image_key = COALESCE(image_key, ?) WHERE id = ?",
                     (dept, dur, desc, r["code"].lower(), r["id"]))


def reset_db(conn: sqlite3.Connection) -> None:
    init_db(conn)
    tables = [
        "audit_log", "appeals", "capacity_changes", "assignments",
        "allocation_runs", "preferences", "applicants", "programs", "form_schema", "site_content",
        "notifications", "withdrawals", "password_resets", "announcements", "settings", "admin_users",
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
        dept, dur, desc = PROGRAM_DETAILS.get(code, ("", "", ""))
        cur.execute(
            "INSERT INTO programs (code, name, capacity, min_score, required_track, department, duration, description, image_key) VALUES (?,?,?,?,?,?,?,?,?)",
            (code, name, cap, min_score, track, dept, dur, desc, code.lower()),
        )
    programs = {row["code"]: dict(row) for row in cur.execute("SELECT * FROM programs")}
    seed_form_schema(conn)
    base_time = datetime(2026, 10, 1, 9, 0, 0)

    for i in range(1, n_applicants + 1):
        track = rng.choices(TRACKS, weights=[0.42, 0.2, 0.23, 0.15])[0]
        score = max(30, min(100, int(rng.gauss(68, 14))))
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        email = f"applicant{i:03d}@seatwisee.demo"
        form_data = {
            "category": rng.choices(["General", "OBC", "SC", "ST", "EWS"], weights=[0.4, 0.27, 0.15, 0.08, 0.1])[0],
            "city": rng.choice(CITIES),
            "phone": "9" + "".join(str(rng.randint(0, 9)) for _ in range(9)),
            "gap_years": rng.choice([0, 0, 0, 1, 2]),
        }
        applied_at = (base_time + timedelta(minutes=rng.randint(0, 20000))).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute(
            "INSERT INTO applicants (name, email, score, track, form_data, applied_at, application_status, phone, address) "
            "VALUES (?,?,?,?,?,?,'applied',?,?)",
            (name, email, score, track, json.dumps(form_data), applied_at, form_data["phone"], form_data["city"]),
        )
        aid = cur.lastrowid
        # Simulated document paths for seeded users (files are not materialised on disk).
        cur.execute(
            "UPDATE applicants SET marksheet_path = ?, scorecard_path = ? WHERE id = ?",
            (document_path(aid, "marksheet", "pdf"), document_path(aid, "scorecard", "pdf"), aid),
        )

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


# --------------------------------------------------------------------------- settings & policies
DEFAULT_SETTINGS = {
    # Allocation policy. "preference_first": maximise preference points, merit tie-break (original behaviour).
    # "merit_first": lexicographic — seats filled, then entrance-score merit, then preferences, then earliest application.
    "objective_mode": "preference_first",
    "max_preferences": "5",
    "lock_confirmed_seats": "1",          # confirmed admissions are never moved by reallocation
    "reallocation_mu": "1000",            # displacement penalty: 1000 = never move a seated applicant unless forced;
                                          # a small value (e.g. 1) lets provisional applicants upgrade into vacancies
    "demo_mode": "1",                     # shows the "demonstration data" banner
    "offer_accept_days": "7",             # informational deadline printed on offers (not auto-enforced)
    "institute_tagline": "Discover Opportunities. Unlock Your Future.",
    "academic_session": "2026-27",
}


def seed_settings(conn: sqlite3.Connection) -> None:
    for k, v in DEFAULT_SETTINGS.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    conn.commit()


def get_setting(conn: sqlite3.Connection, key: str, default: Optional[str] = None) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row:
        return row["value"]
    return DEFAULT_SETTINGS.get(key, default if default is not None else "")


def get_settings(conn: sqlite3.Connection) -> Dict[str, str]:
    out = dict(DEFAULT_SETTINGS)
    out.update({r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM settings")})
    return out


def set_setting(conn: sqlite3.Connection, key: str, value: str, actor: str = "admin") -> None:
    conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')", (key, str(value)))
    conn.commit()
    log_audit(conn, actor, "setting_changed", {"key": key, "value": str(value)[:200]})


def policy_snapshot(conn: sqlite3.Connection) -> dict:
    st = get_settings(conn)
    return {k: st[k] for k in ("objective_mode", "max_preferences", "lock_confirmed_seats", "reallocation_mu")}


# --------------------------------------------------------------------------- admin users
def ensure_admin_user(conn: sqlite3.Connection) -> None:
    """First-run admin bootstrap. Password from SEATWISEE_ADMIN_PASSWORD, else the documented demo default."""
    if conn.execute("SELECT COUNT(*) FROM admin_users").fetchone()[0]:
        return
    pw = os.environ.get("SEATWISEE_ADMIN_PASSWORD", "admin123")
    conn.execute("INSERT INTO admin_users (username, email, password_hash) VALUES (?,?,?)",
                 ("admin", os.environ.get("SEATWISEE_ADMIN_EMAIL", "admissions@seatwisee.demo"), hash_password(pw)))
    conn.commit()


def get_admin(conn: sqlite3.Connection, username: str):
    return conn.execute("SELECT * FROM admin_users WHERE lower(username) = ?", ((username or "").strip().lower(),)).fetchone()


def check_admin_login(conn: sqlite3.Connection, username: str, password: str) -> bool:
    row = get_admin(conn, username)
    if row and verify_password(row["password_hash"], (password or "").strip()):
        conn.execute("UPDATE admin_users SET last_login = datetime('now') WHERE id = ?", (row["id"],))
        conn.commit()
        return True
    return False


def set_admin_password(conn: sqlite3.Connection, username: str, new_password: str) -> None:
    if len(new_password) < 6:
        raise ValueError("password must be at least 6 characters")
    conn.execute("UPDATE admin_users SET password_hash = ? WHERE lower(username) = ?", (hash_password(new_password), username.lower()))
    conn.commit()
    log_audit(conn, "admin", "admin_password_changed", {"username": username})


def admin_uses_default_password(conn: sqlite3.Connection) -> bool:
    row = get_admin(conn, "admin")
    return bool(row) and verify_password(row["password_hash"], "admin123")


# --------------------------------------------------------------------------- application ids & offer lifecycle
APP_ID_BASE = 1000
OFFER_STATES = ("none", "provisional", "confirmed", "waitlisted")


def app_id(applicant_id: int) -> str:
    return f"APP{APP_ID_BASE + int(applicant_id)}"


def parse_app_id(text: str) -> Optional[int]:
    t = (text or "").strip().upper()
    if t.startswith("APP") and t[3:].isdigit():
        n = int(t[3:]) - APP_ID_BASE
        return n if n > 0 else None
    return int(t) if t.isdigit() else None


def set_offer_status(conn: sqlite3.Connection, applicant_id: int, status: str, actor: str = "system") -> None:
    if status not in OFFER_STATES:
        raise ValueError("bad offer status")
    conn.execute("UPDATE applicants SET offer_status = ? WHERE id = ?", (status, applicant_id))
    conn.commit()
    log_audit(conn, actor, "offer_status", {"applicant_id": applicant_id, "status": status})


def confirmed_assignment_map(conn: sqlite3.Connection) -> Dict[int, int]:
    """applicant -> program for applicants whose admission is CONFIRMED in the current run (locked by policy)."""
    run = get_current_run(conn)
    if run is None:
        return {}
    rows = conn.execute(
        """SELECT a.applicant_id, a.program_id FROM assignments a JOIN applicants ap ON ap.id = a.applicant_id
           WHERE a.run_id = ? AND a.program_id IS NOT NULL AND ap.offer_status = 'confirmed' AND ap.status = 'active'""",
        (run["id"],)).fetchall()
    return {r["applicant_id"]: r["program_id"] for r in rows}


# --------------------------------------------------------------------------- notifications (records only; dispatch in services)
def insert_notification(conn: sqlite3.Connection, *, applicant_id: Optional[int], channel: str, event: str, subject: str,
                        body: str, status: str, provider_response: Optional[str] = None, dedupe_key: Optional[str] = None) -> Optional[int]:
    try:
        cur = conn.execute(
            "INSERT INTO notifications (applicant_id, channel, event, subject, body, status, provider_response, dedupe_key) VALUES (?,?,?,?,?,?,?,?)",
            (applicant_id, channel, event, subject, body, status, provider_response, dedupe_key))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None            # duplicate (dedupe_key) -> skipped


def load_notifications(conn: sqlite3.Connection, applicant_id: Optional[int] = None, limit: int = 300) -> pd.DataFrame:
    if applicant_id is None:
        return pd.read_sql_query(
            """SELECT n.id, n.created_at, n.channel, n.event, a.name AS applicant, a.email, n.subject, n.status, n.provider_response
               FROM notifications n LEFT JOIN applicants a ON a.id = n.applicant_id ORDER BY n.id DESC LIMIT ?""", conn, params=(limit,))
    return pd.read_sql_query(
        "SELECT id, created_at, channel, event, subject, body, status, provider_response, read_at FROM notifications WHERE applicant_id = ? ORDER BY id DESC LIMIT ?",
        conn, params=(applicant_id, limit))


def mark_notifications_read(conn: sqlite3.Connection, applicant_id: int) -> None:
    conn.execute("UPDATE notifications SET read_at = datetime('now') WHERE applicant_id = ? AND channel = 'in_app' AND read_at IS NULL", (applicant_id,))
    conn.commit()


# --------------------------------------------------------------------------- withdrawals
def request_withdrawal(conn: sqlite3.Connection, applicant_id: int, reason: str) -> int:
    open_req = conn.execute("SELECT id FROM withdrawals WHERE applicant_id = ? AND status = 'requested'", (applicant_id,)).fetchone()
    if open_req:
        return open_req["id"]
    cur = conn.execute("INSERT INTO withdrawals (applicant_id, reason) VALUES (?, ?)", (applicant_id, reason.strip()[:500]))
    conn.commit()
    log_audit(conn, "student", "withdrawal_requested", {"applicant_id": applicant_id, "withdrawal_id": cur.lastrowid})
    return cur.lastrowid


def load_withdrawals(conn: sqlite3.Connection, status: Optional[str] = None) -> pd.DataFrame:
    q = """SELECT w.id, w.requested_at, w.applicant_id, a.name AS applicant, a.email, p.code AS released_program, w.reason, w.status,
                  w.decided_at, w.decided_by, w.run_id_after
           FROM withdrawals w JOIN applicants a ON a.id = w.applicant_id LEFT JOIN programs p ON p.id = w.released_program_id"""
    params: tuple = ()
    if status:
        q += " WHERE w.status = ?"; params = (status,)
    return pd.read_sql_query(q + " ORDER BY w.id DESC", conn, params=params)


def get_withdrawal(conn: sqlite3.Connection, wid: int):
    return conn.execute("SELECT * FROM withdrawals WHERE id = ?", (wid,)).fetchone()


def decide_withdrawal(conn: sqlite3.Connection, wid: int, approve: bool, actor: str, released_program_id: Optional[int] = None,
                      run_id_after: Optional[int] = None) -> None:
    conn.execute("UPDATE withdrawals SET status = ?, decided_at = datetime('now'), decided_by = ?, released_program_id = ?, run_id_after = ? WHERE id = ?",
                 ("approved" if approve else "rejected", actor, released_program_id, run_id_after, wid))
    conn.commit()
    log_audit(conn, actor, "withdrawal_" + ("approved" if approve else "rejected"), {"withdrawal_id": wid, "run_after": run_id_after})


# --------------------------------------------------------------------------- announcements
def add_announcement(conn: sqlite3.Connection, title: str, body: str, audience: str = "all") -> int:
    cur = conn.execute("INSERT INTO announcements (title, body, audience) VALUES (?,?,?)", (title.strip(), body.strip(), audience))
    conn.commit()
    log_audit(conn, "admin", "announcement_posted", {"id": cur.lastrowid, "title": title[:80], "audience": audience})
    return cur.lastrowid


def load_announcements(conn: sqlite3.Connection, audience: Optional[str] = None, active_only: bool = True) -> pd.DataFrame:
    q = "SELECT id, created_at, title, body, audience, is_active FROM announcements"
    conds, params = [], []
    if active_only:
        conds.append("is_active = 1")
    if audience:
        conds.append("audience IN ('all', ?)"); params.append(audience)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    return pd.read_sql_query(q + " ORDER BY id DESC", conn, params=tuple(params))


def set_announcement_active(conn: sqlite3.Connection, aid: int, active: bool) -> None:
    conn.execute("UPDATE announcements SET is_active = ? WHERE id = ?", (int(active), aid))
    conn.commit()


# --------------------------------------------------------------------------- password reset (students)
def create_password_reset(conn: sqlite3.Connection, email: str) -> Optional[str]:
    row = find_applicant_by_email(conn, email)
    if not row:
        return None
    token = secrets.token_hex(4).upper()
    conn.execute("INSERT INTO password_resets (applicant_id, token) VALUES (?, ?)", (row["id"], token))
    conn.commit()
    log_audit(conn, "system", "password_reset_requested", {"applicant_id": row["id"]})
    return token


def redeem_password_reset(conn: sqlite3.Connection, email: str, token: str, new_password: str) -> bool:
    row = find_applicant_by_email(conn, email)
    if not row or len(new_password) < 6:
        return False
    pr = conn.execute("SELECT * FROM password_resets WHERE applicant_id = ? AND token = ? AND used = 0 ORDER BY id DESC LIMIT 1",
                      (row["id"], (token or "").strip().upper())).fetchone()
    if not pr:
        return False
    conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (pr["id"],))
    conn.execute("UPDATE applicants SET password_hash = ? WHERE id = ?", (hash_password(new_password), row["id"]))
    conn.commit()
    log_audit(conn, "student", "password_reset_completed", {"applicant_id": row["id"]})
    return True


# --------------------------------------------------------------------------- program management
def upsert_program(conn: sqlite3.Connection, *, program_id: Optional[int], code: str, name: str, capacity: int, min_score: int,
                   required_track: Optional[str], department: str = "", duration: str = "", description: str = "", is_open: bool = True) -> int:
    code = code.strip().upper()
    if not code or not name.strip():
        raise ValueError("code and name are required")
    if capacity < 0 or not 0 <= min_score <= 100:
        raise ValueError("capacity must be >= 0 and min score 0-100")
    track = required_track if required_track else None
    clash = conn.execute("SELECT id FROM programs WHERE upper(code) = ? AND id IS NOT ?", (code, program_id)).fetchone()
    if clash:
        raise ValueError(f"program code '{code}' is already used by another program; choose a unique Program ID")
    if program_id is None:
        cur = conn.execute(
            "INSERT INTO programs (code, name, capacity, min_score, required_track, department, duration, description, is_open, image_key) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (code, name.strip(), capacity, min_score, track, department, duration, description, int(is_open), code.lower()))
        conn.commit()
        log_audit(conn, "admin", "program_added", {"id": cur.lastrowid, "code": code, "capacity": capacity})
        return cur.lastrowid
    old = conn.execute("SELECT capacity FROM programs WHERE id = ?", (program_id,)).fetchone()
    conn.execute(
        "UPDATE programs SET code=?, name=?, capacity=?, min_score=?, required_track=?, department=?, duration=?, description=?, is_open=? WHERE id=?",
        (code, name.strip(), capacity, min_score, track, department, duration, description, int(is_open), program_id))
    if old and old["capacity"] != capacity:
        conn.execute("INSERT INTO capacity_changes (program_id, old_capacity, new_capacity, reason) VALUES (?,?,?,?)",
                     (program_id, old["capacity"], capacity, "edited in Program Management"))
    conn.commit()
    log_audit(conn, "admin", "program_edited", {"id": program_id, "code": code, "capacity": capacity})
    return program_id


def program_references(conn: sqlite3.Connection, program_id: int) -> Dict[str, int]:
    return {
        "preferences": conn.execute("SELECT COUNT(*) FROM preferences WHERE program_id = ?", (program_id,)).fetchone()[0],
        "assignments": conn.execute("SELECT COUNT(*) FROM assignments WHERE program_id = ?", (program_id,)).fetchone()[0],
        "appeals": conn.execute("SELECT COUNT(*) FROM appeals WHERE requested_program_id = ?", (program_id,)).fetchone()[0],
    }


def delete_program(conn: sqlite3.Connection, program_id: int) -> None:
    """Only allowed when nothing references the program; otherwise close it (is_open=0) instead."""
    refs = program_references(conn, program_id)
    if any(refs.values()):
        raise ValueError(f"program is referenced ({refs}); close it instead of deleting")
    conn.execute("DELETE FROM programs WHERE id = ?", (program_id,))
    conn.commit()
    log_audit(conn, "admin", "program_deleted", {"id": program_id})


# --------------------------------------------------------------------------- accounts & applications
def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(stored: Optional[str], password: str) -> bool:
    if not stored:
        return False
    try:
        _algo, salt, _digest = stored.split("$", 2)
    except ValueError:
        return False
    return secrets.compare_digest(hash_password(password, salt), stored)


def register_account(conn: sqlite3.Connection, *, name: str, email: str, phone: str, address: str, password: str) -> int:
    """Create a basic account (application_status='registered'). No educational data yet."""
    name, email = name.strip(), email.lower().strip()
    if not name or "@" not in email:
        raise ValueError("name and a valid email are required")
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    if find_applicant_by_email(conn, email):
        raise ValueError("that email is already registered")
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO applicants (name, email, score, track, application_status, password_hash, phone, address, form_data) "
        "VALUES (?,?,0,'',?,?,?,?,?)",
        (name, email, "registered", hash_password(password), phone.strip(), address.strip(), json.dumps({})),
    )
    conn.commit()
    log_audit(conn, "public", "account_registered", {"applicant_id": cur.lastrowid, "email": email})
    return cur.lastrowid


def has_applied(row) -> bool:
    return bool(row) and row["application_status"] == "applied"


def submit_application(
    conn: sqlite3.Connection, applicant_id: int, *, score: int, track: str,
    ranked_program_ids: Sequence[int], form_data: Optional[Dict[str, object]] = None,
) -> None:
    """Attach the educational application to an existing account and enter the allocation pool."""
    if not ranked_program_ids:
        raise ValueError("rank at least one program")
    max_prefs = int(get_setting(conn, "max_preferences", "5") or 5)
    if len(ranked_program_ids) > max_prefs:
        raise ValueError(f"at most {max_prefs} preferences are allowed")
    if track not in TRACKS:
        raise ValueError("unknown track")
    if not 0 <= int(score) <= 100:
        raise ValueError("score must be 0-100")
    cur = conn.cursor()
    cur.execute(
        "UPDATE applicants SET score = ?, track = ?, form_data = ?, application_status = 'applied', applied_at = datetime('now') WHERE id = ?",
        (int(score), track, json.dumps(form_data or {}), applicant_id),
    )
    cur.execute("DELETE FROM preferences WHERE applicant_id = ?", (applicant_id,))
    for rank, pid in enumerate(ranked_program_ids, start=1):
        cur.execute("INSERT INTO preferences (applicant_id, program_id, rank) VALUES (?,?,?)", (applicant_id, int(pid), rank))
    conn.commit()
    log_audit(conn, "student", "application_submitted", {"applicant_id": applicant_id, "prefs": [int(p) for p in ranked_program_ids]})


# --------------------------------------------------------------------------- site content (CMS)
def seed_site_content(conn: sqlite3.Connection) -> None:
    for key, (_label, text) in DEFAULT_SITE_CONTENT.items():
        conn.execute("INSERT OR IGNORE INTO site_content (section_key, content_text) VALUES (?, ?)", (key, text))
    conn.commit()


def get_site_content(conn: sqlite3.Connection) -> Dict[str, str]:
    rows = conn.execute("SELECT section_key, content_text FROM site_content").fetchall()
    content = {k: v[1] for k, v in DEFAULT_SITE_CONTENT.items()}
    content.update({r["section_key"]: r["content_text"] for r in rows})
    return content


def get_site_text(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT content_text FROM site_content WHERE section_key = ?", (key,)).fetchone()
    if row:
        return row["content_text"]
    return DEFAULT_SITE_CONTENT.get(key, ("", default))[1] or default


def set_site_content(conn: sqlite3.Connection, key: str, text: str, actor: str = "admin") -> None:
    if not key or not key.replace("_", "").isalnum():
        raise ValueError("invalid section key")
    conn.execute(
        """INSERT INTO site_content (section_key, content_text, updated_at) VALUES (?, ?, datetime('now'))
           ON CONFLICT(section_key) DO UPDATE SET content_text = excluded.content_text, updated_at = datetime('now')""",
        (key, text),
    )
    conn.commit()
    log_audit(conn, actor, "site_content_updated", {"key": key, "chars": len(text)})


def reset_site_content(conn: sqlite3.Connection, key: str) -> None:
    if key not in DEFAULT_SITE_CONTENT:
        raise ValueError("unknown section key")
    set_site_content(conn, key, DEFAULT_SITE_CONTENT[key][1])


# --------------------------------------------------------------------------- dynamic form schema
def seed_form_schema(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT COUNT(*) FROM form_schema").fetchone()[0]:
        return
    for order, (key, label, ftype, req, options) in enumerate(DEFAULT_FORM_FIELDS):
        conn.execute(
            "INSERT INTO form_schema (field_key, label, field_type, required, options, sort_order) VALUES (?,?,?,?,?,?)",
            (key, label, ftype, req, json.dumps(options) if options else None, order),
        )
    conn.commit()


def load_form_schema(conn: sqlite3.Connection) -> List[dict]:
    rows = conn.execute("SELECT * FROM form_schema ORDER BY sort_order, id").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["options"] = json.loads(d["options"]) if d["options"] else []
        d["required"] = bool(d["required"])
        out.append(d)
    return out


def slugify_key(label: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", label.strip().lower()).strip("_")
    return key or "field"


def add_form_field(conn: sqlite3.Connection, *, label: str, field_type: str, required: bool, options: Optional[Sequence[str]] = None) -> str:
    if field_type not in ("text", "number", "select"):
        raise ValueError("field_type must be text, number or select")
    if field_type == "select" and not options:
        raise ValueError("select fields need at least one option")
    key = base = slugify_key(label)
    n = 2
    while conn.execute("SELECT 1 FROM form_schema WHERE field_key = ?", (key,)).fetchone():
        key = f"{base}_{n}"
        n += 1
    order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM form_schema").fetchone()[0]
    conn.execute(
        "INSERT INTO form_schema (field_key, label, field_type, required, options, sort_order) VALUES (?,?,?,?,?,?)",
        (key, label.strip(), field_type, int(required), json.dumps(list(options)) if options else None, order),
    )
    conn.commit()
    log_audit(conn, "admin", "form_field_added", {"key": key, "label": label, "type": field_type, "required": required})
    return key


def remove_form_field(conn: sqlite3.Connection, field_key: str) -> None:
    conn.execute("DELETE FROM form_schema WHERE field_key = ?", (field_key,))
    conn.commit()
    log_audit(conn, "admin", "form_field_removed", {"key": field_key})


def validate_form_response(schema: List[dict], response: Dict[str, object]) -> List[str]:
    """Return a list of human-readable problems (empty = valid)."""
    problems = []
    for f in schema:
        v = response.get(f["field_key"])
        empty = v is None or (isinstance(v, str) and not v.strip())
        if f["required"] and empty:
            problems.append(f"'{f['label']}' is required")
        elif not empty and f["field_type"] == "number":
            try:
                float(v)
            except (TypeError, ValueError):
                problems.append(f"'{f['label']}' must be a number")
        elif not empty and f["field_type"] == "select" and v not in f["options"]:
            problems.append(f"'{f['label']}' must be one of {f['options']}")
    return problems


# --------------------------------------------------------------------------- documents (local file system)
def safe_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"file type '.{ext}' not allowed; use {sorted(ALLOWED_EXTENSIONS)}")
    return ext


def document_path(applicant_id: int, kind: str, ext: str) -> str:
    """Secure, predictable relative path: uploads/000123_12thMarksheet.pdf. Never uses the client filename."""
    if kind not in DOC_KINDS:
        raise ValueError(f"unknown document kind {kind}")
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"extension {ext} not allowed")
    return f"{UPLOAD_DIR.name}/{int(applicant_id):06d}_{DOC_KINDS[kind]}.{ext}"


def save_document(conn: sqlite3.Connection, applicant_id: int, kind: str, filename: str, data: bytes) -> str:
    """Write bytes to uploads/ under a secure name and record the path on the applicant row."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"file exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit")
    if not data:
        raise ValueError("empty file")
    ext = safe_extension(filename)
    rel = document_path(applicant_id, kind, ext)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # remove stale versions with a different extension
    for old in UPLOAD_DIR.glob(f"{int(applicant_id):06d}_{DOC_KINDS[kind]}.*"):
        old.unlink()
    (UPLOAD_DIR.parent / rel).write_bytes(data)
    col = "marksheet_path" if kind == "marksheet" else "scorecard_path"
    conn.execute(f"UPDATE applicants SET {col} = ? WHERE id = ?", (rel, applicant_id))
    conn.commit()
    log_audit(conn, "student", "document_uploaded", {"applicant_id": applicant_id, "kind": kind, "path": rel, "bytes": len(data)})
    return rel


def resolve_document(rel_path: Optional[str]) -> Optional[Path]:
    """Absolute path if the file exists on disk, else None (seeded users have simulated paths)."""
    if not isinstance(rel_path, str) or not rel_path:
        return None
    p = (UPLOAD_DIR.parent / rel_path).resolve()
    if UPLOAD_DIR.resolve() not in p.parents:      # path-traversal guard
        return None
    return p if p.is_file() else None


# --------------------------------------------------------------------------- reads
def load_programs(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query("SELECT * FROM programs ORDER BY id", conn)


def load_applicants(conn: sqlite3.Connection, active_only: bool = False) -> pd.DataFrame:
    q = "SELECT * FROM applicants"
    if active_only:
        q += " WHERE status = 'active'"
    return pd.read_sql_query(q + " ORDER BY id", conn)


def load_applicants_full(conn: sqlite3.Connection) -> pd.DataFrame:
    """Applicants joined with dynamic form responses (one column per field) and document flags."""
    df = pd.read_sql_query("SELECT * FROM applicants ORDER BY id", conn)
    schema = load_form_schema(conn)
    parsed = df["form_data"].apply(lambda v: json.loads(v) if v else {})
    for f in schema:
        df[f["label"]] = parsed.apply(lambda d, k=f["field_key"]: d.get(k))
    df["marksheet_on_disk"] = df["marksheet_path"].apply(lambda p: resolve_document(p) is not None)
    df["scorecard_on_disk"] = df["scorecard_path"].apply(lambda p: resolve_document(p) is not None)
    return df.drop(columns=["form_data"])


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
        Applicant(id=r["id"], name=r["name"], score=r["score"], track=r["track"], status=r["status"], email=r["email"],
                  applied_at=r["applied_at"] or "")
        for r in conn.execute("SELECT * FROM applicants WHERE application_status = 'applied' ORDER BY id")
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
    """Persist a solver result as a new run version (with the policy it was solved under). Returns run id."""
    pref_score = problem.total_points(assignment)
    cur = conn.cursor()
    if make_current:
        cur.execute("UPDATE allocation_runs SET is_current = 0")
    cur.execute(
        """INSERT INTO allocation_runs
           (mode, solver_status, objective, best_bound, wall_time_s, preference_score,
            assigned_count, reassigned_count, parent_run_id, is_current, notes, policy_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (mode, solver_status, objective, best_bound, wall_time_s, pref_score,
         len(assignment), reassigned_count, parent_run_id, 1 if make_current else 0, notes, json.dumps(policy_snapshot(conn))),
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
    conn: sqlite3.Connection, *, name: str, email: str, score: int, track: str, ranked_program_ids: Sequence[int],
    form_data: Optional[Dict[str, object]] = None,
) -> int:
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO applicants (name, email, score, track, form_data, application_status) VALUES (?,?,?,?,?,'applied')",
        (name, email.lower().strip(), score, track, json.dumps(form_data or {})),
    )
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
