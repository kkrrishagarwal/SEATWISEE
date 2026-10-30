"""Dedicated authentication view (current_page == "login"): ONE login for students and administrators,
registration (account only) and forgot-password. Role is resolved from the database by auth_service.
"""
from __future__ import annotations

import streamlit as st

from database import db_manager as db
from services import auth_service, notification_service as ns
from ui.common import BRAND, SYSTEM, conn

CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
header[data-testid="stHeader"], #MainMenu, footer { display:none !important; }
[data-testid="stAppViewContainer"] { background: radial-gradient(900px 400px at 50% -10%, #1B3B6B 0%, #0B1F3A 60%); }
.block-container { padding-top: 2.5rem !important; max-width: 100% !important; }
h1.gw-title, .gw-title { text-align:center; color:#fff !important; font-weight:900; font-size:2.2rem; letter-spacing:-.5px; margin:0; padding:0; }
.gw-sub { text-align:center; color:rgba(255,255,255,.7); margin:4px 0 22px; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) { background:#fff; border-radius:22px; padding:26px 26px 22px; box-shadow:0 24px 60px rgba(0,0,0,.35); }
div[data-testid="stForm"] { border:none !important; padding:0 !important; }
div[data-testid="stFormSubmitButton"] > button { background:linear-gradient(135deg,#F5B301,#FF9F1C) !important; color:#0B1F3A !important; font-weight:800 !important; border:none !important; border-radius:14px !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) div[data-testid="stButton"] > button { background:transparent !important; color:#0B1F3A !important; border:1.5px solid #0B1F3A !important; border-radius:14px !important; font-weight:700 !important; margin-top:8px; }
</style>
"""


def _set_session(user: dict) -> None:
    st.session_state["auth_role"] = user["role"]
    st.session_state["auth_name"] = user["name"]
    if user["role"] == auth_service.ROLE_STUDENT:
        st.session_state["auth_student_id"] = user["id"]
        st.session_state["current_page"] = "student_portal"
    else:
        st.session_state["auth_admin_id"] = user["id"]
        st.session_state["current_page"] = "admin_dashboard"
    st.session_state["show_register"] = False
    st.session_state["show_forgot"] = False


def render() -> None:
    c = conn()
    st.markdown(CSS, unsafe_allow_html=True)
    content = db.get_site_content(c)
    top_l, _, _ = st.columns([1, 2, 1])
    with top_l:
        if st.button("← Back to Home", key="back_home", type="tertiary"):
            st.session_state.update(current_page="home", show_register=False, show_forgot=False)
            st.rerun()
    st.markdown(f"<h1 class='gw-title'>{SYSTEM} Gateway</h1><p class='gw-sub'>{content.get('institute_name', BRAND)} · {BRAND}</p>", unsafe_allow_html=True)
    _, mid, _ = st.columns([1, 1.25, 1])
    with mid:
        if st.session_state.get("show_register"):
            _register(c)
        elif st.session_state.get("show_forgot"):
            _forgot(c)
        else:
            _login(c)


def _login(c):
    with st.form("unified_login"):
        st.markdown("### Sign in")
        st.caption("One sign-in for students and the admissions office. Your role is detected from your account.")
        ident = st.text_input("Email address or username", key="login_ident", placeholder="you@example.com")
        pw = st.text_input("Password", type="password", key="login_pw")
        go = st.form_submit_button("Login", type="primary", width="stretch")
    if go:
        user = auth_service.authenticate(c, ident, pw)
        if user:
            _set_session(user)
            st.rerun()
        st.error("Invalid credentials.")
    b1, b2 = st.columns(2)
    if b1.button("Register as New Student", key="goto_register", width="stretch"):
        st.session_state["show_register"] = True
        st.rerun()
    if b2.button("Forgot password?", key="goto_forgot", width="stretch"):
        st.session_state["show_forgot"] = True
        st.rerun()
    st.caption("Demo accounts: admin `admin` / `admin123` · student `applicant001@seatwisee.demo` (no password)")


def _register(c):
    with st.form("account_register"):
        st.markdown("### Create your account")
        st.caption("Student accounts only. The educational application is completed after signing in.")
        name = st.text_input("Full name *", key="reg_name")
        email = st.text_input("Email *", key="reg_email")
        phone = st.text_input("Phone number *", key="reg_phone", placeholder="10-digit mobile, used for WhatsApp updates")
        address = st.text_area("Address *", key="reg_address", height=70)
        p1, p2 = st.columns(2)
        pw = p1.text_input("Password *", type="password", key="reg_pw")
        pw2 = p2.text_input("Confirm password *", type="password", key="reg_pw2")
        submitted = st.form_submit_button("Create account", type="primary", width="stretch")
    if st.button("← Back to login", key="reg_back", width="stretch"):
        st.session_state["show_register"] = False
        st.rerun()
    if not submitted:
        return
    problems = []
    if not name.strip():
        problems.append("Full name is required")
    if "@" not in email or "." not in email.split("@")[-1]:
        problems.append("A valid email is required")
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        problems.append("A valid phone number is required")
    if not address.strip():
        problems.append("Address is required")
    if len(pw) < 6:
        problems.append("Password must be at least 6 characters")
    if pw != pw2:
        problems.append("Passwords do not match")
    if problems:
        st.error("Please fix:\n\n- " + "\n- ".join(problems))
        return
    try:
        aid = db.register_account(c, name=name, email=email, phone=phone, address=address, password=pw)
    except ValueError as e:
        st.error(str(e))
        return
    res = ns.notify(c, aid, "account_registered", dedupe="welcome")
    st.toast("📧 Email sent: Welcome to SEATWISEE!" if res.get("email") == "sent" else "Account created · welcome message delivered in your portal", icon="✅")
    user = auth_service.authenticate(c, email, pw)
    _set_session(user)
    st.rerun()


def _forgot(c):
    with st.form("forgot_pw"):
        st.markdown("### Reset your password")
        st.caption("Enter your registered email. A reset code is emailed when email delivery is configured; otherwise it is shown here (demonstration mode).")
        email = st.text_input("Registered email", key="fp_email")
        req = st.form_submit_button("Send reset code", width="stretch")
    if req:
        token = db.create_password_reset(c, email)
        if token:
            st.session_state["fp_pending_email"] = email
            res = ns.notify(c, db.find_applicant_by_email(c, email)["id"], "password_reset",
                            {"body": f"Your {BRAND} password reset code is {token}."}, channels=("email",), dedupe=f"reset:{token}")
            if res.get("email") == "sent":
                st.success("Reset code emailed.")
            else:
                st.info(f"Email delivery is not configured. Your reset code is **{token}**.")
        else:
            st.error("No account with that email.")
    with st.form("redeem_pw"):
        st.markdown("Enter the code and a new password")
        em2 = st.text_input("Email", key="fp_email2", value=st.session_state.get("fp_pending_email", ""))
        tok = st.text_input("Reset code", key="fp_token")
        npw = st.text_input("New password", type="password", key="fp_new")
        ok = st.form_submit_button("Update password", type="primary", width="stretch")
    if ok:
        if db.redeem_password_reset(c, em2, tok, npw):
            st.success("Password updated. Sign in with your new password.")
            st.session_state["show_forgot"] = False
            st.rerun()
        st.error("Invalid code or password too short (min 6).")
    if st.button("← Back to login", key="fp_back", width="stretch"):
        st.session_state["show_forgot"] = False
        st.rerun()
