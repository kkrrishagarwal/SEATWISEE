"""Student portal — eight sections in the SEATWISEE purple design system. Shows ONLY the signed-in student's own data.

Presentation only: every value comes from the student's own records via database/db_manager and services.*;
all submissions call the same service functions as before (validation, secure uploads, notifications unchanged).
"""
from __future__ import annotations

import base64
import importlib
import json

import pandas as pd
import streamlit as st

from database import db_manager as db
from services import notification_service as ns
from ui import auth
from ui import design as ds
from ui.common import BRAND, conn
from ui.design import esc


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
    ":material/home: Dashboard", ":material/edit_square: Apply Now", ":material/description: My Application", ":material/school: Admission Result",
    ":material/undo: Withdrawal", ":material/balance: Appeal", ":material/notifications: Notifications", ":material/download: Downloads")
NAV_OPTIONS = [NAV_DASHBOARD, NAV_APPLY, NAV_MYAPP, NAV_RESULT, NAV_WITHDRAW, NAV_APPEAL, NAV_NOTIF, NAV_DOCS]
LOGO = "app/static/images/logo.png"


def goto(section: str) -> None:
    st.session_state["student_nav"] = section


def _plain(nav: str) -> str:
    return nav.split(" ", 1)[1] if nav.startswith(":material/") else nav


def _s(v) -> str:
    """String for display; pandas NaN/None become ''."""
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


# ---------------------------------------------------------------- shared helpers
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


def _doc_row(title, path, rel):
    state = "Uploaded" if path is not None else ("Recorded (seed record)" if rel else "Not uploaded")
    variant = "ok" if path is not None else ("info" if rel else "bad")
    st.html(f"<div class='sw-doc'><span class='ic'>{ds.ICONS['file']}</span><div><b>{esc(title)}</b><small>{esc(path.name) if path else esc(state)}</small></div>"
            f"<span style='margin-left:auto'>{ds.pill(state.split(' (')[0], variant)}</span></div>")


def _doc_preview(rel_path, title):
    path = db.resolve_document(rel_path)
    _doc_row(title, path, rel_path)
    if path is None:
        return
    data = path.read_bytes()
    if path.suffix.lower() == ".pdf":
        st.markdown(f'<iframe src="data:application/pdf;base64,{base64.b64encode(data).decode()}" width="100%" height="300" style="border-radius:12px;border:1px solid #E5E7EB"></iframe>', unsafe_allow_html=True)
    else:
        try:
            st.image(data, width="stretch")
        except Exception:
            st.caption("Preview unavailable for this file.")
    st.download_button(f"Download {title}", data, file_name=path.name, key=f"dl_{title}_{path.name}", icon=":material/download:")


def _status(c, a):
    """(label, variant, detail, seat) — the single source of truth for the student's current state."""
    seat = db.current_assignment_for(c, a["id"]) if db.has_applied(a) else None
    if a["status"] != "active":
        return "Withdrawn", "bad", "Your application has been withdrawn. Contact the admissions office if this is unexpected.", seat
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


def _journey(a, seat):
    """Real progress steps for the progress card (no arbitrary percentages)."""
    applied = db.has_applied(a)
    docs = bool(a["marksheet_path"] and a["scorecard_path"])
    checked = a["eligibility_status"] in ("eligible", "ineligible")
    seated = seat is not None and seat["program_id"] is not None
    return [("Account created", True), ("Application submitted", applied), ("Documents uploaded", applied and docs),
            ("Eligibility checked", applied and checked), ("Allocation published", seat is not None),
            ("Seat allotted", seated), ("Offer accepted", a["offer_status"] == "confirmed")]


def _offer_deadline(c):
    run = db.get_current_run(c)
    if run is None:
        return None, None
    days = int(db.get_setting(c, "offer_accept_days", "7"))
    return days, pd.Timestamp(run["created_at"]) + pd.Timedelta(days=days)


