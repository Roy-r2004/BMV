"""PDF rendering through r30's own export helpers (design 11.4).

`app/pipeline/export_pdf.py` is imported and never modified (frozen manifest,
section 13.5). Everything the page is made of comes from there: the brand
faces F_*, the markdown flowables, the section rule `_h1`, the table, the
table of contents, the body frame, the `Page N` footer and the
`DRAFT - REQUIRES VALIDATION` stamp. That is not laziness - it is what makes
MF2.7 true: `tools/inspect_pdf.inspect` is called UNCHANGED on engine PDFs
and its font, footer and stamp checks pass, because these are literally the
same fonts, the same footer and the same stamp.

The laws this module enforces:

  D1  identical content renders identical bytes. `rl_config.invariant = 1`
      (export_pdf.py:34) removes the build timestamp; the section counter is
      reset per document; nothing else about a render depends on the clock,
      the path or the order the registry was loaded in. A release hash
      therefore identifies CONTENT
  D2  the DRAFT stamp is drawn on EVERY page while any blocking finding is
      open, or on none - the state inspect() checks. A document that is not
      releasable says so on every page a reader can open it at
  D3  the engine's own chrome (the running header) is stripped by
      strip_engine_chrome() before any semantic law reads the page, so L3,
      L6, L11 and L14 judge the prose and not the furniture
  D4  the document never ends on a nearly empty page: the closing block is
      three lines kept together (presentation_findings' last-page law, and
      the r30-r29 lesson that a closing block and its heading travel
      together)
  D5  the table of contents lists the document's sections and NOT itself. It
      is drawn from the same pieces as r30's `_toc`, with the one difference
      that makes that true (see _TOC_HEAD)
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any, Sequence

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    Frame,
    HRFlowable,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
)
from reportlab.platypus.tableofcontents import TableOfContents

from app.pipeline.export_pdf import (
    _EngagementDoc,
    _S,
    _SECTION_COUNTER,
    _h1,
    _markdown_flowables,
    _page_chrome,
    _rich,
    _table,
    strip_page_chrome,
    F_SB,
    LINE,
)

from app.engine.work_products.render_md import ArtifactRef, RenderedProduct, RenderedSection

# The stamp string, drawn by export_pdf._page_chrome (export_pdf.py:1723) and
# looked for verbatim by tools/inspect_pdf. Declared here so the engine can
# strip it from extracted text; a test pins it against the r30 source, because
# two spellings of this string would mean a document that says DRAFT and a
# gate that cannot see it.
DRAFT_STAMP = "DRAFT \u2014 REQUIRES VALIDATION"

# The body frame of an r30 volume (export_pdf.py:1858). The clipping check
# (gates/presentation.py) measures spans against these same insets.
FRAME_LEFT_MM = 18
FRAME_BOTTOM_MM = 20
TABLE_WIDTH_MM = 168

_HEADER_SIZE = 6.8
_ELLIPSIS = "..."


def header_label(title: str) -> str:
    """The running header. It is the product's own title, cut to what fits
    left of the centred stamp - measured in the face it is drawn in, so the
    header cannot overrun the frame on a long decision statement (a clipping
    finding), and cut identically here and in strip_engine_chrome so the
    stripper always removes exactly what the painter drew."""
    text = (title or "").strip()
    available = A4[0] / 2 - (FRAME_LEFT_MM + 6) * mm
    if pdfmetrics.stringWidth(text.upper(), F_SB, _HEADER_SIZE) <= available:
        return text
    cut = text
    while cut and pdfmetrics.stringWidth((cut + _ELLIPSIS).upper(), F_SB, _HEADER_SIZE) > available:
        cut = cut[:-1]
    return cut + _ELLIPSIS


def strip_engine_chrome(text: str, title: str = "") -> str:
    """D3. Remove the engine's running header and the draft stamp, then hand
    the rest to r30's own chrome stripper (export_pdf.py:1686), which removes
    the footer, the page numbers and the table of contents. A sentence broken
    by a page break comes back as one sentence."""
    out = text or ""
    label = header_label(title).upper()
    if label:
        out = out.replace(label, " ")
    out = out.replace(DRAFT_STAMP, " ")
    return strip_page_chrome(out)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_text(path: str) -> str:
    """The page as a reader gets it. pymupdf is the same extractor the
    presentation and semantic gates use, so what this returns is what the laws
    judge."""
    try:
        import pymupdf
    except ImportError:  # pragma: no cover - the gate reports the miss instead
        return ""
    doc = pymupdf.open(path)
    try:
        return "\n".join(doc[n].get_text() for n in range(doc.page_count))
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Flowables
# ---------------------------------------------------------------------------

# D5. `_EngagementDoc.afterFlowable` (export_pdf.py:307) turns a paragraph into
# a table-of-contents entry by its STYLE NAME: every Paragraph styled "h1toc"
# is notified as a level-0 entry. `export_pdf._toc` (export_pdf.py:819) styles
# its own "Contents" heading with _S["h1toc"], so an r30 volume's contents page
# opens by listing itself as entry 1. The release gate never catches it -
# strip_page_chrome removes the whole contents block as front matter before any
# law reads the page - but a client opening the file sees it. So the engine
# draws that heading in a style that INHERITS every visual attribute of h1toc
# under a different name: the same heading on the same page, absent from the
# list beneath it. export_pdf.py is frozen (section 13.5) and is not edited to
# fix this; the fix lives here, where the engine builds its own front matter.
_TOC_HEAD = ParagraphStyle("engine_toc_head", parent=_S["h1toc"])


def _toc_flowables() -> list:
    """r30's `_toc` (export_pdf.py:819) rebuilt from the same pieces - the same
    level styles, the same rule, the same page break - with _TOC_HEAD in place
    of _S["h1toc"] on the heading. Rebuilt rather than post-filtered because
    the notification happens during multiBuild, where there is nothing left to
    filter."""
    toc = TableOfContents()
    toc.levelStyles = [_S["toc0"], _S["toc1"]]
    return [
        Paragraph("Contents", _TOC_HEAD),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=8),
        toc,
        PageBreak(),
    ]


def _title_block(title: str, subtitle: str) -> list:
    return [
        Spacer(1, 18),
        Paragraph("WORK PRODUCT", _S["kicker"]),
        Paragraph(_rich(title), _S["cover_title"]),
        Paragraph(_rich(subtitle), _S["cover_sub"]),
    ]


def _section_flowables(section: RenderedSection) -> list:
    """A section is its rule and heading (the r30 `_h1`), then either its
    structured rows as an r30 table or its markdown as r30 flowables. The
    cells are the registry's own strings: nothing is escaped or shortened to
    fit a table, because that would be this renderer rewriting a claim."""
    flows = _h1(section.title)
    if section.rows:
        width = TABLE_WIDTH_MM * mm / max(1, len(section.head))
        flows.append(_table(list(section.head), [list(r) for r in section.rows],
                            [width] * len(section.head)))
    elif section.body:
        flows += _markdown_flowables(section.body)
    return flows


# The closing block: three lines about how the document is made, kept
# together so the last page can never carry one orphaned line of content
# (presentation_findings' last-page law). Generic by construction - it says
# nothing about any engagement.
CLOSING_LINES = (
    "Every claim in this document is printed from the engagement registry, once, in one wording.",
    "Figures are printed from the recorded quantity and its stated basis; nothing is restated in prose.",
    "Where the record is silent this document says so rather than estimating.",
)


def _closing_flowables(draft: bool) -> list:
    lines = list(CLOSING_LINES)
    if draft:
        lines.append("This document is a draft: open integrity findings are listed in the Integrity Record.")
    return [Spacer(1, 14), KeepTogether([Paragraph(_rich(line), _S["meta"]) for line in lines])]


def build_flowables(product: RenderedProduct, *, subtitle: str, draft: bool) -> list:
    _SECTION_COUNTER["n"] = 0                       # D1: the numbering starts at 1 for every document
    flows = _title_block(product.title, subtitle)
    flows += _toc_flowables()
    for section in product.sections:
        flows += _section_flowables(section)
    flows += _closing_flowables(draft)
    return flows


# ---------------------------------------------------------------------------
# The artifact
# ---------------------------------------------------------------------------

def render_pdf(product: RenderedProduct, *, out_path: str, draft: bool = True,
               subtitle: str = "", registry_hash: str = "") -> ArtifactRef:
    """Render one product to `out_path` and describe the artifact: its sha256,
    the registry hash it was rendered from (the cache rule at
    export_pdf.py:1756 rebuilds only when those differ) and the chrome-stripped
    text the semantic laws read."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    flows = build_flowables(product, subtitle=subtitle, draft=draft)

    doc = _EngagementDoc(out_path, pagesize=A4, title=product.title, author="Build My Version")
    W, H = A4
    body = Frame(FRAME_LEFT_MM * mm, FRAME_BOTTOM_MM * mm, W - 2 * FRAME_LEFT_MM * mm,
                 H - (FRAME_BOTTOM_MM + 16) * mm, id="content")
    doc.addPageTemplates([
        PageTemplate(id="body", frames=[body],
                     onPage=_page_chrome(header_label(product.title), "", draft=draft)),
    ])
    doc.multiBuild(flows)

    text = extract_text(out_path)
    return ArtifactRef(product_id=product.product_id, fmt="pdf", path=out_path,
                       sha256=sha256_of(out_path),
                       registry_hash=registry_hash or product.registry_hash,
                       extracted_text=strip_engine_chrome(text, product.title))


def render_markdown_artifact(product: RenderedProduct, *, out_path: str,
                             registry_hash: str = "") -> ArtifactRef:
    """The same product as a markdown file. Written with an explicit newline so
    the bytes - and therefore the hash - are the same on every platform."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(product.markdown)
    return ArtifactRef(product_id=product.product_id, fmt="md", path=out_path,
                       sha256=sha256_of(out_path),
                       registry_hash=registry_hash or product.registry_hash,
                       extracted_text=product.markdown)
