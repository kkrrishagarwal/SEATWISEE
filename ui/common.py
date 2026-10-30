"""Shared helpers for the Streamlit pages: DB handle, charts, solver glue, PDF export."""
from __future__ import annotations

import io
from collections import Counter
from typing import Dict, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database import db_manager as db
from optimization.cp_sat_model import SolveResult, solve_initial, solve_reassign
from optimization.problem import ProblemData
from optimization.validator import validate

BRAND = "DO! u want"
SYSTEM = "SEATWISEE"

STATUS_COLORS = {"OPTIMAL": "green", "FEASIBLE": "orange", "INFEASIBLE": "red", "UNKNOWN": "gray", "MODEL_INVALID": "red"}


@st.cache_resource
def conn():
    return db.ensure_seeded()


def status_badge(status: str, explanation: str = "") -> None:
    color = STATUS_COLORS.get(status, "gray")
    st.markdown(f":{color}[**{status}**] {explanation}")


def run_and_persist(mode: str, notes: str = "", mu: int = 1000, time_limit: float = 20.0) -> tuple[SolveResult, Optional[int], ProblemData]:
    """Solve against live DB state, validate independently, persist only if the validator agrees."""
    c = conn()
    problem = db.build_problem(c, previous={} if mode == "initial" else None)
    res = solve_initial(problem, time_limit_s=time_limit) if mode == "initial" else solve_reassign(problem, mu=mu, time_limit_s=time_limit)
    run_id = None
    if res.has_solution:
        rep = validate(problem, res.assignment)
        if rep.ok:
            parent = db.get_current_run(c)
            run_id = db.save_run(
                c, mode=mode, solver_status=res.status, assignment=res.assignment, problem=problem,
                objective=res.objective, best_bound=res.best_bound, wall_time_s=res.wall_time_s,
                reassigned_count=res.reassigned_count, parent_run_id=parent["id"] if parent else None, notes=notes,
            )
        else:
            res.notes.append("VALIDATOR REJECTED the solver output; nothing was persisted.")
            res.notes.extend(v.message for v in rep.violations[:10])
    return res, run_id, problem


def program_labels(problem: ProblemData) -> Dict[Optional[int], str]:
    labels: Dict[Optional[int], str] = {p.id: p.code for p in problem.programs}
    labels[None] = "Unassigned"
    return labels


def sankey_displacement(problem: ProblemData, before: Dict[int, int], after: Dict[int, int], title: str = "Where did people move?") -> go.Figure:
    """Sankey: left = program before, right = program after. Only applicants whose seat changed."""
    labels = program_labels(problem)
    moved = {a: (before.get(a), after.get(a)) for a in set(before) | set(after) if before.get(a) != after.get(a)}
    flows = Counter(moved.values())
    if not flows:
        fig = go.Figure()
        fig.add_annotation(text="No applicant changed seat", showarrow=False, font=dict(size=18))
        fig.update_layout(height=250, title=title)
        return fig
    left = sorted({b for b, _ in flows}, key=lambda k: (k is None, str(k)))
    right = sorted({a for _, a in flows}, key=lambda k: (k is None, str(k)))
    node_labels = [f"{labels[b]} (before)" for b in left] + [f"{labels[a]} (after)" for a in right]
    li = {b: i for i, b in enumerate(left)}
    ri = {a: len(left) + i for i, a in enumerate(right)}
    fig = go.Figure(go.Sankey(
        node=dict(label=node_labels, pad=18, thickness=18),
        link=dict(
            source=[li[b] for (b, a) in flows], target=[ri[a] for (b, a) in flows],
            value=[v for v in flows.values()],
            label=[f"{labels[b]} → {labels[a]}: {v}" for (b, a), v in flows.items()],
        ),
    ))
    fig.update_layout(title=title, height=max(300, 40 * len(node_labels) + 120), margin=dict(l=10, r=10, t=50, b=10))
    return fig


