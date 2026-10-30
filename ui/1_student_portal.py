"""Student portal — sidebar navigation with 8 sections. Shows ONLY the signed-in student's own data."""
from __future__ import annotations

import base64
import json

import pandas as pd
import streamlit as st

import importlib

from database import db_manager as db
from services import notification_service as ns
from ui import auth
from ui.common import BRAND, conn


class _Lazy:
    def __init__(self, name): self._n, self._m = name, None
    def __getattr__(self, item):
        if self._m is None:
            self._m = importlib.import_module(self._n)
        return getattr(self._m, item)


re_ = _Lazy("optimization.reallocation_engine")
aps = _Lazy("services.application_service")
_ev = _Lazy("reports.evaluation_pdf")
_cm = _Lazy("ui.common")


def evaluation_pdf(*a, **k): return _ev.evaluation_pdf(*a, **k)
def allotment_letter_pdf(*a, **k): return _cm.allotment_letter_pdf(*a, **k)
def application_receipt_pdf(*a, **k): return _cm.application_receipt_pdf(*a, **k)

NAV_DASHBOARD, NAV_APPLY, NAV_MYAPP, NAV_RESULT, NAV_WITHDRAW, NAV_APPEAL, NAV_NOTIF, NAV_DOCS = (
    "🏠 Dashboard", "📝 Apply Now", "📄 My Application", "🎓 Admission Result", "↩️ Withdrawal", "⚖️ Appeal", "🔔 Notifications", "⬇️ Downloads")
NAV_OPTIONS = [NAV_DASHBOARD, NAV_APPLY, NAV_MYAPP, NAV_RESULT, NAV_WITHDRAW, NAV_APPEAL, NAV_NOTIF, NAV_DOCS]


def goto(section: str) -> None:
    st.session_state["student_nav"] = section


PORTAL_CSS = """
<style>
.sw-card { border-radius:18px; padding:22px 24px; margin:6px 0 14px; border:1px solid rgba(15,23,42,.08); background:#fff; box-shadow:0 8px 24px rgba(11,31,58,.06); }
.sw-card.ok { background:linear-gradient(135deg,#ECFDF5,#F0FDF4); border-color:#A7F3D0; } .sw-card.warn { background:linear-gradient(135deg,#FFFBEB,#FEF3C7); border-color:#FDE68A; }
.sw-card.info { background:linear-gradient(135deg,#EFF6FF,#EEF2FF); border-color:#BFDBFE; } .sw-card.bad { background:#FEF2F2; border-color:#FECACA; }
.sw-card h3 { margin:0 0 6px; font-weight:800; } .sw-card p { margin:0; color:#475569; }
.sw-seat { font-size:1.6rem; font-weight:900; color:#065F46; margin:6px 0; }
.sw-step { display:flex; gap:12px; align-items:center; margin:6px 0; color:#334155; }
.sw-step .dot { width:26px; height:26px; border-radius:50%; display:grid; place-items:center; font-weight:800; font-size:.8rem; color:#fff; background:#94A3B8; }
.sw-step .dot.done { background:#059669; } .sw-step .dot.now { background:#F59E0B; }
.sw-notif { border-left:4px solid #0B1F3A; background:#fff; padding:10px 14px; border-radius:10px; margin-bottom:8px; box-shadow:0 4px 14px rgba(11,31,58,.05); }
.sw-notif small { color:#64748B; }
</style>
"""


def _render_dynamic_fields(schema):
    out = {}
    for f in schema:
        label = f["label"] + (" *" if f["required"] else "")
        key = f"dyn_{f['field_key']}"
        if f["field_type"] == "select":
            out[f["field_key"]] = st.selectbox(label, [""] + f["options"], key=key) or None
        else:
            v = st.text_input(label, key=key, placeholder="e.g. 0" if f["field_type"] == "number" else "")
            out[f["field_key"]] = v.strip() if v and v.strip() else None
    return out


