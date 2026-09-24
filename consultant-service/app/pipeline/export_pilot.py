"""The action plan as a document they can print, pin up, and send to staff.

Same faces, colours and page chrome as the three volumes, so it sits in the
same binder — but short on purpose. The volumes are read once; this one is
used every week for the length of the trial, so it opens with what to do,
carries the message ready to send, and ends with a blank tracking sheet the
owner fills in by hand if they would rather not use the tracker online.
"""

import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, HRFlowable, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.config import settings
from app.models import Request
from app.pipeline import action_plan as _plan
from app.pipeline import answer as _answer
from app.pipeline.export_pdf import (
    ACCENT, LINE, TINT, WARN, WARN_BG, ZEBRA, _S, _callout, _cover_painter, _page_chrome, _rich, _table,
)


def _safe(text: str) -> str:
    """The brand faces ship as small subsets without the maths signs the
    working uses; a sign they cannot draw prints as a hollow box."""
    return (str(text or "").replace("≈ ", "about ").replace("≈", "about ")
            .replace("×", "x").replace("−", "-"))


def _h(text: str) -> list:
    return [Spacer(1, 12), Paragraph(_rich(text), _S["h1toc"]),
            HRFlowable(width=14 * mm, thickness=2.2, color=ACCENT, spaceBefore=3, spaceAfter=9, hAlign="LEFT")]


def _sheet(measures: list[dict], weeks: int) -> Table:
    """The tracking sheet: one row per measure, one column per week, blank."""
    weeks = max(2, min(12, int(weeks or 6)))
    head = ["Measure", "Today"] + [f"W{i}" for i in range(1, weeks + 1)]
    rows = []
    for m in measures:
        base = m.get("baseline")
        base_txt = (f"{base:g}" if isinstance(base, (int, float)) else "measure in W1")
        rows.append([f"{m.get('name', '')}" + (f" ({m['unit']})" if m.get("unit") else ""), base_txt]
                    + [" "] * weeks)  # a space, not "": the table prints a dash for empty
    usable = 174 * mm
    first, second = 50 * mm, 22 * mm
    rest = (usable - first - second) / weeks
    table = _table(head, rows, [first, second] + [rest] * weeks)
    table.setStyle(TableStyle([
        ("GRID", (2, 1), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 11),
        ("TOPPADDING", (0, 1), (-1, -1), 11),
    ]))
    return table


def build_pilot_pdf(req: Request) -> str:
    plan = _plan.load(req)
    if not plan or plan.get("status") != _plan.READY:
        raise ValueError("plan not ready")
    ans = _answer.load(req) or {}
    name = req.business_name or "Your business"
    title = plan.get("title") or "Your first-weeks plan"

    flows = [
        Spacer(1, 60 * mm),
        Paragraph(_rich(f"{plan.get('weeks', 6)} weeks").upper(), _S["cover_vol"]),
        Paragraph(_rich(title), _S["cover_title"]),
        HRFlowable(width=16 * mm, thickness=2.5, color=ACCENT, spaceAfter=12, hAlign="LEFT"),
        Paragraph(_rich(name), _S["cover_sub"]),
        Spacer(1, 14),
        Paragraph(_rich(f"Prepared {datetime.utcnow().strftime('%B %d, %Y')}"), _S["meta"]),
        Paragraph("None of this needs software to begin.", _S["meta"]),
        NextPageTemplate("body"),
        PageBreak(),
    ]

    finding = " ".join(x for x in (ans.get("headline"), ans.get("turn")) if x)
    if finding:
        flows += _h("What we found")
        flows.append(Paragraph(f"<b>{_rich(finding)}</b>", _S["body"]))
        if ans.get("sub"):
            flows.append(Paragraph(_rich(ans["sub"]), _S["body"]))
        move = ans.get("move")
        if move:
            flows.append(_callout(
                f"<b>{_rich(_safe(move['display']))}</b> — {_rich(move.get('label') or '')}<br/>"
                f"<font color='#52607a'>Working: {_rich(_safe(move['working']))}. "
                f"Numbers marked proposed are ours, not yours.</font>", ACCENT, TINT))
    if plan.get("summary"):
        flows.append(Spacer(1, 6))
        flows.append(Paragraph(_rich(plan["summary"]), _S["body"]))

    flows += _h("Start here on Monday")
    for i, step in enumerate(plan.get("monday") or [], 1):
        flows.append(KeepTogether([
            Paragraph(f"<b>{_rich(step['do'])}</b>", _S["bullet"], bulletText=f"{i}."),
            Paragraph(_rich(step.get("why") or ""), _S["meta"]) if step.get("why") else Spacer(1, 0),
            Spacer(1, 4),
        ]))

    if plan.get("schedule"):
        flows += _h("Week by week")
        flows.append(_table(["When", "What happens"],
                            [[r["when"], r["do"]] for r in plan["schedule"]], [32 * mm, 142 * mm]))

    if plan.get("message"):
        msg = plan["message"]
        flows += _h("The message, ready to send")
        flows.append(Paragraph(_rich(f"To {msg.get('to', 'your customers')}:"), _S["meta"]))
        flows.append(Spacer(1, 4))
        flows.append(_callout(_rich(msg["text"]).replace("\n", "<br/>"), ACCENT, TINT))

    if plan.get("measures"):
        flows += _h("What to track")
        flows.append(_table(
            ["Measure", "Should", "Today", "Where today comes from"],
            [[m["name"] + (f" ({m['unit']})" if m.get("unit") else ""),
              {"up": "go up", "down": "come down", "hold": "hold steady"}.get(m.get("watch"), "go up"),
              f"{m['baseline']:g}" if isinstance(m.get("baseline"), (int, float)) else "—",
              "your own figure" if m.get("baseline_from") else "measure it in week 1"]
             for m in plan["measures"]],
            [70 * mm, 28 * mm, 24 * mm, 52 * mm]))

    if plan.get("decision_rule"):
        flows += _h("The decision at the end")
        flows.append(_callout(f"<b>{_rich(plan['decision_rule'])}</b>", ACCENT, TINT))
        if plan.get("if_it_fails"):
            flows.append(Spacer(1, 6))
            flows.append(Paragraph(_rich(f"If it says stop: {plan['if_it_fails']}"), _S["body"]))

    if plan.get("assumptions"):
        flows += _h("What this plan has not proven yet")
        flows.append(_callout(
            "The trial exists to settle these. Until it does, treat them as assumptions:<br/>"
            + "<br/>".join(f"• {_rich(a)}" for a in plan["assumptions"]), WARN, WARN_BG))

    if plan.get("measures"):
        flows += [PageBreak()] + _h("Tracking sheet")
        flows.append(Paragraph("Fill in one column at the end of each week. Or use the tracker "
                               "on your package page, which draws it for you.", _S["meta"]))
        flows.append(Spacer(1, 8))
        flows.append(_sheet(plan["measures"], plan.get("weeks") or 6))

    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{req.id}-pilot.pdf")
    doc = BaseDocTemplate(out_path, pagesize=A4, title=f"{name} — {title}", author="Build My Version")
    W, H = A4
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[Frame(74 * mm, 20 * mm, W - 92 * mm, H - 40 * mm, id="cover")],
                     onPage=_cover_painter("pilot", req)),
        PageTemplate(id="body", frames=[Frame(18 * mm, 20 * mm, W - 36 * mm, H - 36 * mm, id="content")],
                     onPage=_page_chrome(title, name)),
    ])
    doc.build(flows)
    return out_path
