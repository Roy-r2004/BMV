"""The deck's opening, from the same storyline as the files.

The answer, then the register, then one slide per proof section, then the
plan. A section's slide title is that section's title, so it cannot differ
from the page.
"""
from __future__ import annotations


def storyline_slides(prs, story, req) -> None:
    """Add the storyline slides to `prs`, in the order the client reads them."""
    from pptx.util import Inches

    from app.figures.known import PLAN_WEEKS_ID, known_for
    from app.figures.model import display
    from app.pipeline import action_plan
    from app.pipeline.export_pptx import FONT_DISPLAY, MARGIN, _add_bg, _add_text, _hex_to_rgb
    from app.storyline.pdf import rests_line

    blank = prs.slide_layouts[6]
    ground = _hex_to_rgb("#020617")
    ink = _hex_to_rgb("#f8fafc")
    quiet = _hex_to_rgb("#94a3b8")
    accent = _hex_to_rgb("#22d3ee")

    def new():
        slide = prs.slides.add_slide(blank)
        _add_bg(slide, ground)
        return slide

    page = story.answer
    slide = new()
    if page.question:
        _add_text(slide, page.question, MARGIN, Inches(0.7), Inches(11.6), Inches(1.3),
                  size=28, color=ink, font=FONT_DISPLAY)
    top = 2.2
    for line in page.answer_lines:
        _add_text(slide, line, MARGIN, Inches(top), Inches(11.6), Inches(0.4), size=18, color=ink)
        top += 0.5
    rest = rests_line(page.rests_on)
    if rest:
        _add_text(slide, rest, MARGIN, Inches(top), Inches(11.6), Inches(0.5), size=14, color=quiet)

    if story.register is not None:
        slide = new()
        _add_text(slide, "The register", MARGIN, Inches(0.55), Inches(11.6), Inches(0.7),
                  size=28, color=ink, font=FONT_DISPLAY)
        top = 1.5
        for row in story.register.rows:
            _add_text(slide, f"{row.recommendation} {row.owner}", MARGIN, Inches(top),
                      Inches(11.6), Inches(0.4), size=16, color=ink)
            top += 0.48

    for section in story.sections:
        slide = new()
        _add_text(slide, section.title, MARGIN, Inches(0.55), Inches(11.6), Inches(0.8),
                  size=28, color=ink, font=FONT_DISPLAY)
        exhibit = section.exhibit
        top = 1.6
        if exhibit is not None and exhibit.caption:
            _add_text(slide, exhibit.caption, MARGIN, Inches(top), Inches(11.6), Inches(0.4),
                      size=16, color=accent)
            top += 0.45
            if exhibit.takeaway:
                _add_text(slide, exhibit.takeaway, MARGIN, Inches(top), Inches(11.6), Inches(0.4),
                          size=16, color=ink)
                top += 0.45
            for row in (exhibit.data or {}).get("rows") or []:
                label = row.get("label") if isinstance(row.get("label"), str) else ""
                if not label:
                    continue
                if row.get("figure_id"):
                    shown = " ".join(part for part in (label, row.get("display"), row.get("tag")) if part)
                else:
                    shown = label
                _add_text(slide, shown, MARGIN, Inches(top), Inches(11.6), Inches(0.35), size=14, color=ink)
                top += 0.4
        if section.takeaway:
            _add_text(slide, section.takeaway, MARGIN, Inches(6.3), Inches(11.6), Inches(0.5),
                      size=16, color=ink)

    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if not isinstance(phases, list) or not phases:
        return
    slide = new()
    _add_text(slide, "The plan", MARGIN, Inches(0.55), Inches(11.6), Inches(0.7),
              size=28, color=ink, font=FONT_DISPLAY)
    figure = known_for(req).get(PLAN_WEEKS_ID)
    top = 1.5
    if figure is not None:
        _add_text(slide, f"This plan runs for {display(figure)}.", MARGIN, Inches(top),
                  Inches(11.6), Inches(0.4), size=16, color=ink)
        top += 0.5
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        title = phase.get("title") if isinstance(phase.get("title"), str) else ""
        if not title:
            continue
        _add_text(slide, title, MARGIN, Inches(top), Inches(11.6), Inches(0.4), size=16, color=ink)
        top += 0.45