def _up_next(c, a, label, seat):
    """Most relevant pending action → (title, text, button label, target section, deadline text or '')."""
    if label == "Withdrawn":
        return "No further action", "Your application is withdrawn.", "View notifications", NAV_NOTIF, ""
    if not db.has_applied(a):
        return "Complete your admission application", "Submit your entrance score, track, ranked programs and both mandatory documents.", "Apply Now", NAV_APPLY, ""
    if not (a["marksheet_path"] and a["scorecard_path"]):
        return "Upload missing documents", "Both the 12th marksheet and the entrance scorecard are mandatory for allocation.", "Open My Application", NAV_MYAPP, ""
    if label == "Not Eligible":
        return "Review your eligibility result", "See the program-by-program reasons and raise an appeal if something is wrong.", "Open My Application", NAV_MYAPP, ""
    if seat is None:
        return "Wait for the allocation", "Your application is complete. You will be notified when the admissions office publishes the allocation.", "Track application", NAV_MYAPP, ""
    if seat["program_id"] is None:
        return "You are on the waitlist", "Seats released by withdrawals are refilled automatically. You may also appeal for a specific program.", "Open Appeal", NAV_APPEAL, ""
    if a["offer_status"] != "confirmed":
        _, deadline = _offer_deadline(c)
        left = (deadline - pd.Timestamp.now()).days if deadline is not None else None
        dl = (f"Accept by {deadline:%d %b %Y} · {max(left, 0)} day(s) left") if deadline is not None else ""
        return "Accept your provisional offer", f"Confirm your seat in {seat['code']} — {seat['program_name']} and download the allotment letter.", "Open Admission Result", NAV_RESULT, dl
    return "Admission confirmed", "Download your allotment letter and keep an eye on announcements for reporting instructions.", "Downloads", NAV_DOCS, ""


# ---------------------------------------------------------------- Dashboard
def render_dashboard(c, a):
    content = db.get_site_content(c)
    label, cls, detail, seat = _status(c, a)
    applied = db.has_applied(a)
    unread = int((db.load_notifications(c, a["id"]).pipe(lambda d: d[(d.channel == "in_app") & d.read_at.isna()])).shape[0])
    chips = [(f"Status: {label}", cls)]
    if db.get_setting(c, "academic_session", ""):
        chips.append((f"Session {db.get_setting(c, 'academic_session', '')}", ""))
    ds.hero(f"Hello, {a['name'].split()[0] if a['name'] else 'Student'}!", ds.today_label(), "Welcome back. Here's your admission journey at a glance.",
            chips=chips, unread=unread, avatar=ds.initials(a["name"]))
    steps = _journey(a, seat)
    done = sum(1 for _, ok in steps if ok); nxt = next((n for n, ok in steps if not ok), "")
    with ds.card():
        ds.progress("Application Progress", done, len(steps), steps, next_label=nxt)
    el = a["eligibility_status"]; off = a["offer_status"]
    ds.stat_cards([
        {"icon": "file", "label": "Application Status", "value": "Submitted" if applied else "Not started", "variant": ""},
        {"icon": "check", "label": "Eligibility Status", "value": el.title(), "variant": "" if el == "eligible" else ("red" if el == "ineligible" else "lav")},
        {"icon": "award", "label": "Admission / Offer", "value": {"provisional": "Provisional", "confirmed": "Confirmed", "waitlisted": "Waitlisted"}.get(off, "—"),
         "variant": "green" if off == "confirmed" else ("amber" if off == "waitlisted" else "")},
        {"icon": "bell", "label": "Unread Notifications", "value": unread, "variant": "light"},
    ])
    _eligibility_feedback(c, a)
    left, right = st.columns([1.65, 1], gap="medium")
    with left:
        with ds.card():
            title, text, btn, target, dl = _up_next(c, a, label, seat)
            st.html(f"<div class='sw-card-title'>Up Next</div><div class='sw-upnext'><span class='ic'>{ds.ICONS['clock']}</span><div><h4>{esc(title)}</h4><p>{esc(text)}</p></div>"
                    f"{f'<span class=dl>{esc(dl)}</span>' if dl else ''}</div>")
            st.button(btn + " →", key="dash_upnext", type="primary", on_click=goto, args=(target,))
        with ds.card("Application Analytics", "Your own application at a glance"):
            prefs = db.load_preferences(c); n_prefs = int((prefs.applicant_id == a["id"]).sum())
            ndocs = int(bool(a["marksheet_path"])) + int(bool(a["scorecard_path"]))
            alloc = seat["code"] if seat and seat["program_id"] else ("Waitlisted" if seat else ("Pending" if applied else "—"))
            ds.facts([("Application", "Submitted" if applied else "Not submitted"), ("Ranked preferences", n_prefs if applied else "—"), ("Documents", f"{ndocs}/2"),
                      ("Eligibility", el.title()), ("Allocation", alloc)])
    with right:
        with ds.card("Announcements", icon="bell"):
            ann = db.load_announcements(c, audience="students")
            if ann.empty:
                st.caption("No active announcements.")
            else:
                st.html("<ul class='sw-list'>" + "".join(f"<li><b>{esc(r.title)}</b>{esc(r.body)}<br><small>{esc(str(r.created_at)[:16])}</small></li>" for r in ann.head(4).itertuples()) + "</ul>")
        with ds.card("Quick links"):
            st.button("My Application", key="dash_go_apply", on_click=goto, args=(NAV_MYAPP if applied else NAV_APPLY,), width="stretch")
            st.button("Admission result", key="dash_go_result", on_click=goto, args=(NAV_RESULT,), width="stretch")
            st.button("Notifications", key="dash_go_notif", on_click=goto, args=(NAV_NOTIF,), width="stretch")
    programs = db.load_programs(c)
    if "is_open" in programs:
        programs = programs[programs.is_open.fillna(1).astype(int) == 1]
    if len(programs):
        cur = db.get_current_assignment_map(c)
        with ds.card("Programs open for admission", f"{len(programs)} program(s) accepting applications this session", icon="cap"):
            cells = []
            for r in programs.itertuples():
                taken = sum(1 for p in cur.values() if p == int(r.id)); seats = f"{taken}/{int(r.capacity)} seats allotted" if cur else f"{int(r.capacity)} seats"
                cells.append(f"<div class='sw-prog-card'><div class='code'>{esc(r.code)}</div><h4>{esc(r.name)}</h4><p>{esc(_s(r.department))}{' · ' + esc(_s(r.duration)) if _s(r.duration) else ''}</p>"
                             f"<div class='meta'>{ds.pill('Track: ' + (_s(r.required_track) or 'Any'))}{ds.pill('Min score ' + str(int(r.min_score)), 'muted')}{ds.pill(seats, 'info')}</div></div>")
            st.html(f"<div class='sw-progs'>{''.join(cells)}</div>")
    with st.expander("How the application works"):
        st.markdown("1. Prepare your 12th marksheet and entrance scorecard (PDF/PNG/JPG, ≤ 8 MB).\n2. Submit the application with your score, track and ranked programs.\n"
                    "3. Track eligibility verification and allocation here.\n4. Accept your provisional offer under Admission Result and download your letter.")
    with st.expander("About the institute"):
        st.write(content.get("about_us", "")); st.caption(content.get("contact_info", ""))


