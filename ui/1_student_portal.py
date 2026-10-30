"""Student portal — branded "DO! u want".

Two states:
  * not logged in  -> registration form (dynamic fields + two mandatory document uploads)
  * logged in      -> ONLY this student's own data: ranking, documents, current seat.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from database import db_manager as db
from ui import auth
from ui.common import BRAND, conn


def _render_dynamic_fields(schema):
    """Draw admin-defined fields and return {field_key: value}."""
    out = {}
    for f in schema:
        label = f["label"] + (" *" if f["required"] else "")
        key = f"dyn_{f['field_key']}"
        if f["field_type"] == "select":
            out[f["field_key"]] = st.selectbox(label, [""] + f["options"], key=key) or None
        elif f["field_type"] == "number":
            v = st.text_input(label, key=key, placeholder="e.g. 0")
            out[f["field_key"]] = v.strip() if v and v.strip() else None
        else:
            v = st.text_input(label, key=key)
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
        b64 = base64.b64encode(data).decode()
        st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="320"></iframe>', unsafe_allow_html=True)
    else:
        try:
            st.image(data, width=320)
        except Exception:
            st.warning("Image could not be rendered (corrupt or unsupported). Use the download button.")
    st.download_button(f"Download {title}", data, file_name=path.name, key=f"dl_{title}_{path.name}")


def render_registration(c, compact: bool = False) -> None:
    if not compact:
        st.markdown(f"<h1 style='margin-bottom:0'>{BRAND}</h1><p style='color:gray;margin-top:0'>Tell us what you want. Our solver finds the fairest seat for everyone.</p>", unsafe_allow_html=True)
    programs = db.load_programs(c)
    with st.expander("Browse programs", expanded=False):
        show = programs[["code", "name", "capacity", "min_score", "required_track"]].rename(
            columns={"code": "Code", "name": "Program", "capacity": "Seats", "min_score": "Min score", "required_track": "Track required"})
        show["Track required"] = show["Track required"].fillna("Any")
        st.dataframe(show, hide_index=True, width="stretch")

    schema = db.load_form_schema(c)
    if not compact:
        st.subheader("Application form")
    with st.form("register", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full name *")
            email = st.text_input("Email *")
        with c2:
            score = st.slider("Entrance score *", 0, 100, 70)
            track = st.selectbox("Your track *", db.TRACKS)
        if schema:
            st.markdown("**Additional details** (set by the college)")
            cols = st.columns(2)
            dyn = {}
            for idx, f in enumerate(schema):
                with cols[idx % 2]:
                    dyn.update(_render_dynamic_fields([f]))
        else:
            dyn = {}
        options = [f"{r.code} — {r.name}" for r in programs.itertuples()]
        ranked = st.multiselect("Rank up to 5 programs in order of preference (first = most wanted) *", options, max_selections=5)
        st.markdown("**Mandatory documents** (PDF, PNG or JPG, max 8 MB each)")
        u1, u2 = st.columns(2)
        marksheet = u1.file_uploader("12th Board Marksheet *", type=["pdf", "png", "jpg", "jpeg"], key="up_marksheet")
        scorecard = u2.file_uploader("CUET PG / Entrance Exam Scorecard *", type=["pdf", "png", "jpg", "jpeg"], key="up_scorecard")
        submitted = st.form_submit_button("DO! I want these seats", type="primary")

    if not submitted:
        return
    problems = []
    if not name.strip():
        problems.append("Full name is required")
    if "@" not in email:
        problems.append("A valid email is required")
    if not ranked:
        problems.append("Rank at least one program")
    problems += db.validate_form_response(schema, dyn)
    if marksheet is None:
        problems.append("12th Board Marksheet upload is mandatory")
    if scorecard is None:
        problems.append("Entrance Exam Scorecard upload is mandatory")
    if db.find_applicant_by_email(c, email):
        problems.append("That email is already registered — log in instead")
    if problems:
        st.error("Please fix:\n\n- " + "\n- ".join(problems))
        return
    code_to_id = dict(zip(programs.code, programs.id))
    ids = [code_to_id[o.split(" — ")[0]] for o in ranked]
    clean = {}
    for f in schema:
        v = dyn.get(f["field_key"])
        if v is None:
            continue
        clean[f["field_key"]] = float(v) if f["field_type"] == "number" else v
    try:
        aid = db.add_applicant(c, name=name.strip(), email=email, score=score, track=track, ranked_program_ids=ids, form_data=clean)
        db.save_document(c, aid, "marksheet", marksheet.name, marksheet.getvalue())
        db.save_document(c, aid, "scorecard", scorecard.name, scorecard.getvalue())
    except ValueError as e:
        st.error(f"Upload rejected: {e}")
        return
    st.success(f"Registered! Your applicant ID is **{aid}**. Documents saved. Logging you in…")
    auth.login_student(email, c)
    st.rerun()


def render_my_portal(c, aid: int) -> None:
    """Logged-in student dashboard: status, allocation, downloads. No registration form here."""
    import json
    from ui.common import application_receipt_pdf

    a = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    st.markdown(f"<h1 style='margin-bottom:0'>{BRAND}</h1>", unsafe_allow_html=True)
    st.subheader(f"Hello, {a['name']}")

    seat = db.current_assignment_for(c, aid)
    docs_ok = bool(a["marksheet_path"]) and bool(a["scorecard_path"])
    if a["status"] != "active":
        app_status = "Withdrawn"
    elif seat is None:
        app_status = "Submitted · awaiting allocation"
    elif seat["program_id"] is None:
        app_status = "Allocation published · unassigned"
    else:
        app_status = "Allocation published · seated"

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Applicant ID", a["id"])
    k2.metric("Application status", app_status)
    k3.metric("Documents", "Complete" if docs_ok else "Incomplete")
    k4.metric("Score · Track", f"{a['score']} · {a['track']}")

    st.markdown("#### Allocated program")
    if seat is None:
        st.info("The college has not run the allocation yet. Check back later.")
    elif seat["program_id"] is None:
        st.warning("You are currently **unassigned**. You may raise an appeal with the admin office.")
    else:
        st.success(f"**{seat['code']} — {seat['program_name']}** · your choice #{seat['rank_obtained']}")
        if seat["previous_program_id"] and seat["previous_program_id"] != seat["program_id"]:
            st.caption("This changed in the latest reallocation.")

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("#### Your application")
        prefs = db.load_preferences(c)
        mine = prefs[prefs.applicant_id == aid]
        st.write("Ranking: " + " › ".join(f"#{r.rank} {r.code}" for r in mine.itertuples()))
        data = json.loads(a["form_data"] or "{}")
        for f in db.load_form_schema(c):
            st.write(f"{f['label']}: {data.get(f['field_key'], '—')}")
        st.caption(f"Applied at {a['applied_at']}")
    with right:
        st.markdown("#### Downloads")
        receipt = application_receipt_pdf(c, aid)
        st.download_button("⬇ Application receipt (PDF)", receipt, f"receipt_{aid:06d}.pdf", "application/pdf", key="dl_receipt", width="stretch")
        for rel, title in ((a["marksheet_path"], "12th Board Marksheet"), (a["scorecard_path"], "Entrance Exam Scorecard")):
            path = db.resolve_document(rel)
            if path is not None:
                st.download_button(f"⬇ {title}", path.read_bytes(), path.name, key=f"dl_{title}", width="stretch")
            elif rel:
                st.caption(f"{title}: recorded as `{rel}` (file not available for download)")
            else:
                st.caption(f"{title}: not uploaded")
        with st.expander("Replace a document"):
            kind = st.selectbox("Which document", ["marksheet", "scorecard"], format_func=lambda k: db.DOC_KINDS[k])
            up = st.file_uploader("New file", type=["pdf", "png", "jpg", "jpeg"], key="replace_doc")
            if up is not None and st.button("Upload replacement"):
                try:
                    db.save_document(c, aid, kind, up.name, up.getvalue())
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))


def render() -> None:
    """Kept for backwards compatibility; app.py routes directly to the two functions above."""
    c = conn()
    if auth.current_role() == auth.ROLE_STUDENT and auth.current_student_id():
        render_my_portal(c, auth.current_student_id())
    else:
        render_registration(c)
