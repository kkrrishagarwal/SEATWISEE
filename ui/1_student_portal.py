"""Student portal — three sections: Home / Dashboard · Apply Now · Check Allotment Result.

Registration (account) happens on the gateway. The educational application — score, track,
admin-defined fields, ranked preferences and the two mandatory uploads — lives in "Apply Now".
"""
from __future__ import annotations

import base64
import json

import streamlit as st

from database import db_manager as db
from ui import auth
from ui.common import BRAND, allotment_letter_pdf, application_receipt_pdf, conn

NAV_DASHBOARD = "🏠 Dashboard"
NAV_APPLY = "📝 Apply Now"
NAV_RESULT = "🎓 Allotment Confirmation"
NAV_OPTIONS = [NAV_DASHBOARD, NAV_APPLY, NAV_RESULT]


def goto(section: str) -> None:
    """Programmatic navigation inside the portal (used by dashboard buttons and post-submit)."""
    st.session_state["student_nav"] = section


PORTAL_CSS = """
<style>
.sw-card { border-radius:18px; padding:22px 24px; margin:6px 0 14px; border:1px solid rgba(15,23,42,.08); background:#fff; box-shadow:0 8px 24px rgba(11,31,58,.06); }
.sw-card.ok { background:linear-gradient(135deg,#ECFDF5,#F0FDF4); border-color:#A7F3D0; }
.sw-card.warn { background:linear-gradient(135deg,#FFFBEB,#FEF3C7); border-color:#FDE68A; }
.sw-card.info { background:linear-gradient(135deg,#EFF6FF,#EEF2FF); border-color:#BFDBFE; }
.sw-card h3 { margin:0 0 6px; font-weight:800; }
.sw-card p { margin:0; color:#475569; }
.sw-seat { font-size:1.6rem; font-weight:900; color:#065F46; margin:6px 0; }
.sw-step { display:flex; gap:12px; align-items:center; margin:6px 0; color:#334155; }
.sw-step .dot { width:26px; height:26px; border-radius:50%; display:grid; place-items:center; font-weight:800; font-size:.8rem; color:#fff; background:#94A3B8; }
.sw-step .dot.done { background:#059669; } .sw-step .dot.now { background:#F59E0B; }
</style>
"""


# ---------------------------------------------------------------- helpers
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


def _doc_preview(rel_path, title):
    st.markdown(f"**{title}**")
    path = db.resolve_document(rel_path)
    if rel_path and path is None:
        st.caption(f"`{rel_path}` · recorded (simulated seed file, not on disk)")
        return
    if path is None:
        st.caption("not uploaded")
        return
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
    """(label, css-class, detail) describing where this student is in the journey."""
    seat = db.current_assignment_for(c, a["id"])
    if a["status"] != "active":
        return "Withdrawn", "warn", "Your application has been withdrawn. Contact the admissions office to reinstate it.", seat
    if not db.has_applied(a):
        return "Action Required", "warn", "Your account is ready. Complete the educational application in **Apply Now** to enter the allocation.", seat
    docs_ok = bool(a["marksheet_path"]) and bool(a["scorecard_path"])
    if not docs_ok:
        return "Action Required", "warn", "Your application is missing a document. Upload it in **Apply Now**.", seat
    if seat is None:
        return "Application Pending", "info", "Your application is complete and under review. Allocation has not been published yet.", seat
    if seat["program_id"] is None:
        return "Not Allotted", "warn", "The current allocation did not assign you a seat. You may appeal to the admissions office.", seat
    return "Seat Allotted", "ok", f"Congratulations — you hold a seat in **{seat['code']} — {seat['program_name']}**.", seat


