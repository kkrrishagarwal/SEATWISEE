"""SEATWISEE — strict session-state router. Public brand: "DO! u want".

current_page            role      what renders (and nothing else)
----------------------  --------  ---------------------------------------------
home (default)          none      ui/0_college_home.py   public college website
login                   none      ui/login_gateway.py    unified login + registration
student_portal          student   ui/1_student_portal.py
admin_dashboard         admin     ui/2_admin_dashboard.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ui import auth  # noqa: E402
from ui.common import BRAND, SYSTEM, conn  # noqa: E402

PAGES = {"home", "login", "student_portal", "admin_dashboard"}

_role = st.session_state.get("auth_role")
st.set_page_config(
    page_title=f"{BRAND} · {SYSTEM}", page_icon="🎯", layout="wide",
    initial_sidebar_state="expanded" if _role else "collapsed",
)

college = importlib.import_module("ui.0_college_home")
gateway = importlib.import_module("ui.login_gateway")
student = importlib.import_module("ui.1_student_portal")
admin = importlib.import_module("ui.2_admin_dashboard")

c = conn()


def resolve_page() -> str:
    """Single source of truth for routing. Role always wins over the requested page."""
    role = auth.current_role()
    if role == auth.ROLE_ADMIN:
        st.session_state["current_page"] = "admin_dashboard"
    elif role == auth.ROLE_STUDENT and auth.current_student_id():
        st.session_state["current_page"] = "student_portal"
    else:
        # ?page=login[&intent=apply] from the HTML nav / footer links on the home page
        if st.query_params.get("page") == "login":
            st.session_state["current_page"] = "login"
            if st.query_params.get("intent") == "apply":
                st.session_state["post_login_intent"] = "apply"
                st.session_state["show_register"] = True
            st.query_params.clear()
        page = st.session_state.get("current_page", "home")
        if page not in ("home", "login"):
            page = "home"
        st.session_state["current_page"] = page
    return st.session_state["current_page"]


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### {SYSTEM}")
        st.write(f"Signed in as **{st.session_state.get('auth_name')}**")
        st.caption(f"Role: {auth.current_role()}")
        if st.button("Log out", key="logout_btn", width="stretch"):
            auth.logout()
            st.session_state["current_page"] = "home"
            st.session_state.pop("show_register", None)
            st.session_state.pop("student_nav", None)
            st.session_state.pop("post_login_intent", None)
            st.rerun()


page = resolve_page()
if page == "admin_dashboard":
    render_sidebar()
    admin.render()
elif page == "student_portal":
    render_sidebar()
    student.render_my_portal(c, auth.current_student_id())
elif page == "login":
    gateway.render()
else:
    college.render(c)
