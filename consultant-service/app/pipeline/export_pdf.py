"""PDF export for the two written deliverables — the blueprint and the
technical plan — as documents a client can print, forward, and file.

reportlab, not HTML-to-PDF: pure-Python, no headless browser or system
libraries in the Docker image. The markdown the pipeline writes is
regular enough (##/### headings, bullets, **bold** lead-ins) that a
small purpose-built parser covers it; anything unrecognized degrades to
a plain paragraph rather than an error.

The blueprint PDF appends the structured consultancy layers (scoreboard,
journey); the technical PDF appends the core procedures. Sections that a
run doesn't have are simply absent — same fail-open rule as everywhere.
"""

import html
import json
import os
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import settings
from app.models import Request

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#52607a")
ACCENT = colors.HexColor("#2563eb")
LINE = colors.HexColor("#dbe4f2")
TINT = colors.HexColor("#f2f6fd")

_S = {
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=8.5, textColor=ACCENT,
                             spaceAfter=4, leading=12, tracking=1),
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=26, textColor=INK,
                            leading=30, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11, textColor=MUTED,
                               leading=15, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, textColor=INK,
                         leading=19, spaceBefore=16, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, textColor=INK,
                         leading=15, spaceBefore=11, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=INK,
                           leading=14.5, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, textColor=INK,
                             leading=14, leftIndent=10, bulletIndent=2, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11.5),
    "cellhead": ParagraphStyle("cellhead", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=10),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, textColor=MUTED, leading=12),
}

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _rich(text: str) -> str:
    """Escape, then translate the markdown inline forms our prompts emit."""
    out = html.escape(text, quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    return out


def _markdown_flowables(md: str) -> list:
    flows = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            flows.append(Spacer(1, 4))
            flows.append(Paragraph(_rich(line[3:]), _S["h1"]))
            flows.append(HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=6))
        elif line.startswith("### "):
            flows.append(Paragraph(_rich(line[4:]), _S["h2"]))
        elif line.startswith(("- ", "* ")):
            flows.append(Paragraph(_rich(line[2:]), _S["bullet"], bulletText="•"))
        elif re.match(r"^\d+\.\s", line):
            num, rest = line.split(".", 1)
            flows.append(Paragraph(_rich(rest.strip()), _S["bullet"], bulletText=f"{num}."))
        else:
            flows.append(Paragraph(_rich(line), _S["body"]))
    return flows


def _cover(doc_label: str, req: Request) -> list:
    concept = req.concept_name or req.business_name or ""
    date = datetime.utcnow().strftime("%B %d, %Y")
    return [
        Paragraph("BUILD MY VERSION", _S["kicker"]),
        Paragraph(_rich(doc_label), _S["title"]),
        Paragraph(_rich(f"{concept} — prepared exclusively for {req.business_name}"), _S["subtitle"]),
        Paragraph(date, _S["meta"]),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=14),
    ]


def _scoreboard_flowables(scoreboard: list) -> list:
    if not scoreboard:
        return []
    head = [Paragraph(t, _S["cellhead"]) for t in ("Metric", "Baseline", "Target", "Owner", "Review")]
    rows = [head]
    for r in scoreboard:
        rows.append([
            Paragraph(_rich(str(r.get(k) or "—")), _S["cell"])
            for k in ("metric", "baseline", "target", "owner", "review")
        ])
    table = Table(rows, colWidths=[42 * mm, 34 * mm, 52 * mm, 20 * mm, 22 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), TINT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, LINE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return [
        Spacer(1, 4),
        Paragraph("The scoreboard", _S["h1"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=6),
        Paragraph(
            "Baselines are your own numbers, or “measure in week 1” — never an estimate of ours.",
            _S["meta"],
        ),
        Spacer(1, 4),
        table,
    ]


def _journey_flowables(journey: dict | None) -> list:
    stages = (journey or {}).get("stages") or []
    if not stages:
        return []
    flows = [
        Spacer(1, 4),
        Paragraph("The customer journey", _S["h1"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=6),
    ]
    for i, s in enumerate(stages, start=1):
        flows.append(Paragraph(f"{i}. {_rich(s.get('stage') or '')}", _S["h2"]))
        if s.get("customer_action"):
            flows.append(Paragraph("<b>Your customer:</b> " + _rich(s["customer_action"]), _S["body"]))
        if s.get("frontstage"):
            flows.append(Paragraph("<b>What they see:</b> " + _rich(s["frontstage"]), _S["body"]))
        if s.get("fail_point_removed"):
            flows.append(Paragraph("<b>What no longer goes wrong:</b> " + _rich(s["fail_point_removed"]), _S["body"]))
    return flows


def _procedures_flowables(procedures: list) -> list:
    if not procedures:
        return []
    flows = [
        Spacer(1, 4),
        Paragraph("Core procedures", _S["h1"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=6),
        Paragraph(
            "The recurring routines this business runs on once live — who (or which AI) does each step.",
            _S["meta"],
        ),
    ]
    for p in procedures:
        flows.append(Paragraph(_rich(p.get("name") or ""), _S["h2"]))
        if p.get("trigger"):
            flows.append(Paragraph("<b>Starts when:</b> " + _rich(p["trigger"]), _S["body"]))
        for i, step in enumerate(p.get("steps") or [], start=1):
            actor = step.get("actor") or ""
            label = f"<b>[{_rich(actor)}]</b> " if actor else ""
            flows.append(Paragraph(label + _rich(step.get("step") or ""), _S["bullet"], bulletText=f"{i}."))
        for e in p.get("exceptions") or []:
            flows.append(
                Paragraph(
                    f"<b>If {_rich(e.get('when') or '')}:</b> " + _rich(e.get("then") or ""),
                    _S["bullet"], bulletText="!",
                )
            )
    return flows


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 12 * mm, "Build My Version · buildmyversion.com · consulting@buildmyversion.com")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf(req: Request, kind: str) -> str:
    """Render one deliverable ('blueprint' | 'technical') to a PDF file and
    return its path. Raises ValueError when the underlying document is not
    on the request yet."""
    if kind == "blueprint":
        md = req.mvp_blueprint
        label = "The Blueprint"
    else:
        md = req.technical_plan
        label = "The Technical Plan"
    if not md:
        raise ValueError(f"{kind} document not ready")

    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{req.id}-{kind}.pdf")

    flows = _cover(label, req)
    flows += _markdown_flowables(md)

    if kind == "blueprint":
        flows += _journey_flowables(json.loads(req.journey_json) if req.journey_json else None)
        flows += _scoreboard_flowables(json.loads(req.scoreboard_json) if req.scoreboard_json else [])
    else:
        procs = json.loads(req.procedures_json)["procedures"] if req.procedures_json else []
        flows += _procedures_flowables(procs)

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"{req.concept_name or req.business_name} — {label}",
        author="Build My Version",
    )
    doc.build(flows, onFirstPage=_footer, onLaterPages=_footer)
    return out_path
