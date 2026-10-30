"""Administrator workspace — 12 sidebar sections. Consistent with the college site; no solver internals in normal views."""
from __future__ import annotations

import json
from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import db_manager as db
from optimization import reallocation_engine as re_
from optimization.validator import validate
from reports.application_pdf import dataframe_pdf
from services import application_service as aps, notification_service as ns
from ui.common import appeal_pdf, assignment_df, occupancy_chart, rank_chart, sankey_displacement, status_badge

SECTIONS = ["📊 Overview", "🎓 Program Management", "📥 All Applications", "✅ Selected Candidates", "⚙️ Allocation Management",
            "🔄 Reallocation Management", "⚖️ Appeals", "📈 Analytics", "🔔 Notifications", "📣 Announcements", "🧾 Audit History", "🛠 Settings"]

CSS = """<style>
.ad-card { border-radius:16px; padding:16px 18px; background:#fff; border:1px solid rgba(15,23,42,.08); box-shadow:0 8px 24px rgba(11,31,58,.06); }
.ad-card b { display:block; font-size:1.7rem; font-weight:900; color:#0B1F3A; } .ad-card span { color:#64748B; font-size:.82rem; font-weight:600; letter-spacing:.4px; text-transform:uppercase; }
</style>"""


def _card(col, label, value):
    col.markdown(f"<div class='ad-card'><b>{value}</b><span>{label}</span></div>", unsafe_allow_html=True)


def _publish_feedback(out):
    if out is None:
        st.info("No allocation published yet; nothing to re-run."); return
    status_badge(out.solve.status, out.solve.explanation)
    if out.published:
        st.success(out.message + f" Offers: {out.offers}. Notified {len(out.notified)} applicant(s).")
        if out.comparison:
            cmp = out.comparison
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Moved", cmp["moved_count"]); c2.metric("Newly seated", len(cmp["newly_seated"])); c3.metric("Lost seat", len(cmp["lost_seat"])); c4.metric("Preference Δ", cmp["points_delta"])
            st.plotly_chart(sankey_displacement(out.problem, out.problem.previous, out.solve.assignment), width="stretch", key=f"sk_{out.run_id}")
    else:
        st.error(out.message)
        if out.validation and not out.validation.ok:
            st.dataframe(pd.DataFrame(out.validation.as_rows()), hide_index=True, width="stretch")


# ====================================================================== 1 Overview
def sec_overview(c):
    total = c.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
    applied = c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied'").fetchone()[0]
    programs = db.load_programs(c)
    offers = dict(c.execute("SELECT offer_status, COUNT(*) FROM applicants WHERE status='active' GROUP BY offer_status").fetchall())
    withdrawn = c.execute("SELECT COUNT(*) FROM applicants WHERE status='withdrawn'").fetchone()[0]
    pending_appeals = c.execute("SELECT COUNT(*) FROM appeals WHERE decision IN ('submitted','evaluated')").fetchone()[0]
    pending_wd = c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='requested'").fetchone()[0]
    run = db.get_current_run(c)
    r1 = st.columns(5); r2 = st.columns(5)
    _card(r1[0], "Registered students", total); _card(r1[1], "Applications", applied); _card(r1[2], "Programs", len(programs))
    _card(r1[3], "Total seats", int(programs.capacity.sum())); _card(r1[4], "Allocated", offers.get("provisional", 0) + offers.get("confirmed", 0))
    _card(r2[0], "Confirmed", offers.get("confirmed", 0)); _card(r2[1], "Waitlisted", offers.get("waitlisted", 0)); _card(r2[2], "Withdrawn", withdrawn)
    _card(r2[3], "Pending appeals", pending_appeals); _card(r2[4], "Pending withdrawals", pending_wd)
    st.markdown("")
    if db.admin_uses_default_password(c):
        st.warning("The administrator account still uses the default password. Change it under Settings.")
    if run:
        st.info(f"Current allocation: version **#{run['id']}** · {run['mode']} · solver status {run['solver_status']} · {run['created_at']}")
        problem = db.build_problem(c); st.plotly_chart(occupancy_chart(problem, dict(problem.previous)), width="stretch", key="ov_occ")
    else:
        st.info("No allocation has been published yet. Go to Allocation Management.")
    st.markdown("**Recent activity**"); st.dataframe(db.load_audit(c, 12), hide_index=True, width="stretch")