# ---------------------------------------------------------------- Apply Now
def render_apply(c, a):
    if db.has_applied(a):
        with ds.card("Application submitted", icon="check"):
            st.success(f"Your application **{db.app_id(a['id'])}** is submitted. See **My Application** for details.")
            st.button("Open My Application", key="apply_open_myapp", on_click=goto, args=(NAV_MYAPP,))
        return
    if a["status"] != "active":
        st.warning("This account is withdrawn."); return
    programs = db.load_programs(c)
    programs = programs[programs.is_open.fillna(1).astype(int) == 1] if "is_open" in programs else programs
    schema = db.load_form_schema(c)
    max_prefs = int(db.get_setting(c, "max_preferences", "5"))
    review = st.session_state.get("apply_review")
    ds.section("Educational application", f"Fields marked * are required · rank up to {max_prefs} programs · both documents are mandatory")
    ds.stepper(["Your details", "Program preferences", "Documents", "Review & submit"], 3 if review else 0)
    options = [f"{r.code} — {r.name}" for r in programs.itertuples()]
    wanted = st.session_state.pop("apply_intent_program", None)
    if wanted and "apply_prefs" not in st.session_state:
        pre = [o for o in options if o.split(" — ")[0] == wanted]
        if pre:
            st.session_state["apply_prefs"] = pre
            st.info(f"**{wanted}** has been placed as your first preference. Add more programs below in order of preference.")

    if review:
        # Final review before submission: nothing is written until "Confirm and submit".
        with ds.card("Review your application", "Check everything below. Use 'Edit answers' to change anything before submitting.", icon="check"):
            ds.facts([("Entrance score", review["score"]), ("Track", review["track"]), ("Ranked programs", len(review["ranked"])), ("Documents", "2/2")])
            st.markdown("**Preferences:** " + " › ".join(f"#{i + 1} {o}" for i, o in enumerate(review["ranked"])))
            for f in schema:
                st.markdown(f"**{f['label']}:** {review['dyn'].get(f['field_key']) or '—'}")
            st.markdown(f"**12th Board Marksheet:** {review['marksheet'].name} · **Entrance Scorecard:** {review['scorecard'].name}")
            b1, b2 = st.columns(2)
            confirm = b1.button("Confirm and submit application", type="primary", key="apply_confirm", width="stretch")
            if b2.button("Edit answers", key="apply_edit", width="stretch"):
                st.session_state.pop("apply_review", None); st.rerun()
        if confirm:
            _submit_application(c, a, programs, schema, review); return

    with ds.card("Programs and eligibility", "Minimum entrance score and required track for every program", icon="cap"):
        show = programs[["code", "name", "capacity", "min_score", "required_track", "duration"]].rename(columns={"code": "Code", "name": "Program", "capacity": "Seats", "min_score": "Min score", "required_track": "Track required", "duration": "Duration"})
        show["Track required"] = show["Track required"].fillna("Any"); st.dataframe(show, hide_index=True, width="stretch")
    holder = st.expander("Edit answers", expanded=False) if review else ds.card("Application form", "Everything is saved in one step; uploading a file does not clear your other answers.", icon="file")
    with holder:
        # Every input lives inside ONE form with permanent keys: file uploads cannot trigger reruns that clear other fields.
        with st.form("application_form", clear_on_submit=False):
            st.markdown("**1 · Your details**")
            c1, c2 = st.columns(2)
            score = c1.slider("Entrance score *", 0, 100, 70, key="apply_score")
            track = c2.selectbox("Your track *", db.TRACKS, key="apply_track")
            dyn = {}
            if schema:
                cols = st.columns(2)
                for idx, f in enumerate(schema):
                    with cols[idx % 2]:
                        dyn.update(_render_dynamic_fields([f]))
            st.markdown("**2 · Program preferences**")
            ranked = st.multiselect(f"Rank up to {max_prefs} programs in order of preference *", options, max_selections=max_prefs, key="apply_prefs")
            st.markdown("**3 · Mandatory documents** (PDF, PNG or JPG, max 8 MB each)")
            u1, u2 = st.columns(2)
            marksheet = u1.file_uploader("12th Board Marksheet *", type=["pdf", "png", "jpg", "jpeg"], key="up_marksheet")
            scorecard = u2.file_uploader("CUET PG / Entrance Exam Scorecard *", type=["pdf", "png", "jpg", "jpeg"], key="up_scorecard")
            if marksheet is not None: u1.caption(f"✅ {marksheet.name} · {marksheet.size / 1024:.0f} KB")
            if scorecard is not None: u2.caption(f"✅ {scorecard.name} · {scorecard.size / 1024:.0f} KB")
            submitted = st.form_submit_button("Review application", type="primary", width="stretch")
    if not submitted:
        return
    problems = db.validate_form_response(schema, dyn)
    if not ranked: problems.append("Rank at least one program")
    if marksheet is None: problems.append("12th Board Marksheet upload is mandatory")
    if scorecard is None: problems.append("Entrance Exam Scorecard upload is mandatory")
    for up in (marksheet, scorecard):
        if up is not None and up.size > 8 * 1024 * 1024: problems.append(f"{up.name} exceeds 8 MB")
    if problems:
        st.error("Please fix:\n\n- " + "\n- ".join(problems)); return
    st.session_state["apply_review"] = {"score": score, "track": track, "dyn": dyn, "ranked": ranked, "marksheet": marksheet, "scorecard": scorecard}
    st.rerun()


