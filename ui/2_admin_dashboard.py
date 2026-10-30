"""Admin dashboard — metrics, allocation triggers, capacity shocks, withdrawals, validator, audit."""
from __future__ import annotations

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

    tab_alloc, tab_shock, tab_valid, tab_data, tab_audit = st.tabs(["Allocate", "Capacity shock & withdrawals", "Validate", "Data", "Audit trail"])

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