# ====================================================================== 2 Program Management
def sec_programs(c):
    programs = db.load_programs(c)
    cur = db.get_current_assignment_map(c); used = Counter(cur.values())
    view = programs.copy(); view["allocated"] = view.id.map(lambda i: used.get(int(i), 0)); view["vacant"] = view.capacity - view.allocated
    view["applications"] = view.id.map(lambda i: c.execute("SELECT COUNT(*) FROM preferences WHERE program_id=?", (int(i),)).fetchone()[0])
    st.dataframe(view[["id", "code", "name", "department", "duration", "capacity", "allocated", "vacant", "min_score", "required_track", "is_open", "applications"]], hide_index=True, width="stretch")
    st.markdown("#### Add or edit a program")
    labels = {"— new program —": None} | {f"{r.code} · {r.name}": int(r.id) for r in programs.itertuples()}
    pick = st.selectbox("Program", list(labels), key="pm_pick"); pid = labels[pick]
    row = programs[programs.id == pid].iloc[0] if pid else None
    with st.form("pm_form"):
        c1, c2, c3 = st.columns(3)
        code = c1.text_input("Program ID / code", value=row.code if row is not None else "", key="pm_code")
        name = c2.text_input("Program name", value=row["name"] if row is not None else "", key="pm_name")
        dept = c3.text_input("Department / school", value=(row.department or "") if row is not None else "", key="pm_dept")
        c4, c5, c6, c7 = st.columns(4)
        cap = c4.number_input("Capacity", 0, 2000, int(row.capacity) if row is not None else 30, key="pm_cap")
        mins = c5.number_input("Minimum entrance score (CUET/entrance requirement)", 0, 100, int(row.min_score) if row is not None else 50, key="pm_min")
        track = c6.selectbox("Required track", ["Any"] + db.TRACKS, index=(["Any"] + db.TRACKS).index(row.required_track) if row is not None and row.required_track in db.TRACKS else 0, key="pm_track")
        dur = c7.text_input("Duration", value=(row.duration or "") if row is not None else "3 years", key="pm_dur")
        desc = st.text_area("Description", value=(row.description or "") if row is not None else "", key="pm_desc", height=80)
        is_open = st.checkbox("Open for applications", value=bool(int(row.is_open or 0)) if row is not None else True, key="pm_open")
        save = st.form_submit_button("Save program", type="primary")
    if save:
        try:
            db.upsert_program(c, program_id=pid, code=code, name=name, capacity=int(cap), min_score=int(mins), required_track=None if track == "Any" else track,
                              department=dept, duration=dur, description=desc, is_open=is_open)
            st.success("Saved." + (" Capacity changed: run a reallocation under Reallocation Management." if row is not None and int(cap) != int(row.capacity) else "")); st.rerun()
        except ValueError as e:
            st.error(str(e))
    if pid:
        refs = db.program_references(c, pid)
        if st.button("Delete program", key="pm_delete"):
            try:
                db.delete_program(c, pid); st.success("Deleted."); st.rerun()
            except ValueError as e:
                st.error(str(e) + " — uncheck 'Open for applications' to retire it instead.")
        st.caption(f"References: {refs}")


# ====================================================================== 3 All Applications
def _applications_df(c) -> pd.DataFrame:
    df = db.load_applicants_full(c)
    prefs = db.load_preferences(c).groupby("applicant_id").apply(lambda g: " › ".join(g.sort_values("rank").code), include_groups=False)
    cur = db.get_current_assignment_map(c); codes = {int(r.id): r.code for r in db.load_programs(c).itertuples()}
    df["Application ID"] = df.id.map(db.app_id); df["Preferences"] = df.id.map(prefs).fillna("")
    df["Allocation"] = df.id.map(lambda i: codes.get(cur.get(int(i)), "waitlisted" if cur and int(i) not in cur else "—"))
    return df


