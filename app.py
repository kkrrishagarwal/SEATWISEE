"""SEATWISEE — strict gateway entry point. Public brand: "DO! u want".

Unauthenticated : sidebar hidden, centred gateway with three tabs
                  (Student Login · New Student Registration · College / Admin Login).
Student         : sidebar shows name + Logout; main area = personal dashboard only.
Admin           : sidebar shows name + Logout; main area = 4-tab admin workspace.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui import auth  # noqa: E402
from ui.common import BRAND, SYSTEM, conn  # noqa: E402

_role = st.session_state.get("auth_role")
st.set_page_config(
    page_title=f"{BRAND} · {SYSTEM}", page_icon="🎯", layout="wide",
    initial_sidebar_state="expanded" if _role else "collapsed",
)

student = importlib.import_module("ui.1_student_portal")
admin = importlib.import_module("ui.2_admin_dashboard")

c = conn()
role = auth.current_role()

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display: none !important; }
section.main > div { padding-top: 2rem; }
</style>
"""


def render_gateway() -> None:
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 2.4, 1])
    with mid:
        st.markdown(
            f"<h1 style='text-align:center;margin-bottom:0'>{SYSTEM} Gateway</h1>"
            f"<p style='text-align:center;color:gray;margin-top:4px'>{BRAND} · constraint-based seat allocation</p>",
            unsafe_allow_html=True,
        )
        tab_student, tab_register, tab_admin = st.tabs(["Student Login", "New Student Registration", "College / Admin Login"])

        with tab_student:
            with st.form("student_login"):
                em = st.text_input("Registered email", key="login_email", placeholder="applicant001@seatwisee.demo")
                go = st.form_submit_button("Sign in", type="primary", width="stretch")
            if go:
                if auth.login_student(em, c):
                    st.rerun()
                st.error("No applicant with that email. New here? Use the registration tab.")

        with tab_register:
            student.render_registration(c, compact=True)

        with tab_admin:
            st.caption("Demo credentials: username **admin** · password **admin123**")
            with st.form("admin_login"):
                u = st.text_input("Username", key="login_user", value="admin")
                pw = st.text_input("Password", type="password", key="login_pw", placeholder="admin123")
                go = st.form_submit_button("Sign in as admin", type="primary", width="stretch")
            if go:
                if auth.login_admin(u, pw, c):
                    st.rerun()
                st.error("Invalid credentials.")


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {SYSTEM}")
        st.write(f"Signed in as **{st.session_state.get('auth_name')}**")
        st.caption(f"Role: {role}")
        if st.button("Log out", key="logout_btn", width="stretch"):
            auth.logout()
            st.rerun()


if role == auth.ROLE_ADMIN:
    render_sidebar()
    admin.render()
elif role == auth.ROLE_STUDENT and auth.current_student_id():
    render_sidebar()
    student.render_my_portal(c, auth.current_student_id())
else:
    render_gateway()
