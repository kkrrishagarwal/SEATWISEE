"""SEATWISEE — Streamlit entry point with a role-based Login Gateway. Public UI brand: "DO! u want".

Roles
  admin   : username/password (admin / admin123) -> Admin dashboard + Appeal studio
  student : email that exists in SQLite          -> Student portal (own data only)
  (none)  : registration form for new students
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui import auth  # noqa: E402
from ui.common import BRAND, conn  # noqa: E402

st.set_page_config(page_title="DO! u want · SEATWISEE", page_icon="🎯", layout="wide")

student = importlib.import_module("ui.1_student_portal")
admin = importlib.import_module("ui.2_admin_dashboard")
appeals = importlib.import_module("ui.3_appeal_studio")

c = conn()
role = auth.current_role()

# ------------------------------------------------------------------ sidebar: identity + login
with st.sidebar:
    st.markdown("### SEATWISEE")
    st.caption("Constraint-based seat allocation · Google OR-Tools CP-SAT · SQLite · Streamlit")
    if role:
        st.success(f"Signed in as **{st.session_state.get('auth_name')}** ({role})")
        if st.button("Log out", key="logout_btn"):
            auth.logout()
            st.rerun()
    else:
        st.markdown("#### Sign in")
        mode = st.radio("I am a", ["Student", "Admin / Teacher"], horizontal=True, key="login_mode")
        if mode == "Admin / Teacher":
            with st.form("admin_login"):
                u = st.text_input("Username", key="login_user")
                pw = st.text_input("Password", type="password", key="login_pw")
                go = st.form_submit_button("Sign in", type="primary")
            if go:
                if auth.login_admin(u, pw, c):
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        else:
            with st.form("student_login"):
                em = st.text_input("Registered email", key="login_email", placeholder="applicant001@seatwisee.demo")
                go = st.form_submit_button("Sign in", type="primary")
            if go:
                if auth.login_student(em, c):
                    st.rerun()
                else:
                    st.error("No applicant with that email. New here? Register on the right.")
        st.caption("New student? Use the registration form on the main page.")
    st.divider()
    st.markdown(
        "- **Mode A** maximises preference points (merit tie-break)\n"
        "- **Mode B** protects existing seats with penalty μ\n"
        "- **Appeals** force one request and report the ripple\n"
        "- An **independent validator** re-checks every rule"
    )

# ------------------------------------------------------------------ routing by role
if role == auth.ROLE_ADMIN:
    tab_admin, tab_appeal = st.tabs(["🛠 Admin dashboard", "⚖️ Appeal studio"])
    with tab_admin:
        admin.render()
    with tab_appeal:
        appeals.render()
elif role == auth.ROLE_STUDENT:
    student.render()           # own data only; no other applicant is ever queried here
else:
    st.info("Sign in from the sidebar, or register below as a new student.")
    student.render()           # registration form