def sec_applications(c):
    df = _applications_df(c)
    f1, f2, f3, f4 = st.columns(4)
    q = f1.text_input("Applicant name / Application ID / email", key="aa_q")
    prog = f2.multiselect("Program (ranked or allocated)", sorted(db.load_programs(c).code), key="aa_prog")
    status = f3.multiselect("Application status", ["registered", "applied"], key="aa_status")
    elig = f4.multiselect("Eligibility", ["pending", "eligible", "ineligible"], key="aa_elig")
    d1, d2 = st.columns(2)
    start = d1.date_input("Submitted from", value=None, key="aa_from"); end = d2.date_input("Submitted to", value=None, key="aa_to")
    v = df.copy()
    if q:
        m = v.name.str.contains(q, case=False) | v.email.str.contains(q, case=False) | v["Application ID"].str.contains(q.upper())
        aid = db.parse_app_id(q)
        if aid: m |= v.id == aid
        v = v[m]
    if prog: v = v[v.Preferences.apply(lambda s: any(p in s.split(" › ") for p in prog)) | v.Allocation.isin(prog)]
    if status: v = v[v.application_status.isin(status)]
    if elig: v = v[v.eligibility_status.isin(elig)]
    if start: v = v[pd.to_datetime(v.applied_at) >= pd.Timestamp(start)]
    if end: v = v[pd.to_datetime(v.applied_at) <= pd.Timestamp(end) + pd.Timedelta(days=1)]
    v = v.sort_values("applied_at", ascending=False)
    cols = ["Application ID", "name", "email", "phone", "applied_at", "application_status", "Preferences", "eligibility_status", "offer_status", "Allocation", "status"]
    st.dataframe(v[cols], hide_index=True, width="stretch", height=420)
    e1, e2, e3 = st.columns(3)
    e1.download_button("⬇ CSV", v[cols].to_csv(index=False).encode(), "applications.csv", "text/csv", key="aa_csv", width="stretch")
    e2.download_button("⬇ PDF", dataframe_pdf(v[cols], "All applications", f"{len(v)} records"), "applications.pdf", "application/pdf", key="aa_pdf", width="stretch")
    if e3.button("Verify eligibility for all", key="aa_verify", width="stretch"):
        st.success(f"Eligibility verified: {aps.verify_all_eligibility(c)}"); st.rerun()
    st.markdown("#### Application details")
    labels = {f"{r['Application ID']} · {r['name']}": int(r["id"]) for _, r in v.iterrows()}
    if labels:
        pick = st.selectbox("Open", list(labels), key="aa_pick"); aid = labels[pick]
        row = c.execute("SELECT * FROM applicants WHERE id=?", (aid,)).fetchone()
        l, r = st.columns(2)
        with l:
            st.write(f"**{row['name']}** · {row['email']} · {row['phone'] or '—'}"); st.write(f"Address: {row['address'] or '—'}")
            st.write(f"Score {row['score']} · {row['track']} · eligibility {row['eligibility_status']} · offer {row['offer_status']} · {row['status']}")
            st.json(json.loads(row["form_data"] or "{}"), expanded=False)
            st.write("Tracking: " + " → ".join(f"{'✅' if d else '⬜'} {n}" for n, d in aps.tracking(c, row)))
        with r:
            for rel, title in ((row["marksheet_path"], "12th Board Marksheet"), (row["scorecard_path"], "Entrance Scorecard")):
                p = db.resolve_document(rel)
                if p is not None: st.download_button(f"⬇ {title}", p.read_bytes(), p.name, key=f"aa_dl_{title}_{aid}")
                else: st.caption(f"{title}: {rel or 'not uploaded'}" + (" (simulated seed record)" if rel else ""))
            st.dataframe(db.load_notifications(c, aid)[["created_at", "channel", "event", "status"]].head(8), hide_index=True, width="stretch")


