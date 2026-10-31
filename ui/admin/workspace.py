"""Administrator workspace — 12 sidebar sections. Consistent with the college site; no solver internals in normal views."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter

import importlib

import pandas as pd
import streamlit as st

from database import db_manager as db
from services import notification_service as ns
from ui import auth
from ui import design as ds
from ui.common import BRAND
from ui.design import esc


class _Lazy:
    """Import a module on first attribute access (keeps OR-Tools / Plotly / ReportLab out of startup memory)."""
    def __init__(self, name): self._n, self._m = name, None
    def __getattr__(self, item):
        if self._m is None:
            self._m = importlib.import_module(self._n)
        return getattr(self._m, item)


re_ = _Lazy("optimization.reallocation_engine")
aps = _Lazy("services.application_service")
_val = _Lazy("optimization.validator")
_pdf = _Lazy("reports.application_pdf")
_cm = _Lazy("ui.common")
px = _Lazy("plotly.express")
go = _Lazy("plotly.graph_objects")


def validate(*a, **k): return _val.validate(*a, **k)
def dataframe_pdf(*a, **k): return _pdf.dataframe_pdf(*a, **k)
def appeal_pdf(*a, **k): return _cm.appeal_pdf(*a, **k)
def assignment_df(*a, **k): return _cm.assignment_df(*a, **k)
def occupancy_chart(*a, **k): return _cm.occupancy_chart(*a, **k)
def rank_chart(*a, **k): return _cm.rank_chart(*a, **k)
def sankey_displacement(*a, **k): return _cm.sankey_displacement(*a, **k)
def status_badge(*a, **k): return _cm.status_badge(*a, **k)

SECTIONS = [":material/dashboard: Overview", ":material/school: Program Management", ":material/inbox: All Applications", ":material/verified: Selected Candidates",
            ":material/tune: Allocation Management", ":material/sync_alt: Reallocation Management", ":material/balance: Appeals", ":material/monitoring: Analytics",
            ":material/notifications: Notifications", ":material/campaign: Announcements", ":material/history: Audit History", ":material/settings: Settings",
            ":material/logout: Withdrawals", ":material/upload_file: Data Upload"]
LOGO = "app/static/images/logo.png"


def _plain(nav: str) -> str:
    return nav.split(" ", 1)[1] if nav.startswith(":material/") else nav
# Sidebar groups (4 expanders) — every entry must be a member of SECTIONS.
NAV_GROUPS = [
    ("🧭 Command Center", [SECTIONS[0], SECTIONS[4], SECTIONS[5], SECTIONS[7]]),
    ("🗂 Student & Program Data", [SECTIONS[13], SECTIONS[1], SECTIONS[2], SECTIONS[3]]),
    ("⚖️ Appeals & Exceptions", [SECTIONS[6], SECTIONS[12]]),
    ("🛠 Settings & Logs", [SECTIONS[11], SECTIONS[8], SECTIONS[9], SECTIONS[10]]),
]
_GROUP_KEYS = [f"admin_nav_g{i}" for i in range(len(NAV_GROUPS))]


def _nav_changed(group_key: str) -> None:
    """A radio inside one sidebar group changed: make it the active section and clear the other groups."""
    val = st.session_state.get(group_key)
    if val is None:
        return
    st.session_state["admin_nav"] = val
    for gk in _GROUP_KEYS:
        if gk != group_key:
            st.session_state[gk] = None


def render_sidebar_nav() -> str:
    current = st.session_state.get("admin_nav")
    if current not in SECTIONS:
        current = SECTIONS[0]; st.session_state["admin_nav"] = current
    for (title, options), gk in zip(NAV_GROUPS, _GROUP_KEYS):
        st.session_state[gk] = current if current in options else None
        with st.expander(title, expanded=current in options):
            st.radio(title, options, index=None, key=gk, on_change=_nav_changed, args=(gk,), label_visibility="collapsed")
    return current

STATUS_LABELS = {"sent": "Sent", "failed": "Failed", "not_configured": "Failed - Missing Credentials", "skipped": "Skipped - no address", "duplicate": "Skipped - duplicate"}


def _status_label(status: str, detail: str = "") -> str:
    label = STATUS_LABELS.get(status, status)
    if status == "failed" and "authentication" in (detail or "").lower():
        label = "Failed - Invalid Credentials"
    return label


def goto(section: str) -> None:
    st.session_state["admin_nav"] = section


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
            st.plotly_chart(ds.plotly_style(sankey_displacement(out.problem, out.problem.previous, out.solve.assignment)), width="stretch", key=f"sk_{out.run_id}")
    else:
        st.error(out.message)
        if out.validation and not out.validation.ok:
            st.dataframe(pd.DataFrame(out.validation.as_rows()), hide_index=True, width="stretch")


def _ordinal(n) -> str:
    n = int(n); suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf} Choice"


def allocated_roster(c) -> pd.DataFrame:
    """Applicants joined with the current allocation version: everyone who holds a seat right now."""
    run = db.get_current_run(c)
    if run is None:
        return pd.DataFrame(columns=["Application ID", "Full Name", "Email", "Assigned Program", "Preference Achieved", "Status"])
    df = pd.read_sql_query("""SELECT ap.id, ap.name, ap.email, p.code || ' — ' || p.name AS program, a.rank_obtained, ap.offer_status
                              FROM assignments a JOIN applicants ap ON ap.id = a.applicant_id JOIN programs p ON p.id = a.program_id
                              WHERE a.run_id = ? AND a.program_id IS NOT NULL ORDER BY p.code, a.rank_obtained, ap.score DESC""", c, params=(run["id"],))
    return pd.DataFrame({"Application ID": df.id.map(db.app_id), "Full Name": df.name, "Email": df.email, "Assigned Program": df.program,
                         "Preference Achieved": df.rank_obtained.map(_ordinal), "Status": df.offer_status.map({"confirmed": "Confirmed", "provisional": "Provisional"}).fillna("Selected")})


def roster_block(c, key: str) -> None:
    roster = allocated_roster(c)
    st.html(f"<div class='sw-card-title'>Allocated Students <span class='sw-pill ok'>{len(roster)} seated</span></div>")
    if roster.empty:
        st.info("No allocation published yet."); return
    st.download_button("⬇ Export allocated_candidates.csv", roster.to_csv(index=False).encode(), "allocated_candidates.csv", "text/csv",
                       key=f"roster_csv_{key}", type="primary", width="stretch")
    st.dataframe(roster, hide_index=True, width="stretch", height=min(420, 40 + 35 * len(roster)))


def _pitch_demand(c, programs):
    """First-choice demand versus capacity for every programme (the bottleneck the judges should see)."""
    prefs = db.load_preferences(c)
    active = set(pd.read_sql_query("SELECT id FROM applicants WHERE status='active' AND application_status='applied'", c).id)
    first = prefs[(prefs["rank"] == 1) & prefs.applicant_id.isin(active)].groupby("program_id").size()
    return pd.DataFrame([{"Program": f"{r.code}", "Name": r.name, "First-choice demand": int(first.get(int(r.id), 0)), "Seats": int(r.capacity)} for r in programs.itertuples()])


# ====================================================================== 1 Overview — Pitch Flow
def sec_overview(c):
    programs = db.load_programs(c)
    n_students = c.execute("SELECT COUNT(*) FROM applicants WHERE status='active' AND application_status='applied'").fetchone()[0]
    seats = int(programs.capacity.sum()) if len(programs) else 0
    run = db.get_current_run(c)
    demand = _pitch_demand(c, programs)
    hot = demand.sort_values("First-choice demand", ascending=False).iloc[0] if len(demand) else None
    # ---------------- Step 1 · The Input
    ds.section("Step 1 · The Input", "The bottleneck the engine has to resolve")
    ds.kpis([("Students competing", n_students, "v"), ("Total seats", seats, ""), ("Programmes", len(programs), "b"),
             ("Most contested", f"{hot['Program']}: {hot['First-choice demand']} want {hot['Seats']} seats" if hot is not None else "—", "a")])
    if hot is not None:
        st.markdown(f"**{n_students} students competing for {seats} seats.** {hot['First-choice demand']} of them rank **{hot['Name']}** first, which has only **{hot['Seats']}** seats.")
        fig = go.Figure(); fig.add_bar(name="First-choice demand", x=demand.Program, y=demand["First-choice demand"], marker_color="#6D28D9"); fig.add_bar(name="Seats", x=demand.Program, y=demand.Seats, marker_color="#F5B301")
        fig.update_layout(barmode="group", title="First-choice demand vs seats"); st.plotly_chart(ds.plotly_style(fig, 300), width="stretch", key="pf_demand")
    # ---------------- Step 2 · The Engine
    ds.section("Step 2 · The Engine", "CP-SAT solves the whole allocation in one shot, then the independent validator checks it")
    b1, b2 = st.columns([2, 1])
    if b1.button("▶ Run Optimization (Mode A)", type="primary", key="pf_run", width="stretch"):
        with st.spinner("Verifying eligibility and allocating…"):
            aps.verify_all_eligibility(c); st.session_state["al_out"] = re_.run_initial(c, time_limit_s=20); st.session_state.pop("rc_out", None)
        st.rerun()
    b2.caption("Mode A = initial allocation under the policy in Settings (preference-first by default). Re-running publishes a new version.")
    # ---------------- Step 3 · The Output
    ds.section("Step 3 · The Output", "Who got which choice, and the full roster")
    out = st.session_state.get("al_out")
    if out is not None and out.run_id and run and out.run_id == run["id"]:
        status_badge(out.solve.status, out.solve.explanation)
        if out.validation is not None: (st.success if out.validation.ok else st.error)(("Independent validation: PASS — " + ", ".join(out.validation.checks_run)) if out.validation.ok else f"Validation failed: {len(out.validation.violations)} violation(s)")
    if run:
        ts = re_.technical_summary(c)
        o1, o2 = st.columns([1.1, 1], gap="medium")
        with o1:
            st.plotly_chart(ds.plotly_style(rank_chart(type("R", (), {"rank_histogram": ts["rank_histogram"]})()), 320), width="stretch", key="pf_rank")
            ds.facts([("Seated", ts.get("seated", run["assigned_count"])), ("Waitlisted", max(0, n_students - int(ts.get("seated", run["assigned_count"])))), ("First choice", f"{100 * ts['first_choice_rate']:.0f}%" if "first_choice_rate" in ts else "—"), ("Version", f"#{run['id']}")])
        with o2:
            roster_block(c, "pf")
    else:
        st.info("Run the optimisation to see the result.")
    # ---------------- Step 4 · The Shock
    ds.section("Step 4 · The Shock", "A programme loses seats; the engine reallocates with minimal disruption")
    if run and len(programs):
        s1, s2 = st.columns([1, 2])
        sel = s1.selectbox("Programme", programs.code.tolist(), key="pf_prog", format_func=lambda code: f"{code} — {programs.set_index('code').loc[code, 'name']}")
        row = programs[programs.code == sel].iloc[0]; cap = int(row.capacity)
        newcap = s2.slider("Simulate capacity drop → new number of seats", 0, max(cap, 1), max(0, cap - max(1, cap // 2)), key=f"pf_cap_{sel}")
        st.caption(f"{sel} currently has {cap} seats; the slider sets the new capacity ({cap - newcap} seat(s) removed).")
        if st.button("⚡ Run Reallocation (Mode B)", type="primary", key="pf_realloc", width="stretch", disabled=newcap == cap):
            with st.spinner("Re-optimising with the displacement penalty…"):
                st.session_state["rc_out"] = re_.change_capacity(c, int(row.id), int(newcap), f"Pitch simulation: capacity drop {cap}→{newcap}")
            st.rerun()
        rc = st.session_state.get("rc_out")
        if rc is not None:
            st.markdown("**Ripple effect of the capacity drop**"); _publish_feedback(rc)
            roster_block(c, "pf2")
    else:
        st.caption("Available after the first allocation.")
    with st.expander("Advanced Settings"):
        _overview_advanced(c)


def _overview_advanced(c):
    total = c.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
    applied = c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied'").fetchone()[0]
    programs = db.load_programs(c)
    offers = dict(c.execute("SELECT offer_status, COUNT(*) FROM applicants WHERE status='active' GROUP BY offer_status").fetchall())
    withdrawn = c.execute("SELECT COUNT(*) FROM applicants WHERE status='withdrawn'").fetchone()[0]
    pending_appeals = c.execute("SELECT COUNT(*) FROM appeals WHERE decision IN ('submitted','evaluated')").fetchone()[0]
    pending_wd = c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='requested'").fetchone()[0]
    unverified = c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied' AND eligibility_status='pending'").fetchone()[0]
    run = db.get_current_run(c)
    ds.kpis([("Registered students", total, "v"), ("Applications", applied, ""), ("Programs", len(programs), "b"), ("Total seats", int(programs.capacity.sum()), "b"),
             ("Allocated", offers.get("provisional", 0) + offers.get("confirmed", 0), ""), ("Confirmed", offers.get("confirmed", 0), "g"), ("Waitlisted", offers.get("waitlisted", 0), "a"),
             ("Withdrawn", withdrawn, "r"), ("Pending appeals", pending_appeals, "a"), ("Pending withdrawals", pending_wd, "a")])
    if db.admin_uses_default_password(c):
        st.warning("The administrator account still uses the default password. Change it under Settings.")
    left, right = st.columns([1.7, 1], gap="medium")
    with left:
        with ds.card("Allocation status", icon="layers"):
            if run:
                ds.facts([("Current version", f"#{run['id']}"), ("Mode", run["mode"]), ("Solver status", run["solver_status"]), ("Seated", run["assigned_count"]), ("Published", str(run["created_at"])[:16])])
                problem = db.build_problem(c); st.plotly_chart(ds.plotly_style(occupancy_chart(problem, dict(problem.previous)), 360), width="stretch", key="ov_occ")
            else:
                st.info("No allocation has been published yet. Go to Allocation Management.")
                st.button("Open Allocation Management", key="ov_go_alloc", type="primary", on_click=goto, args=(SECTIONS[4],))
        with ds.card("Program-wise seats", "Allocated versus vacant seats in the current version", icon="cap"):
            cur = db.get_current_assignment_map(c); used = Counter(cur.values())
            tbl = pd.DataFrame([{"Program": r.code, "Name": r.name, "Capacity": int(r.capacity), "Allocated": used.get(int(r.id), 0), "Vacant": int(r.capacity) - used.get(int(r.id), 0),
                                 "Min score": int(r.min_score), "Track": r.required_track if isinstance(r.required_track, str) and r.required_track else "Any"} for r in programs.itertuples()])
            st.dataframe(tbl, hide_index=True, width="stretch")
    with right:
        with ds.card("Pending administrative tasks", icon="alert"):
            tasks = [(pending_wd, "withdrawal request(s) awaiting authorisation", SECTIONS[12]), (pending_appeals, "appeal(s) awaiting a decision", SECTIONS[6]),
                     (unverified, "submitted application(s) with eligibility not yet verified", SECTIONS[2])]
            if not any(n for n, _, _ in tasks):
                st.success("Nothing pending.")
            for i, (n, label, target) in enumerate(tasks):
                if n:
                    st.html(f"<div class='sw-upnext' style='margin-bottom:8px'><span class='ic' style='width:40px;height:40px;background:#FEF3C7;color:#B45309'>{ds.ICONS['alert']}</span><div><h4 style='font-size:.95rem'>{n} {esc(label)}</h4></div></div>")
                    st.button(f"Open {_plain(target)}", key=f"ov_task_{i}", on_click=goto, args=(target,), width="stretch")
        with ds.card("Recent applications", icon="inbox"):
            rec = pd.read_sql_query("SELECT id, name, applied_at, eligibility_status FROM applicants WHERE application_status='applied' ORDER BY applied_at DESC LIMIT 6", c)
            if rec.empty: st.caption("No applications yet.")
            else:
                st.html("<ul class='sw-list'>" + "".join(f"<li><b>{esc(r.name)} <small>{db.app_id(int(r.id))}</small></b><small>{esc(str(r.applied_at)[:16])} · </small>{ds.pill(r.eligibility_status, {'eligible': 'ok', 'ineligible': 'bad'}.get(r.eligibility_status, 'muted'))}</li>" for r in rec.itertuples()) + "</ul>")
    with ds.card("Recent activity", "Latest entries of the append-only audit log", icon="clock"):
        st.dataframe(db.load_audit(c, 12), hide_index=True, width="stretch")


# ====================================================================== 2 Program Management
def sec_programs(c):
    programs = db.load_programs(c)
    cur = db.get_current_assignment_map(c); used = Counter(cur.values())
    view = programs.copy(); view["allocated"] = view.id.map(lambda i: used.get(int(i), 0)); view["vacant"] = view.capacity - view.allocated
    view["applications"] = view.id.map(lambda i: c.execute("SELECT COUNT(*) FROM preferences WHERE program_id=?", (int(i),)).fetchone()[0])
    q = st.text_input("Search programs", key="pm_q", placeholder="code, name or department")
    if q: view = view[view.code.str.contains(q, case=False) | view.name.str.contains(q, case=False) | view.department.fillna("").str.contains(q, case=False)]
    ds.kpis([("Programs", len(programs), "v"), ("Open for applications", int(programs.is_open.fillna(1).astype(int).sum()), "g"), ("Total seats", int(programs.capacity.sum()), "b"), ("Vacant seats", int(view.vacant.sum()), "a")])
    with ds.card("Programs", f"{len(view)} program(s)", icon="cap"):
        st.dataframe(view[["id", "code", "name", "department", "duration", "capacity", "allocated", "vacant", "min_score", "required_track", "is_open", "applications"]], hide_index=True, width="stretch")
    ds.section("Add or edit a program", "Capacity changes are recorded and should be followed by a reallocation")
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
        except (ValueError, sqlite3.IntegrityError) as e:
            st.error(f"Could not save: {e}")
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
    ds.kpis([("Accounts", len(df), "v"), ("Submitted", int((df.application_status == "applied").sum()), ""), ("Eligible", int((df.eligibility_status == "eligible").sum()), "g"),
             ("Ineligible", int((df.eligibility_status == "ineligible").sum()), "r"), ("Pending check", int(((df.application_status == "applied") & (df.eligibility_status == "pending")).sum()), "a")])
    ds.section("Filters")
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
    ds.section("Application details", "Contact, preferences, documents, tracking and notification history")
    labels = {f"{r['Application ID']} · {r['name']}": int(r["id"]) for _, r in v.iterrows()}
    if labels:
        pick = st.selectbox("Open", list(labels), key="aa_pick"); aid = labels[pick]
        row = c.execute("SELECT * FROM applicants WHERE id=?", (aid,)).fetchone()
        l, r = st.columns(2)
        with l, ds.card(row["name"], f"{row['email']} · {row['phone'] or '—'}", icon="user"):
            st.write(f"Address: {row['address'] or '—'}")
            ds.facts([("Score", row["score"]), ("Track", row["track"]), ("Eligibility", row["eligibility_status"]), ("Offer", row["offer_status"]), ("Status", row["status"])])
            st.json(json.loads(row["form_data"] or "{}"), expanded=False)
            stages = aps.tracking(c, row); first_open = next((i for i, (_, d) in enumerate(stages) if not d), None)
            ds.timeline([(n, "completed" if d else "pending", "d" if d else ("n" if i == first_open else "")) for i, (n, d) in enumerate(stages)])
        with r, ds.card("Documents and notifications", icon="file"):
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
    ds.kpis([("Allocated", int(summary.Allocated.sum()), ""), ("Confirmed", int(summary.Confirmed.sum()), "g"), ("Vacant", int(summary.Vacant.sum()), "a"), ("Version", f"#{run['id']}", "v")])
    with ds.card():
        roster_block(c, "sc")
    with ds.card("Program summary", icon="cap"):
        st.dataframe(summary, hide_index=True, width="stretch")
    ds.section("Candidates by program")
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
    run = db.get_current_run(c)
    ds.kpis([("Policy", settings["objective_mode"].replace("_", " "), "v"), ("Max preferences", settings["max_preferences"], ""), ("Confirmed seats locked", "yes" if settings["lock_confirmed_seats"] == "1" else "no", "g"),
             ("Offer window", f"{settings['offer_accept_days']} days", "b"), ("Current version", f"#{run['id']}" if run else "none", ""), ("Solver status", run["solver_status"] if run else "—", "g" if run and run["solver_status"] == "OPTIMAL" else "a")])
    st.caption("Policy and acceptance window are configured under Settings.")
    c1, c2 = st.columns([1, 2], gap="medium")
    with c1, ds.card("Run allocation", "Solves, validates independently, then publishes a new version", icon="layers"):
        tl = st.slider("Time limit (s)", 1, 60, 20, key="al_tl")
        sure = st.checkbox("I understand this publishes a new allocation version and notifies applicants", key="al_sure")
        if st.button("▶ Run initial allocation", type="primary", key="al_run", width="stretch", disabled=not sure):
            with st.spinner("Allocating…"):
                st.session_state["al_out"] = re_.run_initial(c, time_limit_s=tl)
            st.rerun()
        if st.button("Send provisional-offer notifications again", key="al_renotify", width="stretch") and run:
            n = 0
            for a, p in db.get_current_assignment_map(c).items():
                r = ns.notify(c, a, "provisional_offer", {"program": db.load_programs(c).set_index("id").loc[p, "code"]}, dedupe=f"offer_resend:{run['id']}")
                n += r.get("in_app") == "sent"
            st.success(f"Queued for {n} applicants (duplicates skipped).")
    with c2, ds.card("Allocation outcome", icon="check"):
        out = st.session_state.get("al_out")
        if out: _publish_feedback(out)
        if run:
            ts = re_.technical_summary(c)
            ds.facts([("Seated", ts.get("seated", run["assigned_count"])), ("Vacant seats", ts.get("vacant_seats", "—")), ("Fill rate", f"{100 * ts['fill_rate']:.0f}%" if "fill_rate" in ts else "—"),
                      ("First choice", f"{100 * ts['first_choice_rate']:.0f}%" if "first_choice_rate" in ts else "—")])
            st.plotly_chart(ds.plotly_style(rank_chart(type("R", (), {"rank_histogram": ts["rank_histogram"]})()), 320), width="stretch", key="al_rank")
        elif not out:
            st.info("No allocation published yet.")
    with st.expander("Technical allocation summary (administrators)"):
        st.json(re_.technical_summary(c) if run else {"info": "no run"})
        if run:
            problem = db.build_problem(c); rep = validate(problem, dict(problem.previous))
            st.success("Independent validation: PASS — " + ", ".join(rep.checks_run)) if rep.ok else st.error(f"Validation: {len(rep.violations)} violation(s) — reallocate")
    with ds.card("Allocation history", icon="clock"):
        st.dataframe(db.load_runs(c)[["id", "mode", "solver_status", "assigned_count", "reassigned_count", "preference_score", "created_at", "notes"]], hide_index=True, width="stretch")


# ====================================================================== 6 Reallocation Management
def sec_withdrawals(c):
    pending = db.load_withdrawals(c, "requested"); allw = db.load_withdrawals(c)
    ds.kpis([("Awaiting authorisation", len(pending), "a"), ("Approved", int((allw.status == "approved").sum()) if len(allw) else 0, "g"), ("Rejected", int((allw.status == "rejected").sum()) if len(allw) else 0, "r")])
    ds.section("Withdrawal requests", "Authorising releases the seat and immediately re-runs the minimal-disruption reallocation")
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
    st.divider(); st.markdown("#### Withdrawal history"); st.dataframe(db.load_withdrawals(c), hide_index=True, width="stretch")
    st.caption("Authorising a withdrawal releases the seat and immediately re-runs the minimal-disruption reallocation (see Reallocation Management for capacity changes and vacancies).")


def sec_reallocation(c):
    run = db.get_current_run(c); runs = db.load_runs(c)
    ds.kpis([("Current version", f"#{run['id']}" if run else "none", "v"), ("Reallocation runs", int((runs["mode"] != "initial").sum()) if len(runs) else 0, ""),
             ("Moved in last version", run["reassigned_count"] if run else 0, "a"), ("Pending withdrawals", len(db.load_withdrawals(c, "requested")), "a")])
    ds.section("Capacity changes", "Recorded with a reason, then the engine reallocates with minimal disruption")
    programs = db.load_programs(c)
    c1, c2, c3 = st.columns(3)
    sel = c1.selectbox("Program", programs.code.tolist(), key="rc_prog"); row = programs[programs.code == sel].iloc[0]
    newcap = c2.number_input("New capacity", 0, 2000, int(row.capacity), key="rc_cap"); reason = c3.text_input("Reason", "Seats revised", key="rc_reason")
    if st.button("Apply capacity change and reallocate", key="rc_apply"):
        with st.spinner("Re-optimising…"):
            st.session_state["rc_out"] = re_.change_capacity(c, int(row.id), int(newcap), reason)
        st.rerun()
    if "rc_out" in st.session_state: _publish_feedback(st.session_state["rc_out"])
    ds.section("Vacancies and eligible waitlisted candidates", "Why a seat is empty and who could fill it")
    rep = re_.vacancy_report(c)
    if rep: st.dataframe(pd.DataFrame(rep), hide_index=True, width="stretch")
    else: st.success("No vacant seats, or no allocation yet.")
    if st.button("Run minimal-disruption reallocation now", key="rc_run"):
        with st.spinner("Re-optimising…"):
            st.session_state["rc_out"] = re_.run_reallocation(c, "manual run from Reallocation Management")
        st.rerun()
    st.markdown("**Capacity change history**"); st.dataframe(db.load_capacity_changes(c), hide_index=True, width="stretch")


# ====================================================================== 7 Appeals
def sec_appeals(c):
    df = aps.load_appeals_full(c)
    ds.kpis([("Appeals", len(df), "v"), ("Open", int(df.decision.isin(["submitted", "evaluated"]).sum()) if len(df) else 0, "a"), ("Accepted", int((df.decision == "accepted").sum()) if len(df) else 0, "g"), ("Rejected", int((df.decision == "rejected").sum()) if len(df) else 0, "r")])
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
            st.plotly_chart(ds.plotly_style(sankey_displacement(problem, cf.baseline, cf.alternative, "Effect of granting this appeal")), width="stretch", key="ap_sankey")
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
    ap = aps.load_appeals_full(c); w = db.load_withdrawals(c); runs_all = db.load_runs(c)
    ds.kpis([("Applications", int(c.execute("SELECT COUNT(*) FROM applicants WHERE application_status='applied'").fetchone()[0]), "v"), ("Appeals", len(ap), ""), ("Appeals accepted", int((ap.decision == "accepted").sum()) if len(ap) else 0, "g"),
             ("Withdrawals approved", int((w.status == "approved").sum()) if len(w) else 0, "r"), ("Allocation versions", len(runs_all), "b")])
    a0, b0 = st.columns(2)
    a0.plotly_chart(ds.plotly_style(px.bar(dist, x="code", y="first-choice applications", title="Application distribution (first choice)"), 340), width="stretch", key="an_dist")
    tracks = pd.DataFrame(c.execute("SELECT track, COUNT(*) n FROM applicants WHERE application_status='applied' GROUP BY track").fetchall(), columns=["track", "n"])
    b0.plotly_chart(ds.plotly_style(px.pie(tracks, names="track", values="n", title="Applicants by academic track", hole=.55), 340), width="stretch", key="an_tracks")
    if run:
        used = Counter(cur.values()); seats = pd.DataFrame([{"Program": r.code, "Allocated": used.get(int(r.id), 0), "Vacant": max(0, int(r.capacity) - used.get(int(r.id), 0))} for r in programs.itertuples()])
        fig = go.Figure(); fig.add_bar(name="Allocated", x=seats.Program, y=seats.Allocated); fig.add_bar(name="Vacant", x=seats.Program, y=seats.Vacant); fig.update_layout(barmode="stack", title="Program-wise seat utilisation")
        st.plotly_chart(ds.plotly_style(fig, 340), width="stretch", key="an_util")
        offers = pd.DataFrame(c.execute("SELECT offer_status, COUNT(*) n FROM applicants WHERE status='active' AND application_status='applied' GROUP BY offer_status").fetchall(), columns=["status", "n"])
        a, b = st.columns(2)
        a.plotly_chart(ds.plotly_style(px.pie(offers, names="status", values="n", title="Selected · confirmed · waitlisted", hole=.55), 340), width="stretch", key="an_offers")
        hist = re_.technical_summary(c)["rank_histogram"]
        b.plotly_chart(ds.plotly_style(px.bar(x=[f"Choice #{k}" for k in hist], y=list(hist.values()), title="Preference satisfaction", labels={"x": "", "y": "applicants"}), 340), width="stretch", key="an_pref")
        runs = db.load_runs(c).sort_values("id")
        c1, c2 = st.columns(2)
        c1.plotly_chart(ds.plotly_style(px.line(runs, x="id", y="reassigned_count", markers=True, title="Reallocation statistics (applicants moved per version)", labels={"id": "version", "reassigned_count": "moved"}), 320), width="stretch", key="an_realloc")
        c2.plotly_chart(ds.plotly_style(px.line(runs, x="id", y="assigned_count", markers=True, title="Allocation-version trend (seated applicants)", labels={"id": "version", "assigned_count": "seated"}), 320), width="stretch", key="an_trend")
    else:
        st.info("Seat utilisation, offer distribution, preference satisfaction and reallocation charts appear once an allocation is published.")


# ====================================================================== 9 Notifications
def sec_notifications(c):
    status = ns.integration_status()
    df_all = db.load_notifications(c, limit=500)
    ds.kpis([("Email", "configured" if status["email"]["configured"] else "not configured", "g" if status["email"]["configured"] else "a"),
             ("WhatsApp", "configured" if status["whatsapp"]["configured"] else "not configured", "g" if status["whatsapp"]["configured"] else "a"),
             ("Sent", int((df_all.status == "sent").sum()), "g"), ("Failed", int((df_all.status == "failed").sum()), "r"), ("Not configured", int((df_all.status == "not_configured").sum()), "a")])
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
            status_, _, detail_ = res.partition(": ")
            (st.success if status_ == "sent" else st.error)(f"{ch}: {_status_label(status_, detail_)} — {detail_}")
    df = df_all
    ds.section("Delivery log", "Every attempt with the provider's real response")
    f1, f2, f3 = st.columns(3); ch = f1.multiselect("Channel", ["in_app", "email", "whatsapp"], key="nt_ch"); stt = f2.multiselect("Status", ["sent", "failed", "not_configured", "skipped"], key="nt_st")
    ev = f3.multiselect("Event", sorted(df.event.dropna().unique().tolist()), key="nt_ev")
    if ch: df = df[df.channel.isin(ch)]
    if stt: df = df[df.status.isin(stt)]
    if ev: df = df[df.event.isin(ev)]
    df = df.copy(); df.insert(df.columns.get_loc("status") + 1, "result", [_status_label(s_, d_) for s_, d_ in zip(df.status, df.provider_response.fillna(""))])
    st.dataframe(df, hide_index=True, width="stretch", height=380)
    st.caption("Statuses reflect the provider's real response. 'not_configured' means no credentials were present; nothing was sent.")


# ====================================================================== 10 Announcements
def sec_announcements(c):
    ds.section("Announcements", "Shown on student dashboards (students / all) or the public website (public / all)")
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
    ds.section("Website content (CMS)", "Institute name, hero, about and contact text used by the public website and the portals")
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
    with ds.card("Allocation versions", "Each version is traceable to its parent and policy snapshot", icon="layers"):
        st.dataframe(db.load_runs(c), hide_index=True, width="stretch", height=220)
    ds.section("Audit log", "Append-only; entries cannot be edited or deleted from this interface")
    q = st.text_input("Filter action / details", key="au_q"); df = db.load_audit(c, 1000)
    if q: df = df[df.action.str.contains(q, case=False) | df.details.fillna("").str.contains(q, case=False)]
    st.dataframe(df, hide_index=True, width="stretch", height=420)
    st.download_button("⬇ Audit CSV", df.to_csv(index=False).encode(), "audit.csv", "text/csv", key="au_csv")


# ====================================================================== 12 Settings
def sec_settings(c):
    s = db.get_settings(c)
    t_gen, t_alloc, t_acc, t_form, t_int, t_danger = st.tabs(["General", "Allocation policy", "Account security", "Application form", "Integrations", "Danger zone"])
    with t_gen, ds.card("General configuration", icon="grid"):
        with st.form("set_general"):
            sess = st.text_input("Academic session", s["academic_session"]); tag = st.text_input("Institute tagline", s["institute_tagline"])
            days = st.number_input("Offer acceptance window (days, informational)", 1, 60, int(s["offer_accept_days"]))
            demo = st.checkbox("Demonstration mode banner", value=s["demo_mode"] == "1")
            ok_g = st.form_submit_button("Save general settings", type="primary")
        if ok_g:
            for k, v in {"offer_accept_days": days, "academic_session": sess, "institute_tagline": tag, "demo_mode": int(demo)}.items():
                if str(v) != str(s.get(k)): db.set_setting(c, k, str(v))
            st.success("Saved."); st.rerun()
    with t_alloc, ds.card("Allocation policy", "Applies to the next allocation run; existing versions keep their policy snapshot", icon="layers"):
        with st.form("set_policy"):
            mode = st.selectbox("Objective hierarchy", ["preference_first", "merit_first"], index=0 if s["objective_mode"] == "preference_first" else 1,
                                help="preference_first: maximise ranked-preference satisfaction, entrance score breaks ties. merit_first: fill seats, then entrance-score merit, then preferences, then earliest application. No other merit weightings are applied.")
            maxp = st.number_input("Maximum preferences per applicant", 1, 10, int(s["max_preferences"]))
            lock = st.checkbox("Confirmed admissions are never moved by reallocation", value=s["lock_confirmed_seats"] == "1")
            mu = st.number_input("Reallocation displacement penalty (1000 = never disturb seated applicants; 1 = allow upgrades into vacancies)", 1, 100000, int(float(s["reallocation_mu"])))
            ok = st.form_submit_button("Save allocation policy", type="primary")
        if ok:
            for k, v in {"objective_mode": mode, "max_preferences": maxp, "lock_confirmed_seats": int(lock), "reallocation_mu": mu}.items():
                if str(v) != str(s.get(k)): db.set_setting(c, k, str(v))
            st.success("Saved. Policy changes apply to the next allocation run."); st.rerun()
    with t_acc, ds.card("Administrator account", icon="user"):
        if db.admin_uses_default_password(c): st.warning("The default password is still in use.")
        with st.form("set_pw"):
            old = st.text_input("Current password", type="password"); new = st.text_input("New password", type="password"); new2 = st.text_input("Confirm new password", type="password")
            ok2 = st.form_submit_button("Change password", type="primary")
        if ok2:
            if not db.check_admin_login(c, "admin", old): st.error("Current password is incorrect.")
            elif new != new2 or len(new) < 6: st.error("New passwords must match and be at least 6 characters.")
            else: db.set_admin_password(c, "admin", new); st.success("Password changed.")
    with t_form, ds.card("Application form builder", "Extra fields students must answer in Apply Now", icon="file"):
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
    with t_int, ds.card("Integration status", "Live view of the email and WhatsApp configuration", icon="mail"):
        st.json(ns.integration_status())
        st.caption("Email reads SMTP_HOST, SMTP_PORT (587 = STARTTLS), SMTP_USER, SMTP_PASSWORD and optional SMTP_FROM from the .env file.")
        with st.form("set_test_email"):
            to = st.text_input("Send a test email to", placeholder="you@example.com")
            go_ = st.form_submit_button("Send Test", type="primary")
        if go_:
            if "@" not in (to or ""): st.error("Enter a valid email address.")
            else:
                res = ns.send_test(c, to, "").get("email", "failed: no result")
                status_, _, detail_ = res.partition(": ")
                (st.success if status_ == "sent" else st.error)(f"{_status_label(status_, detail_)} — {detail_}")
    with t_danger, ds.card("Danger zone", icon="alert"):
        st.error("Resetting replaces every applicant, program, allocation version, appeal, notification and audit entry with the 200-applicant demonstration seed. This cannot be undone.")
        sure = st.checkbox("I understand that all current records will be lost", key="reset_sure")
        if st.button("Clear all applicants (keep programmes, settings and website content)", key="clear_applicants", width="stretch", disabled=not sure):
            n = db.clear_applicant_data(c)
            for k in ("al_out", "rw_out", "rc_out", "ap_cf"): st.session_state.pop(k, None)
            st.success(f"Removed {n} applicant record(s). Import real applicants under Data Upload."); st.rerun()
        st.html("<div class='sw-card-title' style='margin-top:8px'>🎤 Pitch mode</div><p class='sw-card-sub'>4 programmes · 15 seats · 20 applicants · 10 of them want AI Engineering first. Deterministic, so the demo looks the same every time.</p>")
        if st.button("🎤 RESET DB TO 3-MINUTE PITCH DATA", key="reset_pitch", type="primary", width="stretch", disabled=not sure):
            db.seed_micro_pitch_demo(c)
            for k in ("al_out", "rw_out", "rc_out", "ap_cf"): st.session_state.pop(k, None)
            st.session_state["admin_nav"] = SECTIONS[0]; st.rerun()
        if st.button("Reset database to demonstration seed (200 applicants)", key="reset_db", disabled=not sure):
            db.reset_db(c); db.seed_demo(c)
            for k in ("al_out", "rw_out", "rc_out", "ap_cf"): st.session_state.pop(k, None)
            st.rerun()


# ====================================================================== Data Upload (CSV ingestion)
def sec_data_upload(c):
    n_app = c.execute("SELECT COUNT(*) FROM applicants").fetchone()[0]
    n_prog = c.execute("SELECT COUNT(*) FROM programs").fetchone()[0]
    ds.kpis([("Applicants in database", n_app, "v"), ("Programmes", n_prog, "b"), ("Max preferences", db.get_setting(c, "max_preferences", "5"), ""),
             ("Email delivery", "configured" if ns.integration_status()["email"]["configured"] else "not configured", "g" if ns.integration_status()["email"]["configured"] else "a")])
    if db.get_setting(c, "demo_mode") == "1" and n_app:
        st.warning("The database still holds synthetic demonstration applicants. Clear them under Settings → Danger zone before importing real data.")
    l, r = st.columns([1, 1.4], gap="medium")
    with l, ds.card("1 · Download the template", "Fill one row per applicant", icon="file"):
        tpl = db.csv_template(c)
        st.download_button("⬇ Sample CSV Template", tpl.to_csv(index=False).encode(), "seatwisee_applicants_template.csv", "text/csv", key="csv_tpl", type="primary", width="stretch")
        st.markdown("**Required:** Full Name, Email, Score (0-100), Track, Preference 1.  \n**Optional:** Phone, Address, Preference 2 onwards.  \n"
                    f"**Track** is one of {', '.join(db.TRACKS)}. **Preferences** are programme codes or full names, in order.")
        progs = db.load_programs(c)[["code", "name", "capacity", "min_score", "required_track"]].rename(columns={"code": "Code", "name": "Programme", "capacity": "Seats", "min_score": "Min score", "required_track": "Track"})
        progs["Track"] = progs["Track"].fillna("Any"); st.dataframe(progs, hide_index=True, width="stretch")
    with r, ds.card("2 · Upload and validate", "Nothing is written until you confirm the import", icon="file"):
        if st.session_state.get("csv_done"):
            st.success(st.session_state["csv_done"])
        up = st.file_uploader("Applicants CSV", type=["csv"], key=f"csv_upload_{st.session_state.get('csv_gen', 0)}")
        if up is None:
            st.caption("Upload a .csv file to see a validation preview."); return
        try:
            raw = pd.read_csv(up, dtype=str, keep_default_na=False)
            valid, report = db.parse_applicants_csv(c, raw)
        except Exception as e:
            st.error(f"Could not read this CSV: {e}"); return
        ok, bad = len(valid), int((report.Result != "OK").sum())
        report = report[["Line", "Result", "Full Name", "Email", "Preferences"]]
        if bad and (report.Result == "email already registered").all():
            st.warning("Every row is already in the database: this file has been imported before. Nothing new to import.")
        ds.facts([("Rows in file", len(report)), ("Valid", ok), ("With errors", bad)])
        st.dataframe(report.style.apply(lambda row: ["background-color:#FEE2E2" if row.Result != "OK" else ""] * len(row), axis=1), hide_index=True, width="stretch", height=min(380, 40 + 35 * len(report)))
        if bad:
            st.download_button("⬇ Error report CSV", report[report.Result != "OK"].to_csv(index=False).encode(), "import_errors.csv", "text/csv", key="csv_err")
        email_them = st.checkbox("Email each imported applicant a welcome message (tells them to set a password with 'Forgot password'; sent in the background)", value=True, key="csv_email")
        if st.button(f"Import {ok} valid applicant(s)", type="primary", key="csv_import", width="stretch", disabled=ok == 0):
            with st.spinner("Creating accounts and applications…"):
                ids = db.import_applicants(c, valid)
                counts = aps.verify_all_eligibility(c)
                if email_them:
                    ns.notify_bulk_background(db.DEFAULT_DB_PATH, ids, "account_registered", dedupe="welcome")
                if db.get_setting(c, "demo_mode") == "1" and not c.execute("SELECT COUNT(*) FROM applicants WHERE email LIKE '%@seatwisee.demo'").fetchone()[0]:
                    db.set_setting(c, "demo_mode", "0")
            st.session_state["csv_done"] = (f"Imported {len(ids)} applicant(s) from {up.name}. Eligibility: {counts.get('eligible', 0)} eligible, {counts.get('ineligible', 0)} ineligible."
                                            + (" Welcome emails are being sent in the background; results appear in the Notifications delivery log." if email_them else ""))
            st.session_state["csv_gen"] = st.session_state.get("csv_gen", 0) + 1   # fresh uploader: the imported file is not re-validated
            st.toast(f"{len(ids)} applicants imported", icon="✅"); st.rerun()


def render(c) -> None:
    ds.inject()
    institute = db.get_site_text(c, "institute_name", "Institute")
    with st.sidebar:
        ds.sidebar_brand(BRAND, institute, LOGO)
        ds.refresh_button()
        st.html("<div class='sw-navhead'>Administration</div>")
        section = render_sidebar_nav()
        ds.sidebar_profile(st.session_state.get("auth_name") or "Administrator", ["Administrator · full access", institute], auth.full_logout)
    run = db.get_current_run(c); status = ns.integration_status()
    pend_ap = c.execute("SELECT COUNT(*) FROM appeals WHERE decision IN ('submitted','evaluated')").fetchone()[0]
    pend_wd = c.execute("SELECT COUNT(*) FROM withdrawals WHERE status='requested'").fetchone()[0]
    chips = [(f"Version #{run['id']} · {run['solver_status']}" if run else "No allocation published", "ok" if run and run["solver_status"] in ("OPTIMAL", "FEASIBLE") else "warn"),
             ("Email " + ("on" if status["email"]["configured"] else "off"), "ok" if status["email"]["configured"] else "warn"),
             ("WhatsApp " + ("on" if status["whatsapp"]["configured"] else "off"), "ok" if status["whatsapp"]["configured"] else "warn")]
    if pend_ap: chips.append((f"{pend_ap} appeal(s) pending", "bad"))
    if pend_wd: chips.append((f"{pend_wd} withdrawal(s) pending", "bad"))
    ds.hero(f"{institute}", f"Administrator · {_plain(section)} · {ds.today_label()}", chips=chips, unread=pend_ap + pend_wd, avatar="AD", overlap=False)
    st.html("<div style='height:12px'></div>")
    if section == SECTIONS[0]:
        q = st.columns(5)
        for col, (label, target) in zip(q, [("Run allocation", SECTIONS[4]), ("Applications", SECTIONS[2]), ("Appeals", SECTIONS[6]), ("Withdrawals", SECTIONS[12]), ("Settings", SECTIONS[11])]):
            col.button(label, key=f"qa_{target}", on_click=goto, args=(target,), width="stretch")
    {SECTIONS[0]: sec_overview, SECTIONS[1]: sec_programs, SECTIONS[2]: sec_applications, SECTIONS[3]: sec_selected, SECTIONS[4]: sec_allocation,
     SECTIONS[5]: sec_reallocation, SECTIONS[6]: sec_appeals, SECTIONS[7]: sec_analytics, SECTIONS[8]: sec_notifications, SECTIONS[9]: sec_announcements,
     SECTIONS[10]: sec_audit, SECTIONS[11]: sec_settings, SECTIONS[12]: sec_withdrawals, SECTIONS[13]: sec_data_upload}[section](c)