def _eligibility_feedback(c, a):
    """Explain exactly why an application is ineligible (or which ranked programs it qualifies for)."""
    if a["eligibility_status"] != "ineligible":
        return
    details = aps.ineligibility_details(c, a["id"])
    if not details:
        st.error("**Not eligible.** Your application does not qualify for any program you ranked. Contact the admissions office."); return
    lines = [f"**#{rk} {code}** — " + ("; ".join(reasons) if reasons else "eligible") for rk, code, reasons in details]
    st.error(f"**Not eligible for any ranked program** (entrance score {a['score']}, track {a['track']}). Program-by-program reasons:\n\n- " + "\n- ".join(lines)
             + "\n\nYou may raise an **Appeal** or contact the admissions office if you believe this is incorrect.")


def _doc_preview(rel_path, title):
    st.markdown(f"**{title}**")
    path = db.resolve_document(rel_path)
    if rel_path and path is None:
        st.caption(f"`{rel_path}` · recorded (simulated seed file, not on disk)"); return
    if path is None:
        st.caption("not uploaded"); return
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        st.markdown(f'<iframe src="data:application/pdf;base64,{base64.b64encode(data).decode()}" width="100%" height="300"></iframe>', unsafe_allow_html=True)
    else:
        try:
            st.image(data, width=300)
        except Exception:
            st.warning("Image could not be rendered. Use the download button.")
    st.download_button(f"Download {title}", data, file_name=path.name, key=f"dl_{title}_{path.name}")


def _status(c, a):
    seat = db.current_assignment_for(c, a["id"])
    if a["status"] != "active":
        return "Withdrawn", "warn", "Your application has been withdrawn. Your record is retained for audit.", seat
    if not db.has_applied(a):
        return "Action Required", "warn", "Your account is ready. Complete the educational application in **Apply Now** to enter the allocation.", seat
    if not (a["marksheet_path"] and a["scorecard_path"]):
        return "Action Required", "warn", "Your application is missing a document. Upload it under **My Application**.", seat
    if a["eligibility_status"] == "ineligible":
        return "Not Eligible", "bad", "You do not meet the eligibility floor of any program you ranked. Contact the admissions office.", seat
    if seat is None:
        return "Application Pending", "info", "Your application is complete and under review. Allocation has not been published yet.", seat
    if seat["program_id"] is None:
        return "Waitlisted", "warn", "The current allocation did not assign you a seat. Seats released by withdrawals are filled automatically.", seat
    if a["offer_status"] == "confirmed":
        return "Admission Confirmed", "ok", f"Your admission to **{seat['code']} — {seat['program_name']}** is confirmed.", seat
    return "Provisional Offer", "ok", f"You have been provisionally allotted **{seat['code']} — {seat['program_name']}**. Accept your offer under **Admission Result**.", seat


# ---------------------------------------------------------------- Dashboard
def render_dashboard(c, a):
    content = db.get_site_content(c)
    label, cls, detail, seat = _status(c, a)
    applied = db.has_applied(a)
    st.subheader(f"Welcome, {a['name']}!")
    if not applied:
        st.markdown("Please navigate to **Apply Now** to submit your documents and program preferences.")
    for r in db.load_announcements(c, audience="students").head(3).itertuples():
        st.info(f"**{r.title}** · {r.body}")
    st.markdown(f"<div class='sw-card {cls}'><h3>Status: {label}</h3><p>{detail}</p></div>", unsafe_allow_html=True)
    _eligibility_feedback(c, a)
    b1, b2, b3, _ = st.columns([1, 1, 1, 1])
    b1.button("Go to Apply Now →" if not applied else "My application", type="primary" if not applied else "secondary", key="dash_go_apply",
              on_click=goto, args=(NAV_APPLY if not applied else NAV_MYAPP,), width="stretch")
    b2.button("Admission result →", key="dash_go_result", on_click=goto, args=(NAV_RESULT,), width="stretch")
    b3.button("Notifications", key="dash_go_notif", on_click=goto, args=(NAV_NOTIF,), width="stretch")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Application ID", db.app_id(a["id"]) if applied else "—")
    k2.metric("Application", "Submitted" if applied else "Not started")
    k3.metric("Eligibility", a["eligibility_status"].title())
    k4.metric("Selected program", seat["code"] if seat and seat["program_id"] else "—")
    st.markdown("#### Application tracking")
    stages = aps.tracking(c, a) or [("Application Submitted", False)]
    st.markdown("".join(f"<div class='sw-step'><div class='dot {'done' if done else ''}'>{'✓' if done else i+1}</div>{name}</div>" for i, (name, done) in enumerate(stages)), unsafe_allow_html=True)
    unread = int((db.load_notifications(c, a["id"]).pipe(lambda d: d[(d.channel == "in_app") & d.read_at.isna()])).shape[0])
    if unread:
        st.caption(f"🔔 {unread} unread notification(s)")
    with st.expander("How the application works"):
        st.markdown("1. Prepare your 12th marksheet and entrance scorecard (PDF/PNG/JPG, ≤ 8 MB).\n2. Submit the application with your score, track and ranked programs.\n"
                    "3. Track eligibility verification and allocation here.\n4. Accept your provisional offer under Admission Result and download your letter.")
    with st.expander("About the institute"):
        st.write(content.get("about_us", "")); st.caption(content.get("contact_info", ""))