def occupancy_chart(problem: ProblemData, assignment: Dict[int, int]) -> go.Figure:
    used = Counter(assignment.values())
    codes = [p.code for p in problem.programs]
    fig = go.Figure()
    fig.add_bar(name="Seated", x=codes, y=[used.get(p.id, 0) for p in problem.programs])
    fig.add_bar(name="Free", x=codes, y=[max(0, p.capacity - used.get(p.id, 0)) for p in problem.programs])
    fig.update_layout(barmode="stack", height=320, margin=dict(l=10, r=10, t=30, b=10), title="Seat occupancy per program")
    return fig


def rank_chart(res: SolveResult) -> go.Figure:
    hist = res.rank_histogram
    fig = go.Figure(go.Bar(x=[f"Choice #{k}" for k in hist], y=list(hist.values()), text=list(hist.values()), textposition="auto"))
    fig.update_layout(height=300, title="Preference satisfaction (which choice did applicants get?)", margin=dict(l=10, r=10, t=40, b=10))
    return fig


def assignment_df(problem: ProblemData, assignment: Dict[int, int], previous: Optional[Dict[int, int]] = None) -> pd.DataFrame:
    labels = program_labels(problem)
    rows = []
    for a in problem.applicants:
        pid = assignment.get(a.id)
        row = {
            "ID": a.id, "Name": a.name, "Track": a.track, "Score": a.score, "Status": a.status,
            "Program": labels[pid], "Choice #": problem.pref_rank.get((a.id, pid)) if pid else None,
            "Points": problem.points(a.id, pid),
        }
        if previous is not None:
            prev = previous.get(a.id)
            row["Previous"] = labels[prev]
            row["Changed"] = "✔" if prev != pid else ""
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- PDF
def appeal_pdf(problem: ProblemData, cf, applicant_name: str, program_code: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    labels = program_labels(problem)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{SYSTEM} appeal report")
    ss = getSampleStyleSheet()
    story = [
        Paragraph(f"{SYSTEM} · Counterfactual Appeal Report", ss["Title"]),
        Paragraph(f"Appellant: <b>{applicant_name}</b> (ID {cf.applicant_id}) &nbsp; Requested: <b>{program_code}</b>", ss["Normal"]),
        Spacer(1, 8),
        Paragraph(f"Solver status: <b>{cf.solve.status}</b> — {cf.solve.explanation}", ss["Normal"]),
        Paragraph(f"Recommendation: <b>{cf.recommendation}</b>", ss["Normal"]),
        Spacer(1, 8),
    ]
    if cf.pre_check_reasons:
        story.append(Paragraph("Pre-checks: " + "; ".join(cf.pre_check_reasons), ss["Normal"]))
    if cf.feasible:
        m = cf.metrics
        data = [["Metric", "Baseline", "If granted", "Delta"],
                ["Applicants seated", m["before_assigned"], m["after_assigned"], m["after_assigned"] - m["before_assigned"]],
                ["Preference points", m["before_points"], m["after_points"], m["points_delta"]],
                ["Applicants moved", "-", m["moved_count"], ""],
                ["Others displaced", "-", cf.displaced_count, ""],
                ["Validator", "-", "PASS" if cf.validation.ok else "FAIL", ""]]
        t = Table(data, hAlign="LEFT")
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
        story += [t, Spacer(1, 10), Paragraph("Ripple effect", ss["Heading3"])]
        rows = [["Applicant", "Role", "Before", "After", "Choice before→after", "Δ points"]]
        for r in cf.ripple:
            rows.append([f"{r.name} ({r.applicant_id})", r.kind, labels[r.before_program], labels[r.after_program],
                         f"{r.before_rank or '-'} → {r.after_rank or '-'}", r.points_delta])
        t2 = Table(rows, hAlign="LEFT", repeatRows=1)
        t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
        story.append(t2)
    else:
        story.append(Paragraph("No alternative allocation exists that honours this request. Reasons: " + "; ".join(cf.solve.notes), ss["Normal"]))
    story += [Spacer(1, 12), Paragraph("Generated by SEATWISEE (Google OR-Tools CP-SAT). Validation performed by an independent rule checker.", ss["Italic"])]
    doc.build(story)
    return buf.getvalue()


def application_receipt_pdf(c, applicant_id: int) -> bytes:
    """One-page PDF receipt of a student's application and current allocation status."""
    import json
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    a = c.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,)).fetchone()
    prefs = db.load_preferences(c)
    mine = prefs[prefs.applicant_id == applicant_id]
    seat = db.current_assignment_for(c, applicant_id)
    data = json.loads(a["form_data"] or "{}")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{SYSTEM} application receipt")
    ss = getSampleStyleSheet()
    story = [Paragraph(f"{SYSTEM} · {BRAND} — Application Receipt", ss["Title"]),
             Paragraph(f"Applicant ID <b>{a['id']}</b> · {a['name']} · {a['email']}", ss["Normal"]),
             Paragraph(f"Applied at {a['applied_at']} · Status: {a['status']}", ss["Normal"]), Spacer(1, 10)]
    rows = [["Field", "Value"], ["Entrance score", a["score"]], ["Track", a["track"]]]
    for f in db.load_form_schema(c):
        rows.append([f["label"], data.get(f["field_key"], "-")])
    rows.append(["Ranked preferences", " > ".join(f"#{r.rank} {r.code}" for r in mine.itertuples())])
    rows.append(["12th Board Marksheet", a["marksheet_path"] or "not uploaded"])
    rows.append(["Entrance Scorecard", a["scorecard_path"] or "not uploaded"])
    if seat is None:
        alloc = "Allocation not yet published"
    elif seat["program_id"] is None:
        alloc = "Unassigned in current allocation"
    else:
        alloc = f"{seat['code']} - {seat['program_name']} (choice #{seat['rank_obtained']})"
    rows.append(["Allocated program", alloc])
    t = Table(rows, hAlign="LEFT", colWidths=[160, 340])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                           ("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t, Spacer(1, 12), Paragraph("Generated by SEATWISEE. Allocation decisions are produced by Google OR-Tools CP-SAT and verified by an independent validator.", ss["Italic"])]
    doc.build(story)
    return buf.getvalue()


def allotment_letter_pdf(c, applicant_id: int) -> bytes:
    """Seat allotment letter for an applicant who holds a seat in the current run."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    a = c.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,)).fetchone()
    seat = db.current_assignment_for(c, applicant_id)
    run = db.get_current_run(c)
    inst = db.get_site_text(c, "institute_name", SYSTEM)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=f"{SYSTEM} seat allotment letter")
    ss = getSampleStyleSheet()
    story = [Paragraph(f"{inst}", ss["Title"]), Paragraph("Provisional Seat Allotment Letter", ss["Heading2"]), Spacer(1, 8),
             Paragraph(f"Dear <b>{a['name']}</b>,", ss["Normal"]), Spacer(1, 6)]
    if seat and seat["program_id"]:
        story.append(Paragraph(f"We are pleased to inform you that you have been allotted a seat in "
                               f"<b>{seat['code']} — {seat['program_name']}</b> (your preference #{seat['rank_obtained']}).", ss["Normal"]))
    else:
        story.append(Paragraph("No seat has been allotted to you in the current allocation round.", ss["Normal"]))
    story.append(Spacer(1, 10))
    rows = [["Applicant ID", a["id"]], ["Email", a["email"]], ["Entrance score", a["score"]], ["Track", a["track"]],
            ["Allocation run", f"#{run['id']} · {run['solver_status']} · {run['created_at']}" if run else "—"]]
    t = Table(rows, hAlign="LEFT", colWidths=[150, 330])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    story += [t, Spacer(1, 14),
              Paragraph("This allotment was produced by the SEATWISEE constraint engine (Google OR-Tools CP-SAT) and verified by an "
                        "independent validator. It is provisional until document verification at the admissions office.", ss["Italic"])]
    doc.build(story)
    return buf.getvalue()
