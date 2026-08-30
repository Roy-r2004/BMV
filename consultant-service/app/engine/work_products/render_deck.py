"""The decision deck, built from r30's pptx primitives (design 11.4).

`app/pipeline/export_pptx.py` is imported and never modified: `_add_bg`,
`_rect`, `_hairline`, `_kicker`, `_add_text` and `_add_bullets` are the only
things that put anything on a slide here, so a deck looks like the rest of
the deliverables rather than like a second template.

The laws this module enforces:

  K1  a slide carries the claims a section already rendered - the same
      strings, printed once by the registry. The deck never words anything of
      its own, so a figure cannot differ between the deck and the report
  K2  nothing is dropped to make a slide fit. More claims than a slide holds
      means more slides (BULLETS_PER_SLIDE is a slide's capacity, not a cap
      on what an engagement may say)
  K3  a draft deck says so on the cover, the way a draft PDF says so on every
      page: a reader must never receive an unreleased claim that looks final
"""
from __future__ import annotations

import hashlib
import os
from typing import Sequence

from pptx import Presentation
from pptx.util import Inches, Pt

from app.pipeline.export_pptx import (
    MARGIN,
    SLIDE_H,
    SLIDE_W,
    _add_bg,
    _add_bullets,
    _add_text,
    _hairline,
    _hex_to_rgb,
    _kicker,
)

from app.engine.work_products.render_md import ArtifactRef, RenderedProduct, RenderedSection
from app.engine.work_products.render_pdf import DRAFT_STAMP

# The r30 deck palette, by hex through the pipeline's own converter: deck and
# report read as one deliverable (export_pptx's opening note).
GROUND = _hex_to_rgb("#0b1220")
INK_ON_DARK = _hex_to_rgb("#e6edf7")
MUTED_ON_DARK = _hex_to_rgb("#9aa8c0")
ACCENT = _hex_to_rgb("#22d3ee")
WARN = _hex_to_rgb("#f8b471")

# How many bullets one slide holds at this type size. A capacity of the slide,
# not a count of anything an engagement has: claim number BULLETS_PER_SLIDE+1
# starts a continuation slide (K2).
BULLETS_PER_SLIDE = 6
# Characters a bullet is clamped to by _add_bullets. Clamping is a layout
# decision the primitive already owns; the full claim is in the report.
BULLET_CLAMP = 220


def _blank(prs: Presentation):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _add_bg(slide, GROUND)
    return slide


def _cover(prs: Presentation, product: RenderedProduct, subtitle: str, draft: bool) -> None:
    slide = _blank(prs)
    _kicker(slide, "decision deck", MARGIN, Inches(1.9), ACCENT)
    _add_text(slide, product.title, MARGIN, Inches(2.4), SLIDE_W - 2 * MARGIN, Inches(2.2),
              size=40, color=INK_ON_DARK, bold=True)
    _hairline(slide, ACCENT, MARGIN, Inches(4.8), Inches(2.2))
    if subtitle:
        _add_text(slide, subtitle, MARGIN, Inches(5.0), SLIDE_W - 2 * MARGIN, Inches(0.6),
                  size=16, color=MUTED_ON_DARK)
    if draft:
        # K3: the same words the PDF stamps, so one release state is described
        # one way across every format.
        _add_text(slide, DRAFT_STAMP, MARGIN, SLIDE_H - Inches(1.1), SLIDE_W - 2 * MARGIN, Inches(0.5),
                  size=12, color=WARN, bold=True)


def section_bullets(section: RenderedSection) -> list[str]:
    """The claims of a section, as bullets. Structured rows give their first
    column (the claim) with the rest as its qualifiers; a prose section gives
    its bullet lines, and a narrative gives its paragraphs."""
    if section.rows:
        out = []
        for row in section.rows:
            rest = "; ".join(f"{h}: {v}" for h, v in zip(section.head[1:], row[1:]))
            out.append(f"{row[0]} ({rest})" if rest else row[0])
        return out
    lines = [l.strip() for l in (section.body or "").splitlines() if l.strip()]
    return [l[2:].strip() if l.startswith("- ") else l for l in lines]


def _section_slides(prs: Presentation, section: RenderedSection) -> None:
    bullets = section_bullets(section)
    if not bullets:
        return
    pages = [bullets[i:i + BULLETS_PER_SLIDE] for i in range(0, len(bullets), BULLETS_PER_SLIDE)]
    for n, page in enumerate(pages):
        slide = _blank(prs)
        _kicker(slide, section.title, MARGIN, Inches(0.6), ACCENT)
        if len(pages) > 1:
            _add_text(slide, f"{n + 1} of {len(pages)}", SLIDE_W - MARGIN - Inches(1.4), Inches(0.6),
                      Inches(1.4), Inches(0.32), size=11, color=MUTED_ON_DARK)
        _add_bullets(slide, page, MARGIN, Inches(1.4), SLIDE_W - 2 * MARGIN, SLIDE_H - Inches(2.2),
                     size=16, color=INK_ON_DARK, accent=ACCENT, clamp=BULLET_CLAMP)


def _closing(prs: Presentation, lines: Sequence[str]) -> None:
    slide = _blank(prs)
    _kicker(slide, "how to read this deck", MARGIN, Inches(1.6), ACCENT)
    _add_bullets(slide, list(lines), MARGIN, Inches(2.3), SLIDE_W - 2 * MARGIN, Inches(3.4),
                 size=15, color=MUTED_ON_DARK, accent=ACCENT)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def render_deck(product: RenderedProduct, *, out_path: str, draft: bool = True, subtitle: str = "",
                registry_hash: str = "") -> ArtifactRef:
    """One product as a pptx deck. The text is the product's own rendered
    text, so the deck cannot say anything the report does not."""
    from app.engine.work_products.render_pdf import CLOSING_LINES

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    prs = Presentation()
    prs.slide_width, prs.slide_height = SLIDE_W, SLIDE_H
    _cover(prs, product, subtitle, draft)
    for section in product.sections:
        _section_slides(prs, section)
    _closing(prs, CLOSING_LINES)
    prs.save(out_path)

    text = "\n".join(shape.text_frame.text for slide in prs.slides for shape in slide.shapes
                     if shape.has_text_frame)
    return ArtifactRef(product_id=product.product_id, fmt="pptx", path=out_path, sha256=_sha256(out_path),
                       registry_hash=registry_hash or product.registry_hash, extracted_text=text)
