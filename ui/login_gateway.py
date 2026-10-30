"""Dedicated login gateway view (current_page == "login"). Clean, centred, no college imagery.

Unified login (Email or Username + Password) resolves the role; a toggle shows the
registration form. "← Back to Home" returns to the public website.
"""
from __future__ import annotations

import importlib

import streamlit as st

from database import db_manager as db
from ui import auth
from ui.common import BRAND, SYSTEM, conn

CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
header[data-testid="stHeader"], #MainMenu, footer { display:none !important; }
[data-testid="stAppViewContainer"] { background: radial-gradient(900px 400px at 50% -10%, #1B3B6B 0%, #0B1F3A 60%); }
.block-container { padding-top: 2.5rem !important; max-width: 100% !important; }
h1.gw-title, .gw-title { text-align:center; color:#fff !important; font-weight:900; font-size:2.2rem; letter-spacing:-.5px; margin:0; padding:0; }
.gw-sub { text-align:center; color:rgba(255,255,255,.7); margin:4px 0 22px; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) { background:#fff; border-radius:22px; padding:26px 26px 22px;
  box-shadow:0 24px 60px rgba(0,0,0,.35); }
div[data-testid="stForm"] { border:none !important; padding:0 !important; }
div[data-testid="stFormSubmitButton"] > button { background:linear-gradient(135deg,#F5B301,#FF9F1C) !important; color:#0B1F3A !important;
  font-weight:800 !important; border:none !important; border-radius:14px !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) div[data-testid="stButton"] > button { background:transparent !important; color:#0B1F3A !important;
  border:1.5px solid #0B1F3A !important; border-radius:14px !important; font-weight:700 !important; margin-top:8px; }
div[data-testid="stButton"] > button[kind="tertiary"], .gw-back div[data-testid="stButton"] > button { color:#fff !important; }
</style>
"""


def _go_home() -> None:
    st.session_state["current_page"] = "home"
    st.session_state["show_register"] = False


def render() -> None:
    c = conn()
    st.markdown(CSS, unsafe_allow_html=True)
    content = db.get_site_content(c)

    top_l, _, _ = st.columns([1, 2, 1])
    with top_l:
        if st.button("← Back to Home", key="back_home", type="tertiary"):
            _go_home()
            st.rerun()

    st.markdown(f"<h1 class='gw-title'>{SYSTEM} Gateway</h1><p class='gw-sub'>{content.get('institute_name', BRAND)} · {BRAND}</p>",
                unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1.25, 1])
    with mid:
        if st.session_state.get("show_register"):
            student = importlib.import_module("ui.1_student_portal")
            with st.form("register_shell", border=False):
                st.markdown("### Register as a new student")
                st.form_submit_button("← Back to login", on_click=lambda: st.session_state.update(show_register=False))
            student.render_registration(c, compact=True)
            return

        with st.form("unified_login"):
            st.markdown("### Sign in")
            st.caption("Students: registered email, password not required. Admissions office: username and password.")
            ident = st.text_input("Email or Username", key="login_ident", placeholder="applicant001@seatwisee.demo  or  admin")
            pw = st.text_input("Password", type="password", key="login_pw", placeholder="students: leave blank")
            go = st.form_submit_button("Sign in", type="primary", width="stretch")
        if go:
            role = auth.login_unified(ident, pw, c)
            if role:
                st.session_state["current_page"] = "admin_dashboard" if role == auth.ROLE_ADMIN else "student_portal"
                st.session_state["show_register"] = False
                st.rerun()
            st.error("Invalid credentials.")
        if st.button("Register as New Student", key="goto_register", width="stretch"):
            st.session_state["show_register"] = True
            st.rerun()
