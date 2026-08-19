"""PDF export — the two engagement volumes a client pays for.

The BLUEPRINT volume is the strategy document: the written blueprint,
who the customers are and how they're kept, the service-blueprint
journey, the organization chart with decision rights, the KPI
scoreboard, the risk register with per-role change impact, and the
execution playbook (quick wins first) — closed by the decision frame.

The TECHNICAL volume is the build document: the owner-voice technical
plan, then the full per-module engineering appendix rendered from the
structured specs the pipeline already produced (features, data model,
agent anatomy, APIs, integrations, security, build order, acceptance),
and the core operating procedures.

Every page is real generated content — sections a run doesn't have are
simply absent, the same fail-open rule as everywhere. reportlab, not
HTML-to-PDF: pure-Python, no headless browser in the Docker image. Each
volume opens with a cover and a table of contents (multiBuild resolves
the page numbers).
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
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.config import settings
from app.models import Request

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#52607a")
ACCENT = colors.HexColor("#2563eb")
LINE = colors.HexColor("#dbe4f2")
TINT = colors.HexColor("#f2f6fd")
GOOD = colors.HexColor("#047857")
WARN = colors.HexColor("#b45309")

# Style names matter: "h1toc"/"h2toc" are how headings register themselves
# in the table of contents (see _EngagementDoc.afterFlowable).
_S = {
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=9, textColor=ACCENT,
                             spaceAfter=4, leading=12),
    "cover_title": ParagraphStyle("cover_title", fontName="Helvetica-Bold", fontSize=34,
                                  textColor=INK, leading=38, spaceAfter=10),
    "cover_sub": ParagraphStyle("cover_sub", fontName="Helvetica", fontSize=13, textColor=MUTED,
                                leading=18, spaceAfter=4),
    "h1toc": ParagraphStyle("h1toc", fontName="Helvetica-Bold", fontSize=15, textColor=INK,
                            leading=19, spaceBefore=16, spaceAfter=6),
    "h2toc": ParagraphStyle("h2toc", fontName="Helvetica-Bold", fontSize=11.5, textColor=INK,
                            leading=15, spaceBefore=11, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT,
                         leading=13, spaceBefore=8, spaceAfter=3),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=INK,
                           leading=14.5, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, textColor=INK,
                             leading=14, leftIndent=10, bulletIndent=2, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11.5),
    "cellhead": ParagraphStyle("cellhead", fontName="Helvetica-Bold", fontSize=8, textColor=MUTED, leading=10),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, textColor=MUTED, leading=12),
    "toc0": ParagraphStyle("toc0", fontName="Helvetica-Bold", fontSize=10, textColor=INK, leading=16),
    "toc1": ParagraphStyle("toc1", fontName="Helvetica", fontSize=9, textColor=MUTED,
                           leading=14, leftIndent=12),
}

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _rich(text: str) -> str:
    """Escape, then translate the markdown inline forms our prompts emit."""
    out = html.escape(str(text), quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    return out


def _h1(text: str):
    return [
        Spacer(1, 4),
        Paragraph(_rich(text), _S["h1toc"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=6),
    ]


class _EngagementDoc(SimpleDocTemplate):
    """SimpleDocTemplate that feeds every h1toc/h2toc heading into the
    TableOfContents flowable during multiBuild passes."""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            name = flowable.style.name
            if name == "h1toc":
                self.notify("TOCEntry", (0, flowable.getPlainText(), self.page))
            elif name == "h2toc":
                self.notify("TOCEntry", (1, flowable.getPlainText(), self.page))


def _split_md_sections(md: str) -> list[tuple[str, str]]:
    """[(heading, section_markdown_including_heading)] in document order.
    Text before the first ## becomes ('', preamble)."""
    sections = []
    current_head = ""
    current_lines: list[str] = []
    for raw in (md or "").splitlines():
        if raw.strip().startswith("## "):
            if current_lines or current_head:
                sections.append((current_head, "\n".join(current_lines)))
            current_head = raw.strip()[3:].strip()
            current_lines = [raw]
        else:
            current_lines.append(raw)
    if current_lines or current_head:
        sections.append((current_head, "\n".join(current_lines)))
    return [(h, body) for h, body in sections if body.strip()]


def _markdown_flowables(md: str) -> list:
    flows = []
    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            flows += _h1(line[3:])
        elif line.startswith("### "):
            flows.append(Paragraph(_rich(line[4:]), _S["h2toc"]))
        elif line.startswith(("- ", "* ")):
            flows.append(Paragraph(_rich(line[2:]), _S["bullet"], bulletText="•"))
        elif re.match(r"^\d+\.\s", line):
            num, rest = line.split(".", 1)
            flows.append(Paragraph(_rich(rest.strip()), _S["bullet"], bulletText=f"{num}."))
        else:
            flows.append(Paragraph(_rich(line), _S["body"]))
    return flows


