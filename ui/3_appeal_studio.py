"""Appeal studio — what-if simulations: force one applicant into a program and show the ripple."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from database import db_manager as db
from optimization.counterfactual import evaluate_appeal
from ui.common import appeal_pdf, conn, program_labels, sankey_displacement, status_badge


def render() -> None:
    c = conn()
    st.header("Appeal studio · what-if sandbox")
    current = db.get_current_run(c)
    if not current:
        st.info("Publish an allocation first (Admin → Allocate).")
        return
    problem = db.build_problem(c)
    labels = program_labels(problem)

    apps = db.load_applicants(c, active_only=True)
    cur = problem.previous
    left, right = st.columns([1, 2], gap="large")
    with left:
        opts = {f"{r.id} · {r.name} — now: {labels[cur.get(r.id)]}": r.id for r in apps.itertuples()}
        pick = st.selectbox("Appellant", list(opts.keys()))
        aid = opts[pick]
        prefs = db.load_preferences(c)
        mine = prefs[prefs.applicant_id == aid]
        st.caption("Their ranking: " + " › ".join(f"#{r.rank} {r.code}" for r in mine.itertuples()))
        prog_opts = {f"{p.code} — {p.name}": p.id for p in problem.programs}
        default_idx = 0
        if len(mine):
            top = mine.iloc[0].code
            default_idx = [k.split(" — ")[0] for k in prog_opts].index(top)
        target_label = st.selectbox("Requested program", list(prog_opts.keys()), index=default_idx)
        target = prog_opts[target_label]
        reasons = problem.ineligibility_reasons(aid, target)
        if reasons:
            st.warning("Eligibility pre-check: " + "; ".join(reasons))
        mu = st.number_input("μ (protect existing seats)", 1, 100000, 1000, step=100)
        go = st.button("Simulate appeal", type="primary")

    if go:
        with st.spinner("Cloning state and re-solving with the request forced…"):
            cf = evaluate_appeal(problem, aid, target, mu=mu)
        st.session_state["last_cf"] = (cf, pick, target_label)
        db.record_appeal(
            c, applicant_id=aid, requested_program_id=target, baseline_run_id=current["id"],
            solver_status=cf.solve.status, feasible=cf.feasible, displaced_count=cf.displaced_count,
            preference_delta=cf.preference_delta, result=cf.to_dict(),
        )

    with right:
        if "last_cf" in st.session_state:
            cf, who, tlabel = st.session_state["last_cf"]
            status_badge(cf.solve.status, cf.solve.explanation)
            if cf.recommendation.startswith("GRANT"):
                st.success(cf.recommendation)
            elif cf.recommendation.startswith("REVIEW"):
                st.warning(cf.recommendation)
            else:
                st.error(cf.recommendation)
            if cf.feasible:
                m = cf.metrics
                a, b, cc, d = st.columns(4)
                a.metric("Others displaced", cf.displaced_count)
                b.metric("Preference Δ", m["points_delta"], help="Total preference points, alternative minus baseline")
                cc.metric("Seated Δ", m["after_assigned"] - m["before_assigned"])
                d.metric("Validator", "PASS" if cf.validation.ok else "FAIL")
                st.plotly_chart(sankey_displacement(problem, cf.baseline, cf.alternative, "Ripple effect of granting this appeal"), width="stretch", key="appeal_sankey")
                rows = [{
                    "Applicant": f"{r.name} ({r.applicant_id})", "Role": r.kind,
                    "Before": labels[r.before_program], "After": labels[r.after_program],
                    "Choice before": r.before_rank, "Choice after": r.after_rank, "Δ points": r.points_delta,
                } for r in cf.ripple]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            for n in cf.solve.notes:
                st.caption("• " + n)
            name = who.split(" · ")[1].split(" — ")[0]
            pdf = appeal_pdf(problem, cf, name, tlabel.split(" — ")[0])
            st.download_button("Download appeal report (PDF)", pdf, f"appeal_{cf.applicant_id}_{cf.target_program_id}.pdf", "application/pdf")
        else:
            st.info("Pick an appellant and a program, then simulate. Nothing is changed in the live allocation; the engine solves a cloned copy.")

    st.divider()
    st.subheader("Appeal history")
    st.dataframe(db.load_appeals(c), hide_index=True, width="stretch")
