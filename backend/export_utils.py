"""
export_utils.py — Unique Feature 3: Export to PDF and CSV
Generates a professional ranked leaderboard report using ReportLab
"""
import io
import csv
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


SCORE_COLORS = {
    "Strong Match":  colors.HexColor("#059669"),
    "Good Match":    colors.HexColor("#4f46e5"),
    "Partial Match": colors.HexColor("#d97706"),
    "Weak Match":    colors.HexColor("#dc2626"),
}


def generate_pdf_report(job: dict, resumes: list) -> bytes:
    """
    Generate a professional PDF leaderboard report for a job posting.
    Returns PDF bytes ready to stream to client.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title", fontSize=18, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#1e1b4b"), spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "Sub", fontSize=10, fontName="Helvetica",
        textColor=colors.HexColor("#6b7280"), spaceAfter=2
    )
    section_style = ParagraphStyle(
        "Section", fontSize=11, fontName="Helvetica-Bold",
        textColor=colors.HexColor("#4f46e5"), spaceBefore=10, spaceAfter=6
    )

    story = []

    # Header
    story.append(Paragraph("☁ Cloud Resume Screener", title_style))
    story.append(Paragraph(f"Screening Report — {job.get('title','')} @ {job.get('company','')}", sub_style))
    story.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')} | "
        f"Total Candidates: {len(resumes)}",
        sub_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e0e7ff"), spaceAfter=10))

    # KPI summary row
    if resumes:
        scores = [r.get("score", 0) for r in resumes]
        avg    = sum(scores) / len(scores)
        kpi_data = [
            ["Top Score", "Average Score", "Candidates", "Strong Matches"],
            [
                f"{scores[0]:.1f}%",
                f"{avg:.1f}%",
                str(len(resumes)),
                str(sum(1 for r in resumes if r.get("verdict") == "Strong Match")),
            ]
        ]
        kpi_table = Table(kpi_data, colWidths=[42*mm]*4)
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND",  (0,0), (-1,0), colors.HexColor("#eef2ff")),
            ("BACKGROUND",  (0,1), (-1,1), colors.HexColor("#f8fafc")),
            ("TEXTCOLOR",   (0,0), (-1,0), colors.HexColor("#4338ca")),
            ("TEXTCOLOR",   (0,1), (-1,1), colors.HexColor("#111827")),
            ("FONTNAME",    (0,0), (-1,0), "Helvetica"),
            ("FONTNAME",    (0,1), (-1,1), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0), (-1,0), 8),
            ("FONTSIZE",    (0,1), (-1,1), 14),
            ("ALIGN",       (0,0), (-1,-1), "CENTER"),
            ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,0), (-1,-1), [colors.HexColor("#eef2ff"), colors.HexColor("#f8fafc")]),
            ("GRID",        (0,0), (-1,-1), 0.5, colors.HexColor("#c7d2fe")),
            ("ROUNDEDCORNERS", [4]),
            ("TOPPADDING",  (0,0), (-1,-1), 8),
            ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ]))
        story.append(kpi_table)
        story.append(Spacer(1, 10))

    # Ranked candidates table
    story.append(Paragraph("Candidate Rankings", section_style))

    headers = ["Rank", "Name", "Score", "Verdict", "Skills", "Exp", "Top Skills"]
    rows = [headers]
    for r in resumes:
        top_skills = ", ".join(
            s for cat in list(r.get("skills", {}).values())[:2]
            for s in cat[:3]
        )[:40]
        rows.append([
            f"#{r.get('rank','')}",
            r.get("candidate_name", "")[:22],
            f"{r.get('score',0):.1f}%",
            r.get("verdict", ""),
            str(r.get("total_skills", 0)),
            f"{r.get('experience_years',0)}yr",
            top_skills,
        ])

    col_widths = [14*mm, 38*mm, 18*mm, 28*mm, 14*mm, 12*mm, None]
    table = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = TableStyle([
        ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#4f46e5")),
        ("TEXTCOLOR",     (0,0), (-1,0), colors.white),
        ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0), 8),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("ALIGN",         (1,1), (1,-1), "LEFT"),
        ("ALIGN",         (6,1), (6,-1), "LEFT"),
        ("FONTNAME",      (0,1), (-1,-1), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-1), 8),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [colors.white, colors.HexColor("#f5f3ff")]),
        ("GRID",          (0,0), (-1,-1), 0.3, colors.HexColor("#e0e7ff")),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 4),
    ])
    # Color verdict cells
    for i, r in enumerate(resumes, start=1):
        c = SCORE_COLORS.get(r.get("verdict",""), colors.gray)
        ts.add("TEXTCOLOR", (3, i), (3, i), c)
        ts.add("FONTNAME",  (3, i), (3, i), "Helvetica-Bold")
        # Shade top 3 ranks
        if i <= 3:
            ts.add("BACKGROUND", (0, i), (0, i), colors.HexColor("#ede9fe"))
    table.setStyle(ts)
    story.append(table)

    # Gap analysis section for top 3
    story.append(Spacer(1, 8))
    story.append(Paragraph("Top 3 Candidates — Gap Analysis", section_style))
    for r in resumes[:3]:
        gap = r.get("gap_analysis", {})
        if not gap:
            continue
        story.append(Paragraph(
            f"<b>#{r['rank']} {r.get('candidate_name','')}</b> — "
            f"{gap.get('total_matched',0)}/{gap.get('total_required',0)} required skills matched "
            f"({gap.get('match_percentage',0)}%)",
            ParagraphStyle("gap", fontSize=9, fontName="Helvetica",
                           textColor=colors.HexColor("#374151"), spaceAfter=2)
        ))
        if gap.get("missing_skills"):
            missing_str = "Missing: " + ", ".join(gap["missing_skills"][:8])
            story.append(Paragraph(
                missing_str,
                ParagraphStyle("miss", fontSize=8, fontName="Helvetica",
                               textColor=colors.HexColor("#dc2626"), spaceAfter=6)
            ))

    # Footer
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e0e7ff")))
    story.append(Paragraph(
        "Generated by Cloud Resume Screener v2 — FastAPI · spaCy · sklearn TF-IDF · Neon PostgreSQL · AWS S3",
        ParagraphStyle("footer", fontSize=7, fontName="Helvetica",
                       textColor=colors.HexColor("#9ca3af"), alignment=TA_CENTER)
    ))

    doc.build(story)
    return buf.getvalue()


def generate_csv_report(job: dict, resumes: list) -> str:
    """Generate CSV export of ranked candidates."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Rank","Name","Score","Verdict","Email","Phone","GitHub","LinkedIn",
        "Experience (yrs)","Total Skills","TF-IDF","Skill Match","Exp Fit","Edu Fit",
        "Skills Matched","Skills Missing","Top Skills"
    ])
    for r in resumes:
        bd  = r.get("score_breakdown", {})
        gap = r.get("gap_analysis", {})
        c   = r.get("contact", {}) or {}
        top = "; ".join(
            s for cat in list(r.get("skills",{}).values())[:3] for s in cat[:3]
        )
        writer.writerow([
            r.get("rank",""),
            r.get("candidate_name",""),
            f"{r.get('score',0):.2f}",
            r.get("verdict",""),
            c.get("email",""),
            c.get("phone",""),
            c.get("github",""),
            c.get("linkedin",""),
            r.get("experience_years",0),
            r.get("total_skills",0),
            f"{bd.get('tfidf_similarity',0):.1f}",
            f"{bd.get('skill_match',0):.1f}",
            f"{bd.get('experience_fit',0):.1f}",
            f"{bd.get('education_fit',0):.1f}",
            gap.get("total_matched",0),
            gap.get("total_missing",0),
            top,
        ])
    return buf.getvalue()