# ---------------------------------------------------------------- A. Home / Dashboard
def render_dashboard(c, a) -> None:
    content = db.get_site_content(c)
    label, cls, detail, seat = _status(c, a)
    applied = db.has_applied(a)
    docs_ok = bool(a["marksheet_path"]) and bool(a["scorecard_path"])

    st.subheader(f"Welcome, {a['name']}!")
    if not applied:
        st.markdown("Please navigate to the **Apply Now** section to submit your documents and program preferences. "
                    "Your seat can only be allocated once your application is complete.")
    elif seat is None:
        st.markdown("Your application is in. We will publish the allotment here and notify you by email once the admissions office runs the allocation.")
    else:
        st.markdown("Your allotment has been published. Open **Allotment Confirmation** to view it and download your letter.")

    if content.get("announcements", "").strip():
        st.info(f"**Announcements** · {content['announcements']}")

    st.markdown(f"<div class='sw-card {cls}'><h3>Status: {label}</h3><p>{detail}</p></div>", unsafe_allow_html=True)

    b1, b2, _ = st.columns([1, 1, 2])
    if not applied:
        b1.button("Go to Apply Now →", type="primary", key="dash_go_apply", on_click=goto, args=(NAV_APPLY,), width="stretch")
    else:
        b1.button("View my application", key="dash_go_apply", on_click=goto, args=(NAV_APPLY,), width="stretch")
    b2.button("Check allotment →", key="dash_go_result", on_click=goto, args=(NAV_RESULT,), width="stretch")

    st.markdown("#### Your progress")
    steps = [("Account created", True, False), ("Application submitted", applied, not applied),
             ("Documents uploaded", applied and docs_ok, applied and not docs_ok),
             ("Allotment published", seat is not None, applied and docs_ok and seat is None)]
    st.markdown("".join(
        f"<div class='sw-step'><div class='dot {'done' if done else ('now' if now else '')}'>{'✓' if done else i+1}</div>{name}</div>"
        for i, (name, done, now) in enumerate(steps)), unsafe_allow_html=True)

    k1, k2, k3 = st.columns(3)
    k1.metric("Applicant ID", a["id"])
    k2.metric("Profile", "Complete" if a["phone"] and a["address"] else "Incomplete")
    k3.metric("Application", "Submitted" if applied else "Not started")

    st.markdown("#### How the application works")
    st.markdown(
        "1. **Prepare your documents.** You will need a scan or photo of your 12th Board Marksheet and your CUET PG / entrance exam scorecard (PDF, PNG or JPG, up to 8 MB each).\n"
        "2. **Fill in the Apply Now form.** Enter your entrance score and track, answer the college's additional questions, and rank up to five programs in order of preference. Your first choice carries the most weight.\n"
        "3. **Submit once.** You receive a confirmation email (simulated in this demo) and can download a receipt. Documents can be re-uploaded later if needed.\n"
        "4. **Wait for the allotment.** The admissions office runs the SEATWISEE engine, which assigns seats fairly by preference, eligibility and capacity. Check **Allotment Confirmation** for your result and letter."
    )
    with st.expander("Eligibility rules in brief"):
        progs = db.load_programs(c)
        for r in progs.itertuples():
            track = r.required_track if isinstance(r.required_track, str) and r.required_track else "any track"
            st.write(f"**{r.code}** {r.name}: minimum score {int(r.min_score)}, {track}, {int(r.capacity)} seats")
    with st.expander("About the institute"):
        st.write(content.get("about_us", ""))
        st.caption(content.get("contact_info", ""))
    with st.expander("My account details"):
        st.write(f"Email: {a['email']}")
        st.write(f"Phone: {a['phone'] or '—'}")
        st.write(f"Address: {a['address'] or '—'}")


