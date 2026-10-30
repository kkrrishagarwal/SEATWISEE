"""Admin dashboard — metrics, allocation triggers, capacity shocks, withdrawals, validator, audit."""
from __future__ import annotations

import base64
import json

import pandas as pd
import streamlit as st

from database import db_manager as db
from optimization.validator import validate
from ui.common import assignment_df, conn, occupancy_chart, run_and_persist, sankey_displacement, status_badge


def _show_result(res, problem, run_id):
    status_badge(res.status, res.explanation)
    if res.has_solution:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Seated", res.assigned_count, help="Applicants holding a seat")
        c2.metric("Unassigned", len(res.unassigned))
        c3.metric("Preference pts", res.preference_score)
        if res.mode == "reassign":
            c4.metric("Reassigned", res.reassigned_count, help="Applicants whose seat differs from the previous allocation")
        else:
            c4.metric("Kept from before", "n/a", help="Mode A ignores the previous allocation")
        c5.metric("Solve time", f"{res.wall_time_s:.2f}s")
        if res.status == "FEASIBLE":
            st.warning(f"Feasible but not proven optimal. Objective {res.objective:.0f}, best bound {res.best_bound:.0f}.")
        if run_id:
            st.success(f"Persisted as run #{run_id} (now current). Validator: PASS.")
    for n in res.notes:
        st.caption("• " + n)


