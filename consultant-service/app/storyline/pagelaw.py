"""How a page is allowed to look.

A title is measured with the proof page's own type and width. It is never
shrunk to fit, and a word is never cut off to fit. Two lines is the limit.
The rest of the page law is added with the pages that render it.
"""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

#: The proof-page title size. It is not reduced to make a long title fit.
TITLE_SIZE = 15.5

#: The only stamps a proof page may carry.
STAMPS = {"ESTIMATE", "PRELIMINARY", "ILLUSTRATIVE", "SAMPLE DATA", "FOR DISCUSSION"}

_OURS = {"our estimate", "worked out"}


def title_lines(text: str, font: str | None = None, size: float | None = None,
                width: float | None = None) -> int:
    """How many lines `text` takes at the proof-page title size.

    The font, size and width are the proof page's when they are left out:
    the same face and the same text width the page gives a heading.
    """
    font, size, width = _defaults(font, size, width)
    words = [word for word in str(text or "").split() if word]
    if not words:
        return 0
    lines = 1
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if stringWidth(trial, font, size) <= width:
            current = trial
        elif current:
            lines += 1
            current = word
        else:
            current = word
    return lines


def _defaults(font, size, width):
    if font is not None and size is not None and width is not None:
        return font, size, width
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm

    from app.pipeline.export_pdf import F_HEAD

    return (
        font or F_HEAD,
        TITLE_SIZE if size is None else size,
        (A4[0] - 36 * mm) if width is None else width,
    )


def check_section(section) -> list[str]:
    """Plain reasons the section cannot be printed as it is. Empty means it can."""
    reasons = []
    title = str(getattr(section, "title", "") or "")
    if title_lines(title) > 2:
        reasons.append("The title is more than two lines. It has to fit on two lines.")
    exhibits = getattr(section, "exhibits", None)
    if exhibits is None:
        one = getattr(section, "exhibit", None)
        exhibits = () if one is None else (one,)
    if len(tuple(exhibits)) > 1:
        reasons.append("A proof page has one exhibit.")
    lines = list(getattr(section, "foot", ()) or ())
    if lines and _kinds(lines) != sorted(_kinds(lines), key=lambda kind: _RANK[kind]):
        reasons.append("The foot is out of order. It goes: the numbered notes, then Note, then Source.")
    ours = _worked(section)
    for line in lines:
        if not str(line).strip().startswith("Source:"):
            continue
        ends = str(line).strip().endswith("BMV analysis")
        if ours and not ends:
            reasons.append("The source line has to end with BMV analysis, because a number on the page is ours or worked out.")
        if not ours and ends:
            reasons.append("The source line ends with BMV analysis, and every number on the page is the client's or a reference.")
    stamp = getattr(section, "stamp", None)
    if stamp and stamp not in STAMPS:
        reasons.append(f"The stamp {stamp} is not one this page uses.")
    return reasons


def pdf_findings(path: str) -> list[str]:
    """What is wrong with the rendered file. Every reason names its page."""
    from app.engine.gates.presentation import clipping_findings
    from app.pipeline.export_pdf import presentation_findings

    reasons = []
    for reason in list(presentation_findings(path)) + list(clipping_findings(path)):
        if "page" not in reason.lower():
            reason = f"page 1: {reason}"
        reasons.append(reason)
    return reasons


_RANK = {"footnote": 0, "note": 1, "source": 2}


def _kinds(lines) -> list[str]:
    out = []
    for line in lines:
        text = str(line).strip()
        if text.startswith("Source:"):
            out.append("source")
        elif text.startswith("Note:"):
            out.append("note")
        else:
            out.append("footnote")
    return out


def _worked(section) -> bool:
    exhibit = getattr(section, "exhibit", None)
    data = getattr(exhibit, "data", None) if exhibit is not None else None
    rows = data.get("rows") if isinstance(data, dict) else []
    return any(isinstance(row, dict) and row.get("tag") in _OURS for row in rows or [])
