"""Unified admin workspace — exactly four tabs.

1. Command Center            : KPIs, Run Initial Allocation (Mode A), seat occupancy
2. Disruptions & Appeals     : capacity shocks, withdrawals, Mode B reassignment, appeal sandbox
3. Form Builder & Records    : dynamic form fields, student table, document viewer
4. Audit & Compliance        : independent validator, run history, capacity history, appeals, audit log
"""
from __future__ import annotations

import base64
import importlib
import json

import pandas as pd
import streamlit as st

from database import db_manager as db
from optimization.validator import validate
from ui.common import assignment_df, conn, occupancy_chart, rank_chart, run_and_persist, sankey_displacement, status_badge

appeals = importlib.import_module("ui.3_appeal_studio")


# ====================================================================== shared pieces
def _show_result(res, run_id):
    status_badge(res.status, res.explanation)
    if res.has_solution:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Seated", res.assigned_count)
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


# ====================================================================== TAB 1
def _command_center(c, current, problem, cur_assign):
    active = len(problem.active_applicant_ids)
    seats = sum(problem.capacity.values())
    seated = len(cur_assign)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Total applicants", active, f"{len(problem.applicants) - active} withdrawn" if len(problem.applicants) - active else None)
    k2.metric("Total seats", seats)
    k3.metric("Seated", seated if current else "—")
    k4.metric("Unassigned", active - seated if current else "—")
    k5.metric("Solver status", current["solver_status"] if current else "no run yet")

    st.markdown("")
    left, right = st.columns([1, 2], gap="large")
    with left:
        st.markdown("#### Step 1 · Allocate")
        st.caption("Mode A: maximise preference points (100 / 50 / 20 / 10 / 5), merit tie-break. Ignores previous runs.")
        with st.expander("Advanced"):
            tl = st.slider("Solver time limit (s)", 1, 60, 20, key="cc_tl")
        if st.button("▶ Run Initial Allocation (Mode A)", type="primary", width="stretch", key="cc_run_a"):
            with st.spinner("Solving with CP-SAT…"):
                res, run_id, prob = run_and_persist("initial", notes="Mode A from Command Center", time_limit=tl)
            st.session_state["last_result"] = (res, prob, run_id)
            st.rerun()
        if current:
            st.info(f"Current run **#{current['id']}** · {current['mode']} · {current['solver_status']} · "
                    f"{current['assigned_count']} seated · {current['preference_score']} pts")
    with right:
        lr = st.session_state.get("last_result")
        if lr and lr[0].mode == "initial":
            res, prob, run_id = lr
            _show_result(res, run_id)
            if res.has_solution:
                st.plotly_chart(rank_chart(res), width="stretch", key="cc_rank_chart")
        elif not current:
            st.info("No allocation yet. Press **Run Initial Allocation** to seat the applicants.")
    if cur_assign:
        st.plotly_chart(occupancy_chart(problem, cur_assign), width="stretch", key="cc_occupancy")


