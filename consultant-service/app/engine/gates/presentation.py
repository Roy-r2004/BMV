"""The page itself, not the words (design 12.2, spec section 7).

Three deterministic checks run on every rendered PDF, and L9 is all three:

  P1  `export_pdf.presentation_findings` (export_pdf.py:475), UNCHANGED -
      every drawn font embedded, every printed character round-tripping
      through extraction, no orphaned heading or label heading, no thin
      last page. Run 53-r24 drew every bullet in Helvetica and 53-r29 typed
      a ballot box in a face that carries none; both were invisible to any
      check that read the words instead of the file
  P2  `tools/inspect_pdf.inspect` (inspect_pdf.py:32), UNCHANGED - brand
      fonts embedded, every page rendering, no blank page, footer numbering
      consistent with physical order, the DRAFT stamp on every page or on
      none, no client-unsafe artifact in the text. It is called unchanged
      (MF2.7) because engine PDFs are drawn with r30's own faces, footer and
      stamp: the same file, the same checks, no parameterised copy
  P3  `clipping_findings` (MF2.5), the check r30 declared not automatable and
      left to a human: a text span outside the body frame, two spans on
      different lines whose boxes collide, a span whose right edge runs past
      the frame. A clipped word is not a wording defect and no reader of the
      extracted text can see it

and one thing they all need first:

  P4  the engine's own chrome comes off before any semantic law reads the
      page (design 12.3). The running header, the DRAFT stamp, the footer
      and the table of contents are furniture; a law that judged them would
      report the page number as an untraceable figure

`import_tool` reaches `tools/` the way r30's own scripts do - by putting the
directory on sys.path - because `tools/` is not a package and must stay
byte-identical (frozen manifest, section 13.5).
"""
from __future__ import annotations

import importlib
import os
import re
import sys
from typing import Any, Mapping, Sequence

from reportlab.lib.units import mm

from app.engine.types import Finding, Severity

# The id gates/laws.py registers this check under. Spelled here so a finding
# raised by the presentation gate and one raised by the law registry carry the
# same law name; a test pins the two against each other.
LAW_PRESENTATION = "L9.presentation"

# The body frame of an engine volume, in millimetres. render_pdf lays it out in
# reportlab's bottom-left origin (Frame(18mm, 20mm, W-36mm, H-36mm),
# export_pdf.py:1858); this module measures spans in pymupdf's top-left origin,
# and the two must name the same rectangle or the check measures nothing. The
# left and bottom insets are read from render_pdf when it is importable so
# there is one number, not two.
FRAME_LEFT_MM = 18.0
FRAME_BOTTOM_MM = 20.0
# render_pdf's frame is (H - (FRAME_BOTTOM_MM + 16) mm) tall, so 16 mm of the
# top is left for the accent rule, the header label and the stamp.
FRAME_TOP_MM = 16.0

# A span may sit one point outside the frame: reportlab positions glyphs on
# fractional coordinates and a hairline of antialiasing is not a defect.
CLIP_TOLERANCE_PT = 1.0

# Two boxes on different lines that share more than a fifth of the smaller are
# printed over each other. Below that they are neighbours: descenders and
# accents routinely reach into the line below.
OVERLAP_FRACTION = 0.20

# Page furniture is drawn at 6.8 pt and 7.3 pt (export_pdf.py:1710-1734); the
# smallest body face on a page is 7.8 pt (the table head). A span in the header
# or footer band SMALLER than this is chrome; anything bigger down there is
# content that escaped the frame, and is reported.
CHROME_MAX_PT = 7.5

_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


# ---------------------------------------------------------------------------
# tools/ and app/pipeline/, imported and never modified
# ---------------------------------------------------------------------------

