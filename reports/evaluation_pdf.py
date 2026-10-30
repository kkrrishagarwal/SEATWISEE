"""Per-student admission evaluation report. Contains ONLY that student's information."""
from __future__ import annotations

import io
import json

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database import db_manager as db

BRAND = "DO! u want"


def evaluation_pdf(conn, applicant_id: int) -> bytes:
    a = conn.execute("SELECT * FROM applicants WHERE id = ?", (applicant_id,)).fetchone()
    inst = db.get_site_text(conn, "institute_name", "Institute")
    prefs = db.load_preferences(conn)
    mine = prefs[prefs.applicant_id == applicant_id]
    problem = db.build_problem(conn, previous={})
    seat = db.current_assignment_for(conn, applicant_id)
    run = db.get_current_run(conn)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="Admission evaluation report")
    ss = getSampleStyleSheet()
    story = [Paragraph(f"{inst} · {BRAND}", ss["Title"]), Paragraph("Individual Admission Evaluation Report", ss["Heading2"]),
             Paragraph(f"Application ID <b>{db.app_id(applicant_id)}</b> · {a['name']} · {a['email']}", ss["Normal"]), Spacer(1, 10)]
    rows = [["Item", "Value"], ["Application status", a["application_status"]], ["Eligibility status", a["eligibility_status"]],
            ["Offer status", a["offer_status"]], ["Entrance score", a["score"]], ["Track", a["track"]],
            ["Submitted at", a["applied_at"]], ["Documents", ("marksheet ✓ " if a["marksheet_path"] else "marksheet ✗ ") + ("scorecard ✓" if a["scorecard_path"] else "scorecard ✗")]]
    t = Table(rows, hAlign="LEFT", colWidths=[160, 330])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story += [t, Spacer(1, 12), Paragraph("Preference-by-preference evaluation", ss["Heading3"])]
    prow = [["#", "Program", "Eligible?", "Reason / outcome"]]
    in_pool = applicant_id in problem.applicant_ids
    for r in mine.itertuples():
        if in_pool:
            reasons = problem.ineligibility_reasons(applicant_id, r.program_id)
            elig = "Yes" if not reasons else "No"
            outcome = "; ".join(reasons) if reasons else ("ALLOTTED" if seat and seat["program_id"] == r.program_id else "eligible, seat not allotted in this round")
        else:
            elig, outcome = "—", "application not submitted"
        prow.append([r.rank, r.code, elig, Paragraph(outcome, ss["BodyText"])])
    t2 = Table(prow, hAlign="LEFT", colWidths=[25, 70, 60, 335])
    t2.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t2, Spacer(1, 12), Paragraph("Allocation result", ss["Heading3"])]
    if run is None:
        story.append(Paragraph("Allocation has not been published yet.", ss["Normal"]))
    elif seat and seat["program_id"]:
        story.append(Paragraph(f"Allotted <b>{seat['code']} — {seat['program_name']}</b> (preference #{seat['rank_obtained']}) in allocation version #{run['id']} "
                               f"(solver status {run['solver_status']}). Offer status: <b>{a['offer_status']}</b>.", ss["Normal"]))
    else:
        story.append(Paragraph(f"Not allotted in allocation version #{run['id']}. Status: <b>{a['offer_status']}</b>. "
                               "Seats may open through withdrawals; you will be notified automatically.", ss["Normal"]))
    pol = json.loads(run["policy_json"]) if run and run["policy_json"] else {}
    story += [Spacer(1, 12), Paragraph(f"Allocation policy in force: {pol.get('objective_mode', 'preference_first')} · max preferences {pol.get('max_preferences', '5')}. "
                                        "Decisions are produced by the SEATWISEE constraint engine and independently validated. This report contains only your own information.", ss["Italic"])]
    doc.build(story)
    return buf.getvalue()