def _logo_flowable():
    path = getattr(settings, "BMV_LOGO_PATH", None)
    if not path or not os.path.isfile(path):
        return None
    img = Image(path, width=16 * mm, height=16 * mm)
    img.hAlign = "LEFT"
    return img


def _cover(doc_label: str, sub_label: str, req: Request) -> list:
    concept = req.concept_name or req.business_name or ""
    date = datetime.utcnow().strftime("%B %d, %Y")
    logo = _logo_flowable()
    return ([logo, Spacer(1, 4)] if logo else []) + [
        Spacer(1, 50 * mm) if logo else Spacer(1, 60 * mm),
        Paragraph("BUILD MY VERSION", _S["kicker"]),
        HRFlowable(width=30 * mm, thickness=2.5, color=ACCENT, spaceAfter=12, hAlign="LEFT"),
        Paragraph(_rich(doc_label), _S["cover_title"]),
        Paragraph(_rich(concept), _S["cover_sub"]),
        Paragraph(_rich(sub_label), _S["cover_sub"]),
        Spacer(1, 8),
        Paragraph(_rich(f"Prepared exclusively for {req.business_name} · {date}"), _S["meta"]),
        Paragraph("Confidential — for the addressee's team and advisors.", _S["meta"]),
        PageBreak(),
    ]