def render() -> None:
    c = conn()
    st.header("Admin dashboard")
    current = db.get_current_run(c)
    problem = db.build_problem(c)
    cur_assign = dict(problem.previous)

    # ---------------- KPIs
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Applicants (active)", len(problem.active_applicant_ids), f"{len(problem.applicants) - len(problem.active_applicant_ids)} withdrawn")
    k2.metric("Programs", len(problem.programs))
    k3.metric("Total seats", sum(problem.capacity.values()))
    k4.metric("Current run", f"#{current['id']} · {current['mode']}" if current else "none")
    k5.metric("Solver status", current["solver_status"] if current else "—")

    tab_alloc, tab_shock, tab_valid, tab_students, tab_form, tab_data, tab_audit = st.tabs(
        ["Allocate", "Capacity shock & withdrawals", "Validate", "Students & documents", "Form builder", "Data", "Audit trail"])

    # ---------------- Allocate
    with tab_alloc:
        colA, colB = st.columns([1, 2])
        with colA:
            tl = st.slider("Solver time limit (s)", 1, 60, 20)
            st.markdown("**Mode A — initial allocation**  \nMaximise preference points (100/50/20/10/5). Ignores any previous allocation.")
            if st.button("Run initial allocation", type="primary"):
                with st.spinner("Solving with CP-SAT…"):
                    res, run_id, prob = run_and_persist("initial", notes="Mode A from dashboard", time_limit=tl)
                st.session_state["last_result"] = (res, prob, run_id)
                st.rerun()
            st.markdown("**Mode B — re-allocate preserving seats**  \nMaximise preference − μ·displacement against the current run.")
            mu = st.number_input("μ (displacement penalty)", 1, 100000, 1000, step=100, help="Any value above 100 makes keeping a seat outrank any preference gain.")
            if st.button("Re-allocate (Mode B)"):
                if not current:
                    st.error("No current allocation to preserve. Run Mode A first.")
                else:
                    with st.spinner("Solving with CP-SAT…"):
                        res, run_id, prob = run_and_persist("reassign", notes=f"Mode B μ={mu}", mu=mu, time_limit=tl)
                    st.session_state["last_result"] = (res, prob, run_id)
                    st.rerun()
        with colB:
            if "last_result" in st.session_state:
                res, prob, run_id = st.session_state["last_result"]
                _show_result(res, prob, run_id)
                if res.has_solution:
                    from ui.common import rank_chart
                    st.plotly_chart(rank_chart(res), width="stretch", key="alloc_rank_chart")
                    if res.mode == "reassign":
                        st.plotly_chart(sankey_displacement(prob, prob.previous, res.assignment), width="stretch", key="alloc_sankey")
            elif current:
                st.info(f"Current allocation is run #{current['id']} ({current['solver_status']}, {current['assigned_count']} seated, {current['preference_score']} pts).")
            else:
                st.info("No allocation yet. Run Mode A to seat the 200 applicants.")
        if cur_assign:
            st.plotly_chart(occupancy_chart(problem, cur_assign), width="stretch", key="alloc_occupancy")

    # ---------------- Shock
    with tab_shock:
        st.markdown("Change the world, then press **Re-allocate** to see who must move and who stays put.")
        s1, s2 = st.columns(2)
        with s1:
            st.subheader("Capacity change")
            prog_df = db.load_programs(c)
            sel = st.selectbox("Program", prog_df.code.tolist(), key="shock_prog")
            row = prog_df[prog_df.code == sel].iloc[0]
            new_cap = st.number_input("New capacity", 0, 500, int(row.capacity), key="shock_cap")
            reason = st.text_input("Reason", "Lab space reduced", key="shock_reason")
            if st.button("Apply capacity change"):
                old, new = db.update_capacity(c, int(row.id), int(new_cap), reason)
                st.success(f"{sel}: {old} → {new} seats. Now re-allocate in Mode B.")
                st.rerun()
        with s2:
            st.subheader("Withdraw applicant")
            apps = db.load_applicants(c, active_only=True)
            labels = {f"{r.id} · {r.name} ({r.track}, {r.score})": r.id for r in apps.itertuples()}
            pick = st.selectbox("Applicant", list(labels.keys()), key="wd_pick")
            wreason = st.text_input("Reason", "Accepted elsewhere", key="wd_reason")
            if st.button("Withdraw"):
                db.withdraw_applicant(c, labels[pick], wreason)
                st.success("Withdrawn. Re-allocate in Mode B to free the seat.")
                st.rerun()
        st.divider()
        if current:
            if st.button("Re-allocate now (Mode B, μ=1000)", type="primary", key="shock_realloc"):
                with st.spinner("Solving…"):
                    res, run_id, prob = run_and_persist("reassign", notes="Mode B after shock", mu=1000)
                st.session_state["last_result"] = (res, prob, run_id)
                st.rerun()
        if "last_result" in st.session_state and st.session_state["last_result"][0].mode == "reassign":
            res, prob, run_id = st.session_state["last_result"]
            st.markdown("**Latest Mode B result**")
            _show_result(res, prob, run_id)
            if res.has_solution:
                st.plotly_chart(sankey_displacement(prob, prob.previous, res.assignment), width="stretch", key="shock_sankey")
                moved = assignment_df(prob, res.assignment, prob.previous)
                moved = moved[moved.Changed == "✔"]
                st.caption(f"{len(moved)} applicant(s) changed seat; everyone else kept theirs.")
                st.dataframe(moved, hide_index=True, width="stretch")
        st.subheader("Capacity change history")
        st.dataframe(db.load_capacity_changes(c), hide_index=True, width="stretch")

    # ---------------- Validate
    with tab_valid:
        st.markdown("Independent validator: pure Python, **no OR-Tools**, re-checks every declared rule against the current run.")
        if not cur_assign:
            st.info("Nothing to validate yet.")
        else:
            rep = validate(problem, cur_assign)
            if rep.ok:
                st.success(f"PASS — checks run: {', '.join(rep.checks_run)}")
            else:
                st.error(f"{len(rep.violations)} violation(s) found")
                st.dataframe(pd.DataFrame(rep.as_rows()), hide_index=True, width="stretch")
            occ = pd.DataFrame([{"Program": p.code, "Capacity": p.capacity, "Seated": rep.seats_used.get(p.id, 0)} for p in problem.programs])
            occ["Utilisation"] = (occ.Seated / occ.Capacity.clip(lower=1)).round(2)
            st.dataframe(occ, hide_index=True, width="stretch")
            st.caption("Note: the current run may have been solved against older capacities. A capacity cut shows here as a violation until you re-allocate — that is the point of the check.")

    # ---------------- Students & documents
    with tab_students:
        _render_students(c)

    # ---------------- Form builder
    with tab_form:
        _render_form_builder(c)

    # ---------------- Data
    with tab_data:
        if cur_assign or current:
            df = assignment_df(problem, cur_assign, None)
            f1, f2 = st.columns(2)
            prog_filter = f1.multiselect("Program", sorted(df.Program.unique()))
            track_filter = f2.multiselect("Track", sorted(df.Track.unique()))
            if prog_filter:
                df = df[df.Program.isin(prog_filter)]
            if track_filter:
                df = df[df.Track.isin(track_filter)]
            st.dataframe(df, hide_index=True, width="stretch", height=420)
            st.download_button("Download allocation CSV", df.to_csv(index=False).encode(), "allocation.csv", "text/csv")
        st.subheader("Run history (versions)")
        st.dataframe(db.load_runs(c), hide_index=True, width="stretch")
        with st.expander("Danger zone"):
            if st.button("Reset database to demo seed (200 applicants)"):
                db.reset_db(c)
                db.seed_demo(c)
                st.session_state.pop("last_result", None)
                st.rerun()

    # ---------------- Audit
    with tab_audit:
        st.dataframe(db.load_audit(c, 500), hide_index=True, width="stretch", height=500)