def import_tool(name: str):
    """A module from `tools/`, imported UNCHANGED (MF2.7). `tools/` is not a
    package and must stay byte-identical, so it is reached the way r30's own
    scripts and tests reach it: by putting the directory on sys.path."""
    tools_dir = os.path.join(_SERVICE_ROOT, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    return importlib.import_module(name)


def draft_stamp() -> str:
    """The one spelling of the release state. Two spellings would mean a page
    that says DRAFT and a gate that cannot see it, so it is read from the
    renderer rather than retyped; the fallback is the same literal r30 draws
    (export_pdf.py:1723) for a caller that has no renderer loaded."""
    try:
        from app.engine.work_products.render_pdf import DRAFT_STAMP

        return DRAFT_STAMP
    except Exception:                                     # pragma: no cover - renderer absent
        return "DRAFT \u2014 REQUIRES VALIDATION"


# The engine volume's own front matter: a "Contents" heading, the table it
# introduces, and the section counter `_h1` prints. r30's stripper removes a
# table of contents whose entries carry their page number on the same line
# (export_pdf.py:1707); pymupdf lays the same table out with the number on a
# line of its own, so the engine reads its own navigation off structurally -
# from the heading to the first section - rather than by pattern.
_TOC_HEADING = "Contents"
_SECTION_MARK = re.compile(r"\bSECTION\s+0*\d{1,3}\b")


def strip_engine_front_matter(text: str) -> str:
    """P4 for the pages the engine itself lays out. Navigation is not prose: a
    law that read the table of contents would report its page numbers as
    untraceable figures, and every document would be a draft."""
    out = text or ""
    mark = _SECTION_MARK.search(out)
    if mark is not None:
        at = out.find(_TOC_HEADING)
        if 0 <= at < mark.start():
            out = out[:at] + " " + out[mark.start():]
    return _SECTION_MARK.sub(" ", out)


def strip_chrome(text: str, title: str = "") -> str:
    """P4. The page as a reader reads it: the engine's running header and
    stamp off, then r30's own chrome stripper (export_pdf.py:1686) for the
    footer and the page numbers, then the engine's own front matter."""
    try:
        from app.engine.work_products.render_pdf import strip_engine_chrome

        stripped = strip_engine_chrome(text, title)
    except Exception:                                     # pragma: no cover - renderer absent
        from app.pipeline.export_pdf import strip_page_chrome

        stripped = strip_page_chrome((text or "").replace(draft_stamp(), " "))
    return strip_engine_front_matter(stripped)


def page_text(path: str) -> str:
    """Every page of the file, extracted with pymupdf - the same extractor the
    laws read, so what this returns is what they judge."""
    try:
        import pymupdf
    except ImportError:                                   # pragma: no cover - reported, not silently passed
        return ""
    doc = pymupdf.open(path)
    try:
        return "\n".join(doc[n].get_text() for n in range(doc.page_count))
    finally:
        doc.close()


def normalise(text: str) -> str:
    """One space between words and nothing else. A PDF breaks a sentence
    wherever the line ends; a claim that survived onto the page must be found
    there whatever the line breaks did to it."""
    return " ".join((text or "").split())


def readable_text(ref: Any, title: str = "") -> str:
    """The chrome-stripped, whitespace-normalised text of one artifact. An
    ArtifactRef already carries the stripped text when a renderer built it;
    the strip is repeated (it is idempotent) so a ref assembled by hand from a
    raw extraction is judged on the same page as one that was not."""
    text = getattr(ref, "extracted_text", "") or ""
    if not text and getattr(ref, "path", ""):
        text = page_text(ref.path)
    return normalise(strip_chrome(text, title))


def sha256_of_file(path: str) -> str:
    """The artifact's own hash, recomputed. `tools/release_audit._sha256`
    unchanged: a release record and a law must agree on what a file's hash
    is."""
    return import_tool("release_audit")._sha256(path)


# ---------------------------------------------------------------------------
# P3: clipping
# ---------------------------------------------------------------------------

class _Box:
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, bbox: Sequence[float]):
        self.x0, self.y0, self.x1, self.y1 = (float(v) for v in bbox)

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)

    def intersection(self, other: "_Box") -> float:
        w = min(self.x1, other.x1) - max(self.x0, other.x0)
        h = min(self.y1, other.y1) - max(self.y0, other.y0)
        return w * h if w > 0 and h > 0 else 0.0


