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

HIDE_SIDEBAR_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] { display: none !important; }
.gate-card { background: white; border: 1px solid rgba(15,23,42,.08); border-radius: 18px; padding: 8px 4px 2px; box-shadow: 0 12px 36px rgba(11,31,58,.10); }
.gate-announce { background: #FFF7E0; border-left: 4px solid #F5B301; padding: 12px 16px; border-radius: 10px; color: #4B3A00; }
.gate-about { color: #475569; font-size: .95rem; line-height: 1.6; }
</style>
"""


def render_gateway() -> None:
    st.markdown(HIDE_SIDEBAR_CSS, unsafe_allow_html=True)
    content = db.get_site_content(c)
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        st.markdown(
            f"<h1 style='text-align:center;margin-bottom:0'>{content['hero_title']}</h1>"
            f"<p style='text-align:center;color:gray;margin-top:6px'>{content['hero_subtitle']}</p>",
            unsafe_allow_html=True,
        )
        if content.get("announcements", "").strip():
            st.markdown(f"<div class='gate-announce'><b>Announcements</b><br>{content['announcements']}</div>", unsafe_allow_html=True)
        st.markdown("")

        if st.session_state.get("show_register"):
            st.subheader("Register as a new student")
            if st.button("← Back to login", key="back_to_login"):
                st.session_state["show_register"] = False
                st.rerun()
            student.render_registration(c, compact=True)
            return

        with st.form("unified_login"):
            st.markdown("#### Sign in")
            ident = st.text_input("Email or Username", key="login_ident", placeholder="applicant001@seatwisee.demo  or  admin")
            pw = st.text_input("Password", type="password", key="login_pw", placeholder="students: leave blank · admin: admin123")
            go = st.form_submit_button("Sign in", type="primary", width="stretch")
        if go:
            resolved = auth.login_unified(ident, pw, c)
            if resolved:
                st.rerun()
            st.error("Invalid credentials.")
        if st.button("Register as New Student", key="goto_register", width="stretch"):
            st.session_state["show_register"] = True
            st.rerun()

        with st.expander("About us"):
            st.markdown(f"<p class='gate-about'>{content['about_us']}</p>", unsafe_allow_html=True)
            st.caption(content.get("contact_info", ""))


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