def _submit_application(c, a, programs, schema, review):
    code_to_id = dict(zip(programs.code, programs.id))
    ids = [int(code_to_id[o.split(" — ")[0]]) for o in review["ranked"]]
    dyn = review["dyn"]
    clean = {f["field_key"]: (float(dyn[f["field_key"]]) if f["field_type"] == "number" else dyn[f["field_key"]]) for f in schema if dyn.get(f["field_key"]) is not None}
    try:
        db.save_document(c, a["id"], "marksheet", review["marksheet"].name, review["marksheet"].getvalue())
        db.save_document(c, a["id"], "scorecard", review["scorecard"].name, review["scorecard"].getvalue())
        db.submit_application(c, a["id"], score=review["score"], track=review["track"], ranked_program_ids=ids, form_data=clean)
        elig = aps.verify_eligibility(c, a["id"])
    except ValueError as e:
        st.error(f"Submission rejected: {e}"); return
    st.session_state.pop("apply_review", None)
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
        with ds.card("No application yet", icon="file"):
            st.warning("You have not submitted an application yet."); st.button("Apply Now", key="myapp_go_apply", on_click=goto, args=(NAV_APPLY,))
        return
    prefs = db.load_preferences(c); mine = prefs[prefs.applicant_id == a["id"]].sort_values("rank")
    el = a["eligibility_status"]; off = a["offer_status"]
    ds.stat_cards([
        {"icon": "file", "label": "Application ID", "value": db.app_id(a["id"]), "variant": ""},
        {"icon": "clock", "label": "Submitted", "value": str(a["applied_at"])[:10], "variant": "light", "hint": str(a["applied_at"])[11:16]},
        {"icon": "check", "label": "Eligibility", "value": el.title(), "variant": "green" if el == "eligible" else ("red" if el == "ineligible" else "lav")},
        {"icon": "award", "label": "Offer status", "value": off.title() if off != "none" else "In process", "variant": "green" if off == "confirmed" else ("amber" if off == "waitlisted" else "lav")},
    ])
    _eligibility_feedback(c, a)
    l, r = st.columns(2, gap="medium")
    with l:
        with ds.card("Submitted details", icon="file"):
            ds.facts([("Entrance score", a["score"]), ("Track", a["track"]), ("Ranked programs", len(mine))])
            st.html("<ul class='sw-list'>" + "".join(f"<li>{ds.pill('#' + str(row.rank))} &nbsp;<b style='display:inline'>{esc(row.code)}</b></li>" for row in mine.itertuples()) + "</ul>")
            data = json.loads(a["form_data"] or "{}")
            for f in db.load_form_schema(c):
                st.markdown(f"**{f['label']}:** {data.get(f['field_key'], '—')}")
        with ds.card("Application tracking", icon="clock"):
            stages = aps.tracking(c, a)
            first_open = next((i for i, (_, d) in enumerate(stages) if not d), None)
            ds.timeline([(n, "completed" if d else ("in progress" if i == first_open else "pending"), "d" if d else ("n" if i == first_open else "")) for i, (n, d) in enumerate(stages)])
    with r:
        with ds.card("Documents", "Both documents are mandatory for allocation", icon="file"):
            _doc_preview(a["marksheet_path"], "12th Board Marksheet"); _doc_preview(a["scorecard_path"], "Entrance Exam Scorecard")
            with st.expander("Upload / replace a document"):
                kind = st.selectbox("Which document", ["marksheet", "scorecard"], format_func=lambda k: db.DOC_KINDS[k], key="rep_kind")
                up = st.file_uploader("File", type=["pdf", "png", "jpg", "jpeg"], key="replace_doc")
                if up is not None and st.button("Upload", key="rep_btn", type="primary"):
                    try:
                        db.save_document(c, a["id"], kind, up.name, up.getvalue()); st.toast("Document saved", icon="📎"); st.rerun()
                    except ValueError as e:
                        st.error(str(e))


