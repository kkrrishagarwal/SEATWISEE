"""Role-based access control for SEATWISEE. Session-state based; no external auth."""
from __future__ import annotations

import hashlib
import hmac
from typing import Optional

import streamlit as st

from database import db_manager as db

# Hardcoded admin credential per the project brief. Stored as a salted SHA-256 so the
# plaintext never sits in session state or logs. Change SALT/HASH together to rotate.
ADMIN_USER = "admin"
_SALT = "seatwisee-local"
_ADMIN_HASH = hashlib.sha256((_SALT + "admin123").encode()).hexdigest()

ROLE_ADMIN = "admin"
ROLE_STUDENT = "student"


def _check_admin(user: str, password: str) -> bool:
    digest = hashlib.sha256((_SALT + password).encode()).hexdigest()
    return user.strip() == ADMIN_USER and hmac.compare_digest(digest, _ADMIN_HASH)


def current_role() -> Optional[str]:
    return st.session_state.get("auth_role")


def current_student_id() -> Optional[int]:
    return st.session_state.get("auth_student_id")


def login_admin(user: str, password: str, conn) -> bool:
    if _check_admin(user, password):
        st.session_state["auth_role"] = ROLE_ADMIN
        st.session_state["auth_name"] = "Administrator"
        db.log_audit(conn, "admin", "login", {"user": ADMIN_USER})
        return True
    db.log_audit(conn, "system", "login_failed", {"user": user[:40], "role": "admin"})
    return False


def login_student(email: str, conn) -> bool:
    row = db.find_applicant_by_email(conn, email)
    if row is None:
        db.log_audit(conn, "system", "login_failed", {"email": email[:80], "role": "student"})
        return False
    st.session_state["auth_role"] = ROLE_STUDENT
    st.session_state["auth_student_id"] = int(row["id"])
    st.session_state["auth_name"] = row["name"]
    db.log_audit(conn, "student", "login", {"applicant_id": int(row["id"])})
    return True


def logout() -> None:
    for k in ("auth_role", "auth_student_id", "auth_name", "last_result", "last_cf"):
        st.session_state.pop(k, None)


def require(role: str) -> bool:
    """Guard for a page: returns True if the current session holds `role`, else renders a stop message."""
    if current_role() != role:
        st.error("You are not authorised to view this page.")
        return False
    return True
