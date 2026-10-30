"""Admin exports: applications list and program-wise selected candidates as PDF tables."""
from __future__ import annotations

import io

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def dataframe_pdf(df: pd.DataFrame, title: str, subtitle: str = "", max_rows: int = 400) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=title, leftMargin=24, rightMargin=24, topMargin=28, bottomMargin=24)
    ss = getSampleStyleSheet()
    story = [Paragraph(title, ss["Title"])]
    if subtitle:
        story.append(Paragraph(subtitle, ss["Normal"]))
    story.append(Spacer(1, 8))
    d = df.head(max_rows).copy()
    data = [list(map(str, d.columns))] + [[str(v)[:40] for v in row] for row in d.itertuples(index=False)]
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B1F3A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("GRID", (0, 0), (-1, -1), 0.3, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F8FC")])]))
    story.append(t)
    if len(df) > max_rows:
        story.append(Paragraph(f"… {len(df) - max_rows} more rows (use the CSV export for the full list)", ss["Italic"]))
    doc.build(story)
    return buf.getvalue()