# ---------------------------------------------------------------- Apply Now
def render_apply(c, a):
    if db.has_applied(a):
        st.success(f"Your application **{db.app_id(a['id'])}** is submitted. See **My Application** for details.")
        st.button("Open My Application", key="apply_open_myapp", on_click=goto, args=(NAV_MYAPP,))
        return
    if a["status"] != "active":
        st.warning("This account is withdrawn."); return
    programs = db.load_programs(c)
    programs = programs[programs.is_open.fillna(1).astype(int) == 1] if "is_open" in programs else programs
    schema = db.load_form_schema(c)
    max_prefs = int(db.get_setting(c, "max_preferences", "5"))
    st.markdown("#### Educational application")
    st.caption(f"Fields marked * are required. Rank up to {max_prefs} programs. Both documents are mandatory.")
    with st.expander("Programs and eligibility"):
        show = programs[["code", "name", "capacity", "min_score", "required_track", "duration"]].rename(columns={"code": "Code", "name": "Program", "capacity": "Seats", "min_score": "Min score", "required_track": "Track required", "duration": "Duration"})
        show["Track required"] = show["Track required"].fillna("Any"); st.dataframe(show, hide_index=True, width="stretch")
    options = [f"{r.code} — {r.name}" for r in programs.itertuples()]
    wanted = st.session_state.pop("apply_intent_program", None)
    if wanted and "apply_prefs" not in st.session_state:
        pre = [o for o in options if o.split(" — ")[0] == wanted]
        if pre:
            st.session_state["apply_prefs"] = pre
            st.info(f"**{wanted}** has been placed as your first preference. Add more programs below in order of preference.")
    # Every input lives inside ONE form: file uploads no longer trigger reruns that clear the other fields,
    # and each widget has a permanent key so values persist in session state until submission.
    with st.form("application_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        score = c1.slider("Entrance score *", 0, 100, 70, key="apply_score")
        track = c2.selectbox("Your track *", db.TRACKS, key="apply_track")
        dyn = {}
        if schema:
            st.markdown("**Additional details**")
            cols = st.columns(2)
            for idx, f in enumerate(schema):
                with cols[idx % 2]:
                    dyn.update(_render_dynamic_fields([f]))
        ranked = st.multiselect(f"Rank up to {max_prefs} programs in order of preference *", options, max_selections=max_prefs, key="apply_prefs")
        st.markdown("**Mandatory documents** (PDF, PNG or JPG, max 8 MB each)")
        u1, u2 = st.columns(2)
        marksheet = u1.file_uploader("12th Board Marksheet *", type=["pdf", "png", "jpg", "jpeg"], key="up_marksheet")
        scorecard = u2.file_uploader("CUET PG / Entrance Exam Scorecard *", type=["pdf", "png", "jpg", "jpeg"], key="up_scorecard")
        submitted = st.form_submit_button("Submit application", type="primary", width="stretch")
    if not submitted:
        return
    problems = db.validate_form_response(schema, dyn)
    if not ranked: problems.append("Rank at least one program")
    if marksheet is None: problems.append("12th Board Marksheet upload is mandatory")
    if scorecard is None: problems.append("Entrance Exam Scorecard upload is mandatory")
    if problems:
        st.error("Please fix:\n\n- " + "\n- ".join(problems)); return
    code_to_id = dict(zip(programs.code, programs.id))
    ids = [int(code_to_id[o.split(" — ")[0]]) for o in ranked]
    clean = {f["field_key"]: (float(dyn[f["field_key"]]) if f["field_type"] == "number" else dyn[f["field_key"]]) for f in schema if dyn.get(f["field_key"]) is not None}
    try:
        db.save_document(c, a["id"], "marksheet", marksheet.name, marksheet.getvalue())
        db.save_document(c, a["id"], "scorecard", scorecard.name, scorecard.getvalue())
        db.submit_application(c, a["id"], score=score, track=track, ranked_program_ids=ids, form_data=clean)
        elig = aps.verify_eligibility(c, a["id"])
    except ValueError as e:
        st.error(f"Submission rejected: {e}"); return
    res = ns.notify(c, a["id"], "application_submitted", {"n_prefs": str(len(ids))}, dedupe="applied")
    if elig == "eligible":
        ns.notify(c, a["id"], "eligibility_verified", dedupe="eligible")
    st.toast(f"📧 Email sent to {a['email']}: Application Received & Under Review!" if res.get("email") == "sent" else f"Application {db.app_id(a['id'])} received · confirmation delivered in your portal", icon="✅")
    st.success(f"**Application ID {db.app_id(a['id'])}**\n\n📧 Receipt{' emailed to ' + a['email'] if res.get('email') == 'sent' else ' (email delivery not configured; shown here)'}: "
               f"Dear {a['name']}, your application with {len(ids)} ranked program(s) and both documents has been received and is under review.")
    st.balloons()
    st.button("Back to Dashboard", key="after_apply", on_click=goto, args=(NAV_DASHBOARD,))


# ---------------------------------------------------------------- My Application
def render_my_application(c, a):
    if not db.has_applied(a):
        st.warning("You have not submitted an application yet."); st.button("Apply Now", key="myapp_go_apply", on_click=goto, args=(NAV_APPLY,)); return
    prefs = db.load_preferences(c); mine = prefs[prefs.applicant_id == a["id"]]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Application ID", db.app_id(a["id"])); k2.metric("Submitted", str(a["applied_at"])[:16]); k3.metric("Eligibility", a["eligibility_status"].title()); k4.metric("Status", a["offer_status"].title() if a["offer_status"] != "none" else "In process")
    _eligibility_feedback(c, a)
    l, r = st.columns(2, gap="large")
    with l:
        st.markdown("#### Submitted details")
        st.write(f"Entrance score **{a['score']}** · Track **{a['track']}**")
        st.write("Preferences: " + " › ".join(f"#{row.rank} {row.code}" for row in mine.itertuples()))
        data = json.loads(a["form_data"] or "{}")
        for f in db.load_form_schema(c):
            st.write(f"{f['label']}: {data.get(f['field_key'], '—')}")
        st.markdown("#### Document status")
        st.write(("✅" if a["marksheet_path"] else "❌") + " 12th Board Marksheet   " + ("✅" if a["scorecard_path"] else "❌") + " Entrance Scorecard")
    with r:
        _doc_preview(a["marksheet_path"], "12th Board Marksheet"); _doc_preview(a["scorecard_path"], "Entrance Exam Scorecard")
        with st.expander("Upload / replace a document"):
            kind = st.selectbox("Which document", ["marksheet", "scorecard"], format_func=lambda k: db.DOC_KINDS[k], key="rep_kind")
            up = st.file_uploader("File", type=["pdf", "png", "jpg", "jpeg"], key="replace_doc")
            if up is not None and st.button("Upload", key="rep_btn"):
                try:
                    db.save_document(c, a["id"], kind, up.name, up.getvalue()); st.toast("Document saved", icon="📎"); st.rerun()
                except ValueError as e:
                    st.error(str(e))


# ---------------------------------------------------------------- Admission Result
def render_result(c, a):
    st.markdown("#### My admission result")
    if not db.has_applied(a):
        st.warning("You have not submitted an application yet."); return
    run = db.get_current_run(c); seat = db.current_assignment_for(c, a["id"])
    if run is None or seat is None:
        st.markdown("<div class='sw-card info'><h3>Pending Allocation</h3><p>Allocation is in progress. You will be notified when it is published.</p></div>", unsafe_allow_html=True); return
    if seat["program_id"] is None:
        st.markdown("<div class='sw-card warn'><h3>Waitlisted</h3><p>No seat was allotted in the current round. Your ranked programs were full or you did not meet their eligibility floor. "
                    "Seats released by withdrawals are filled automatically and you will be notified. You may also submit an appeal.</p></div>", unsafe_allow_html=True); return
    confirmed = a["offer_status"] == "confirmed"
    st.markdown(f"<div class='sw-card ok'><h3>{'✅ Admission Confirmed' if confirmed else '🎉 Provisional Offer'}</h3><div class='sw-seat'>{seat['code']} — {seat['program_name']}</div>"
                f"<p>Allotted against your preference #{seat['rank_obtained']} · allocation version #{run['id']}.</p></div>", unsafe_allow_html=True)
    st.markdown(f"**Why this program?** It is the highest-ranked program on your list for which you were eligible and a seat was available under the allocation policy in force.")
    if not confirmed:
        st.caption(f"Accept within {db.get_setting(c, 'offer_accept_days', '7')} days of the offer to confirm your admission.")
        if st.button("Accept offer and confirm admission", type="primary", key="accept_offer"):
            re_.confirm_offer(c, a["id"]); st.toast("Admission confirmed", icon="🎓"); st.rerun()
    st.download_button("⬇ Allotment letter (PDF)", allotment_letter_pdf(c, a["id"]), f"allotment_{db.app_id(a['id'])}.pdf", "application/pdf", key="dl_allotment")


# ---------------------------------------------------------------- Withdrawal
def render_withdrawal(c, a):
    st.markdown("#### Withdrawal request")
    if a["status"] != "active":
        st.info("Your application is already withdrawn."); return
    if not db.has_applied(a):
        st.warning("Nothing to withdraw yet."); return
    pending = db.load_withdrawals(c); mine = pending[pending.applicant_id == a["id"]]
    if len(mine):
        st.dataframe(mine[["requested_at", "reason", "status", "decided_at"]], hide_index=True, width="stretch")
    if len(mine) and (mine.status == "requested").any():
        st.info("Your request is awaiting authorisation by the admissions office."); return
    st.warning("Withdrawing releases your seat (if any) to the next qualifying applicant. This requires authorisation by the admissions office and cannot be undone by you.")
    with st.form("withdraw_form"):
        reason = st.text_area("Reason", key="wd_reason_student", height=90)
        ok = st.form_submit_button("Request withdrawal", type="primary")
    if ok:
        if len(reason.strip()) < 5:
            st.error("Please give a short reason."); return
        db.request_withdrawal(c, a["id"], reason); ns.notify(c, a["id"], "withdrawal_requested", dedupe=f"wd_req:{a['id']}")
        st.toast("Withdrawal request submitted", icon="↩️"); st.rerun()


# ---------------------------------------------------------------- Appeal
def render_appeal(c, a):
    st.markdown("#### Appeal for a different program")
    if not db.has_applied(a):
        st.warning("Submit an application first."); return
    if db.get_current_run(c) is None:
        st.info("Appeals open once the allocation is published."); return
    seat = db.current_assignment_for(c, a["id"]); programs = db.load_programs(c)
    cur = f"{seat['code']} — {seat['program_name']}" if seat and seat["program_id"] else "Unassigned / waitlisted"
    st.write(f"Current allocation: **{cur}**")
    df = aps.load_appeals_full(c); mine = df[df.applicant_id == a["id"]]
    if len(mine):
        st.markdown("**Your appeals**")
        st.dataframe(mine[["created_at", "requested", "reason", "decision", "decided_at"]].rename(columns={"decision": "status"}), hide_index=True, width="stretch")
    if len(mine) and (mine.decision == "submitted").any():
        st.info("Your appeal is awaiting evaluation."); return
    prefs = db.load_preferences(c); ranked = prefs[prefs.applicant_id == a["id"]].program_id.tolist()
    opts = {f"{r.code} — {r.name}" + ("" if r.id in ranked else " (not in your ranked list)"): int(r.id) for r in programs.itertuples() if not (seat and seat["program_id"] == r.id)}
    with st.form("appeal_form"):
        target = st.selectbox("Requested program", list(opts), key="appeal_target")
        reason = st.text_area("Reason for the appeal", key="appeal_reason", height=90)
        ok = st.form_submit_button("Submit appeal", type="primary")
    if ok:
        if len(reason.strip()) < 10:
            st.error("Please explain your appeal in at least a sentence."); return
        try:
            aps.submit_student_appeal(c, a["id"], opts[target], reason); st.toast("Appeal submitted", icon="⚖️"); st.rerun()
        except ValueError as e:
            st.error(str(e))


# ---------------------------------------------------------------- Notifications
def render_notifications(c, a):
    st.markdown("#### Notifications")
    df = db.load_notifications(c, a["id"]); inapp = df[df.channel == "in_app"]
    if inapp.empty:
        st.info("No notifications yet.")
    for r in inapp.itertuples():
        st.markdown(f"<div class='sw-notif'><b>{r.subject}</b><br>{r.body}<br><small>{r.created_at}{' · new' if pd.isna(r.read_at) else ''}</small></div>", unsafe_allow_html=True)
    db.mark_notifications_read(c, a["id"])
    ext = df[df.channel != "in_app"]
    if len(ext):
        with st.expander("Email / WhatsApp delivery log"):
            st.dataframe(ext[["created_at", "channel", "subject", "status", "provider_response"]], hide_index=True, width="stretch")


# ---------------------------------------------------------------- Downloads
def render_downloads(c, a):
    st.markdown("#### Downloads")
    st.caption("Each report contains only your own information.")
    if db.has_applied(a):
        st.download_button("⬇ Application receipt (PDF)", application_receipt_pdf(c, a["id"]), f"receipt_{db.app_id(a['id'])}.pdf", "application/pdf", key="dl_receipt", width="stretch")
        st.download_button("⬇ Admission evaluation report (PDF)", evaluation_pdf(c, a["id"]), f"evaluation_{db.app_id(a['id'])}.pdf", "application/pdf", key="dl_eval", width="stretch")
        if db.get_current_run(c):
            st.download_button("⬇ Allocation result / allotment letter (PDF)", allotment_letter_pdf(c, a["id"]), f"allotment_{db.app_id(a['id'])}.pdf", "application/pdf", key="dl_allot2", width="stretch")
    else:
        st.info("Reports become available after you submit your application.")
    for rel, title in ((a["marksheet_path"], "12th Board Marksheet"), (a["scorecard_path"], "Entrance Exam Scorecard")):
        path = db.resolve_document(rel)
        if path is not None:
            st.download_button(f"⬇ {title}", path.read_bytes(), path.name, key=f"dl_{title}", width="stretch")


# ---------------------------------------------------------------- entry
def render_my_portal(c, aid: int) -> None:
    a = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    content = db.get_site_content(c)
    st.markdown(PORTAL_CSS, unsafe_allow_html=True)
    intent = st.session_state.pop("post_login_intent", None)
    apply_intent = bool(st.session_state.pop("apply_intent", False)) or intent == "apply"
    if apply_intent and not db.has_applied(a):
        st.session_state["student_nav"] = NAV_APPLY   # deep link: land on Apply Now once, then normal navigation resumes
    elif st.session_state.get("student_nav") not in NAV_OPTIONS:
        st.session_state["student_nav"] = NAV_DASHBOARD
    with st.sidebar:
        st.markdown("#### Student menu")
        section = st.radio("Student menu", NAV_OPTIONS, key="student_nav", label_visibility="collapsed")
    st.markdown(f"<h1 style='margin-bottom:0'>{content.get('institute_name', BRAND)}</h1><p style='color:gray;margin-top:4px'>Student portal · {BRAND} · {section}</p>", unsafe_allow_html=True)
    {NAV_DASHBOARD: render_dashboard, NAV_APPLY: render_apply, NAV_MYAPP: render_my_application, NAV_RESULT: render_result,
     NAV_WITHDRAW: render_withdrawal, NAV_APPEAL: render_appeal, NAV_NOTIF: render_notifications, NAV_DOCS: render_downloads}[section](c, a)


def render() -> None:
    c = conn()
    if auth.current_role() == auth.ROLE_STUDENT and auth.current_student_id():
        render_my_portal(c, auth.current_student_id())
