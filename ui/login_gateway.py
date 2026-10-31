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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"],
header[data-testid="stHeader"], #MainMenu, footer { display:none !important; }
.stApp, .stApp *:not([data-testid="stIconMaterial"]):not([role="img"]):not(code) { font-family:'Inter',system-ui,-apple-system,'Segoe UI',Roboto,sans-serif; }
[data-testid="stAppViewContainer"] { background: radial-gradient(900px 500px at 85% 10%, rgba(139,92,246,.45), transparent 60%), radial-gradient(700px 400px at 10% 90%, rgba(245,179,1,.18), transparent 60%), linear-gradient(120deg, #0B1F3A 0%, #122B4F 55%, #3B1F8A 100%); }
.block-container { padding-top: 1.6rem !important; padding-bottom: 3rem !important; max-width: 100% !important; }

/* brand header */
.gw-head { display:flex; flex-direction:column; align-items:center; gap:10px; margin:6px 0 22px; text-align:center; }
.gw-head img { width:58px; height:58px; border-radius:16px; box-shadow:0 10px 30px rgba(245,179,1,.35); }
.gw-title { color:#fff !important; font-weight:900; font-size:2.1rem; letter-spacing:-.8px; margin:0; line-height:1.1; }
.gw-sub { color:rgba(255,255,255,.75); margin:0; font-size:.95rem; }
.gw-chip { display:inline-flex; gap:6px; align-items:center; padding:5px 12px; border-radius:999px; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.22); color:#FFE9A8; font-size:.74rem; font-weight:700; letter-spacing:1.5px; text-transform:uppercase; }

/* the card */
div[data-testid="stColumn"]:has([data-testid="stForm"]) { background:#fff; border-radius:24px; padding:30px 30px 24px; box-shadow:0 30px 80px rgba(3,7,18,.45); border-top:5px solid #6D28D9; }
div[data-testid="stForm"] { border:none !important; padding:0 !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) h3 { color:#0F172A !important; font-weight:900 !important; letter-spacing:-.6px; margin-bottom:0 !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stCaptionContainer"] p { color:#64748B !important; }

/* labels */
div[data-testid="stColumn"]:has([data-testid="stForm"]) label p { color:#1E293B !important; font-weight:700 !important; font-size:.88rem !important; }

/* clearly visible input boxes (Streamlit 1.66: stTextInputRootElement / stTextAreaRootElement) */
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextInputRootElement"],
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextAreaRootElement"] {
  background:#F8FAFC !important; border:1.5px solid #CBD5E1 !important; border-radius:12px !important; min-height:48px; transition:border-color .15s, box-shadow .15s, background .15s; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) input, div[data-testid="stColumn"]:has([data-testid="stForm"]) textarea { color:#0F172A !important; font-size:.98rem !important; padding-left:14px !important; caret-color:#6D28D9; background:transparent !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) input::placeholder, div[data-testid="stColumn"]:has([data-testid="stForm"]) textarea::placeholder { color:#94A3B8 !important; opacity:1; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextInputRootElement"]:hover, div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextAreaRootElement"]:hover { border-color:#A78BFA !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextInputRootElement"]:focus-within, div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextAreaRootElement"]:focus-within {
  border-color:#6D28D9 !important; background:#fff !important; box-shadow:0 0 0 4px rgba(109,40,217,.15) !important; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) [data-testid="stTextInputRootElement"] button { color:#64748B !important; }

/* buttons */
div[data-testid="stFormSubmitButton"] > button { background:linear-gradient(135deg,#F5B301,#FF9F1C) !important; color:#0B1F3A !important; font-weight:800 !important; font-size:1rem !important; border:none !important; border-radius:14px !important; min-height:50px; box-shadow:0 12px 26px rgba(245,179,1,.35); transition:transform .15s; }
div[data-testid="stFormSubmitButton"] > button:hover { transform:translateY(-1px); filter:brightness(1.04); }
div[data-testid="stColumn"]:has([data-testid="stForm"]) div[data-testid="stButton"] > button { background:#fff !important; color:#5B21B6 !important; border:1.5px solid #C4B5FD !important; border-radius:14px !important; font-weight:700 !important; min-height:46px; margin-top:6px; }
div[data-testid="stColumn"]:has([data-testid="stForm"]) div[data-testid="stButton"] > button:hover { background:#F5F3FF !important; border-color:#6D28D9 !important; }
.st-key-back_home button { color:#fff !important; font-weight:700 !important; }
.st-key-back_home button:hover { color:#FFD75E !important; }

/* trust strip under the card */
.gw-trust { display:flex; justify-content:center; gap:18px; flex-wrap:wrap; margin-top:20px; color:rgba(255,255,255,.75); font-size:.82rem; }
.gw-trust span { display:inline-flex; align-items:center; gap:6px; }
.gw-trust b { color:#FFD75E; }
.gw-demo { background:#F5F3FF; border:1px dashed #C4B5FD; border-radius:12px; padding:10px 12px; color:#4C1D95; font-size:.8rem; margin-top:12px; line-height:1.5; }
.gw-demo code { background:#EDE9FE; color:#4C1D95; padding:1px 6px; border-radius:6px; }
@media (max-width: 760px) { div[data-testid="stColumn"]:has([data-testid="stForm"]) { padding:22px 18px 18px; } .gw-title { font-size:1.7rem; } }
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
    st.html(CSS)
    content = db.get_site_content(c)
    top_l, _, _ = st.columns([1, 2, 1])
    with top_l:
        if st.button("← Back to Home", key="back_home", type="tertiary"):
            st.session_state.update(current_page="home", show_register=False, show_forgot=False)
            st.rerun()
    st.html(f"<div class='gw-head'><img src='app/static/images/logo.png' alt=''><span class='gw-chip'>Admissions {db.get_setting(c, 'academic_session', '')}</span>"
            f"<h1 class='gw-title'>Welcome to {BRAND}</h1><p class='gw-sub'>{content.get('institute_name', '')} · {SYSTEM} admissions portal</p></div>")
    _, mid, _ = st.columns([1, 1.25, 1])
    with mid:
        if st.session_state.get("show_register"):
            _register(c)
        elif st.session_state.get("show_forgot"):
            _forgot(c)
        else:
            _login(c)
    st.html("<div class='gw-trust'><span>🔒 <b>Encrypted</b> passwords</span><span>⚖️ <b>Fair</b>, validated seat allocation</span><span>📩 Status updates by <b>email</b></span></div>")


def _login(c):
    with st.form("unified_login"):
        st.markdown("### Sign in")
        st.caption("One sign-in for students and the admissions office. Your role is detected from your account.")
        ident = st.text_input("Email address or username", key="login_ident", placeholder="you@example.com")
        pw = st.text_input("Password", type="password", key="login_pw", placeholder="Enter your password")
        go = st.form_submit_button("Login", type="primary", width="stretch")
    if go:
        user = auth_service.authenticate(c, ident, pw)
        if user:
            _set_session(user)
            st.rerun()
        st.error("Invalid credentials.")
    b1, b2 = st.columns(2)
    if b1.button("Create account", key="goto_register", icon=":material/person_add:", width="stretch"):
        st.session_state["show_register"] = True
        st.rerun()
    if b2.button("Forgot password?", key="goto_forgot", icon=":material/key:", width="stretch"):
        st.session_state["show_forgot"] = True
        st.rerun()
    st.html("<div class='gw-demo'><b>Demo accounts</b> · admin <code>admin</code> / <code>admin123</code> · student <code>applicant001@seatwisee.demo</code> (no password)</div>")


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
