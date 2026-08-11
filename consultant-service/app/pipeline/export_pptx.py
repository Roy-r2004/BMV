"""Builds a downloadable PowerPoint recap of a request's deliverable:
opening slide contrasting today vs. the AI-powered vision, one slide per
AI employee using that employee's generated hero image, and a closing
next-steps slide.

Pure presentation assembly — no AI calls, no cost. Reads whatever the
pipeline already produced (analysis/consult/plan JSON + GeneratedImage
files on disk) and degrades gracefully when an employee has no image yet.
"""

import json
import os

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Emu, Inches, Pt

from app.config import settings
from app.models import Request
from app.pipeline._shared import employees_with_ids

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.6)

_DARK_BG = RGBColor(0x0B, 0x10, 0x20)
_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
_LIGHT_BG = RGBColor(0xF8, 0xFA, 0xFC)
_SLATE = RGBColor(0x47, 0x55, 0x69)
_SLATE_DARK = RGBColor(0x0F, 0x17, 0x2A)
_MUTED = RGBColor(0x94, 0xA3, 0xB8)


def _hex_to_rgb(hex_color: str | None, fallback: str = "#4f46e5") -> RGBColor:
    value = (hex_color or fallback).lstrip("#")
    if len(value) != 6:
        value = fallback.lstrip("#")
    return RGBColor(int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _abs_image_path(file_path: str) -> str | None:
    """`/uploads/images/{id}/{file}.png` -> absolute path on disk, or None if missing."""
    marker = "/uploads/"
    if marker not in file_path:
        return None
    rel = file_path.split(marker, 1)[1]
    abs_path = os.path.join(settings.UPLOADS_DIR, rel)
    return abs_path if os.path.isfile(abs_path) else None


def _presentation_variant(file_path: str, variant: str) -> str | None:
    """The W4 composite beside a screenshot — `<slug>_0.png` -> `<slug>_hero.png`.

    Returns None when compositing was off or the file predates it, so the
    deck falls back to the raw screenshot rather than losing a slide.
    """
    raw = _abs_image_path(file_path)
    if raw is None:
        return None
    directory, name = os.path.split(raw)
    stem = name.rsplit("_0.png", 1)[0] if name.endswith("_0.png") else os.path.splitext(name)[0]
    candidate = os.path.join(directory, f"{stem}_{variant}.png")
    return candidate if os.path.isfile(candidate) else None


def _place_image_contain(slide, img_path: str, left, top, width, height):
    """Places an image entirely inside the box, centered, aspect preserved.

    The counterpart to _place_image_cover, and the right choice for a W4
    composite: that image is already a designed frame with its own margins
    and shadow, so cropping it to fill a box cuts off the presentation the
    compositor just built. Cover still applies to raw screenshots.
    """
    with Image.open(img_path) as im:
        native_w, native_h = im.size
    scale = min(width / native_w, height / native_h)
    draw_w, draw_h = int(native_w * scale), int(native_h * scale)
    return slide.shapes.add_picture(
        img_path,
        int(left + (width - draw_w) / 2),
        int(top + (height - draw_h) / 2),
        width=draw_w, height=draw_h,
    )


def _place_image_cover(slide, img_path: str, left, top, width, height) -> None:
    """Places an image filling exactly (left, top, width, height) with no
    distortion and no letterboxing — crops the longer axis, like CSS
    `object-fit: cover`. Plain `add_picture(..., width=, height=)` stretches
    the source to fit both dimensions, which visibly distorts any image
    whose aspect ratio doesn't already match the target box.
    """
    with Image.open(img_path) as im:
        native_w, native_h = im.size
    native_ratio = native_w / native_h
    target_ratio = width / height

    pic = slide.shapes.add_picture(img_path, left, top, width=width, height=height)
    if native_ratio > target_ratio:
        # Image relatively wider than the box — crop left/right.
        visible_fraction = target_ratio / native_ratio
        crop = (1 - visible_fraction) / 2
        pic.crop_left = crop
        pic.crop_right = crop
    elif native_ratio < target_ratio:
        # Image relatively taller than the box — crop top/bottom.
        visible_fraction = native_ratio / target_ratio
        crop = (1 - visible_fraction) / 2
        pic.crop_top = crop
        pic.crop_bottom = crop


def _add_bg(slide, color: RGBColor) -> None:
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _add_text(
    slide,
    text: str,
    left, top, width, height,
    *,
    size: int,
    color: RGBColor,
    bold: bool = False,
    align=PP_ALIGN.LEFT,
    font: str = "Calibri",
    anchor=None,
    line_spacing: float | None = None,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    if line_spacing:
        p.line_spacing = line_spacing
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return box


def _add_bullets(
    slide,
    items: list[str],
    left, top, width, height,
    *,
    size: int,
    color: RGBColor,
    accent: RGBColor,
    gap: float = 1.35,
):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(size * gap)
        run = p.add_run()
        run.text = f"›  {item}"
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return box


def _add_accent_bar(slide, color: RGBColor, left, top, width, height=Emu(0)) -> None:
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height or Pt(5))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def _eyebrow(slide, text: str, left, top, color: RGBColor):
    return _add_text(
        slide, text.upper(), left, top, Inches(8), Inches(0.4),
        size=13, color=color, bold=True,
    )


def _title_slide_layout(prs: Presentation, slide):
    slide.shapes.title = None  # blank layout has no placeholders to clear


def build_presentation(
    req: Request,
    analysis: dict,
    consult_result: dict,
    plan_result: dict,
    images: list,
) -> Presentation:
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    theme = plan_result.get("visual_theme") or {}
    primary = _hex_to_rgb(theme.get("primary_color"))
    concept = plan_result.get("concept_name") or req.business_name

    images_by_employee: dict[str, list] = {}
    for img in images:
        images_by_employee.setdefault(img.role_id, []).append(img)
    for lst in images_by_employee.values():
        lst.sort(key=lambda i: i.variant)

    # ── Slide 1: where you are -> where {concept} takes you ──────────────
    slide = prs.slides.add_slide(blank)
    _add_bg(slide, _DARK_BG)
    _add_accent_bar(slide, primary, 0, 0, SLIDE_W)

    _add_text(
        slide, req.business_name, MARGIN, Inches(0.5), Inches(12), Inches(0.5),
        size=14, color=_MUTED, bold=True,
    )
    _add_text(
        slide, f"What we have — and where {concept} takes you", MARGIN, Inches(0.95),
        Inches(12.1), Inches(1.1), size=30, color=_WHITE, bold=True,
    )

    # Capped tightly (3 per column, not 4-5) and given a wide clearance gap
    # before the summary line below — a real stress test (a verbose dental
    # clinic's 4 long pain points) overflowed into the summary at looser
    # caps/spacing. 3 short, punchy bullets read better anyway.
    col_w = Inches(5.85)
    left_x = MARGIN
    right_x = Inches(6.9)
    top_y = Inches(2.3)
    bullets_h = Inches(3.65)

    _eyebrow(slide, "Today", left_x, top_y, RGBColor(0xF8, 0x71, 0x71))
    pain_points = (analysis.get("pain_points") or [])[:3]
    _add_bullets(
        slide, pain_points or ["Manual, reactive operations with no AI layer."],
        left_x, top_y + Inches(0.5), col_w, bullets_h,
        size=15, color=RGBColor(0xE2, 0xE8, 0xF0), accent=RGBColor(0xF8, 0x71, 0x71), gap=1.15,
    )

    _eyebrow(slide, f"With {concept}", right_x, top_y, RGBColor(0x4A, 0xDE, 0x80))
    outcome_lines = [analysis.get("growth_opportunity") or ""] if analysis.get("growth_opportunity") else []
    outcome_lines += (consult_result.get("recommended_features") or [])[:2]
    _add_bullets(
        slide, [x for x in outcome_lines if x][:3],
        right_x, top_y + Inches(0.5), col_w, bullets_h,
        size=15, color=RGBColor(0xE2, 0xE8, 0xF0), accent=RGBColor(0x4A, 0xDE, 0x80), gap=1.15,
    )

    _add_text(
        slide, consult_result.get("consulting_summary") or "", MARGIN, Inches(6.65),
        Inches(12.1), Inches(0.75), size=12, color=_MUTED, align=PP_ALIGN.LEFT,
    )

    # ── One slide per product screen, built on the W4 composites ──────────
    # These are the slides the deck exists for: the client seeing their own
    # software, framed. They come before the AI-employee slides because the
    # screenshot is what earns the rest of the reading.
    for i, img in enumerate(images):
        hero = _presentation_variant(img.file_path, "hero") or _abs_image_path(img.file_path)
        if hero is None:
            continue
        slide = prs.slides.add_slide(blank)
        _add_bg(slide, _LIGHT_BG)
        _add_accent_bar(slide, primary, 0, 0, SLIDE_W)

        _add_text(
            slide, f"{concept.upper()}  ·  SCREEN {i + 1:02d}", MARGIN, Inches(0.45),
            Inches(8), Inches(0.4), size=12, color=primary, bold=True,
        )
        _add_text(
            slide, img.role_label or "Product screen", MARGIN, Inches(0.8),
            Inches(9), Inches(0.6), size=24, color=_SLATE_DARK, bold=True,
        )

        details = [
            p for p in (
                _presentation_variant(img.file_path, "detail_1"),
                _presentation_variant(img.file_path, "detail_2"),
            ) if p
        ]
        if details:
            # Hero left, the crops stacked right. Both columns start at the
            # same y and end near the same y, so the slide reads as one
            # block rather than a picture floating beside a caption — the
            # first rendered deck had a postage stamp adrift in white.
            _place_image_contain(slide, hero, MARGIN, Inches(1.55), Inches(8.5), Inches(5.4))
            _add_text(
                slide, "IN DETAIL", Inches(9.25), Inches(1.55), Inches(3.4), Inches(0.3),
                size=11, color=_MUTED, bold=True,
            )
            top = Inches(1.95)
            slot_h = Inches(2.45)
            for detail in details[:2]:
                _place_image_contain(slide, detail, Inches(9.25), top, Inches(3.5), slot_h)
                top = top + slot_h + Inches(0.15)
        else:
            _place_image_contain(slide, hero, MARGIN, Inches(1.55), Inches(12.13), Inches(5.4))

    # ── One slide per AI employee ─────────────────────────────────────────
    for i, emp in enumerate(employees_with_ids(consult_result)):
        slide = prs.slides.add_slide(blank)
        _add_bg(slide, _LIGHT_BG)
        _add_accent_bar(slide, primary, 0, 0, SLIDE_W)

        _add_text(
            slide, f"AI EMPLOYEE {i + 1:02d}", MARGIN, Inches(0.5), Inches(6), Inches(0.4),
            size=13, color=primary, bold=True,
        )
        _add_text(
            slide, emp.get("title", "AI Employee"), MARGIN, Inches(0.9), Inches(6.1), Inches(0.9),
            size=26, color=_SLATE_DARK, bold=True,
        )
        _add_text(
            slide, emp.get("why", ""), MARGIN, Inches(1.85), Inches(6.1), Inches(3.5),
            size=14, color=_SLATE, line_spacing=1.3,
        )

        # Image, right side. Images are product screens of ONE product now
        # (dashboard/schedule/analytics), not per-employee — when there's no
        # employee-keyed image (the normal case since the screen pipeline),
        # cycle through the product screens across the employee slides.
        # Sized to a composite's own proportions (about 3:2) instead of a
        # tall box: contain inside a portrait box centers a wide image in the
        # middle of it, which is how the first rendered deck ended up with a
        # small screenshot adrift between two bands of white.
        pic_left, pic_top = Inches(6.75), Inches(1.15)
        pic_w, pic_h = Inches(6.0), Inches(4.3)
        emp_images = images_by_employee.get(emp.get("id", ""), [])
        if not emp_images and images:
            emp_images = [images[i % len(images)]]
        # Prefer the composite and CONTAIN it: cover-cropping a wide
        # desktop screenshot into this tall box shows a vertical slice of
        # the interface, and cropping a composite cuts off the frame the
        # compositor just drew.
        source = emp_images[0].file_path if emp_images else None
        composite = _presentation_variant(source, "hero") if source else None
        img_path = composite or (_abs_image_path(source) if source else None)
        if img_path:
            if composite:
                _place_image_contain(slide, img_path, pic_left, pic_top, pic_w, pic_h)
            else:
                _place_image_cover(slide, img_path, pic_left, pic_top, pic_w, pic_h)
            _add_text(
                slide,
                f"{emp_images[0].role_label} — {concept}",
                pic_left, pic_top + pic_h + Inches(0.1), pic_w, Inches(0.35),
                size=11, color=_MUTED, align=PP_ALIGN.CENTER,
            )
            _add_text(
                slide, f"Prepared for {req.business_name}", MARGIN, Inches(6.55),
                Inches(6), Inches(0.4), size=11, color=_MUTED,
            )
        else:
            from pptx.enum.shapes import MSO_SHAPE

            placeholder = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, pic_left, pic_top, pic_w, pic_h)
            placeholder.fill.solid()
            placeholder.fill.fore_color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
            placeholder.line.color.rgb = RGBColor(0xCB, 0xD5, 0xE1)
            tf = placeholder.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER
            run = p.add_run()
            run.text = "Image pending"
            run.font.size = Pt(16)
            run.font.color.rgb = _SLATE

    # ── Closing slide ─────────────────────────────────────────────────────
    slide = prs.slides.add_slide(blank)
    _add_bg(slide, _DARK_BG)
    _add_accent_bar(slide, primary, 0, 0, SLIDE_W)

    _add_text(
        slide, "The next step", MARGIN, Inches(0.7), Inches(10), Inches(0.4),
        size=13, color=_MUTED, bold=True,
    )
    _add_text(
        slide, f"Ready to make {concept} real?", MARGIN, Inches(1.1), Inches(12), Inches(1),
        size=30, color=_WHITE, bold=True,
    )

    employees = (consult_result.get("recommended_ai_employees") or [])[:4]
    if employees:
        n = len(employees)
        col_w = Inches((12.133 - (n - 1) * 0.25) / n)
        gap = Inches(0.25)
        card_top = Inches(2.5)
        card_h = Inches(2.9)
        for i, emp in enumerate(employees):
            x = MARGIN + i * (col_w + gap)
            from pptx.enum.shapes import MSO_SHAPE

            card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, card_top, col_w, card_h)
            card.fill.solid()
            card.fill.fore_color.rgb = RGBColor(0x14, 0x1B, 0x2E)
            card.line.color.rgb = RGBColor(0x2A, 0x33, 0x4A)
            tf = card.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.TOP
            tf.margin_left = Pt(16)
            tf.margin_right = Pt(16)
            tf.margin_top = Pt(18)
            tf.margin_bottom = Pt(18)
            p0 = tf.paragraphs[0]
            p0.alignment = PP_ALIGN.LEFT
            r0 = p0.add_run()
            r0.text = emp.get("title", "AI Employee")
            r0.font.bold = True
            r0.font.size = Pt(15)
            r0.font.color.rgb = _WHITE
            r0.font.name = "Calibri"
            p1 = tf.add_paragraph()
            p1.alignment = PP_ALIGN.LEFT
            p1.space_before = Pt(8)
            r1 = p1.add_run()
            r1.text = emp.get("why", "")
            r1.font.size = Pt(11.5)
            r1.font.color.rgb = _MUTED
            r1.font.name = "Calibri"

    _add_text(
        slide, f"Prepared exclusively for {req.business_name}", MARGIN, Inches(6.7),
        Inches(12), Inches(0.5), size=12, color=_MUTED,
    )

    return prs


def export_path_for(request_id: int) -> str:
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"{request_id}.pptx")