def body_frame(width: float, height: float, *, left_mm: float | None = None,
               bottom_mm: float | None = None, top_mm: float | None = None) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of the body frame in pymupdf points, y down.
    The insets come from the renderer when it is importable, so the rectangle
    the check measures against is the rectangle the renderer laid out."""
    left = FRAME_LEFT_MM if left_mm is None else left_mm
    bottom = FRAME_BOTTOM_MM if bottom_mm is None else bottom_mm
    top = FRAME_TOP_MM if top_mm is None else top_mm
    if left_mm is None:
        try:
            from app.engine.work_products import render_pdf as _rp

            left = float(_rp.FRAME_LEFT_MM)
            bottom = float(_rp.FRAME_BOTTOM_MM) if bottom_mm is None else bottom
        except Exception:                                 # pragma: no cover - renderer absent
            pass
    return (left * mm, top * mm, width - left * mm, height - bottom * mm)


def _is_chrome(text: str, box: _Box, size: float, frame: tuple[float, float, float, float],
               chrome_texts: frozenset) -> bool:
    """Furniture the page draws OUTSIDE the frame on purpose: the accent
    header, the stamp, the studio line, `Page N`. A span wholly inside one of
    those bands and smaller than any body face is furniture; a span that
    merely LEANS into a band is content that escaped the frame and is
    reported."""
    flat = normalise(text)
    if not flat:
        return True
    if flat in chrome_texts:
        return True
    # "Page 7" - the footer number, matched literally rather than by pattern.
    if flat.startswith("Page ") and flat[5:].strip().isdigit():
        return True
    _left, top, _right, bottom = frame
    in_band = box.y1 <= top + CLIP_TOLERANCE_PT or box.y0 >= bottom - CLIP_TOLERANCE_PT
    return in_band and size <= CHROME_MAX_PT


def _spans(doc, n: int):
    """(block index, line index, box, text, size) for every printing span on
    page n. A span with no ink is not on the page."""
    out = []
    for bi, block in enumerate(doc[n].get_text("dict")["blocks"]):
        for li, line in enumerate(block.get("lines", [])):
            for span in line.get("spans", []):
                if not str(span.get("text") or "").strip():
                    continue
                out.append((bi, li, _Box(span["bbox"]), str(span["text"]), float(span.get("size") or 0.0)))
    return out


def clipping_findings(path: str, *, title: str = "", frame_mm: Mapping[str, float] | None = None,
                      chrome_texts: Sequence[str] = ()) -> list[str]:
    """MF2.5. What a human page review was asked to catch, done arithmetically.

    Three failures, each read off the span boxes of the finished file:

      * a span outside the body frame - text the layout pushed past the
        margin the document was designed to keep
      * a span whose right edge runs past the frame's right edge; called out
        separately because an unbreakable token (a long identifier, a URL,
        a joined word) overflows to the right and nowhere else, and that is
        the failure this check exists for
      * two spans on DIFFERENT lines whose boxes share more than
        OVERLAP_FRACTION of the smaller - lines printed over each other

    Page furniture is excluded: it is drawn outside the frame deliberately.
    """
    try:
        import pymupdf
    except ImportError:                                   # pragma: no cover
        return ["pymupdf is not installed: clipping could not be checked"]

    known = set(normalise(t) for t in chrome_texts if t)
    known.add(normalise(draft_stamp()))
    if title:
        known.add(normalise(title).upper())
        try:
            from app.engine.work_products.render_pdf import header_label

            known.add(normalise(header_label(title)).upper())
        except Exception:                                 # pragma: no cover - renderer absent
            pass
    frozen = frozenset(known)

    kw = dict(frame_mm or {})
    out: list[str] = []
    doc = pymupdf.open(path)
    try:
        for n in range(doc.page_count):
            rect = doc[n].rect
            frame = body_frame(rect.width, rect.height, left_mm=kw.get("left"),
                               bottom_mm=kw.get("bottom"), top_mm=kw.get("top"))
            left, top, right, bottom = frame
            content = []
            for bi, li, box, text, size in _spans(doc, n):
                if _is_chrome(text, box, size, frame, frozen):
                    continue
                content.append((bi, li, box, text))
                shown = normalise(text)[:48]
                if box.x1 > right + CLIP_TOLERANCE_PT:
                    out.append(f"text runs past the right edge of the body frame on page {n + 1} "
                               f"by {box.x1 - right:.1f} pt: \"{shown}\"")
                elif (box.x0 < left - CLIP_TOLERANCE_PT or box.y0 < top - CLIP_TOLERANCE_PT
                        or box.y1 > bottom + CLIP_TOLERANCE_PT):
                    out.append(f"text lies outside the body frame on page {n + 1}: \"{shown}\"")
            out += _overlaps(content, n)
    finally:
        doc.close()
    return out


def _overlaps(content: Sequence[tuple], page_index: int) -> list[str]:
    """Boxes on different lines that collide. Sorted by top edge so the sweep
    stops comparing as soon as the next box starts below the current one's
    bottom - the check must not become quadratic on a long document."""
    out: list[str] = []
    ordered = sorted(content, key=lambda item: (item[2].y0, item[2].x0))
    for i, (bi, li, box, text) in enumerate(ordered):
        for bj, lj, other, other_text in ordered[i + 1:]:
            if other.y0 >= box.y1:
                break
            if (bi, li) == (bj, lj):
                continue
            shared = box.intersection(other)
            smaller = min(box.area, other.area)
            if smaller > 0 and shared > OVERLAP_FRACTION * smaller:
                out.append(f"two lines overlap by {100 * shared / smaller:.0f}% of the smaller on page "
                           f"{page_index + 1}: \"{normalise(text)[:32]}\" over \"{normalise(other_text)[:32]}\"")
    return out


# ---------------------------------------------------------------------------
# P1 + P2 + P3: the whole of L9
# ---------------------------------------------------------------------------

def stamp_findings(inspection: Mapping[str, Any]) -> list[str]:
    """D2 without an expected state: the stamp is on EVERY page or on none.
    `inspect` only makes that comparison when it is told which state to
    expect, and the gate runs before the state is known - a document stamped
    on some pages is broken whichever state it turns out to be in."""
    pages = int(inspection.get("pages") or 0)
    stamped = int(inspection.get("draft_stamped_pages") or 0)
    if 0 < stamped < pages:
        return [f"DRAFT stamp on {stamped} of {pages} pages - every page must carry it or none may"]
    return []


def inspect_pdf_result(path: str, *, expect: str | None = None, concept: str | None = None,
                       registry: Mapping[str, Any] | None = None) -> dict:
    """P2. `tools/inspect_pdf.inspect`, called unchanged."""
    return import_tool("inspect_pdf").inspect(path, expect=expect, concept=concept, registry=registry)


def presentation_issues(path: str, *, title: str = "", expect: str | None = None,
                        concept: str | None = None, registry: Mapping[str, Any] | None = None) -> list[str]:
    """Every presentation issue on one file, as sentences. The three checks
    are listed in one place because L9 IS the three: dropping any of them
    would leave a class of broken page that nothing else looks at."""
    out: list[str] = []
    out += list(pipeline_presentation_findings(path))
    result = inspect_pdf_result(path, expect=expect, concept=concept, registry=registry)
    out += list(result.get("failures") or [])
    out += stamp_findings(result)
    out += clipping_findings(path, title=title)
    return out


def pipeline_presentation_findings(path: str) -> list[str]:
    """P1, imported and never reimplemented."""
    from app.pipeline.export_pdf import presentation_findings

    return presentation_findings(path)


def presentation_gate(path: str, *, where: str = "", title: str = "", expect: str | None = None,
                      concept: str | None = None, registry: Mapping[str, Any] | None = None) -> list[Finding]:
    """L9 over one file, as Findings. Every one blocks: a page a reader cannot
    read is not a deliverable, whatever the words on it say."""
    place = where or os.path.basename(path)
    return [Finding(law=LAW_PRESENTATION, where=place, issue=issue,
                    fix="rebuild the artifact; a presentation defect is never edited into the text",
                    severity=Severity.HIGH, blocks_final=True)
            for issue in presentation_issues(path, title=title, expect=expect,
                                             concept=concept, registry=registry)]