# ---------------------------------------------------------------- Admission Result
def render_result(c, a):
    if a["status"] != "active":
        st.html("<div class='sw-result bad'><h3>Withdrawn</h3><p>Your application has been withdrawn and you are not part of the allocation.</p></div>"); return
    if not db.has_applied(a):
        st.html("<div class='sw-result info'><h3>No application yet</h3><p>Submit your application under Apply Now to take part in the allocation.</p></div>")
        st.button("Apply Now", key="res_go_apply", on_click=goto, args=(NAV_APPLY,)); return
    if a["eligibility_status"] == "ineligible":
        st.html("<div class='sw-result bad'><h3>Not Eligible</h3><p>Your application does not meet the eligibility floor of any program you ranked.</p></div>")
        _eligibility_feedback(c, a); return
    run = db.get_current_run(c); seat = db.current_assignment_for(c, a["id"])
    if run is None or seat is None:
        st.html("<div class='sw-result info'><h3>Pending Allocation</h3><p>Allocation is in progress. You will be notified when it is published.</p></div>"); return
    if seat["program_id"] is None:
        st.html("<div class='sw-result warn'><h3>Waitlisted</h3><p>No seat was allotted in the current round. Your ranked programs were full or you did not meet their eligibility floor. "
                "Seats released by withdrawals are filled automatically and you will be notified. You may also submit an appeal.</p></div>")
        st.button("Open Appeal", key="res_go_appeal", on_click=goto, args=(NAV_APPEAL,)); return
    confirmed = a["offer_status"] == "confirmed"
    days, deadline = _offer_deadline(c)
    st.html(f"<div class='sw-result ok'><h3>{'✅ Admission Confirmed' if confirmed else '🎉 Provisional Offer'}</h3><div class='seat'>{esc(seat['code'])} — {esc(seat['program_name'])}</div>"
            f"<p>Allotted against your preference <b>#{seat['rank_obtained']}</b> · allocation version <b>#{run['id']}</b> · published {esc(str(run['created_at'])[:16])}.</p></div>")
    ds.stat_cards([
        {"icon": "award", "label": "Preference rank received", "value": f"#{seat['rank_obtained']}", "variant": "lav"},
        {"icon": "layers", "label": "Allocation version", "value": f"#{run['id']}", "variant": "light"},
        {"icon": "clock", "label": "Offer acceptance window", "value": f"{days} days", "variant": "light", "hint": "accepted" if confirmed else f"until {deadline:%d %b %Y}"},
    ])
    with ds.card("Why this program?"):
        st.markdown("It is the highest-ranked program on your list for which you were eligible and a seat was available under the allocation policy in force. "
                    "Confirmed admissions are protected in later reallocations according to the institute's policy.")
    if not confirmed:
        st.caption(f"Accept within {days} days of the offer (by {deadline:%d %b %Y}) to confirm your admission.")
        if st.button("Accept offer and confirm admission", type="primary", key="accept_offer"):
            re_.confirm_offer(c, a["id"]); st.toast("Admission confirmed", icon="🎓"); st.rerun()
    st.download_button("Allotment letter (PDF)", allotment_letter_pdf(c, a["id"]), f"allotment_{db.app_id(a['id'])}.pdf", "application/pdf", key="dl_allotment", icon=":material/download:")