# ====================================================================== TAB 2
def _disruptions(c, current, problem):
    st.markdown("#### Step 2 · Change the world, then re-allocate with minimal disruption")
    s1, s2 = st.columns(2, gap="large")
    with s1:
        st.markdown("**Capacity shock**")
        prog_df = db.load_programs(c)
        sel = st.selectbox("Program", prog_df.code.tolist(), key="shock_prog")
        row = prog_df[prog_df.code == sel].iloc[0]
        new_cap = st.slider("New capacity", 0, int(row.capacity) + 20, int(row.capacity), key="shock_cap",
                            help="Drag left to cut seats, right to add seats")
        reason = st.text_input("Reason", "Lab space reduced", key="shock_reason")
        if st.button("Apply capacity change", key="shock_apply", width="stretch"):
            old, new = db.update_capacity(c, int(row.id), int(new_cap), reason)
            st.toast(f"{sel}: {old} → {new} seats")
            st.rerun()
    with s2:
        st.markdown("**Withdrawal**")
        apps = db.load_applicants(c, active_only=True)
        labels = {f"{r.id} · {r.name} ({r.track}, {r.score})": r.id for r in apps.itertuples()}
        pick = st.selectbox("Applicant", list(labels.keys()), key="wd_pick")
        wreason = st.text_input("Reason", "Accepted elsewhere", key="wd_reason")
        if st.button("Withdraw applicant", key="wd_apply", width="stretch"):
            db.withdraw_applicant(c, labels[pick], wreason)
            st.toast("Applicant withdrawn")
            st.rerun()

    st.markdown("")
    with st.expander("Advanced"):
        mu = st.number_input("μ (displacement penalty)", 1, 100000, 1000, step=100, key="shock_mu",
                             help="Above 100, keeping an existing seat outranks any preference gain.")
    if not current:
        st.warning("Run the initial allocation first (Command Center).")
    elif st.button("▶ Run Minimal-Disruption Reassignment (Mode B)", type="primary", width="stretch", key="shock_realloc"):
        with st.spinner("Solving…"):
            res, run_id, prob = run_and_persist("reassign", notes=f"Mode B after disruption (μ={mu})", mu=mu)
        st.session_state["last_result"] = (res, prob, run_id)
        st.rerun()

    lr = st.session_state.get("last_result")
    if lr and lr[0].mode == "reassign":
        res, prob, run_id = lr
        st.markdown("**Latest reassignment**")
        _show_result(res, run_id)
        if res.has_solution:
            st.plotly_chart(sankey_displacement(prob, prob.previous, res.assignment), width="stretch", key="shock_sankey")
            moved = assignment_df(prob, res.assignment, prob.previous)
            moved = moved[moved.Changed == "✔"]
            st.caption(f"{len(moved)} applicant(s) changed seat; everyone else kept theirs.")
            st.dataframe(moved, hide_index=True, width="stretch")

    st.divider()
    st.markdown("#### Step 3 · Appeals (what-if sandbox)")
    appeals.render(embedded=True)


# ====================================================================== TAB 3
def _form_builder(c):
    st.markdown("**Application form fields**")
    st.caption("Students must fill these when registering. Changes apply immediately; existing responses are kept.")
    schema = db.load_form_schema(c)
    if schema:
        tbl = pd.DataFrame([{"Label": f["label"], "Type": f["field_type"], "Required": f["required"],
                             "Options": ", ".join(f["options"]) if f["options"] else "", "Key": f["field_key"]} for f in schema])
        st.dataframe(tbl, hide_index=True, width="stretch")
    else:
        st.info("No custom fields yet.")
    a1, a2 = st.columns(2)
    with a1:
        with st.form("add_field", clear_on_submit=True):
            st.markdown("Add a field")
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
                    db.add_form_field(c, label=label, field_type=ftype, required=required, options=opts)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
    with a2:
        if schema:
            st.markdown("Remove a field")
            rm = st.selectbox("Field", [f["field_key"] for f in schema],
                              format_func=lambda k: next(f["label"] for f in schema if f["field_key"] == k), key="rm_field")
            if st.button("Remove field", key="rm_field_btn"):
                db.remove_form_field(c, rm)
                st.rerun()
    st.caption("Document uploads (12th Board Marksheet, Entrance Scorecard) are always mandatory and are not configurable.")


