"""Unified authentication: one identifier + password resolves to a role from the database."""
from __future__ import annotations

from typing import Optional

from database import db_manager as db

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"


def authenticate(conn, identifier: str, password: str) -> Optional[dict]:
    """Returns {"role", "id", "name"} or None. Admins by username, students by email."""
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" not in ident:
        if db.check_admin_login(conn, ident, password):
            row = db.get_admin(conn, ident)
            db.log_audit(conn, "admin", "login", {"user": row["username"]})
            return {"role": ROLE_ADMIN, "id": int(row["id"]), "name": "Administrator"}
        db.log_audit(conn, "system", "login_failed", {"user": ident[:40], "role": "admin"})
        return None
    row = db.find_applicant_by_email(conn, ident)
    if row is None:
        db.log_audit(conn, "system", "login_failed", {"email": ident[:80], "role": "student"})
        return None
    if row["password_hash"] and not db.verify_password(row["password_hash"], (password or "").strip()):
        db.log_audit(conn, "system", "login_failed", {"email": ident[:80], "role": "student", "reason": "bad_password"})
        return None
    db.log_audit(conn, "student", "login", {"applicant_id": int(row["id"])})
    return {"role": ROLE_STUDENT, "id": int(row["id"]), "name": row["name"]}
