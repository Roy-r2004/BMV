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

from reportlab import rl_config

# Deterministic output: identical content must produce identical bytes, so
# a release hash identifies CONTENT, not the moment of rendering. (Run 42's
# reconciliation: three byte-different sets whose text was identical —
# every difference was an embedded build timestamp.)
rl_config.invariant = 1

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    Image,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.config import settings
from app.models import Request

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")

# The brand faces, embedded. Helvetica remains the silent fallback so a
# missing font file can never take a paid deliverable down with it.
_FONTS_OK = False
try:
    pdfmetrics.registerFont(TTFont("Syne-Bold", os.path.join(_FONT_DIR, "Syne-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("Syne-XBold", os.path.join(_FONT_DIR, "Syne-ExtraBold.ttf")))
    pdfmetrics.registerFont(TTFont("Plex", os.path.join(_FONT_DIR, "PlexSans.ttf")))
    pdfmetrics.registerFont(TTFont("Plex-Md", os.path.join(_FONT_DIR, "PlexSans-Medium.ttf")))
    pdfmetrics.registerFont(TTFont("Plex-Sb", os.path.join(_FONT_DIR, "PlexSans-SemiBold.ttf")))
    pdfmetrics.registerFont(TTFont("Plex-Bd", os.path.join(_FONT_DIR, "PlexSans-Bold.ttf")))
    # <b>/<i> inside paragraphs resolve through the family map.
    registerFontFamily("Plex", normal="Plex", bold="Plex-Sb", italic="Plex-Md", boldItalic="Plex-Bd")
    _FONTS_OK = True
except Exception:  # pragma: no cover — depends on packaged files
    pass


def _face(brand: str, fallback: str) -> str:
    return brand if _FONTS_OK else fallback


F_DISPLAY = _face("Syne-XBold", "Helvetica-Bold")
F_HEAD = _face("Syne-Bold", "Helvetica-Bold")
F_BODY = _face("Plex", "Helvetica")
F_MD = _face("Plex-Md", "Helvetica")
F_SB = _face("Plex-Sb", "Helvetica-Bold")
F_BD = _face("Plex-Bd", "Helvetica-Bold")

INK = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#52607a")
ACCENT = colors.HexColor("#2563eb")
ACCENT_DK = colors.HexColor("#1e40af")
LINE = colors.HexColor("#dbe4f2")
TINT = colors.HexColor("#eef4ff")
ZEBRA = colors.HexColor("#f6f9ff")
GOOD = colors.HexColor("#047857")
GOOD_BG = colors.HexColor("#e5f5ef")
WARN = colors.HexColor("#b45309")
WARN_BG = colors.HexColor("#fdf3e3")
RISK = colors.HexColor("#be123c")
RISK_BG = colors.HexColor("#fdeef2")

# Inline hex strings for <font color=...> spans inside paragraphs.
HEX_ACCENT = "#2563eb"
HEX_GOOD = "#047857"
HEX_RISK = "#be123c"
HEX_WARN = "#b45309"
PANEL = colors.HexColor("#0b1220")
CYAN = colors.HexColor("#22d3ee")

# Style names matter: "h1toc"/"h2toc" are how headings register themselves
# in the table of contents (see _EngagementDoc.afterFlowable).
_S = {
    "kicker": ParagraphStyle("kicker", fontName=F_SB, fontSize=8.5, textColor=ACCENT,
                             spaceAfter=4, leading=11),
    "secno": ParagraphStyle("secno", fontName=F_SB, fontSize=8, textColor=ACCENT,
                            leading=10, spaceBefore=0, spaceAfter=3),
    "cover_vol": ParagraphStyle("cover_vol", fontName=F_SB, fontSize=10.5, textColor=ACCENT,
                                leading=14, spaceAfter=8),
    "cover_title": ParagraphStyle("cover_title", fontName=F_DISPLAY, fontSize=31,
                                  textColor=INK, leading=36, spaceAfter=12),
    "cover_sub": ParagraphStyle("cover_sub", fontName=F_MD, fontSize=12.5, textColor=MUTED,
                                leading=18, spaceAfter=4),
    "h1toc": ParagraphStyle("h1toc", fontName=F_HEAD, fontSize=15.5, textColor=INK,
                            leading=20, spaceBefore=4, spaceAfter=2),
    "h2toc": ParagraphStyle("h2toc", fontName=F_SB, fontSize=11, textColor=ACCENT_DK,
                            leading=15, spaceBefore=11, spaceAfter=4),
    "h3": ParagraphStyle("h3", fontName=F_SB, fontSize=8.5, textColor=ACCENT,
                         leading=12, spaceBefore=9, spaceAfter=3),
    "callout": ParagraphStyle("callout", fontName=F_BODY, fontSize=9.3, textColor=INK,
                              leading=14.5),
    "body": ParagraphStyle("body", fontName=F_BODY, fontSize=9.3, textColor=INK,
                           leading=15, spaceAfter=5.5, allowWidows=0, allowOrphans=0),
    "bullet": ParagraphStyle("bullet", fontName=F_BODY, fontSize=9.3, textColor=INK,
                             leading=14.2, leftIndent=11, bulletIndent=2, spaceAfter=3.2,
                             bulletColor=ACCENT, allowWidows=0, allowOrphans=0),
    "cell": ParagraphStyle("cell", fontName=F_BODY, fontSize=8.4, textColor=INK, leading=11.8),
    "cellhead": ParagraphStyle("cellhead", fontName=F_SB, fontSize=7.8, textColor=MUTED, leading=10),
    "meta": ParagraphStyle("meta", fontName=F_MD, fontSize=8.4, textColor=MUTED, leading=12.5),
    "toc0": ParagraphStyle("toc0", fontName=F_SB, fontSize=10, textColor=INK, leading=17),
    "toc1": ParagraphStyle("toc1", fontName=F_BODY, fontSize=8.8, textColor=MUTED,
                           leading=13.5, leftIndent=12),
}

_BOLD = re.compile(r"\*\*(.+?)\*\*")
# The JSON shapes in our prompts document fields as <value> — the model
# occasionally imitates that notation around real prose ("<2 hours
# (proposed — client approval required)>"). Unwrap exactly that case;
# genuine less-than signs ("<70%", "<150/month") are left alone.
_WRAPPED_VALUE = re.compile(r"<\s*([^<>\n]*\(proposed[^<>]*)\s*>")


def _strip_artifacts(text: str) -> str:
    from app.pipeline.registry import _CODE_SPAN, _URL_PATH, plain_language

    out = _WRAPPED_VALUE.sub(r"\1", str(text))
    out = re.sub(r"(?<!\.)\.\.(?!\.)", ".", out)
    out = out.replace(".;", ".").replace(".,", ".")
    # code spans and URL paths are identifiers BY DESIGN — masked so the
    # renderer's own normalizations never put a space in them (53-r1 printed
    # "/api/v1/pre dispatch confirmations/{delivery id}")
    masks: dict[str, str] = {}

    def _mask(m: re.Match) -> str:
        key = f"\x00R{len(masks)}\x00"
        masks[key] = m.group(0)
        return key

    out = _CODE_SPAN.sub(_mask, out)
    out = _URL_PATH.sub(_mask, out)
    # engineering identifiers leaking into client prose read as residue:
    # "failed_first_attempt_rate" becomes "failed first attempt rate"
    out = re.sub(r"\b([a-z0-9]+(?:_[a-z0-9]+)+)\b",
                 lambda m: m.group(1).replace("_", " "), out)
    # comparison notation is engineering shorthand, not client prose:
    # "<30 minutes" reads as a placeholder — say the words
    out = plain_language(out)
    out = re.sub(r"(?<![\w<>])<\s*(\d)", r"fewer than \1", out)
    out = re.sub(r"(?<![\w<>])>\s*(\d)", r"more than \1", out)
    for key, original in masks.items():
        out = out.replace(key, original)
    return out


def _rich(text: str) -> str:
    """Escape, then translate the markdown inline forms our prompts emit."""
    out = html.escape(_strip_artifacts(text), quote=False)
    out = _BOLD.sub(r"<b>\1</b>", out)
    return out


_SECTION_COUNTER = {"n": 0}


def _h1(text: str):
    _SECTION_COUNTER["n"] += 1
    return [
        CondPageBreak(55 * mm),
        Spacer(1, 10),
        Paragraph(f"SECTION {_SECTION_COUNTER['n']:02d}", _S["secno"]),
        Paragraph(_rich(text), _S["h1toc"]),
        HRFlowable(width=14 * mm, thickness=2.2, color=ACCENT, spaceBefore=3, spaceAfter=9, hAlign="LEFT"),
    ]


def _callout(text_html: str, fg, bg) -> Table:
    """A tinted callout band with a colored spine — the report's way of
    saying 'this line matters' without shouting."""
    cell = Paragraph(text_html, _S["callout"])
    box = Table([[cell]], colWidths=[168 * mm])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, fg),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return box


class _EngagementDoc(BaseDocTemplate):
    """SimpleDocTemplate that feeds every h1toc/h2toc heading into the
    TableOfContents flowable during multiBuild passes."""

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            name = flowable.style.name
            if name == "h1toc":
                self.notify("TOCEntry", (0, flowable.getPlainText().strip(), self.page))
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


_NUMERALS = {"blueprint": "01", "technical": "02", "operations": "03"}


def _cover_painter(kind: str, req: Request):
    """The cover's left architecture, painted on canvas: a full-height
    deep-navy panel carrying the logo, the wordmark, and a ghosted volume
    numeral — the page a client recognizes across every engagement."""

    def draw(canvas, doc):
        W, H = A4
        panel_w = 62 * mm
        canvas.saveState()
        canvas.setFillColor(PANEL)
        canvas.rect(0, 0, panel_w, H, stroke=0, fill=1)
        canvas.setFillColor(ACCENT)
        canvas.rect(panel_w, 0, 1.2 * mm, H, stroke=0, fill=1)
        canvas.setFillColor(CYAN)
        canvas.rect(panel_w + 1.2 * mm, H - 42 * mm, 0.5 * mm, 26 * mm, stroke=0, fill=1)

        logo_path = getattr(settings, "BMV_LOGO_PATH", None)
        if logo_path and os.path.isfile(logo_path):
            canvas.drawImage(logo_path, 14 * mm, H - 34 * mm, 20 * mm, 20 * mm,
                             mask="auto", preserveAspectRatio=True)
        canvas.setFillColor(colors.white)
        canvas.setFont(F_SB, 9)
        canvas.drawString(14 * mm, H - 42 * mm, "BUILD MY VERSION")
        canvas.setFillColor(CYAN)
        canvas.setFont(F_MD, 7.5)
        canvas.drawString(14 * mm, H - 47 * mm, "AI-native consultancy")

        # the ghosted numeral — the volume's signature
        canvas.setFillColor(colors.white)
        canvas.setFillAlpha(0.09)
        canvas.setFont(F_DISPLAY, 92)
        canvas.drawString(10 * mm, 20 * mm, _NUMERALS.get(kind, ""))
        canvas.setFillAlpha(1)

        canvas.setFillColor(colors.HexColor("#9aa8c0"))
        canvas.setFont(F_MD, 7.5)
        canvas.drawString(14 * mm, 12 * mm, "buildmyversion.com")
        canvas.restoreState()

    return draw


# Artifact classes that must never reach a client and that the renderer
# does NOT auto-repair — any hit forces the DRAFT stamp.
_GATE_ARTIFACTS = [
    ("template token", re.compile(r"\{\{|\{%|%\}")),
    ("literal Null", re.compile(r"\bNull\b")),
    # a template token is a KEYWORD placeholder in any case ("[Insert name]")
    # or an ALL-CAPS token ("[CLIENT_INPUT]"); a merge field in a message
    # script ("Hello [CustomerName]") and a bracketed lowercase word are not
    ("unresolved placeholder", re.compile(r"\[(?:TODO|TBD|PLACEHOLDER|INSERT|YOUR |CLIENT_INPUT)[^\]]*\]", re.IGNORECASE)),
    ("unresolved placeholder", re.compile(r"\[[A-Z][A-Z_]{4,}\]")),
    ("duplicate approval label",
     re.compile(r"\(proposed — client approval required\)[^()]{0,12}\(proposed — client approval required\)")),
    ("invented ROI figure",
     re.compile(r"\d[\d.]*\s*%\s*ROI|ROI (?:of|is|at)\s*~?\d[\d.]*\s*%", re.IGNORECASE)),
    ("currency sign on a count",
     re.compile(r"[$\u20ac\u00a3]\s?\d[\d,]*(?:\.\d+)?\s*(?:inquiries|hours|deliveries|orders|messages|calls|attempts)\b",
                re.IGNORECASE)),
    # "1. some-module-engine: ..." \u2014 an internal id as a client-facing list
    # label, and technical slugs anywhere in prose
    ("internal identifier in client-facing text",
     re.compile(r"(?m)^\s*(?:\d+\.|[-*\u2022])\s*\**[a-z0-9]+(?:-[a-z0-9]+)+\**\s*:|"
                r"\b[a-z0-9]+(?:-[a-z0-9]+)*-(?:engine|predictor|assistant|concierge|resolver|notifier|"
                r"service|api|module|handler|worker|queue|store|ledger|agent|bot|portal|tracker|planner|"
                r"router|sync|feed|manager|dashboard|console|gateway|scheduler|optimizer)\b")),
    ("unsubstituted gate token", re.compile(r"\[\[[A-Z_]+\]\]")),
    # run 46: one sentence computing the same month two ways
    ("mixed monthly identity",
     re.compile(r"(?:[x\u00d7*]\s*30\s*days?)[^.\n]{0,120}(?:(?:/|\u00f7)\s*12\b|12 months)|"
                r"(?:(?:/|\u00f7)\s*12\b|12 months)[^.\n]{0,120}(?:[x\u00d7*]\s*30\s*days?)", re.IGNORECASE)),
]


_GAP_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?\s*%?")


def _registered_values(registry: dict | None) -> list[float]:
    from app.pipeline.registry import proposals

    return [float(c["value"]) for c in proposals(registry or {}) if isinstance(c.get("value"), (int, float))]


def _duplicate_label(cleaned: str, registry: dict | None) -> bool:
    """Two approval labels within a few characters is a duplicate UNLESS the
    text between them is a second, separately registered proposal ('70%
    (proposed …) and 60% (proposed …)') — registry evidence, not a regex
    exception. Without a registry the strict reading stands."""
    rx = next(rx for name, rx in _GATE_ARTIFACTS if name == "duplicate approval label")
    values = _registered_values(registry) if registry else []
    for m in rx.finditer(cleaned):
        gap = cleaned[m.start():m.end()]
        inner = gap[len("(proposed — client approval required)"):-len("(proposed — client approval required)")]
        nums = []
        for n in _GAP_NUMBER.findall(inner):
            try:
                v = float(n.rstrip("%").replace(",", "").strip())
            except ValueError:
                continue
            nums.append(v / 100 if n.strip().endswith("%") else v)
        if nums and values and all(any(abs(v - rv) <= 1e-6 * max(1.0, abs(v)) for rv in values) for v in nums):
            continue
        return True
    return False


def find_artifacts(text: str, registry: dict | None = None) -> list[str]:
    """Names of client-unsafe artifact classes present in `text`, checked
    AFTER the renderer's own deterministic cleanup — only what would truly
    reach the page counts. 'For your build team' lines are the sanctioned
    home of technical identifiers; ordinary hyphenated English is not a slug.
    With a registry, the duplicate-label and identifier classes are judged
    on registered values and declared identifiers."""
    from app.pipeline.registry import _BUILD_TEAM_LINE, _SLUG_ALLOW, client_facing_region, identifier_artifacts

    cleaned = _strip_artifacts(text or "")
    prose = _SLUG_ALLOW.sub(" ", _BUILD_TEAM_LINE.sub(" ", client_facing_region(cleaned)))
    hits = []
    for name, rx in _GATE_ARTIFACTS:
        if name == "duplicate approval label":
            if _duplicate_label(cleaned, registry):
                hits.append(name)
            continue
        if name == "internal identifier in client-facing text":
            ids = [m.get("id") for m in (registry or {}).get("modules") or [] if m.get("id")]
            if identifier_artifacts(prose, ids, (registry or {}).get("technical_identifiers")):
                hits.append(name)
            continue
        if rx.search(cleaned) and name not in hits:
            hits.append(name)
    return hits


# structured fields that hold identifiers BY DESIGN (resolved to names at
# render time) — never scanned as client prose
_ID_KEYS = {"id", "enabled_by", "backstage_modules", "depends_on", "build_order", "module_id",
            "maps_to", "source", "scope", "original_name", "kpi_candidates", "tools", "apis",
            "name_by_id", "renames"}


def _strings_of(obj, skip_keys: set | None = None) -> list[str]:
    skip = _ID_KEYS if skip_keys is None else skip_keys
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for k, v in obj.items() if k not in skip for s in _strings_of(v, skip)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings_of(v, skip)]
    return []


BMV_STATEMENT = ("Prepared by BMV AI. Recommendations and proposed thresholds require client validation. "
                 "This document has not yet been formally approved by the client.")
STATUS_LABELS = {"draft": "DRAFT", "final": "FINAL — CONSULTANCY DELIVERABLE", "client_approved": "CLIENT APPROVED"}


def release_status(req: Request) -> dict:
    """The release decision, computed from THIS run's persisted records:
    its quality bench report and a deterministic artifact scan of every
    client-facing string. Three states:
      draft            — open quality findings exist
      final            — FINAL — CONSULTANCY DELIVERABLE: every quality check passes;
                         client approval is not required
      client_approved  — CLIENT APPROVED: final AND the client supplied the
                         document owner and approver
    {"status": ..., "status_label": ..., "reasons": [...], "client_approval": {...}}."""
    reasons = []
    # Preconditions: a run that never finished, has no documents, or was
    # never audited by the bench can hold NO release decision — run 44's
    # 19-second failure came back "final" because nothing had findings.
    if getattr(req, "status", None) != "done" or getattr(req, "is_failed", False):
        reasons.append("the run did not complete")
    if not (getattr(req, "mvp_blueprint", None) or getattr(req, "technical_plan", None)):
        reasons.append("no documents were produced")
    if not getattr(req, "qa_report_json", None):
        reasons.append("the quality bench never audited this run")
    qa = _loads(getattr(req, "qa_report_json", None), None) or {}
    if isinstance(qa, dict):
        highs = [f for f in (qa.get("findings") or [])
                 if isinstance(f, dict) and f.get("severity") == "high"
                 and not f.get("repaired")
                 and f.get("adjudication") != "false_positive"]
        if highs:
            reasons.append(f"{len(highs)} open high finding(s) on the quality bench")
    corpus_parts = [req.mvp_blueprint or "", req.technical_plan or ""]
    for attr in ("business_case_json", "procedures_json", "checklists_json",
                 "scoreboard_json", "org_json", "journey_json", "playbook_json"):
        corpus_parts.extend(_strings_of(_loads(getattr(req, attr, None), None)))
    from app.pipeline import registry as _reg

    reg = _reg.registry_for(req)
    hits = sorted({h for part in corpus_parts for h in find_artifacts(part, reg)})
    if hits:
        reasons.append("client-unsafe artifacts: " + ", ".join(hits))
    reasons += registry_reasons(req, corpus_parts)
    # client governance is the optional LATER state: a consultancy deliverable
    # is final on its quality checks alone; CLIENT APPROVED needs the client's
    # own owner and approver (intake facts, never invented)
    dc = _reg.document_control(req)
    status = "draft" if reasons else ("client_approved" if dc["complete"] else "final")
    return {"status": status, "status_label": STATUS_LABELS[status], "reasons": reasons, "client_approval": dc}


def registry_reasons(req: Request, corpus_parts: list[str] | None = None,
                     texts: dict[str, str] | None = None) -> list[str]:
    """Release blockers proven against the typed claim registry: paraphrased
    gate restatements, KPI/acceptance numbers mapping to no claim, internal
    identifiers in client text, and monthly-identity drift. `texts` lets the
    audit tools check the EXACT rendered PDF text instead of the markdown."""
    from app.pipeline import pilot_gate as _pg
    from app.pipeline import registry as _reg
    from app.pipeline import timebasis as _tb

    reg = _reg.registry_for(req)
    if not reg:
        return []
    reasons = []
    texts = texts or {"blueprint": req.mvp_blueprint or "", "technical": req.technical_plan or ""}
    gate = reg.get("pilot_gate")
    if gate:
        n = sum(len(_pg.restatement_findings(t, gate)) for t in texts.values())
        if n:
            reasons.append(f"{n} paraphrased pilot-gate restatement(s)")
    n = sum(len(_reg.kpi_number_findings(t, reg, strict_kpi=(label == "blueprint")))
            for label, t in texts.items())
    if n:
        reasons.append(f"{n} KPI/acceptance number(s) map to no registered claim")
    ids = [m["id"] for m in reg.get("modules") or []]
    parts = list(corpus_parts or []) + list(texts.values())
    idhits = sorted({h for part in parts
                     for h in _reg.identifier_artifacts(part, ids, reg.get("technical_identifiers"))})
    if idhits:
        reasons.append("internal identifiers in client-facing text: " + ", ".join(idhits[:6]))
    # cross-volume laws proven on the text: one pilot design, an
    # authentication floor for financial detail, URL-safe API paths, a
    # rules-based pilot, the client's own policy origin
    if gate:
        n = sum(len(_pg.design_findings(t, gate)) for t in texts.values())
        if n:
            reasons.append(f"{n} pilot-design restatement(s) that are not the canonical randomized design")
    n = sum(len(_reg.auth_text_findings(t)) for t in texts.values())
    if n:
        reasons.append(f"{n} sentence(s) gate financial detail on a phone-number match alone")
    n = sum(len(_reg.api_text_findings(t, reg.get("api_paths") or [])) for t in texts.values())
    if n:
        reasons.append(f"{n} API path(s) rendered with spaces")
    modules = _loads(getattr(req, "modules_json", None), None) or []
    procedures = (_loads(getattr(req, "procedures_json", None), None) or {}).get("procedures") or []
    n = len(_reg.pilot_isolation_findings(modules, procedures))
    if n:
        reasons.append(f"{n} pilot specification(s)/procedure(s) depend on AI logic or another module")
    # one pilot procedure set and one attempt count; labeled operating times;
    # the customer never meets the internal queue; the gate's population
    pilot_names = {str(m.get("client_facing_name") or m.get("name") or "") for m in modules
                   if isinstance(m, dict) and m.get("pilot")}
    n = len(_reg.pilot_procedure_findings(procedures, pilot_names))
    if n:
        reasons.append(f"{n} contradiction(s) between the pilot procedures")
    n = len(_reg.operating_time_findings(procedures))
    if n:
        reasons.append(f"{n} unlabeled operating time(s)/cadence(s) in the procedures")
    n = sum(len(_reg.customer_queue_findings(t)) for t in texts.values())
    if n:
        reasons.append(f"{n} sentence(s) send a customer into the internal pilot queue")
    if gate:
        n = sum(len(_reg.population_findings(t, gate, types=reg.get("service_types"), pilot_names=sorted(pilot_names)))
                for t in texts.values())
        if n:
            reasons.append(f"{n} sentence(s) narrow the pilot population below the gate's population")
    annuals = [c["value"] for c in reg.get("claims") or []
               if c.get("type") == "derived_value" and c.get("unit") == "USD"
               and isinstance(c.get("value"), (int, float))]
    if annuals:
        scope = dict(texts)
        scope["business_case"] = " ".join(_strings_of(_loads(getattr(req, "business_case_json", None), None)))
        n = len(_tb.identity_findings(scope, annuals))
        if n:
            reasons.append(f"{n} monthly-identity violation(s)")
    n = len(_reg.policy_findings(texts, reg.get("claims") or []))
    if n:
        reasons.append(f"{n} invented operational policy statement(s)")
    return reasons


def _is_draft(req: Request) -> bool:
    """A package is a draft while its release gate holds ANY open reason —
    the honest state, stamped rather than hidden."""
    return release_status(req)["status"] == "draft"


def _cover(kind: str, doc_label: str, sub_label: str, req: Request) -> list:
    concept = req.concept_name or req.business_name or ""
    date = datetime.utcnow().strftime("%B %d, %Y")
    return [
        Spacer(1, 60 * mm),
        Paragraph(_rich(sub_label).upper(), _S["cover_vol"]),
        Paragraph(_rich(doc_label), _S["cover_title"]),
        HRFlowable(width=16 * mm, thickness=2.5, color=ACCENT, spaceAfter=12, hAlign="LEFT"),
        Paragraph(_rich(concept), _S["cover_sub"]),
    ] + (
        [Paragraph(_rich(f"An engagement for {req.business_name}"), _S["cover_sub"])]
        if concept != req.business_name else []
    ) + [
        Spacer(1, 14),
        Paragraph(_rich(f"Prepared exclusively · {date}"), _S["meta"]),
    ] + (
        [Paragraph(_rich(f"Engagement lead: {settings.ENGAGEMENT_LEAD}"), _S["meta"])]
        if (settings.ENGAGEMENT_LEAD or "").strip() else []
    ) + [
        Paragraph("Confidential — for the addressee's team and advisors.", _S["meta"]),
    ] + _status_lines(req) + [
        NextPageTemplate("body"),
        PageBreak(),
    ]


def _status_lines(req: Request) -> list:
    """The release state on the cover — DRAFT with its warning, FINAL —
    CONSULTANCY DELIVERABLE with the BMV statement, CLIENT APPROVED."""
    status = release_status(req)["status"]
    if status == "draft":
        return [Spacer(1, 6), Paragraph(
            '<font color="#b45309"><b>DRAFT — REQUIRES VALIDATION.</b> The quality review '
            "recorded open findings; resolve them before client release.</font>", _S["meta"])]
    if status == "final":
        return [Spacer(1, 6), Paragraph(f"<b>{STATUS_LABELS['final']}.</b> {BMV_STATEMENT}", _S["meta"])]
    return [Spacer(1, 6), Paragraph(f"<b>{STATUS_LABELS['client_approved']}.</b> Approved by the client's named owner and approver "
                                    "(see Document control in the Operations Manual).", _S["meta"])]


def _toc() -> list:
    toc = TableOfContents()
    toc.levelStyles = [_S["toc0"], _S["toc1"]]
    return [
        Paragraph("Contents", _S["h1toc"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=8),
        toc,
        PageBreak(),
    ]


_CELLHEAD_ON_ACCENT = ParagraphStyle(
    "cellhead_on_accent", fontName=F_SB, fontSize=7.8,
    textColor=colors.white, leading=10,
)


def _table(head: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[Paragraph(t, _CELLHEAD_ON_ACCENT) for t in head]]
    for row in rows:
        data.append([Paragraph(_rich(v or "—"), _S["cell"]) for v in row])
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
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


def _journey_flowables(journey: dict | None, name_by_id: dict | None = None) -> list:
    stages = (journey or {}).get("stages") or []
    if not stages:
        return []
    flows = _h1("The future-state customer journey")
    flows.append(Paragraph(
        "The journey once the modules are built — what your customer does at every stage, and which "
        "parts of the system work for them behind the scenes. Not today's journey.", _S["meta"],
    ))
    for i, s in enumerate(stages, start=1):
        flows.append(Paragraph(f"{i}. {_rich(s.get('stage') or '')}", _S["h2toc"]))
        if s.get("customer_action"):
            flows.append(Paragraph("<b>Your customer:</b> " + _rich(s["customer_action"]), _S["body"]))
        if s.get("frontstage"):
            flows.append(Paragraph("<b>What they see:</b> " + _rich(s["frontstage"]), _S["body"]))
        if s.get("backstage_modules"):
            names = [(name_by_id or {}).get(mid, mid) for mid in s["backstage_modules"]]
            flows.append(Paragraph(
                "<b>Working backstage:</b> " + _rich(", ".join(names)), _S["body"],
            ))
        if s.get("fail_point_removed"):
            flows.append(_callout(
                f'<font color="{HEX_GOOD}"><b>What no longer goes wrong:</b></font> '
                + _rich(s["fail_point_removed"]), GOOD, GOOD_BG,
            ))
            flows.append(Spacer(1, 3))
    return flows


def _decision_right(v, *, hands: bool = False) -> str:
    # AI decision rights are never blank or "Null" in a client document —
    # an empty scope is stated as the deliberate constraint it is.
    s = str(v or "").strip()
    if not s or s.lower() in ("null", "none", "n/a", "-", "nothing"):
        return ("Hands every action to a human for approval." if hands
                else "Does not decide autonomously — proposes, a human approves.")
    return s


def _organization_flowables(org: dict | None) -> list:
    roles = (org or {}).get("roles") or []
    impact = (org or {}).get("change_impact") or []
    if not roles:
        return []
    flows = _h1("The organization — humans and AI on one chart")
    rows = []
    for r in roles:
        is_ai = r.get("type") == "ai"
        rows.append([
            ("AI · " if is_ai else "") + (r.get("role") or ""),
            "; ".join(r.get("responsibilities") or []),
            _decision_right(r.get("decides_alone")) if is_ai else (r.get("decides_alone") or "—"),
            _decision_right(r.get("hands_off"), hands=True) if is_ai else (r.get("hands_off") or "—"),
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
    formulas = [(r.get("metric"), r.get("formula")) for r in scoreboard if r.get("formula")]
    if formulas:
        flows.append(Spacer(1, 3))
        flows.append(Paragraph(
            "How each is measured: " + " · ".join(
                f"<b>{_rich(str(m))}</b> — {_rich(str(f))}" for m, f in formulas),
            _S["meta"],
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
    risk_head = ParagraphStyle("riskhead", parent=_S["h2toc"], textColor=RISK)
    for r in risks:
        flows.append(Paragraph(_rich(r.get("risk") or ""), risk_head))
        if r.get("mitigation"):
            flows.append(_callout("<b>Counter-move:</b> " + _rich(r["mitigation"]), RISK, RISK_BG))
            flows.append(Spacer(1, 2))
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
            tag = f' <font color="{HEX_GOOD}"><b>(no software needed)</b></font>' if w.get("no_software") else ""
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
                f"<b>{_rich(h.get('role') or '')}</b> — when: " + _rich((h.get("when") or "").rstrip("."))
                + ". " + _rich(h.get("why") or ""),
                _S["bullet"], bulletText="•",
            ))
    return flows


_CURRENCY_HINT = re.compile(r"[$\u20ac\u00a3]|\bUSD\b|\bEUR\b|\bGBP\b", re.IGNORECASE)
_UNIT_HINTS = (("inquir", "inquiries"), ("hour", "hours"), ("deliver", "deliveries"),
               ("order", "orders"), ("message", "messages"), ("call", "calls"),
               ("attempt", "attempts"))


def _quantity(v, context: str = "", unit: str | None = None) -> str:
    """Format a computed figure by its UNIT — the one the line's own
    arithmetic declares when the sanitizer recorded it, else inferred from
    its label and arithmetic. A count of inquiries or a number of hours must
    never wear a currency sign — '$127,750 inquiries' was a released defect;
    '2,340 inquiries' for 45 hours x 52 weeks was another."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return str(v or "")
    if unit:
        return f"${v:,.0f}" if unit == "USD" else (f"{v:,.0f} {unit}" if unit != "count" else f"{v:,.0f}")
    ctx = (context or "").lower()
    if _CURRENCY_HINT.search(ctx):
        return f"${v:,.0f}"
    unit = next((u for h, u in _UNIT_HINTS if h in ctx), "")
    return (f"{v:,.0f} {unit}").strip()


def _pilot_gate_flowables(business_case: dict) -> list:
    """The ONE pilot decision gate, rendered as its own box right after the
    decision — every other mention in any volume restates this table. Five
    competing gate criteria in one released document is why this exists."""
    gate = (business_case or {}).get("pilot_gate") or {}
    if not isinstance(gate, dict) or not gate.get("primary_metric"):
        return []
    flows = [Spacer(1, 4), Paragraph("The pilot decision gate", _S["h2toc"]),
             Paragraph(
                 "One gate governs the pilot. Every criterion elsewhere in this engagement "
                 "restates the sentence below verbatim — nothing else counts as pilot success.", _S["meta"])]
    if gate.get("canonical_sentence"):
        # the typed gate: the FULL definition printed once, its short
        # reference (the form every other section uses), then its components
        from app.pipeline import pilot_gate as _pg

        flows.append(_callout(_rich(_pg.full_definition(gate)), ACCENT, TINT))
        flows.append(Spacer(1, 3))
        flows.append(Paragraph("<b>Referenced everywhere else as:</b> " + _rich(_pg.canonical_sentence(gate)), _S["body"]))
        flows.append(Spacer(1, 4))
        unit = ("percentage points" if gate.get("change_kind") == "percentage_point"
                else "% relative" if gate.get("change_kind") == "relative" else "")
        rows = [(label, v) for label, v in (
            ("Duration", f"{gate.get('duration_value'):g} {gate.get('duration_unit')}s (proposed — client approval required)"
             if gate.get("duration_value") else None),
            ("Population", gate.get("population")),
            ("Geography", gate.get("geography")),
            ("Control-group method", gate.get("control_method")),
            ("Primary metric", gate.get("primary_metric")),
            ("Numerator", gate.get("numerator")),
            ("Denominator", gate.get("denominator")),
            ("Baseline", (str(gate.get("baseline") or "") + (" (your figure)" if gate.get("baseline_source") == "client"
                                                              else " (measured in week 1)" if gate.get("baseline_source") == "measure in week 1" else ""))
             if gate.get("baseline") or gate.get("baseline_source") else None),
            ("Target", f"{'rise' if gate.get('direction') == 'rise' else 'fall'} by {gate.get('target_value'):g} {unit} "
                       "(proposed — client approval required)" if gate.get("target_value") is not None else None),
            ("Formula", gate.get("target_formula")),
            ("Change kind", "percentage-point change" if gate.get("change_kind") == "percentage_point"
             else "relative change" if gate.get("change_kind") == "relative" else None),
            ("Guardrails", "; ".join(gate.get("guardrails") or []) + " (proposed — client approval required)"
             if gate.get("guardrails") else None),
            ("Approval status", gate.get("approval_status")),
        ) if v]
    else:
        rows = [(label, gate.get(key)) for label, key in (
            ("Duration", "duration"), ("Population", "population"),
            ("Control group", "control"), ("Primary metric", "primary_metric"),
            ("Baseline", "baseline"), ("Target", "target"), ("Guardrail", "guardrail"),
        ) if gate.get(key)]
    flows.append(_table(["Parameter", "Value"],
                        [[label, str(v)] for label, v in rows], [34 * mm, 134 * mm]))
    approvals = [a for a in (gate.get("approvals_required") or []) if a]
    if approvals:
        flows.append(Paragraph("Before launch, you approve:", _S["body"]))
        for a in approvals:
            flows.append(Paragraph(_rich(str(a)), _S["bullet"], bulletText="•"))
    return flows


def _financial_model_flowables(business_case: dict) -> list:
    """The quantified case: the owner's numbers annualized, three labeled
    scenarios, and the inputs still missing — computed upstream by the
    decomposition, rendered here. Every figure carries its arithmetic; the
    scenarios are the one place a labeled assumption may appear."""
    fm = (business_case or {}).get("financial_model") or {}
    if not isinstance(fm, dict):
        fm = {}
    lines = [l for l in (fm.get("lines") or []) if isinstance(l, dict)]
    # A scenario figure may only print behind its labeled assumption — an
    # unlabeled one would sit under the very sentence promising the label.
    scenarios = [s for s in (fm.get("scenarios") or [])
                 if isinstance(s, dict) and str(s.get("assumption") or "").strip()]
    missing = [m for m in (fm.get("missing_inputs") or []) if m]
    payback = str(fm.get("payback_note") or "").strip()
    # The payback note is a divide-it-yourself instruction by contract: one
    # carrying a currency amount is a pricing leak and is dropped whole.
    if re.search(r"[$\u20ac\u00a3]\s*\d|\d\s*(?:USD|EUR|GBP)\b", payback, re.IGNORECASE):
        payback = ""
    if not lines and not scenarios and not missing and not payback:
        return []
    flows = _h1("The financial case, quantified")
    flows.append(Paragraph(
        "Convention: a 365-day year; every monthly figure in this engagement is a 30-day operating "
        "month (the annual figure ÷ 365 × 30), never one twelfth of the year.", _S["meta"]))
    if lines:
        flows.append(Paragraph(
            "What the current way of working costs, annualized from your own figures:", _S["body"]))
        for l in lines:
            item = _rich(str(l.get("item") or ""))
            arith = _rich(str(l.get("arithmetic") or ""))
            annual = _rich(_quantity(l.get("annual"),
                                     str(l.get("arithmetic") or "") + " " + str(l.get("item") or ""),
                                     unit=l.get("unit")))
            # a figure may only print behind its shown computation
            text = f"<b>{item}</b>" + (f" — {arith}" if arith else "")
            if arith and annual:
                text += f" = <b>{annual}</b>"
            flows.append(Paragraph(text, _S["bullet"], bulletText="•"))
    if scenarios:
        flows.append(Paragraph(
            "Three scenarios. Each assumption is ours and labeled as such; each impact is "
            "computed from your numbers at that assumption — approve or correct the "
            "assumption and the impact recomputes:", _S["body"]))
        flows.append(Spacer(1, 4))
        flows.append(_table(
            ["Scenario", "Assumption (ours — requires your approval)", "Annual impact (computed)"],
            [[str(s.get("name") or ""),
              str(s.get("assumption") or ""),
              re.sub(r",?\s*by your own figures\.?", "",
                     _quantity(s.get("impact"), str(s.get("assumption") or "") + " "
                               + str(s.get("impact") or ""))).strip()]
             for s in scenarios],
            [22 * mm, 78 * mm, 74 * mm],
        ))
    if payback:
        flows.append(Paragraph("<b>Payback:</b> " + _rich(payback), _S["body"]))
    if missing:
        flows.append(Paragraph("To complete this model, we still need from you:", _S["body"]))
        for m in missing:
            flows.append(Paragraph(_rich(str(m)), _S["bullet"], bulletText="•"))
    return flows


def _evidence_flowables(req: Request, business_case: dict, scoreboard: list) -> list:
    """Evidence & method — composed from the engagement's own records with
    no model call: the client's inputs verbatim, the sources used, which
    claims are labeled assumptions, and what awaits measurement. The page
    that separates 'trust us' from 'check us'."""
    facts = [f for f in (_loads(req.ops_numbers_json, []) or []) if isinstance(f, dict)]
    fm = (business_case or {}).get("financial_model") or {}
    if not isinstance(fm, dict):
        fm = {}
    assumptions = [s for s in (fm.get("scenarios") or [])
                   if isinstance(s, dict) and s.get("assumption")]
    to_measure = [str(r.get("metric")) for r in (scoreboard or [])
                  if isinstance(r, dict) and "measure in week 1" in str(r.get("baseline") or "").lower()]
    marker = "Corrections and additions from the briefing chat:"
    corrections = ""
    if req.business_description and marker in req.business_description:
        corrections = req.business_description.split(marker, 1)[1].strip()
    sr = _loads(getattr(req, "site_research_json", None), None)
    has_site = isinstance(sr, dict) and sr.get("source_url")

    # Fail-open for legacy rows: an engagement with no evidence records at
    # all renders exactly as it did before this section existed. Printing a
    # method page for a run that never had the method would be a lie.
    if (not facts and not req.revenue_today and not req.main_problem
            and not has_site and not corrections and not assumptions and not to_measure):
        return []

    flows = _h1("Evidence & method")
    flows.append(Paragraph(
        "Where every figure in this engagement comes from — which claims are facts you supplied, "
        "which are labeled assumptions of ours, and which await measurement.", _S["meta"]))

    if facts or req.revenue_today or req.main_problem:
        flows.append(Paragraph("Facts you supplied", _S["h2toc"]))
    for f in facts:
        q = _rich(str(f.get("question") or ""))
        a = _rich(str(f.get("answer") or ""))
        if q or a:
            flows.append(Paragraph(f"<b>{q}</b> — {a}", _S["bullet"], bulletText="•"))
    if req.revenue_today:
        flows.append(Paragraph(
            "<b>How you earn today (your words)</b> — " + _rich(req.revenue_today),
            _S["bullet"], bulletText="•"))
    if req.main_problem:
        flows.append(Paragraph(
            "<b>The problem (your words)</b> — " + _rich(req.main_problem),
            _S["bullet"], bulletText="•"))
    flows.append(Paragraph("Sources", _S["h2toc"]))
    sources = [
        f"Your intake brief and the discovery questionnaire ({len(facts)} figures, quoted above verbatim)"
        if facts else "Your intake brief"
    ]
    if has_site:
        sources.append(f"Your own site — {sr['source_url']} (facts extracted and weighed in the analysis)")
    if corrections:
        sources.append("Your corrections from the pre-launch briefing chat (quoted below)")
    sources.append(
        "BuildMyVersion's structured decomposition — each numerical claim checked against "
        "the inputs above and the calculations shown in this report")
    for s in sources:
        flows.append(Paragraph(_rich(s), _S["bullet"], bulletText="•"))

    if corrections:
        flows.append(Paragraph("Corrections you made in the briefing chat", _S["h2toc"]))
        for line in corrections.splitlines():
            line = line.strip().lstrip("-• ").strip()
            if line:
                flows.append(Paragraph(_rich(line), _S["bullet"], bulletText="•"))

    if assumptions:
        flows.append(Paragraph("Labeled assumptions (ours — not your data)", _S["h2toc"]))
        for s in assumptions:
            flows.append(Paragraph(
                f"<b>{_rich(str(s.get('name') or ''))}:</b> " + _rich(str(s.get("assumption") or "")),
                _S["bullet"], bulletText="•"))

    if to_measure:
        flows.append(Paragraph("To be measured in week 1", _S["h2toc"]))
        for m in to_measure:
            flows.append(Paragraph(_rich(m), _S["bullet"], bulletText="•"))

    # The typed registry's open approvals: proposals the client signs off —
    # listed here as proposals, stated nowhere as facts.
    try:
        from app.pipeline import registry as _reg

        reg = _reg.registry_for(req)
    except Exception:
        reg = None
    if reg:
        gate = reg.get("pilot_gate") or {}
        kpi_props = [c for c in _reg.proposals(reg) if c.get("type") == "module_kpi"]
        th_props = [c for c in _reg.proposals(reg) if c.get("type") != "module_kpi"]
        flows.append(Paragraph("Awaiting your approval", _S["h2toc"]))
        flows.append(Paragraph(
            "Nothing below is in force. Each item is a proposal of ours registered for your decision; "
            "the documents state client facts and verified arithmetic only.", _S["meta"]))
        for a in gate.get("approvals_required") or []:
            flows.append(Paragraph("<b>Pilot gate:</b> " + _rich(str(a)), _S["bullet"], bulletText="•"))
        if th_props:
            flows.append(Paragraph(
                f"<b>{len(th_props)} operational thresholds, SLAs, sample sizes and capacity assumptions</b> "
                "— each marked '(proposed — client approval required)' where it appears in Volumes II and III.",
                _S["bullet"], bulletText="•"))
        name_of = {m.get("id"): m.get("client_facing_name") for m in reg.get("modules") or []}
        for c in kpi_props:
            flows.append(Paragraph(
                f"<b>Module KPI candidate ({_rich(str(name_of.get(c.get('scope')) or c.get('scope') or ''))}):</b> "
                + _rich(str(c.get("text") or "")) + " — shown as a proposal; not operational until approved.",
                _S["bullet"], bulletText="•"))

    flows.append(Paragraph(
        "Method rule this engagement was produced under: a figure may appear only when it is one "
        "of your inputs above, plain arithmetic on them with the computation shown, or a registered "
        "proposal of ours (a threshold, target or duration) carrying the label "
        "'(proposed — client approval required)'; scenario fractions are explicitly labeled "
        "assumptions; everything else is stated as a mechanism, never a number. Monthly figures use "
        "a 30-day operating month (annual ÷ 365 × 30). Each numerical claim was checked against the "
        "client inputs quoted above and the calculations shown in this report before release.", _S["meta"]))
    return flows


def _decision_flowables(req: Request | None = None) -> list:
    flows = _h1("Three ways forward")
    for title, body in [
        ("We execute this plan for you",
         "The team that wrote it builds it — module by module, in the order above, with you "
         "reviewing at every phase. Email us this document's reference and we reply with the "
         "exact quote."),
        ("Book the executive working session",
         "Ninety minutes with your engagement lead inside your real operation: we pressure-test "
         "this plan against your constraints, correct it together, and you leave with the "
         "corrected plan and an exact quote. Request terms by replying with this document's "
         "reference — the session fee is credited in full against your build."),
        ("Take the plan — it's yours",
         "Every module, data model, procedure, build sequence and acceptance check is written "
         "down here. A competent team can build from this document."),
    ]:
        flows.append(Paragraph(title, _S["h2toc"]))
        flows.append(Paragraph(body, _S["body"]))
    flows.append(Spacer(1, 6))
    lead = (settings.ENGAGEMENT_LEAD or "").strip()
    if lead:
        flows.append(Paragraph("Engagement leadership", _S["h2toc"]))
        flows.append(Paragraph(_rich(lead), _S["body"]))
        # Real accountability only: the release date prints when a reviewer
        # actually released this run — never as an invented formality.
        if req is not None and getattr(req, "reviewed_at", None):
            flows.append(Paragraph(
                _rich(f"Reviewed and released on {req.reviewed_at:%B %d, %Y}."), _S["meta"]))
        flows.append(Spacer(1, 4))
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


def _screens_flowables(req: Request) -> list:
    """The generated product screens, embedded with their spec-derived
    stories. Each image is real pipeline output; missing files are simply
    skipped — a broken image never ships in a paid document."""
    images = sorted(req.images, key=lambda i: (i.role_id, i.variant)) if req.images else []
    shots = []
    for img in images:
        marker = "/uploads/"
        if not img.file_path or marker not in img.file_path:
            continue
        abs_path = os.path.join(settings.UPLOADS_DIR, img.file_path.split(marker, 1)[1])
        if os.path.isfile(abs_path):
            shots.append((img, abs_path))
    if not shots:
        return []
    flows = _h1("The screens")
    flows.append(Paragraph(
        "Your product's interface, drawn with your own services and vocabulary — each screen "
        "annotated with what it does.", _S["meta"],
    ))
    from PIL import Image as PILImage

    for img, abs_path in shots:
        try:
            with PILImage.open(abs_path) as im:
                w, h = im.size
        except Exception:
            continue
        width = 168 * mm
        height = width * h / w
        flows.append(Paragraph(_rich(img.role_label or img.role_id), _S["h2toc"]))
        pic = Image(abs_path, width=width, height=height)
        pic.hAlign = "LEFT"
        flows.append(pic)
        try:
            spec = json.loads(img.spec_json) if img.spec_json else None
        except ValueError:
            spec = None
        if spec:
            sub_line = spec.get("subheading")
            if sub_line:
                flows.append(Paragraph(_rich(sub_line), _S["meta"]))
        flows.append(Spacer(1, 6))
    return flows


def _handbook_flowables(org: dict | None, procedures: list) -> list:
    """Per-role handbook pages, COMPOSED from data already generated: the
    org chart's human roles joined with the procedures that name them and
    the change-impact notes. No model call — pure assembly."""
    roles = [r for r in ((org or {}).get("roles") or []) if r.get("type") == "human"]
    if not roles:
        return []
    impact_by_role = {c.get("role"): c for c in (org or {}).get("change_impact") or []}
    flows = _h1("Role handbook")
    flows.append(Paragraph(
        "One page per human role: what they own, what they decide, and the procedures they run.",
        _S["meta"],
    ))
    for r in roles:
        role_name = r.get("role") or ""
        flows.append(Paragraph(_rich(role_name), _S["h2toc"]))
        for line in r.get("responsibilities") or []:
            flows.append(Paragraph(_rich(line), _S["bullet"], bulletText="•"))
        if r.get("decides_alone"):
            flows.append(Paragraph("<b>Decides alone:</b> " + _rich(r["decides_alone"]), _S["body"]))
        if r.get("hands_off"):
            flows.append(Paragraph("<b>Hands off:</b> " + _rich(r["hands_off"]), _S["body"]))
        mine = [
            p2 for p2 in procedures
            if any(role_name.lower() in str(st.get("actor") or "").lower() for st in p2.get("steps") or [])
        ]
        if mine:
            flows.append(Paragraph(
                "<b>Procedures this role runs:</b> " + _rich(" · ".join(p2.get("name") or "" for p2 in mine)),
                _S["body"],
            ))
        c = impact_by_role.get(role_name)
        if c:
            flows.append(Paragraph(
                "<b>What changes for you:</b> " + _rich(c.get("what_changes") or "")
                + (" <b>To learn:</b> " + _rich(c["must_learn"]) if c.get("must_learn") else ""),
                _S["body"],
            ))
    return flows


def _checklists_flowables(checklists_data: dict | None) -> list:
    checklists = (checklists_data or {}).get("checklists") or []
    forms = (checklists_data or {}).get("forms") or []
    if not checklists and not forms:
        return []
    flows = _h1("Forms & checklists")
    flows.append(Paragraph(
        "The artifacts your team holds in their hands — print them, laminate them, use them from day one.",
        _S["meta"],
    ))
    for c in checklists:
        flows.append(Paragraph(_rich(c.get("name") or ""), _S["h2toc"]))
        if c.get("when"):
            flows.append(Paragraph("<b>When:</b> " + _rich(c["when"]), _S["body"]))
        for item in c.get("items") or []:
            flows.append(Paragraph(_rich(item), _S["bullet"], bulletText="☐"))
    for f in forms:
        flows.append(Paragraph(_rich(f.get("name") or "") + " (form)", _S["h2toc"]))
        if f.get("purpose"):
            flows.append(Paragraph(_rich(f["purpose"]), _S["body"]))
        for field in f.get("fields") or []:
            flows.append(Paragraph(_rich(field) + ": ____________________", _S["bullet"], bulletText="•"))
    return flows


def _doc_control_flowables(req: Request) -> list:
    """Document control for the operations volume — the block a real
    manual opens with, from the run's own records (never invented)."""
    from app.pipeline import registry as _reg

    gate = release_status(req)
    dc = _reg.document_control(req)
    owner = dc["owner"] or "Not yet assigned — set by the client at approval (intake: document owner)"
    approver = dc["approver"] or "Not yet assigned — set by the client at approval (intake: document approver)"
    date = datetime.utcnow().strftime("%B %d, %Y")
    flows = [Paragraph("Document control", _S["h2toc"])]
    rows = [
        ("Version", f"Engagement run {req.id} · generated {date}"),
        ("Status", gate["status_label"]),
    ]
    if gate["status"] == "final":
        rows.append(("Statement", BMV_STATEMENT))
    rows += [
        ("Owner", owner),
        ("Approver", approver),
    ]
    if (settings.ENGAGEMENT_LEAD or "").strip():
        rows.append(("Prepared by", settings.ENGAGEMENT_LEAD.strip()))
    rows += [
        ("Review", "A regenerated engagement supersedes this copy; review at each phase gate."),
        ("Copies", "Uncontrolled when printed."),
    ]
    for label, value in rows:
        flows.append(Paragraph(f"<b>{label}:</b> " + _rich(value), _S["meta"]))
    flows.append(Spacer(1, 6))
    return flows


def _procedures_flowables(procedures: list) -> list:
    if not procedures:
        return []
    flows = _h1("The procedure library")
    flows.append(Paragraph(
        "The recurring routines this business runs on — who (or which AI) does each step. "
        "Grouped by the part of the system each routine belongs to.",
        _S["meta"],
    ))
    present = {str(p.get("phase") or "").strip().lower() for p in procedures if isinstance(p, dict)}
    legend = []
    if "current" in present:
        legend.append("CURRENT — runs today, with what already exists")
    if "pilot" in present:
        legend.append("PILOT — runs during the pilot, with today's tools only")
    if "future" in present:
        legend.append("FUTURE — usable only once its module is built")
    if legend:
        flows.append(Paragraph("States in this library: " + " · ".join(legend), _S["meta"]))
    if "current" not in present:
        flows.append(Paragraph(
            "No current-state routines were documented in this engagement — the library "
            "begins at the pilot; today's informal practice is not restated here.", _S["meta"]))
    last_module = object()
    for p in procedures:
        module = p.get("module")
        if module and module != last_module:
            flows.append(Paragraph(_rich(module), _S["h3"]))
        last_module = module or last_module
        flows.append(Paragraph(_rich(p.get("name") or ""), _S["h2toc"]))
        phase = str(p.get("phase") or "").strip().lower()
        if phase in ("pilot", "future"):
            chip = ("PILOT PROCEDURE — runs during the pilot" if phase == "pilot"
                    else "FUTURE STATE — usable once this module is built, not before")
            flows.append(Paragraph(f'<font color="{HEX_WARN}"><b>{chip}</b></font>', _S["meta"]))
        if p.get("trigger"):
            flows.append(Paragraph("<b>Starts when:</b> " + _rich(p["trigger"]), _S["body"]))
        for i, step in enumerate(p.get("steps") or [], start=1):
            actor = str(step.get("actor") or "").strip().strip("[]").strip()
            if actor:
                color = HEX_ACCENT if actor.lower().startswith("ai") else "#52607a"
                # a role name, never a bracketed tag: "[customer]" reads as a
                # placeholder; "Customer:" reads as the person who acts
                shown = actor if actor[:1].isupper() else actor[0].upper() + actor[1:]
                label = f'<font color="{color}"><b>{_rich(shown)}:</b></font> '
            else:
                label = ""
            flows.append(Paragraph(label + _rich(step.get("step") or ""), _S["bullet"], bulletText=f"{i}."))
        for e in p.get("exceptions") or []:
            flows.append(
                Paragraph(
                    f'<font color="{HEX_WARN}"><b>If {_rich(e.get("when") or "")}:</b></font> '
                    + _rich(e.get("then") or ""),
                    _S["bullet"], bulletText="!",
                )
            )
    return flows


# ── assembly ─────────────────────────────────────────────────────────────


_CHROME_HEAD = re.compile(
    r"\s*(?:THE BLUEPRINT|THE TECHNICAL PLAN|THE OPERATIONS MANUAL)\s*(?:DRAFT — REQUIRES VALIDATION\s*)?"
    r"[^\n]{0,80}?\n")
_CHROME_FOOT = re.compile(r"\s*Build My Version · buildmyversion\.com · consulting@buildmyversion\.com\s*(?:Page \d+\s*)?")
_CHROME_PAGE = re.compile(r"(?m)^\s*Page \d+\s*$\n?")


def strip_page_chrome(text: str, concept: str | None = None) -> str:
    """Remove the running header/footer a PDF page carries from extracted
    text, so a sentence split by a page break reads as one sentence. The
    header line is 'THE TECHNICAL PLAN [DRAFT — REQUIRES VALIDATION] <concept>';
    the footer is the studio line and 'Page N'."""
    out = text or ""
    if concept:
        out = re.sub(r"\s*(?:THE BLUEPRINT|THE TECHNICAL PLAN|THE OPERATIONS MANUAL)\s*(?:DRAFT — REQUIRES VALIDATION\s*)?"
                     + re.escape(concept) + r"\s*", " ", out)
    out = _CHROME_HEAD.sub(" ", out)
    out = _CHROME_FOOT.sub(" ", out)
    out = _CHROME_PAGE.sub("", out)
    return out


def _page_chrome(label: str, concept: str, draft: bool = False):
    """Footer + a slim accent header naming the volume — the mark of a
    document that knows which binder it belongs to. A run whose quality
    bench recorded a high finding is stamped DRAFT on every page."""

    def draw(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1.6)
        canvas.line(18 * mm, A4[1] - 11 * mm, A4[0] - 18 * mm, A4[1] - 11 * mm)
        canvas.setFont(F_SB, 6.8)
        if draft:
            canvas.setFillColor(WARN)
            canvas.drawCentredString(A4[0] / 2, A4[1] - 9 * mm, "DRAFT — REQUIRES VALIDATION")
        canvas.setFillColor(ACCENT)
        canvas.drawString(18 * mm, A4[1] - 9 * mm, label.upper())
        canvas.setFillColor(MUTED)
        canvas.setFont(F_MD, 6.8)
        canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, concept)
        canvas.setFont(F_MD, 7.3)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 12 * mm, "Build My Version · buildmyversion.com · consulting@buildmyversion.com")
        canvas.setFont(F_SB, 7.3)
        canvas.setFillColor(ACCENT_DK)
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def _loads(raw, default):
    try:
        return json.loads(raw) if raw else default
    except ValueError:
        return default


def build_pdf(req: Request, kind: str) -> str:
    """Render one engagement volume ('blueprint' | 'technical') to a PDF
    file and return its path. Raises ValueError when the underlying
    document is not on the request yet."""
    # A finished engagement's volume is deterministic in its stored data,
    # and building all three takes ~30s of CPU — long enough that the
    # download button reads as broken. Serve the file already on disk while
    # it is newer than the run's last data change (a rerun or a reviewer
    # edit bumps updated_at, which invalidates it).
    cached = os.path.join(settings.UPLOADS_DIR, "exports", f"{req.id}-{kind}.pdf")
    if os.path.isfile(cached) and req.updated_at is not None:
        if datetime.utcfromtimestamp(os.path.getmtime(cached)) > req.updated_at:
            return cached

    if kind == "blueprint":
        md = req.mvp_blueprint
        label, sub = "The Blueprint", "Volume I — strategy"
    elif kind == "technical":
        md = req.technical_plan
        label, sub = "The Technical Plan", "Volume II — the build"
    else:
        # The operations manual has no markdown backbone — it is assembled
        # entirely from the structured layers; it needs the procedures.
        md = None
        label, sub = "The Operations Manual", "Volume III — running it day to day"
    if kind != "operations" and not md:
        raise ValueError(f"{kind} document not ready")

    business_case = _loads(req.business_case_json, {})
    journey = _loads(req.journey_json, None)
    org = _loads(req.org_json, None)
    scoreboard = _loads(req.scoreboard_json, [])
    risks = _loads(req.risks_json, [])
    playbook = _loads(req.playbook_json, None)
    procedures = (_loads(req.procedures_json, {}) or {}).get("procedures") or []
    modules = _loads(req.modules_json, [])

    _SECTION_COUNTER["n"] = 0
    flows = _cover(kind, label, sub, req)
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

        flows += md_slot(r"the decision")
        flows += _pilot_gate_flowables(business_case)
        flows += md_slot(r"executive|summary")
        flows += md_slot(r"engagement|context")
        flows += md_slot(r"where you are|today")
        flows += md_slot(r"opportunit")
        flows += _customers_flowables(business_case)
        flows += md_slot(r"makes money")
        flows += _financial_model_flowables(business_case)
        flows += _journey_flowables(
            journey,
            {m.get("id"): m.get("name") for m in modules if isinstance(m, dict) and m.get("id")},
        )
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
        flows += _evidence_flowables(req, business_case, scoreboard)
        flows += _screens_flowables(req)
        flows += _decision_flowables(req)
    elif kind == "technical":
        flows += _markdown_flowables(md)
        flows += _module_appendix_flowables(modules)
        flows += _decision_flowables(req)
    else:
        if not procedures and not org and not (_loads(req.checklists_json, None)):
            raise ValueError("operations manual not ready")
        flows += _doc_control_flowables(req)
        flows += _procedures_flowables(procedures)
        flows += _checklists_flowables(_loads(req.checklists_json, None))
        flows += _handbook_flowables(org, procedures)
        flows += _decision_flowables(req)

    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{req.id}-{kind}.pdf")

    doc = _EngagementDoc(
        out_path, pagesize=A4,
        title=f"{req.concept_name or req.business_name} — {label}",
        author="Build My Version",
    )
    W, H = A4
    cover_frame = Frame(74 * mm, 20 * mm, W - 92 * mm, H - 40 * mm, id="cover")
    body_frame = Frame(18 * mm, 20 * mm, W - 36 * mm, H - 36 * mm, id="content")
    doc.addPageTemplates([
        PageTemplate(id="cover", frames=[cover_frame], onPage=_cover_painter(kind, req)),
        PageTemplate(id="body", frames=[body_frame],
                     onPage=_page_chrome(label, req.concept_name or req.business_name or "",
                                         draft=_is_draft(req))),
    ])
    doc.multiBuild(flows)
    return out_path