# ====================================================================== 4 Selected Candidates
def sec_selected(c):
    run = db.get_current_run(c)
    if run is None:
        st.info("No allocation published yet."); return
    programs = db.load_programs(c); cur = db.get_current_assignment_map(c)
    used = Counter(cur.values()); confirmed = db.confirmed_assignment_map(c)
    summary = pd.DataFrame([{"Program ID": r.code, "Program": r["name"], "Capacity": int(r.capacity), "Allocated": used.get(int(r.id), 0),
                             "Confirmed": sum(1 for a, p in confirmed.items() if p == int(r.id)), "Vacant": int(r.capacity) - used.get(int(r.id), 0),
                             "Waitlisted (ranked it)": c.execute("""SELECT COUNT(*) FROM preferences pr JOIN applicants a ON a.id=pr.applicant_id
                                WHERE pr.program_id=? AND a.offer_status='waitlisted' AND a.status='active'""", (int(r.id),)).fetchone()[0]}
                            for _, r in programs.iterrows()])
    st.dataframe(summary, hide_index=True, width="stretch")
    pick = st.selectbox("Program", [f"{r.code} · {r['name']}" for _, r in programs.iterrows()], key="sc_prog")
    code = pick.split(" · ")[0]; pid = int(programs[programs.code == code].iloc[0].id)
    rows = pd.read_sql_query("""SELECT ap.id, ap.name, ap.email, ap.phone, ap.score, ap.track, a.rank_obtained AS preference, ap.offer_status
                                FROM assignments a JOIN applicants ap ON ap.id=a.applicant_id WHERE a.run_id=? AND a.program_id=? ORDER BY a.rank_obtained, ap.score DESC""", c, params=(run["id"], pid))
    rows.insert(0, "Application ID", rows.id.map(db.app_id)); rows["Status"] = rows.offer_status.map({"confirmed": "Confirmed", "provisional": "Provisional"}).fillna("Selected")
    s1, s2 = st.columns(2); q = s1.text_input("Search candidates", key="sc_q"); fs = s2.multiselect("Status", ["Provisional", "Confirmed"], key="sc_status")
    v = rows
    if q: v = v[v.name.str.contains(q, case=False) | v["Application ID"].str.contains(q.upper())]
    if fs: v = v[v.Status.isin(fs)]
    st.markdown(f"**{code}** · {len(rows)} allocated of {int(programs[programs.code == code].iloc[0].capacity)} seats")
    show = v[["Application ID", "name", "email", "phone", "score", "preference", "Status"]].rename(columns={"name": "Applicant", "preference": "Preference"})
    st.dataframe(show, hide_index=True, width="stretch")
    e1, e2 = st.columns(2)
    e1.download_button(f"⬇ {code} candidates CSV", show.to_csv(index=False).encode(), f"selected_{code}.csv", "text/csv", key="sc_csv", width="stretch")
    e2.download_button(f"⬇ {code} candidates PDF", dataframe_pdf(show, f"Selected candidates · {code}", f"Allocation version #{run['id']}"), f"selected_{code}.pdf", "application/pdf", key="sc_pdf", width="stretch")
    if len(v):
        who = st.selectbox("Candidate details", [f"{r['Application ID']} · {r['name']}" for _, r in v.iterrows()], key="sc_who")
        aid = int(v[v["Application ID"] == who.split(" · ")[0]].iloc[0].id); row = c.execute("SELECT * FROM applicants WHERE id=?", (aid,)).fetchone()
        st.write(f"{row['name']} · {row['email']} · {row['phone'] or '—'} · score {row['score']} · {row['track']} · offer {row['offer_status']}")


# ====================================================================== 5 Allocation Management
def sec_allocation(c):
    settings = db.get_settings(c)
    st.markdown(f"Policy in force: **{settings['objective_mode']}** · max preferences {settings['max_preferences']} · confirmed seats locked: {'yes' if settings['lock_confirmed_seats']=='1' else 'no'} (change under Settings)")
    run = db.get_current_run(c)
    if run: st.info(f"Current version #{run['id']} · {run['mode']} · {run['solver_status']} · {run['assigned_count']} seated · {run['created_at']}")
    c1, c2 = st.columns([1, 2])
    with c1:
        tl = st.slider("Time limit (s)", 1, 60, 20, key="al_tl")
        if st.button("▶ Run initial allocation", type="primary", key="al_run", width="stretch"):
            with st.spinner("Allocating…"):
                st.session_state["al_out"] = re_.run_initial(c, time_limit_s=tl)
            st.rerun()
        if st.button("Send provisional-offer notifications again", key="al_renotify", width="stretch") and run:
            n = 0
            for a, p in db.get_current_assignment_map(c).items():
                r = ns.notify(c, a, "provisional_offer", {"program": db.load_programs(c).set_index("id").loc[p, "code"]}, dedupe=f"offer_resend:{run['id']}")
                n += r.get("in_app") == "sent"
            st.success(f"Queued for {n} applicants (duplicates skipped).")
    with c2:
        out = st.session_state.get("al_out")
        if out: _publish_feedback(out)
        if run:
            problem = db.build_problem(c); st.plotly_chart(rank_chart(type("R", (), {"rank_histogram": re_.technical_summary(c)["rank_histogram"]})()), width="stretch", key="al_rank")
    with st.expander("Technical allocation summary (administrators)"):
        st.json(re_.technical_summary(c) if run else {"info": "no run"})
        if run:
            problem = db.build_problem(c); rep = validate(problem, dict(problem.previous))
            st.success("Independent validation: PASS — " + ", ".join(rep.checks_run)) if rep.ok else st.error(f"Validation: {len(rep.violations)} violation(s) — reallocate")
    st.markdown("**Allocation versions**"); st.dataframe(db.load_runs(c)[["id", "mode", "solver_status", "assigned_count", "reassigned_count", "preference_score", "created_at", "notes"]], hide_index=True, width="stretch")