# ---------------------------------------------------------------- Withdrawal
def render_withdrawal(c, a):
    if a["status"] != "active":
        st.info("Your application is already withdrawn."); return
    if not db.has_applied(a):
        st.warning("Nothing to withdraw yet."); return
    pending = db.load_withdrawals(c); mine = pending[pending.applicant_id == a["id"]]
    l, r = st.columns([1.2, 1], gap="medium")
    with l:
        with ds.card("Request history", icon="clock"):
            if len(mine):
                st.html("<ul class='sw-list'>" + "".join(
                    f"<li><b>{esc(str(x.requested_at)[:16])} {ds.pill(x.status, {'requested': 'warn', 'approved': 'ok', 'rejected': 'bad'}.get(x.status, ''))}</b>{esc(x.reason)}"
                    f"{('<br><small>decided ' + esc(str(x.decided_at)[:16]) + '</small>') if x.decided_at else ''}</li>" for x in mine.itertuples()) + "</ul>")
            else:
                st.caption("No withdrawal requests so far.")
    with r:
        with ds.card("How it works", icon="alert"):
            st.markdown("- Submitting a request **does not** release your seat immediately.\n- Only an authorised administrator can approve it.\n"
                        "- On approval your seat (if any) is released and filled by the next qualifying applicant.\n- An approved withdrawal cannot be undone by you.")
    if len(mine) and (mine.status == "requested").any():
        st.info("Your request is awaiting authorisation by the admissions office."); return
    with ds.card("New withdrawal request", icon="file"):
        with st.form("withdraw_form"):
            reason = st.text_area("Reason", key="wd_reason_student", height=90, placeholder="Tell the admissions office why you are withdrawing")
            ok = st.form_submit_button("Request withdrawal", type="primary")
    if ok:
        if len(reason.strip()) < 5:
            st.error("Please give a short reason."); return
        db.request_withdrawal(c, a["id"], reason); ns.notify(c, a["id"], "withdrawal_requested", dedupe=f"wd_req:{a['id']}")
        st.toast("Withdrawal request submitted", icon="↩️"); st.rerun()