def _student_records(c):
    st.markdown("**Student records & documents**")
    df = db.load_applicants_full(c)
    schema = db.load_form_schema(c)
    dyn_cols = [f["label"] for f in schema]
    cur_map = db.get_current_assignment_map(c)
    programs = {int(r.id): r.code for r in db.load_programs(c).itertuples()}
    df["Allocated"] = df["id"].map(lambda i: programs.get(cur_map.get(int(i)), "—" if cur_map else "not run"))
    f1, f2, f3 = st.columns(3)
    q = f1.text_input("Search name / email", key="stu_search")
    track = f2.multiselect("Track", sorted(df.track.unique()), key="stu_track")
    docs = f3.selectbox("Documents", ["All", "Files on disk", "Simulated / missing"], key="stu_docs")
    view = df.copy()
    if q:
        view = view[view.name.str.contains(q, case=False) | view.email.str.contains(q, case=False)]
    if track:
        view = view[view.track.isin(track)]
    if docs == "Files on disk":
        view = view[view.marksheet_on_disk | view.scorecard_on_disk]
    elif docs == "Simulated / missing":
        view = view[~(view.marksheet_on_disk & view.scorecard_on_disk)]
    show = view[["id", "name", "email", "score", "track", "status", "Allocated", "applied_at"] + dyn_cols +
                ["marksheet_on_disk", "scorecard_on_disk"]].rename(columns={"marksheet_on_disk": "Marksheet file", "scorecard_on_disk": "Scorecard file"})
    st.dataframe(show, hide_index=True, width="stretch", height=360,
                 column_config={"Marksheet file": st.column_config.CheckboxColumn(), "Scorecard file": st.column_config.CheckboxColumn()})
    st.download_button("Download students CSV", show.to_csv(index=False).encode(), "students.csv", "text/csv", key="stu_csv")

    labels = {f"{r.id} · {r.name} ({r.email})": int(r.id) for r in view.itertuples()}
    if not labels:
        st.info("No students match the filter.")
        return
    pick = st.selectbox("View documents of", list(labels.keys()), key="stu_pick")
    aid = labels[pick]
    row = c.execute("SELECT * FROM applicants WHERE id = ?", (aid,)).fetchone()
    data = json.loads(row["form_data"] or "{}")
    st.write(" · ".join(f"**{f['label']}**: {data.get(f['field_key'], '—')}" for f in schema) or "no form responses")
    d1, d2 = st.columns(2)
    with d1:
        _doc_block(row["marksheet_path"], "12th Board Marksheet", key=f"adm_dl_m_{aid}")
    with d2:
        _doc_block(row["scorecard_path"], "Entrance Exam Scorecard", key=f"adm_dl_s_{aid}")


def _form_and_records(c):
    _form_builder(c)
    st.divider()
    _student_records(c)


# ====================================================================== TAB 4
def _audit(c, current, problem, cur_assign):
    st.markdown("**Independent validator** · pure Python, no OR-Tools, re-checks every declared rule against the current run")
    if not cur_assign:
        st.info("Nothing to validate yet.")
    else:
        rep = validate(problem, cur_assign)
        if rep.ok:
            st.success(f"PASS — checks run: {', '.join(rep.checks_run)}")
        else:
            st.error(f"{len(rep.violations)} violation(s) found — a capacity cut or withdrawal has not been re-allocated yet")
            st.dataframe(pd.DataFrame(rep.as_rows()), hide_index=True, width="stretch")
        occ = pd.DataFrame([{"Program": p.code, "Capacity": p.capacity, "Seated": rep.seats_used.get(p.id, 0)} for p in problem.programs])
        occ["Utilisation"] = (occ.Seated / occ.Capacity.clip(lower=1)).round(2)
        st.dataframe(occ, hide_index=True, width="stretch")
    st.divider()
    h1, h2 = st.columns(2)
    with h1:
        st.markdown("**Run history (versions)**")
        st.dataframe(db.load_runs(c), hide_index=True, width="stretch", height=260)
        st.markdown("**Capacity changes**")
        st.dataframe(db.load_capacity_changes(c), hide_index=True, width="stretch", height=200)
    with h2:
        st.markdown("**Appeals evaluated**")
        st.dataframe(db.load_appeals(c), hide_index=True, width="stretch", height=260)
        if cur_assign:
            df = assignment_df(problem, cur_assign, None)
            st.download_button("Download current allocation CSV", df.to_csv(index=False).encode(), "allocation.csv", "text/csv", key="audit_csv")
    st.markdown("**Audit trail** (append-only)")
    st.dataframe(db.load_audit(c, 500), hide_index=True, width="stretch", height=380)
    with st.expander("Danger zone"):
        if st.button("Reset database to demo seed (200 applicants)", key="reset_db"):
            db.reset_db(c)
            db.seed_demo(c)
            st.session_state.pop("last_result", None)
            st.session_state.pop("last_cf", None)
            st.rerun()


# ====================================================================== entry
def render() -> None:
    c = conn()
    current = db.get_current_run(c)
    problem = db.build_problem(c)
    cur_assign = dict(problem.previous)
    st.title("Admin workspace")
    t1, t2, t3, t4 = st.tabs(["🎛 Command Center", "⚡ Disruptions & Appeals", "📋 Form Builder & Student Records", "🔍 Audit & Compliance"])
    with t1:
        _command_center(c, current, problem, cur_assign)
    with t2:
        _disruptions(c, current, problem)
    with t3:
        _form_and_records(c)
    with t4:
        _audit(c, current, problem, cur_assign)