# ====================================================================== 6 Reallocation Management
def sec_reallocation(c):
    st.markdown("#### Withdrawal requests")
    pending = db.load_withdrawals(c, "requested")
    if pending.empty: st.info("No pending withdrawal requests.")
    else:
        st.dataframe(pending[["id", "requested_at", "applicant", "email", "reason"]], hide_index=True, width="stretch")
        pick = st.selectbox("Request", [f"#{r.id} · {r.applicant}" for r in pending.itertuples()], key="rw_pick"); wid = int(pick.split(" · ")[0][1:])
        a1, a2 = st.columns(2)
        if a1.button("Authorise withdrawal and reallocate", type="primary", key="rw_approve", width="stretch"):
            with st.spinner("Releasing seat and re-optimising…"):
                st.session_state["rw_out"] = re_.process_withdrawal(c, wid, approve=True, actor="admin")
            st.rerun()
        if a2.button("Reject request", key="rw_reject", width="stretch"):
            re_.process_withdrawal(c, wid, approve=False, actor="admin"); st.rerun()
    if "rw_out" in st.session_state:
        st.markdown("**Result of the last authorised withdrawal**"); _publish_feedback(st.session_state["rw_out"])
    st.divider(); st.markdown("#### Capacity changes")
    programs = db.load_programs(c)
    c1, c2, c3 = st.columns(3)
    sel = c1.selectbox("Program", programs.code.tolist(), key="rc_prog"); row = programs[programs.code == sel].iloc[0]
    newcap = c2.number_input("New capacity", 0, 2000, int(row.capacity), key="rc_cap"); reason = c3.text_input("Reason", "Seats revised", key="rc_reason")
    if st.button("Apply capacity change and reallocate", key="rc_apply"):
        with st.spinner("Re-optimising…"):
            st.session_state["rc_out"] = re_.change_capacity(c, int(row.id), int(newcap), reason)
        st.rerun()
    if "rc_out" in st.session_state: _publish_feedback(st.session_state["rc_out"])
    st.divider(); st.markdown("#### Vacancies")
    rep = re_.vacancy_report(c)
    if rep: st.dataframe(pd.DataFrame(rep), hide_index=True, width="stretch")
    else: st.success("No vacant seats, or no allocation yet.")
    if st.button("Run minimal-disruption reallocation now", key="rc_run"):
        with st.spinner("Re-optimising…"):
            st.session_state["rc_out"] = re_.run_reallocation(c, "manual run from Reallocation Management")
        st.rerun()
    st.markdown("**History**"); st.dataframe(db.load_withdrawals(c), hide_index=True, width="stretch"); st.dataframe(db.load_capacity_changes(c), hide_index=True, width="stretch")


