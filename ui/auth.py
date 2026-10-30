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
    # Tolerate copy/paste whitespace and username casing; the password itself stays case-sensitive.
    user = (user or "").strip().lower()
    password = (password or "").strip()
    digest = hashlib.sha256((_SALT + password).encode()).hexdigest()
    return user == ADMIN_USER and hmac.compare_digest(digest, _ADMIN_HASH)


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
    db.log_audit(conn, "system", "login_failed", {"user": (user or "")[:40], "role": "admin", "pw_len": len(password or "")})
    return False


def login_student(email: str, conn, password: str = "") -> bool:
    row = db.find_applicant_by_email(conn, email)
    if row is None:
        db.log_audit(conn, "system", "login_failed", {"email": email[:80], "role": "student"})
        return False
    # Accounts created through the registration form carry a password hash and must present it.
    # Seeded demo applicants have none and sign in with email only.
    if row["password_hash"] and not db.verify_password(row["password_hash"], password or ""):
        db.log_audit(conn, "system", "login_failed", {"email": email[:80], "role": "student", "reason": "bad_password"})
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


def login_unified(identifier: str, password: str, conn) -> Optional[str]:
    """Single entry point: resolve role from one identifier.

    'admin' + the admin password          -> ROLE_ADMIN
    an email present in applicants        -> ROLE_STUDENT (password not required for the demo)
    anything else                          -> None
    """
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" not in ident:
        return ROLE_ADMIN if login_admin(ident, password, conn) else None
    return ROLE_STUDENT if login_student(ident, conn, password) else None


def full_logout() -> None:
    """Sign out and clear every navigation/intent key so the next run lands on the public home page."""
    logout()
    for k in ("current_page", "show_register", "show_forgot", "student_nav", "admin_nav", "post_login_intent", "apply_intent", "apply_intent_program", "auth_admin_id",
              "al_out", "rw_out", "rc_out", "ap_cf", "apply_review"):
        st.session_state.pop(k, None)
    st.session_state["current_page"] = "home"