# ---------------------------------------------------------------- Appeal
def render_appeal(c, a):
    if not db.has_applied(a):
        st.warning("Submit an application first."); return
    if db.get_current_run(c) is None:
        st.info("Appeals open once the allocation is published."); return
    seat = db.current_assignment_for(c, a["id"]); programs = db.load_programs(c)
    cur = f"{seat['code']} — {seat['program_name']}" if seat and seat["program_id"] else "Unassigned / waitlisted"
    df = aps.load_appeals_full(c); mine = df[df.applicant_id == a["id"]]
    l, r = st.columns([1, 1.2], gap="medium")
    with l:
        with ds.card("Current allocation", icon="award"):
            st.html(f"<div style='font-size:1.3rem;font-weight:900;color:#5B21B6'>{esc(cur)}</div>" + (f"<p style='color:#64748B;margin:4px 0 0'>Preference #{seat['rank_obtained']}</p>" if seat and seat["program_id"] else ""))
        with ds.card("Appeal status", icon="clock"):
            if len(mine):
                last = mine.iloc[0]; decided = last.decision in ("accepted", "rejected")
                ds.timeline([("Submitted", str(last.created_at)[:16], "d"),
                             ("Evaluated by the admissions office", "counterfactual re-allocation" if last.decision != "submitted" else "pending", "d" if last.decision != "submitted" else "n"),
                             ("Decision", last.decision.title() if decided else "pending", "d" if decided else ("n" if last.decision == "evaluated" else ""))])
            else:
                st.caption("No appeal submitted yet.")
    with r:
        with ds.card("Previous appeals", icon="scale"):
            if len(mine):
                st.dataframe(mine[["created_at", "requested", "reason", "decision", "decided_at"]].rename(columns={"decision": "status"}), hide_index=True, width="stretch")
            else:
                st.caption("None.")
        with ds.card("Guidance", icon="alert"):
            st.markdown("- Only **one open appeal** at a time.\n- The office evaluates whether your request can be granted **without breaking capacity or eligibility rules**, and how many other applicants it would affect.\n- Explain your reason clearly; the decision is recorded and notified to you.")
    if len(mine) and (mine.decision == "submitted").any():
        st.info("Your appeal is awaiting evaluation."); return
    prefs = db.load_preferences(c); ranked = prefs[prefs.applicant_id == a["id"]].program_id.tolist()
    opts = {f"{r.code} — {r.name}" + ("" if r.id in ranked else " (not in your ranked list)"): int(r.id) for r in programs.itertuples() if not (seat and seat["program_id"] == r.id)}
    with ds.card("Submit an appeal", icon="file"):
        with st.form("appeal_form"):
            target = st.selectbox("Requested program", list(opts), key="appeal_target")
            reason = st.text_area("Reason for the appeal", key="appeal_reason", height=90, placeholder="At least one full sentence")
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
    df = db.load_notifications(c, a["id"]); inapp = df[df.channel == "in_app"]
    unread = int(inapp.read_at.isna().sum())
    ds.section("Inbox", f"{len(inapp)} message(s) · {unread} unread")
    if inapp.empty:
        st.info("No notifications yet.")
    for r in inapp.itertuples():
        new = pd.isna(r.read_at)
        st.html(f"<div class='sw-notif {'unread' if new else ''}'><div class='h'><b>{esc(r.subject)}</b>{ds.pill(str(r.event).replace('_', ' '), 'muted')}{ds.pill('new', 'ok') if new else ''}</div>"
                f"<p>{esc(r.body)}</p><small>{esc(str(r.created_at)[:16])}</small></div>")
    db.mark_notifications_read(c, a["id"])
    ext = df[df.channel != "in_app"]
    with ds.card("Email and WhatsApp delivery", "Statuses are the providers' real responses; nothing is shown as sent unless the provider accepted it", icon="mail"):
        if len(ext):
            ds.facts([("Email sent", int(((ext.channel == "email") & (ext.status == "sent")).sum())), ("WhatsApp sent", int(((ext.channel == "whatsapp") & (ext.status == "sent")).sum())),
                      ("Failed", int((ext.status == "failed").sum())), ("Not configured", int((ext.status == "not_configured").sum()))])
            with st.expander("Delivery log"):
                st.dataframe(ext[["created_at", "channel", "event", "subject", "status", "provider_response"]], hide_index=True, width="stretch")
        else:
            st.caption("No email or WhatsApp deliveries recorded for your account.")