# ====================================================================== 7 Appeals
def sec_appeals(c):
    df = aps.load_appeals_full(c)
    st.dataframe(df[["id", "created_at", "source", "applicant", "current_program", "requested", "reason", "solver_status", "feasible", "displaced_count", "decision"]], hide_index=True, width="stretch", height=260)
    open_ = df[df.decision.isin(["submitted", "evaluated"])]
    if open_.empty: st.info("No appeals awaiting a decision."); return
    pick = st.selectbox("Appeal", [f"#{r.id} · {r.applicant} → {r.requested}" for r in open_.itertuples()], key="ap_pick"); apid = int(pick.split(" · ")[0][1:])
    ap = open_[open_.id == apid].iloc[0]
    st.write(f"**{ap.applicant}** requests **{ap.requested}** (currently {ap.current_program or 'unassigned'}). Reason: _{ap.reason or '—'}_")
    if st.button("Evaluate (counterfactual)", type="primary", key="ap_eval"):
        with st.spinner("Evaluating alternative allocation…"):
            st.session_state["ap_cf"] = (apid, aps.evaluate_existing_appeal(c, apid))
        st.rerun()
    if st.session_state.get("ap_cf", (None,))[0] == apid:
        cf = st.session_state["ap_cf"][1]; problem = db.build_problem(c)
        status_badge(cf.solve.status, cf.solve.explanation)
        (st.success if cf.recommendation.startswith("GRANT") else st.warning if cf.recommendation.startswith("REVIEW") else st.error)(cf.recommendation)
        if cf.feasible:
            m = cf.metrics; k = st.columns(5)
            k[0].metric("Feasible", "Yes"); k[1].metric("Others affected", cf.displaced_count); k[2].metric("Preference Δ", m["points_delta"]); k[3].metric("Seated Δ", m["after_assigned"] - m["before_assigned"]); k[4].metric("Validator", "PASS" if cf.validation.ok else "FAIL")
            st.plotly_chart(sankey_displacement(problem, cf.baseline, cf.alternative, "Effect of granting this appeal"), width="stretch", key="ap_sankey")
            util = Counter(cf.alternative.values()); st.caption("Resulting utilisation: " + ", ".join(f"{p.code} {util.get(p.id,0)}/{p.capacity}" for p in problem.programs))
            st.dataframe(pd.DataFrame([{"Applicant": f"{r.name} ({db.app_id(r.applicant_id)})", "Role": r.kind, "Before": r.before_program, "After": r.after_program, "Δ points": r.points_delta} for r in cf.ripple]), hide_index=True, width="stretch")
        st.download_button("⬇ Appeal evaluation (PDF)", appeal_pdf(problem, cf, ap.applicant, ap.requested), f"appeal_{apid}.pdf", "application/pdf", key="ap_pdf")
        d1, d2 = st.columns(2)
        if d1.button("Accept appeal and publish", key="ap_accept", width="stretch", disabled=not cf.feasible):
            try:
                rid = aps.decide_appeal(c, apid, True); st.success(f"Accepted; published version #{rid}."); st.session_state.pop("ap_cf", None); st.rerun()
            except ValueError as e: st.error(str(e))
        if d2.button("Reject appeal", key="ap_reject", width="stretch"):
            aps.decide_appeal(c, apid, False); st.session_state.pop("ap_cf", None); st.rerun()


# ====================================================================== 8 Analytics
def sec_analytics(c):
    programs = db.load_programs(c); cur = db.get_current_assignment_map(c); run = db.get_current_run(c)
    if db.get_setting(c, "demo_mode") == "1": st.caption("Demonstration mode: applicant data is synthetic; charts are computed live from the database.")
    prefs = db.load_preferences(c)
    dist = prefs[prefs["rank"] == 1].groupby("code").size().reindex(programs.code, fill_value=0).reset_index(name="first-choice applications")
    st.plotly_chart(px.bar(dist, x="code", y="first-choice applications", title="Application distribution (first choice)"), width="stretch", key="an_dist")
    if run:
        used = Counter(cur.values()); seats = pd.DataFrame([{"Program": r.code, "Allocated": used.get(int(r.id), 0), "Vacant": max(0, int(r.capacity) - used.get(int(r.id), 0))} for r in programs.itertuples()])
        fig = go.Figure(); fig.add_bar(name="Allocated", x=seats.Program, y=seats.Allocated); fig.add_bar(name="Vacant", x=seats.Program, y=seats.Vacant); fig.update_layout(barmode="stack", title="Program-wise seat utilisation")
        st.plotly_chart(fig, width="stretch", key="an_util")
        offers = pd.DataFrame(c.execute("SELECT offer_status, COUNT(*) n FROM applicants WHERE status='active' AND application_status='applied' GROUP BY offer_status").fetchall(), columns=["status", "n"])
        a, b = st.columns(2)
        a.plotly_chart(px.pie(offers, names="status", values="n", title="Selected · confirmed · waitlisted"), width="stretch", key="an_offers")
        hist = re_.technical_summary(c)["rank_histogram"]
        b.plotly_chart(px.bar(x=[f"Choice #{k}" for k in hist], y=list(hist.values()), title="Preference satisfaction"), width="stretch", key="an_pref")
        runs = db.load_runs(c).sort_values("id")
        st.plotly_chart(px.line(runs, x="id", y="reassigned_count", markers=True, title="Reallocation statistics (applicants moved per version)"), width="stretch", key="an_realloc")
    ap = aps.load_appeals_full(c)
    w = db.load_withdrawals(c)
    k = st.columns(4); k[0].metric("Appeals", len(ap)); k[1].metric("Appeals accepted", int((ap.decision == "accepted").sum()) if len(ap) else 0); k[2].metric("Withdrawals approved", int((w.status == "approved").sum()) if len(w) else 0); k[3].metric("Versions", len(db.load_runs(c)))