# =====================================================================================
def _doc_block(rel_path, title, key):
    st.markdown(f"**{title}**")
    path = db.resolve_document(rel_path)
    if not rel_path:
        st.caption("not uploaded")
        return
    if path is None:
        st.caption(f"`{rel_path}` · path recorded, file not on disk (simulated seed record)")
        return
    data = path.read_bytes()
    st.caption(f"`{rel_path}` · {len(data)/1024:.1f} KB")
    if path.suffix.lower() == ".pdf":
        b64 = base64.b64encode(data).decode()
        st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="360"></iframe>', unsafe_allow_html=True)
    else:
        try:
            st.image(data, width=360)
        except Exception:
            st.warning("Image could not be rendered (corrupt or unsupported). Use the download button.")
    st.download_button(f"Download {title}", data, file_name=path.name, key=key)


def _render_students(c):
    st.markdown("Every applicant with their dynamic form responses and document status. Pick one to view uploaded files.")
    df = db.load_applicants_full(c)
    schema = db.load_form_schema(c)
    dyn_cols = [f["label"] for f in schema]
    f1, f2, f3 = st.columns(3)
    q = f1.text_input("Search name / email", key="stu_search")
    track = f2.multiselect("Track", sorted(df.track.unique()), key="stu_track")
    docs = f3.selectbox("Documents", ["All", "Files on disk", "Simulated / missing"], key="stu_docs")
    view = df.copy()
    if q:
        m = view.name.str.contains(q, case=False) | view.email.str.contains(q, case=False)
        view = view[m]
    if track:
        view = view[view.track.isin(track)]
    if docs == "Files on disk":
        view = view[view.marksheet_on_disk | view.scorecard_on_disk]
    elif docs == "Simulated / missing":
        view = view[~(view.marksheet_on_disk & view.scorecard_on_disk)]
    show = view[["id", "name", "email", "score", "track", "status", "applied_at"] + dyn_cols + ["marksheet_on_disk", "scorecard_on_disk"]].rename(
        columns={"marksheet_on_disk": "Marksheet file", "scorecard_on_disk": "Scorecard file"})
    st.dataframe(show, hide_index=True, width="stretch", height=380,
                 column_config={"Marksheet file": st.column_config.CheckboxColumn(), "Scorecard file": st.column_config.CheckboxColumn()})
    st.download_button("Download students CSV", show.to_csv(index=False).encode(), "students.csv", "text/csv", key="stu_csv")

    st.divider()
    st.subheader("View documents")
    labels = {f"{r.id} · {r.name} ({r.email})": int(r.id) for r in view.itertuples()}
    if not labels:
        st.info("No students match the filter.")
        return
    pick = st.selectbox("Student", list(labels.keys()), key="stu_pick")
    aid = labels[pick]
    row = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    data = json.loads(row["form_data"] or "{}")
    st.write(" · ".join(f"**{f['label']}**: {data.get(f['field_key'], '—')}" for f in schema) or "no form responses")
    d1, d2 = st.columns(2)
    with d1:
        _doc_block(row["marksheet_path"], "12th Board Marksheet", key=f"adm_dl_m_{aid}")
    with d2:
        _doc_block(row["scorecard_path"], "Entrance Exam Scorecard", key=f"adm_dl_s_{aid}")


def _render_form_builder(c):
    st.markdown("Configure the extra fields students must fill in. Changes apply to the registration form immediately. Existing responses are kept.")
    schema = db.load_form_schema(c)
    if schema:
        tbl = pd.DataFrame([{"Key": f["field_key"], "Label": f["label"], "Type": f["field_type"], "Required": f["required"],
                             "Options": ", ".join(f["options"]) if f["options"] else ""} for f in schema])
        st.dataframe(tbl, hide_index=True, width="stretch")
    else:
        st.info("No custom fields yet.")
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**Add a field**")
        with st.form("add_field", clear_on_submit=True):
            label = st.text_input("Label", placeholder="e.g. Hostel required?")
            ftype = st.selectbox("Type", ["text", "number", "select"])
            required = st.checkbox("Required", value=True)
            options = st.text_input("Options for select (comma separated)", placeholder="Yes, No")
            ok = st.form_submit_button("Add field", type="primary")
        if ok:
            opts = [o.strip() for o in options.split(",") if o.strip()] if ftype == "select" else None
            if not label.strip():
                st.error("Label is required.")
            else:
                try:
                    key = db.add_form_field(c, label=label, field_type=ftype, required=required, options=opts)
                    st.success(f"Added field '{label}' (key `{key}`).")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with a2:
        st.markdown("**Remove a field**")
        if schema:
            rm = st.selectbox("Field", [f["field_key"] for f in schema], format_func=lambda k: next(f["label"] for f in schema if f["field_key"] == k), key="rm_field")
            if st.button("Remove field"):
                db.remove_form_field(c, rm)
                st.success("Removed.")
                st.rerun()
