"""SEATWISEE — unified login gateway. Public brand: "DO! u want".

Unauthenticated : sidebar hidden; one login box (Email or Username + Password) and a
                  "Register as New Student" button. Landing text comes from the site_content CMS.
Student         : sidebar shows name + Logout; main area = personal dashboard only.
Admin           : sidebar shows name + Logout; main area = 5-tab admin workspace (incl. Website Editor).
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import db_manager as db  # noqa: E402
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

college = importlib.import_module("ui.0_college_home")


def _login_card() -> None:
    """Unified login (real Streamlit form) rendered as a floating card over the hero."""
    if st.session_state.get("show_register"):
        with st.form("register_shell", border=False):
            st.markdown("### Register as a new student")
            st.form_submit_button("← Back to login", on_click=lambda: st.session_state.update(show_register=False))
        student.render_registration(c, compact=True)
        return
    with st.form("unified_login"):
        st.markdown("### Portal sign in")
        st.caption("Students use their registered email (password not required). Admissions office uses its username and password.")
        ident = st.text_input("Email or Username", key="login_ident", placeholder="applicant001@seatwisee.demo  or  admin")
        pw = st.text_input("Password", type="password", key="login_pw", placeholder="students: leave blank")
        go = st.form_submit_button("Sign in", type="primary", width="stretch")
    if go:
        if auth.login_unified(ident, pw, c):
            st.rerun()
        st.error("Invalid credentials.")
    if st.button("Register as New Student", key="goto_register", width="stretch"):
        st.session_state["show_register"] = True
        st.rerun()


def render_gateway() -> None:
    """Public college website with the unified login embedded under the hero."""
    content = db.get_site_content(c)
    programs = db.load_programs(c)
    stats = {
        "programs": len(programs),
        "seats": int(programs.capacity.sum()) if len(programs) else 0,
        "applicants": c.execute("SELECT COUNT(*) FROM applicants WHERE status='active'").fetchone()[0],
    }
    college.inject_css()
    st.html('<div id="top"></div>')
    college.nav(content)
    college.hero(content)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        _login_card()
    college.programs(programs)
    college.campus(stats)
    college.admissions(content)
    college.footer(content)


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {SYSTEM}")
        st.write(f"Signed in as **{st.session_state.get('auth_name')}**")
        st.caption(f"Role: {role}")
        if st.button("Log out", key="logout_btn", width="stretch"):
            auth.logout()
            st.session_state.pop("show_register", None)
            st.rerun()


if role == auth.ROLE_ADMIN:
    render_sidebar()
    admin.render()
elif role == auth.ROLE_STUDENT and auth.current_student_id():
    render_sidebar()
    student.render_my_portal(c, auth.current_student_id())
else:
    render_gateway()