# ====================================================================== 9 Notifications
def sec_notifications(c):
    status = ns.integration_status()
    a, b = st.columns(2)
    (a.success if status["email"]["configured"] else a.warning)("Email: " + status["email"]["text"])
    (b.success if status["whatsapp"]["configured"] else b.warning)("WhatsApp: " + status["whatsapp"]["text"])
    with st.expander("How to configure"):
        st.markdown("Set environment variables (or Streamlit secrets): `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` (starttls|ssl) · "
                    "`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, optional `WHATSAPP_TEMPLATE`. See `.env.example`.")
    with st.form("nt_test"):
        st.markdown("**Send a test notification**")
        e, p = st.columns(2); to_e = e.text_input("Email"); to_p = p.text_input("WhatsApp number (10 digits)")
        go = st.form_submit_button("Send test")
    if go:
        for ch, res in ns.send_test(c, to_e, to_p).items():
            (st.success if res.startswith("sent") else st.error)(f"{ch}: {res}")
    df = db.load_notifications(c, limit=500)
    f1, f2 = st.columns(2); ch = f1.multiselect("Channel", ["in_app", "email", "whatsapp"], key="nt_ch"); stt = f2.multiselect("Status", ["sent", "failed", "not_configured", "skipped"], key="nt_st")
    if ch: df = df[df.channel.isin(ch)]
    if stt: df = df[df.status.isin(stt)]
    st.dataframe(df, hide_index=True, width="stretch", height=380)
    st.caption("Statuses reflect the provider's real response. 'not_configured' means no credentials were present; nothing was sent.")


# ====================================================================== 10 Announcements
def sec_announcements(c):
    with st.form("ann_form", clear_on_submit=True):
        t = st.text_input("Title"); b = st.text_area("Message", height=90); aud = st.selectbox("Audience", ["all", "students", "public"])
        ok = st.form_submit_button("Post announcement", type="primary")
    if ok and t.strip() and b.strip():
        db.add_announcement(c, t, b, aud); st.rerun()
    df = db.load_announcements(c, active_only=False)
    st.dataframe(df, hide_index=True, width="stretch")
    if len(df):
        pick = st.selectbox("Toggle", [f"#{r.id} · {r.title}" for r in df.itertuples()], key="ann_pick"); aid = int(pick.split(" · ")[0][1:])
        active = bool(df[df.id == aid].iloc[0].is_active)
        if st.button("Deactivate" if active else "Activate", key="ann_toggle"): db.set_announcement_active(c, aid, not active); st.rerun()
    st.divider(); st.markdown("**Website text (CMS)**")
    content = db.get_site_content(c)
    with st.form("cms_form"):
        new = {k: st.text_area(lbl, value=content.get(k, ""), height=68 if k in ("institute_name", "hero_title", "hero_subtitle", "contact_info") else 120, key=f"cms_{k}") for k, (lbl, _) in db.DEFAULT_SITE_CONTENT.items()}
        saved = st.form_submit_button("Save website text", type="primary")
    if saved:
        for k, v in new.items():
            if v != content.get(k, ""): db.set_site_content(c, k, v.strip())
        st.rerun()


# ====================================================================== 11 Audit History
def sec_audit(c):
    run = db.get_current_run(c)
    if run:
        problem = db.build_problem(c); rep = validate(problem, dict(problem.previous))
        st.success("Independent validation of current version: PASS — " + ", ".join(rep.checks_run)) if rep.ok else st.error(f"{len(rep.violations)} violation(s)")
        if not rep.ok: st.dataframe(pd.DataFrame(rep.as_rows()), hide_index=True, width="stretch")
    st.markdown("**Allocation versions** (each traceable to its policy snapshot)"); st.dataframe(db.load_runs(c), hide_index=True, width="stretch", height=220)
    st.markdown("**Audit log**")
    q = st.text_input("Filter action / details", key="au_q"); df = db.load_audit(c, 1000)
    if q: df = df[df.action.str.contains(q, case=False) | df.details.fillna("").str.contains(q, case=False)]
    st.dataframe(df, hide_index=True, width="stretch", height=420)
    st.download_button("⬇ Audit CSV", df.to_csv(index=False).encode(), "audit.csv", "text/csv", key="au_csv")