# ---------------------------------------------------------------- Downloads
def render_downloads(c, a):
    applied = db.has_applied(a); run = db.get_current_run(c)
    seated = applied and run is not None and db.current_assignment_for(c, a["id"]) is not None
    l, r = st.columns(2, gap="medium")
    with l:
        with ds.card("Official documents", "Generated from your own records", icon="file"):
            items = [("Application receipt (PDF)", applied, lambda: application_receipt_pdf(c, a["id"]), f"receipt_{db.app_id(a['id'])}.pdf", "dl_receipt", "Available after you submit your application"),
                     ("Admission evaluation report (PDF)", applied, lambda: evaluation_pdf(c, a["id"]), f"evaluation_{db.app_id(a['id'])}.pdf", "dl_eval", "Available after you submit your application"),
                     ("Allotment letter (PDF)", seated, lambda: allotment_letter_pdf(c, a["id"]), f"allotment_{db.app_id(a['id'])}.pdf", "dl_allot2", "Available after the allocation is published")]
            for title, ok, make, fname, key, why in items:
                st.html(f"<div class='sw-doc'><span class='ic'>{ds.ICONS['file']}</span><div><b>{esc(title)}</b><small>{'Available now' if ok else why}</small></div>"
                        f"<span style='margin-left:auto'>{ds.pill('Ready' if ok else 'Not yet', 'ok' if ok else 'muted')}</span></div>")
                if ok:
                    st.download_button(f"Download {title}", make(), fname, "application/pdf", key=key, width="stretch", icon=":material/download:")
    with r:
        with ds.card("Your uploaded documents", icon="file"):
            for rel, title in ((a["marksheet_path"], "12th Board Marksheet"), (a["scorecard_path"], "Entrance Exam Scorecard")):
                path = db.resolve_document(rel)
                _doc_row(title, path, rel)
                if path is not None:
                    st.download_button(f"Download {title}", path.read_bytes(), path.name, key=f"dl_{title}", width="stretch", icon=":material/download:")


# ---------------------------------------------------------------- entry
def render_my_portal(c, aid: int) -> None:
    a = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    content = db.get_site_content(c)
    ds.inject()
    intent = st.session_state.pop("post_login_intent", None)
    apply_intent = bool(st.session_state.pop("apply_intent", False)) or intent == "apply"
    if apply_intent and not db.has_applied(a):
        st.session_state["student_nav"] = NAV_APPLY   # deep link: land on Apply Now once, then normal navigation resumes
    elif st.session_state.get("student_nav") not in NAV_OPTIONS:
        st.session_state["student_nav"] = NAV_DASHBOARD
    institute = content.get("institute_name", "Syntaxis Institute of Technology")
    with st.sidebar:
        ds.sidebar_brand(BRAND, institute, LOGO)
        st.html("<div class='sw-navhead'>Student portal</div>")
        section = st.radio("Student menu", NAV_OPTIONS, key="student_nav", label_visibility="collapsed")
        ds.sidebar_profile(a["name"], [f"{a['track']} track" if a["track"] else "Student", db.app_id(a["id"]) if db.has_applied(a) else a["email"], institute], auth.full_logout)
    if section != NAV_DASHBOARD:
        ds.hero(_plain(section), f"{institute} · {ds.today_label()}", avatar=ds.initials(a["name"]), overlap=False)
        st.html("<div style='height:18px'></div>")
    {NAV_DASHBOARD: render_dashboard, NAV_APPLY: render_apply, NAV_MYAPP: render_my_application, NAV_RESULT: render_result,
     NAV_WITHDRAW: render_withdrawal, NAV_APPEAL: render_appeal, NAV_NOTIF: render_notifications, NAV_DOCS: render_downloads}[section](c, a)


def render() -> None:
    c = conn()
    if auth.current_role() == auth.ROLE_STUDENT and auth.current_student_id():
        render_my_portal(c, auth.current_student_id())
    else:
        st.error("Please sign in as a student.")
