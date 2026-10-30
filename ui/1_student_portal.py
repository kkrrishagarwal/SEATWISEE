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
    st.subheader(f"Hello, {a['name']}")
    if content.get("announcements", "").strip():
        st.info(f"**Announcements** · {content['announcements']}")
    st.markdown(f"<div class='sw-card {cls}'><h3>{label}</h3><p>{detail}</p></div>", unsafe_allow_html=True)

    applied = db.has_applied(a)
    docs_ok = bool(a["marksheet_path"]) and bool(a["scorecard_path"])
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
    with st.expander("My account details"):
        st.write(f"Email: {a['email']}")
        st.write(f"Phone: {a['phone'] or '—'}")
        st.write(f"Address: {a['address'] or '—'}")
        st.caption(content.get("contact_info", ""))


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
    st.session_state["portal_tab_hint"] = "result"
    if st.button("Go to my dashboard", key="after_apply"):
        st.rerun()


# ---------------------------------------------------------------- C. Check Allotment Result
def render_result(c, a) -> None:
    st.markdown("#### Check allotment result")
    if not db.has_applied(a):
        st.warning("You have not submitted an application yet. Go to **Apply Now** first.")
        return
    run = db.get_current_run(c)
    seat = db.current_assignment_for(c, a["id"])
    if run is None or seat is None:
        st.markdown("<div class='sw-card info'><h3>Allocation is currently in progress.</h3><p>Check back later. "
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
    st.markdown(f"<h1 style='margin-bottom:0'>{content.get('institute_name', BRAND)}</h1>"
                f"<p style='color:gray;margin-top:4px'>Student portal · {BRAND}</p>", unsafe_allow_html=True)
    tab_home, tab_apply, tab_result = st.tabs(["🏠 Home / Dashboard", "📝 Apply Now", "🎓 Check Allotment Result"])
    with tab_home:
        render_dashboard(c, a)
    with tab_apply:
        render_apply(c, a)
    with tab_result:
        render_result(c, a)


def render() -> None:
    c = conn()
    if auth.current_role() == auth.ROLE_STUDENT and auth.current_student_id():
        render_my_portal(c, auth.current_student_id())