# ---------------------------------------------------------------- B. Apply Now
def render_apply(c, a) -> None:
    programs = db.load_programs(c)
    schema = db.load_form_schema(c)

    if db.has_applied(a):
        st.success("Your educational application has been submitted and is under review.")
        prefs = db.load_preferences(c)
        mine = prefs[prefs.applicant_id == a["id"]]
        l, r = st.columns(2, gap="large")
        with l:
            st.markdown("#### Submitted details")
            st.write(f"Entrance score: **{a['score']}** · Track: **{a['track']}**")
            st.write("Ranking: " + " › ".join(f"#{row.rank} {row.code}" for row in mine.itertuples()))
            data = json.loads(a["form_data"] or "{}")
            for f in schema:
                st.write(f"{f['label']}: {data.get(f['field_key'], '—')}")
            st.caption(f"Submitted at {a['applied_at']}")
            st.download_button("⬇ Application receipt (PDF)", application_receipt_pdf(c, a["id"]), f"receipt_{a['id']:06d}.pdf", "application/pdf", key="dl_receipt")
        with r:
            st.markdown("#### Documents")
            _doc_preview(a["marksheet_path"], "12th Board Marksheet")
            _doc_preview(a["scorecard_path"], "Entrance Exam Scorecard")
            with st.expander("Upload / replace a document"):
                kind = st.selectbox("Which document", ["marksheet", "scorecard"], format_func=lambda k: db.DOC_KINDS[k], key="rep_kind")
                up = st.file_uploader("File (PDF/PNG/JPG, max 8 MB)", type=["pdf", "png", "jpg", "jpeg"], key="replace_doc")
                if up is not None and st.button("Upload", key="rep_btn"):
                    try:
                        db.save_document(c, a["id"], kind, up.name, up.getvalue())
                        st.toast("Document saved", icon="📎")
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        return

    st.markdown("#### Educational application")
    st.caption("All fields marked * are required. Both documents are mandatory.")
    with st.expander("Browse programs"):
        show = programs[["code", "name", "capacity", "min_score", "required_track"]].rename(
            columns={"code": "Code", "name": "Program", "capacity": "Seats", "min_score": "Min score", "required_track": "Track required"})
        show["Track required"] = show["Track required"].fillna("Any")
        st.dataframe(show, hide_index=True, width="stretch")
    with st.form("apply_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        score = c1.slider("Entrance score *", 0, 100, 70, key="apply_score")
        track = c2.selectbox("Your track *", db.TRACKS, key="apply_track")
        dyn = {}
        if schema:
            st.markdown("**Additional details** (set by the college)")
            cols = st.columns(2)
            for idx, f in enumerate(schema):
                with cols[idx % 2]:
                    dyn.update(_render_dynamic_fields([f]))
        options = [f"{r.code} — {r.name}" for r in programs.itertuples()]
        ranked = st.multiselect("Rank up to 5 programs in order of preference (first = most wanted) *", options, max_selections=5, key="apply_prefs")
        st.markdown("**Mandatory documents** (PDF, PNG or JPG, max 8 MB each)")
        u1, u2 = st.columns(2)
        marksheet = u1.file_uploader("12th Board Marksheet *", type=["pdf", "png", "jpg", "jpeg"], key="up_marksheet")
        scorecard = u2.file_uploader("CUET PG / Entrance Exam Scorecard *", type=["pdf", "png", "jpg", "jpeg"], key="up_scorecard")
        submitted = st.form_submit_button("Submit application", type="primary", width="stretch")
    if not submitted:
        return
    problems = db.validate_form_response(schema, dyn)
    if not ranked:
        problems.append("Rank at least one program")
    if marksheet is None:
        problems.append("12th Board Marksheet upload is mandatory")
    if scorecard is None:
        problems.append("Entrance Exam Scorecard upload is mandatory")
    if problems:
        st.error("Please fix:\n\n- " + "\n- ".join(problems))
        return
    code_to_id = dict(zip(programs.code, programs.id))
    ids = [int(code_to_id[o.split(" — ")[0]]) for o in ranked]
    clean = {}
    for f in schema:
        v = dyn.get(f["field_key"])
        if v is not None:
            clean[f["field_key"]] = float(v) if f["field_type"] == "number" else v
    try:
        db.save_document(c, a["id"], "marksheet", marksheet.name, marksheet.getvalue())
        db.save_document(c, a["id"], "scorecard", scorecard.name, scorecard.getvalue())
        db.submit_application(c, a["id"], score=score, track=track, ranked_program_ids=ids, form_data=clean)
    except ValueError as e:
        st.error(f"Submission rejected: {e}")
        return
    st.toast(f"📧 Email sent to {a['email']}: Application Received & Under Review!", icon="✅")
    st.success(f"**📧 Email receipt (simulated)**\n\nTo: {a['email']}\n\nSubject: Application Received & Under Review\n\n"
               f"Dear {a['name']}, your application (ID {a['id']}) with {len(ids)} ranked program(s) and both documents has been received. "
               "You will be notified when the allotment is published.")
    st.balloons()
    st.button("Back to Dashboard", key="after_apply", on_click=goto, args=(NAV_DASHBOARD,))


# ---------------------------------------------------------------- C. Check Allotment Result
def render_result(c, a) -> None:
    st.markdown("#### Allotment confirmation")
    if not db.has_applied(a):
        st.warning("You have not submitted an application yet. Go to **Apply Now** first.")
        return
    run = db.get_current_run(c)
    seat = db.current_assignment_for(c, a["id"])
    if run is None or seat is None:
        st.markdown("<div class='sw-card info'><h3>Pending Allocation</h3><p>Allocation is currently in progress. Check back later. "
                    "You will be notified by email when the admissions office publishes the result.</p></div>", unsafe_allow_html=True)
        return
    if seat["program_id"] is None:
        st.markdown("<div class='sw-card warn'><h3>No seat allotted in this round</h3><p>Your ranked programs were full or you did not meet "
                    "their eligibility floor. You may raise an appeal with the admissions office.</p></div>", unsafe_allow_html=True)
        return
    st.markdown(f"<div class='sw-card ok'><h3>🎉 Congratulations, {a['name']}!</h3>"
                f"<div class='sw-seat'>{seat['code']} — {seat['program_name']}</div>"
                f"<p>Allotted against your preference #{seat['rank_obtained']} · allocation run #{run['id']} ({run['solver_status']}).</p></div>",
                unsafe_allow_html=True)
    if seat["previous_program_id"] and seat["previous_program_id"] != seat["program_id"]:
        st.caption("Note: this changed in the latest reallocation.")
    st.download_button("⬇ Download Allotment Letter (PDF)", allotment_letter_pdf(c, a["id"]), f"allotment_{a['id']:06d}.pdf",
                       "application/pdf", type="primary", key="dl_allotment")


# ---------------------------------------------------------------- entry
def render_my_portal(c, aid: int) -> None:
    a = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    content = db.get_site_content(c)
    st.markdown(PORTAL_CSS, unsafe_allow_html=True)

    intent = st.session_state.pop("post_login_intent", None)   # one-shot deep link from the public "Apply Now" CTA
    if intent == "apply" and not db.has_applied(a):
        st.session_state["student_nav"] = NAV_APPLY
    elif st.session_state.get("student_nav") not in NAV_OPTIONS:
        st.session_state["student_nav"] = NAV_DASHBOARD          # post-login default: Dashboard, never the form
    with st.sidebar:
        st.markdown("#### Student menu")
        section = st.radio("Student menu", NAV_OPTIONS, key="student_nav", label_visibility="collapsed")

    st.markdown(f"<h1 style='margin-bottom:0'>{content.get('institute_name', BRAND)}</h1>"
                f"<p style='color:gray;margin-top:4px'>Student portal · {BRAND} · {section}</p>", unsafe_allow_html=True)
    if section == NAV_APPLY:
        render_apply(c, a)
    elif section == NAV_RESULT:
        render_result(c, a)
    else:
        render_dashboard(c, a)


def render() -> None:
    c = conn()
    if auth.current_role() == auth.ROLE_STUDENT and auth.current_student_id():
        render_my_portal(c, auth.current_student_id())
