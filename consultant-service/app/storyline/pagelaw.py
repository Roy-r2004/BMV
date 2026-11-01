"""How a page is allowed to look.

A title is measured with the proof page's own type and width. It is never
shrunk to fit, and a word is never cut off to fit. Two lines is the limit.
The rest of the page law is added with the pages that render it.
"""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

_SIZE = 15.5


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
        _SIZE if size is None else size,
        (A4[0] - 36 * mm) if width is None else width,
    )
