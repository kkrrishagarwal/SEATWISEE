"""SEATWISEE — public brand "DO! u want". Strict session-state router.

current_page                      role      renders (and nothing else)
home/about/academics/courses/...  none      ui/public/site.py        public college website
login                             none      ui/login_gateway.py      unified login · registration · forgot password
student_portal                    student   ui/1_student_portal.py
admin_dashboard                   admin     ui/admin/workspace.py
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from a local .env (never committed) into the environment. Existing variables win."""
    import os
    env = Path(__file__).resolve().parent / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

from ui import auth  # noqa: E402
from ui.common import BRAND, SYSTEM, conn  # noqa: E402

PUBLIC = {"home", "about", "academics", "courses", "admissions", "campus", "contact"}

_role = st.session_state.get("auth_role")
st.set_page_config(page_title=f"{BRAND} · {SYSTEM}", page_icon="🎓", layout="wide", initial_sidebar_state="auto" if _role else "collapsed")

site = importlib.import_module("ui.public.site")
gateway = importlib.import_module("ui.login_gateway")
student = importlib.import_module("ui.1_student_portal")
admin = importlib.import_module("ui.admin.workspace")

c = conn()


def resolve_page() -> str:
    role = auth.current_role()
    if role == auth.ROLE_ADMIN:
        st.session_state["current_page"] = "admin_dashboard"
    elif role == auth.ROLE_STUDENT and auth.current_student_id():
        st.session_state["current_page"] = "student_portal"
    else:
        qp = st.query_params.get("page")
        if qp in PUBLIC or qp == "login":
            st.session_state["current_page"] = qp
            if qp == "login" and st.query_params.get("intent") == "apply":
                st.session_state["post_login_intent"] = "apply"
                st.session_state["apply_intent"] = True
                if st.query_params.get("program"):
                    st.session_state["apply_intent_program"] = st.query_params.get("program").upper()
                st.session_state["show_register"] = True
            keep_program = st.query_params.get("program")
            st.query_params.clear()
            if qp == "courses" and keep_program:
                st.query_params["program"] = keep_program
        page = st.session_state.get("current_page", "home")
        if page not in PUBLIC and page != "login":
            page = "home"
        st.session_state["current_page"] = page
    return st.session_state["current_page"]


page = resolve_page()
if page == "admin_dashboard":
    admin.render(c)
elif page == "student_portal":
    student.render_my_portal(c, auth.current_student_id())
elif page == "login":
    gateway.render()
else:
    site.render(c, page)