def _toc() -> list:
    toc = TableOfContents()
    toc.levelStyles = [_S["toc0"], _S["toc1"]]
    return [
        Paragraph("Contents", _S["h1toc"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=8),
        toc,
        PageBreak(),
    ]


def _table(head: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[Paragraph(t, _S["cellhead"]) for t in head]]
    for row in rows:
        data.append([Paragraph(_rich(v or "—"), _S["cell"]) for v in row])
    table = Table(data, colWidths=widths, repeatRows=1)
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
    return table


# ── blueprint-volume sections ────────────────────────────────────────────


def _customers_flowables(business_case: dict) -> list:
    cust = (business_case or {}).get("customers") or {}
    segments = cust.get("segments") or []
    channels = cust.get("channels") or []
    if not segments and not channels:
        return []
    flows = _h1("Who you serve, and how they arrive")
    if segments:
        flows.append(Paragraph("Customer segments", _S["h3"]))
        for seg in segments:
            flows.append(Paragraph(_rich(seg), _S["bullet"], bulletText="•"))
    if channels:
        flows.append(Paragraph("How they find you", _S["h3"]))
        for ch in channels:
            flows.append(Paragraph(_rich(ch), _S["bullet"], bulletText="•"))
    if cust.get("how_kept"):
        flows.append(Paragraph("<b>How they're kept:</b> " + _rich(cust["how_kept"]), _S["body"]))
    return flows


def _journey_flowables(journey: dict | None) -> list:
    stages = (journey or {}).get("stages") or []
    if not stages:
        return []
    flows = _h1("The customer journey")
    flows.append(Paragraph(
        "What your customer does at every stage — and which parts of the system work for them "
        "behind the scenes.", _S["meta"],
    ))
    for i, s in enumerate(stages, start=1):
        flows.append(Paragraph(f"{i}. {_rich(s.get('stage') or '')}", _S["h2toc"]))
        if s.get("customer_action"):
            flows.append(Paragraph("<b>Your customer:</b> " + _rich(s["customer_action"]), _S["body"]))
        if s.get("frontstage"):
            flows.append(Paragraph("<b>What they see:</b> " + _rich(s["frontstage"]), _S["body"]))
        if s.get("backstage_modules"):
            flows.append(Paragraph(
                "<b>Working backstage:</b> " + _rich(", ".join(s["backstage_modules"])), _S["body"],
            ))
        if s.get("fail_point_removed"):
            flows.append(Paragraph(
                "<b>What no longer goes wrong:</b> " + _rich(s["fail_point_removed"]), _S["body"],
            ))
    return flows


def _organization_flowables(org: dict | None) -> list:
    roles = (org or {}).get("roles") or []
    impact = (org or {}).get("change_impact") or []
    if not roles:
        return []
    flows = _h1("The organization — humans and AI on one chart")
    rows = []
    for r in roles:
        rows.append([
            ("AI · " if r.get("type") == "ai" else "") + (r.get("role") or ""),
            "; ".join(r.get("responsibilities") or []),
            r.get("decides_alone") or "—",
            r.get("hands_off") or "—",
        ])
    flows.append(_table(
        ["Role", "Responsibilities", "Decides alone", "Hands off"],
        rows, [34 * mm, 58 * mm, 39 * mm, 39 * mm],
    ))
    if impact:
        flows.append(Paragraph("What changes for your people", _S["h2toc"]))
        for c in impact:
            flows.append(Paragraph(
                f"<b>{_rich(c.get('role') or '')}:</b> " + _rich(c.get("what_changes") or "")
                + (" <b>Must learn:</b> " + _rich(c["must_learn"]) if c.get("must_learn") else ""),
                _S["bullet"], bulletText="•",
            ))
    return flows


def _scoreboard_flowables(scoreboard: list) -> list:
    if not scoreboard:
        return []
    flows = _h1("The scoreboard")
    flows.append(Paragraph(
        "Baselines are your own numbers, or “measure in week 1” — never an estimate of ours.",
        _S["meta"],
    ))
    flows.append(Spacer(1, 4))
    flows.append(_table(
        ["Metric", "Baseline", "Target", "Owner", "Review"],
        [[r.get("metric"), r.get("baseline"), r.get("target"), r.get("owner"), r.get("review")]
         for r in scoreboard],
        [42 * mm, 34 * mm, 52 * mm, 20 * mm, 22 * mm],
    ))
    return flows


def _risks_flowables(risks: list) -> list:
    if not risks:
        return []
    flows = _h1("What could make this fail — honestly")
    flows.append(Paragraph(
        "The real risks are usually habits, not technology. Each one has a counter-move.",
        _S["meta"],
    ))
    for r in risks:
        flows.append(Paragraph(_rich(r.get("risk") or ""), _S["h2toc"]))
        if r.get("mitigation"):
            flows.append(Paragraph("<b>Counter-move:</b> " + _rich(r["mitigation"]), _S["body"]))
        if r.get("who_feels_it"):
            flows.append(Paragraph("<b>Felt by:</b> " + _rich(r["who_feels_it"]), _S["body"]))
    return flows


_WHO = {"you": "You", "bmv": "BMV", "partner": "Partner"}
_PHASES = [
    ("before", "Before the build — prepare the ground"),
    ("during", "During the build — stay in the loop"),
    ("after", "After launch — run it by the numbers"),
]


def _playbook_flowables(playbook: dict | None) -> list:
    pb = playbook or {}
    steps = pb.get("steps") or []
    wins = pb.get("quick_wins") or []
    people = pb.get("people_plan") or {}
    if not steps and not wins:
        return []
    flows = _h1("The execution playbook")
    if wins:
        flows.append(Paragraph("Your first 30 days — value before any software", _S["h2toc"]))
        for w in wins:
            tag = " <b>(no software needed)</b>" if w.get("no_software") else ""
            flows.append(Paragraph(
                f"<b>{_rich(w.get('title') or '')}</b> — " + _rich(w.get("detail") or "") + tag,
                _S["bullet"], bulletText="•",
            ))
    for phase_id, phase_label in _PHASES:
        phase_steps = [s for s in steps if s.get("phase") == phase_id]
        if not phase_steps:
            continue
        flows.append(Paragraph(phase_label, _S["h2toc"]))
        for i, s in enumerate(phase_steps, start=1):
            who = _WHO.get(s.get("who") or "", s.get("who") or "")
            suffix_bits = [b for b in (who, s.get("horizon")) if b]
            suffix = f" <i>({' · '.join(suffix_bits)})</i>" if suffix_bits else ""
            flows.append(Paragraph(
                f"<b>{_rich(s.get('title') or '')}</b> — " + _rich(s.get("detail") or "") + suffix,
                _S["bullet"], bulletText=f"{i}.",
            ))
    ai_covers = people.get("ai_covers") or []
    humans = people.get("humans_needed") or []
    if ai_covers or humans:
        flows.append(Paragraph("The people plan", _S["h2toc"]))
        for line in ai_covers:
            flows.append(Paragraph("<b>AI covers:</b> " + _rich(line), _S["bullet"], bulletText="•"))
        for h in humans:
            flows.append(Paragraph(
                f"<b>{_rich(h.get('role') or '')}</b> — when: " + _rich(h.get("when") or "")
                + ". " + _rich(h.get("why") or ""),
                _S["bullet"], bulletText="•",
            ))
    return flows


def _decision_flowables() -> list:
    flows = _h1("Three ways forward")
    for title, body in [
        ("We execute this plan for you",
         "The team that wrote it builds it — module by module, in the order above, with you "
         "reviewing at every phase. Email us this document's reference and we reply with the "
         "exact quote."),
        ("Book a deep-dive working session",
         "90 minutes with our consultant inside your real operation. We correct this plan "
         "together and you leave with an exact quote. $200, credited in full against your build."),
        ("Take the plan — it's yours",
         "Every module, data model, procedure, build sequence and acceptance check is written "
         "down here. A competent team can build from this document."),
    ]:
        flows.append(Paragraph(title, _S["h2toc"]))
        flows.append(Paragraph(body, _S["body"]))
    flows.append(Spacer(1, 6))
    flows.append(Paragraph("<b>consulting@buildmyversion.com</b>", _S["body"]))
    return flows


# ── technical-volume sections ────────────────────────────────────────────


def _module_appendix_flowables(modules: list) -> list:
    if not modules:
        return []
    flows = _h1("Module appendix — the engineering detail")
    flows.append(Paragraph(
        "The full anatomy of every module, exactly as specified. This is the level a build team "
        "estimates and works from.", _S["meta"],
    ))
    for idx, m in enumerate(modules, start=1):
        spec = m.get("spec") or {}
        tech = m.get("tech") or {}
        flows.append(Paragraph(f"{idx}. {_rich(m.get('name') or '')}", _S["h2toc"]))
        if m.get("purpose"):
            flows.append(Paragraph(_rich(m["purpose"]), _S["body"]))
        if m.get("users"):
            flows.append(Paragraph("<b>Used by:</b> " + _rich(", ".join(m["users"])), _S["body"]))

        feats = spec.get("features") or []
        if feats:
            flows.append(Paragraph("Features", _S["h3"]))
            for f in feats:
                flows.append(Paragraph(
                    f"<b>{_rich(f.get('name') or '')}</b> — " + _rich(f.get("description") or ""),
                    _S["bullet"], bulletText="•",
                ))
        if spec.get("screens"):
            flows.append(Paragraph("Screens", _S["h3"]))
            flows.append(Paragraph(_rich(" · ".join(spec["screens"])), _S["body"]))

        data_model = tech.get("data_model") or []
        if data_model:
            flows.append(Paragraph("Data model", _S["h3"]))
            flows.append(_table(
                ["Entity", "Key fields"],
                [[e.get("entity"), ", ".join(e.get("fields") or [])] for e in data_model],
                [45 * mm, 125 * mm],
            ))

        agent = tech.get("ai_agent")
        if agent:
            flows.append(Paragraph("The AI agent", _S["h3"]))
            if agent.get("purpose"):
                flows.append(Paragraph(
                    "<b>Purpose:</b> " + _rich(agent["purpose"])
                    + (f" <i>(model tier: {_rich(agent['model_tier'])})</i>" if agent.get("model_tier") else ""),
                    _S["body"],
                ))
            for label, key in [("Knows (brain)", "brain"), ("Guardrails — never does", "guardrails"),
                               ("Evaluation — trusted when", "evaluation")]:
                items = agent.get(key) or []
                if items:
                    flows.append(Paragraph(f"<b>{label}:</b>", _S["body"]))
                    for it in items:
                        flows.append(Paragraph(_rich(it), _S["bullet"], bulletText="•"))
            tools = agent.get("tools") or []
            if tools:
                flows.append(Paragraph("<b>Tools:</b>", _S["body"]))
                for t in tools:
                    flows.append(Paragraph(
                        f"<b>{_rich(t.get('name') or '')}</b> — " + _rich(t.get("does") or ""),
                        _S["bullet"], bulletText="•",
                    ))
            if agent.get("memory"):
                flows.append(Paragraph("<b>Memory:</b> " + _rich(agent["memory"]), _S["body"]))
            if agent.get("escalation"):
                flows.append(Paragraph("<b>Escalation:</b> " + _rich(agent["escalation"]), _S["body"]))
        elif spec.get("ai") is None and "ai" in spec:
            flows.append(Paragraph("<b>No AI component — deliberately.</b>", _S["body"]))

        apis = tech.get("apis") or []
        if apis:
            flows.append(Paragraph("APIs & events", _S["h3"]))
            for a in apis:
                flows.append(Paragraph(
                    f"<b>{_rich(a.get('name') or '')}</b> — " + _rich(a.get("does") or ""),
                    _S["bullet"], bulletText="•",
                ))
        integrations = tech.get("integration_details") or []
        if integrations:
            flows.append(Paragraph("Integrations", _S["h3"]))
            for i2 in integrations:
                flows.append(Paragraph(
                    f"<b>{_rich(i2.get('system') or '')}</b> ({_rich(i2.get('direction') or '')}) — "
                    + _rich(i2.get("data") or ""),
                    _S["bullet"], bulletText="•",
                ))
        if tech.get("security"):
            flows.append(Paragraph("Security", _S["h3"]))
            for s2 in tech["security"]:
                flows.append(Paragraph(_rich(s2), _S["bullet"], bulletText="•"))
        if tech.get("build_sequence"):
            flows.append(Paragraph("Build order", _S["h3"]))
            for i3, step in enumerate(tech["build_sequence"], start=1):
                flows.append(Paragraph(_rich(step), _S["bullet"], bulletText=f"{i3}."))
        if tech.get("done_when"):
            flows.append(Paragraph("It's finished when", _S["h3"]))
            for d in tech["done_when"]:
                flows.append(Paragraph(_rich(d), _S["bullet"], bulletText="✓"))
        if spec.get("kpis"):
            flows.append(Paragraph("<b>You'll know it's working when:</b> " + _rich("; ".join(spec["kpis"])), _S["body"]))
    return flows


def _procedures_flowables(procedures: list) -> list:
    if not procedures:
        return []
    flows = _h1("Core procedures")
    flows.append(Paragraph(
        "The recurring routines this business runs on once live — who (or which AI) does each step.",
        _S["meta"],
    ))
    for p in procedures:
        flows.append(Paragraph(_rich(p.get("name") or ""), _S["h2toc"]))
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


# ── assembly ─────────────────────────────────────────────────────────────


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 12 * mm, "Build My Version · buildmyversion.com · consulting@buildmyversion.com")
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def build_pdf(req: Request, kind: str) -> str:
    """Render one engagement volume ('blueprint' | 'technical') to a PDF
    file and return its path. Raises ValueError when the underlying
    document is not on the request yet."""
    if kind == "blueprint":
        md = req.mvp_blueprint
        label, sub = "The Blueprint", "The strategy volume of your engagement"
    else:
        md = req.technical_plan
        label, sub = "The Technical Plan", "The build volume of your engagement"
    if not md:
        raise ValueError(f"{kind} document not ready")

    business_case = _loads(req.business_case_json, {})
    journey = _loads(req.journey_json, None)
    org = _loads(req.org_json, None)
    scoreboard = _loads(req.scoreboard_json, [])
    risks = _loads(req.risks_json, [])
    playbook = _loads(req.playbook_json, None)
    procedures = (_loads(req.procedures_json, {}) or {}).get("procedures") or []
    modules = _loads(req.modules_json, [])

    flows = _cover(label, sub, req)
    flows += _toc()

    if kind == "blueprint":
        # The canonical consultancy order: front matter (summary, engagement
        # scope, current state, opportunity), then model, journey, solution,
        # operating model, roadmap, scoreboard, risks, success, decision.
        # The written document's sections are interleaved with the
        # structured layers at their proper positions; any section the
        # model wrote that no slot claims still lands before the close —
        # content is never dropped.
        sections = _split_md_sections(md)
        used = set()

        def md_slot(pattern: str) -> list:
            for i, (head, body) in enumerate(sections):
                if i in used:
                    continue
                if re.search(pattern, head, re.IGNORECASE):
                    used.add(i)
                    return _markdown_flowables(body)
            return []

        flows += md_slot(r"executive|summary")
        flows += md_slot(r"engagement|context")
        flows += md_slot(r"where you are|today")
        flows += md_slot(r"opportunit")
        flows += _customers_flowables(business_case)
        flows += md_slot(r"makes money")
        flows += _journey_flowables(journey)
        flows += md_slot(r"module by module|the product")
        flows += _organization_flowables(org)
        flows += md_slot(r"build first")
        flows += _playbook_flowables(playbook)
        flows += _scoreboard_flowables(scoreboard)
        flows += _risks_flowables(risks)
        flows += md_slot(r"success looks like")
        for i, (_, body) in enumerate(sections):
            if i not in used:
                flows += _markdown_flowables(body)
        flows += _decision_flowables()
    else:
        flows += _markdown_flowables(md)
        flows += _module_appendix_flowables(modules)
        flows += _procedures_flowables(procedures)
        flows += _decision_flowables()

    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{req.id}-{kind}.pdf")

    doc = _EngagementDoc(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=20 * mm,
        title=f"{req.concept_name or req.business_name} — {label}",
        author="Build My Version",
    )
    doc.multiBuild(flows, onFirstPage=_footer, onLaterPages=_footer)
    return out_path