# ====================================================================== 12 Settings
def sec_settings(c):
    s = db.get_settings(c)
    st.markdown("#### Allocation policy")
    with st.form("set_policy"):
        mode = st.selectbox("Objective hierarchy", ["preference_first", "merit_first"], index=0 if s["objective_mode"] == "preference_first" else 1,
                            help="preference_first: maximise ranked-preference satisfaction, entrance score breaks ties. merit_first: fill seats, then entrance-score merit, then preferences, then earliest application. No other merit weightings are applied.")
        maxp = st.number_input("Maximum preferences per applicant", 1, 10, int(s["max_preferences"]))
        lock = st.checkbox("Confirmed admissions are never moved by reallocation", value=s["lock_confirmed_seats"] == "1")
        mu = st.number_input("Reallocation displacement penalty (1000 = never disturb seated applicants; 1 = allow upgrades into vacancies)", 1, 100000, int(float(s["reallocation_mu"])))
        days = st.number_input("Offer acceptance window (days, informational)", 1, 60, int(s["offer_accept_days"]))
        sess = st.text_input("Academic session", s["academic_session"]); tag = st.text_input("Institute tagline", s["institute_tagline"])
        demo = st.checkbox("Demonstration mode banner", value=s["demo_mode"] == "1")
        ok = st.form_submit_button("Save settings", type="primary")
    if ok:
        for k, v in {"objective_mode": mode, "max_preferences": maxp, "lock_confirmed_seats": int(lock), "reallocation_mu": mu, "offer_accept_days": days,
                     "academic_session": sess, "institute_tagline": tag, "demo_mode": int(demo)}.items():
            if str(v) != str(s.get(k)): db.set_setting(c, k, str(v))
        st.success("Saved. Policy changes apply to the next allocation run."); st.rerun()
    st.markdown("#### Administrator account")
    with st.form("set_pw"):
        old = st.text_input("Current password", type="password"); new = st.text_input("New password", type="password"); new2 = st.text_input("Confirm new password", type="password")
        ok2 = st.form_submit_button("Change password")
    if ok2:
        if not db.check_admin_login(c, "admin", old): st.error("Current password is incorrect.")
        elif new != new2 or len(new) < 6: st.error("New passwords must match and be at least 6 characters.")
        else: db.set_admin_password(c, "admin", new); st.success("Password changed.")
    st.markdown("#### Application form fields")
    schema = db.load_form_schema(c)
    st.dataframe(pd.DataFrame([{"Label": f["label"], "Type": f["field_type"], "Required": f["required"], "Options": ", ".join(f["options"])} for f in schema]), hide_index=True, width="stretch")
    a1, a2 = st.columns(2)
    with a1, st.form("add_field", clear_on_submit=True):
        label = st.text_input("Label"); ftype = st.selectbox("Type", ["text", "number", "select"]); req = st.checkbox("Required", True); opts = st.text_input("Options (comma separated, select only)")
        if st.form_submit_button("Add field") and label.strip():
            try: db.add_form_field(c, label=label, field_type=ftype, required=req, options=[o.strip() for o in opts.split(",") if o.strip()] or None); st.rerun()
            except ValueError as e: st.error(str(e))
    with a2:
        if schema:
            rm = st.selectbox("Remove field", [f["field_key"] for f in schema], format_func=lambda k: next(f["label"] for f in schema if f["field_key"] == k), key="rm_field")
            if st.button("Remove", key="rm_btn"): db.remove_form_field(c, rm); st.rerun()
    st.markdown("#### Integrations"); st.json(ns.integration_status())
    with st.expander("Danger zone"):
        if st.button("Reset database to demonstration seed (200 applicants)", key="reset_db"):
            db.reset_db(c); db.seed_demo(c)
            for k in ("al_out", "rw_out", "rc_out", "ap_cf"): st.session_state.pop(k, None)
            st.rerun()


def render(c) -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if st.session_state.get("admin_nav") not in SECTIONS: st.session_state["admin_nav"] = SECTIONS[0]
    with st.sidebar:
        st.markdown("#### Admin menu"); section = st.radio("Admin menu", SECTIONS, key="admin_nav", label_visibility="collapsed")
    st.markdown(f"<h1 style='margin-bottom:0'>{db.get_site_text(c, 'institute_name', 'Institute')}</h1><p style='color:gray;margin-top:4px'>Administrator · {section}</p>", unsafe_allow_html=True)
    {SECTIONS[0]: sec_overview, SECTIONS[1]: sec_programs, SECTIONS[2]: sec_applications, SECTIONS[3]: sec_selected, SECTIONS[4]: sec_allocation,
     SECTIONS[5]: sec_reallocation, SECTIONS[6]: sec_appeals, SECTIONS[7]: sec_analytics, SECTIONS[8]: sec_notifications, SECTIONS[9]: sec_announcements,
     SECTIONS[10]: sec_audit, SECTIONS[11]: sec_settings}[section](c)
