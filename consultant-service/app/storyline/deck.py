"""The deck's opening, from the same storyline as the files.

The answer, then the register, then one slide per proof section, then the
plan. A section's slide title is that section's title, so it cannot differ
from the page.

Every box is measured before it is placed: the words are laid out at the
box's width and type size (with a face wider than the deck's own, so the
measure errs on the side of room), and the next box starts below it. When
the next box would pass the foot of the slide, the slide is continued on a
new one under the same title. Nothing is shrunk and nothing is cut.
"""
from __future__ import annotations

from reportlab.pdfbase.pdfmetrics import stringWidth

#: Where the slide's content ends, in inches from the top (a 7.5 in slide).
_FOOT = 7.0
#: The width every content box is given, in inches.
_WIDTH = 11.6
#: The face the deck's words are measured with, and how much wider than it
#: the deck's own face may run. Measuring wide errs on the side of room.
_MEASURE_FACE = "Helvetica"
_MEASURE_BOLD = "Helvetica-Bold"
_WIDER = 1.1
#: A text box's own inset: 0.1 in each side, 0.05 in above and below.
_INSET_W = 0.2
_INSET_H = 0.1
_LEADING = 1.2
_GAP = 0.08


def lines(text: str, width_in: float, size: float, *, bold: bool = False) -> int:
    """How many lines `text` takes in a box `width_in` wide at `size` points."""
    face = _MEASURE_BOLD if bold else _MEASURE_FACE
    room = (width_in - _INSET_W) * 72
    count = 0
    for block in str(text or "").split("\n"):
        words = block.split()
        if not words:
            count += 1
            continue
        count += 1
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if stringWidth(trial, face, size) * _WIDER <= room or not current:
                current = trial
            else:
                count += 1
                current = word
    return max(count, 1)


def height(text: str, width_in: float, size: float, *, bold: bool = False) -> float:
    """The height, in inches, a box needs to hold `text` without overflowing."""
    return lines(text, width_in, size, bold=bold) * size * _LEADING / 72 + _INSET_H


class _Slides:
    """Adds boxes down a slide, and continues on a new slide under the same
    title when the next box would pass the foot."""

    def __init__(self, prs, title: str | None, *, drawn_title: bool = False):
        from pptx.util import Inches

        from app.pipeline.export_pptx import FONT_DISPLAY, MARGIN, _add_bg, _add_text, _hex_to_rgb

        self.prs, self.title, self.drawn_title = prs, title, drawn_title
        self.Inches, self.margin = Inches, MARGIN
        self.add_bg, self.add_text, self.display = _add_bg, _add_text, FONT_DISPLAY
        self.ground = _hex_to_rgb("#020617")
        self.ink = _hex_to_rgb("#f8fafc")
        self.quiet = _hex_to_rgb("#94a3b8")
        self.accent = _hex_to_rgb("#22d3ee")
        self.slide = None
        self.top = 0.0
        self.new()

    def new(self, *, continued: bool = False) -> None:
        self.slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.add_bg(self.slide, self.ground)
        self.top = 0.55
        if continued:
            self._box("Continued", 11, self.quiet, drawn=True, gap=0.0)
        if self.title:
            self._box(self.title, 28, self.ink, font=self.display, drawn=self.drawn_title, gap=0.25)

    def stamp(self, word: str) -> None:
        """A stamp top right: the deck's own word, drawn."""
        self.add_text(self.slide, word, self.margin + self.Inches(_WIDTH - 2.5), self.Inches(0.2),
                      self.Inches(2.5), self.Inches(0.3), size=11, color=self.accent, drawn=True,
                      align=_right())

    def fits(self, needed: float) -> bool:
        return self.top + needed <= _FOOT

    def block(self, items: list[tuple]) -> None:
        """Boxes that stay together on one slide: (text, size, color, drawn, indent)."""
        needed = sum(height(text, _WIDTH - indent, size) + _GAP for text, size, _c, _d, indent in items)
        if not self.fits(needed):
            self.new(continued=True)
        for text, size, color, drawn, indent in items:
            self._box(text, size, color, drawn=drawn, indent=indent)

    def add(self, text: str, size: float, color=None, *, drawn: bool = False, indent: float = 0.0,
            gap: float = _GAP) -> None:
        self.block([(text, size, color or self.ink, drawn, indent)])
        self.top += gap - _GAP

    def _box(self, text, size, color, *, font=None, drawn=False, indent=0.0, gap=_GAP):
        width = _WIDTH - indent
        tall = height(text, width, size, bold=False)
        kwargs = {"size": size, "color": color, "drawn": drawn}
        if font:
            kwargs["font"] = font
        self.add_text(self.slide, text, self.margin + self.Inches(indent), self.Inches(self.top),
                      self.Inches(width), self.Inches(tall), **kwargs)
        self.top += tall + gap


def _right():
    from pptx.enum.text import PP_ALIGN

    return PP_ALIGN.RIGHT


def storyline_slides(prs, story, req) -> None:
    """Add the storyline slides to `prs`, in the order the client reads them."""
    from app.figures.known import PLAN_WEEKS_ID, known_for
    from app.figures.model import display
    from app.pipeline import action_plan

    known = known_for(req)
    _answer(prs, story.answer)
    if story.register is not None:
        _register(prs, story.register, known)
    for section in story.sections:
        _section(prs, section)

    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if not isinstance(phases, list) or not phases:
        return
    slides = _Slides(prs, "The plan", drawn_title=True)
    figure = known.get(PLAN_WEEKS_ID)
    if figure is not None:
        slides.add(f"This plan runs for {display(figure)}.", 16)
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        title = phase.get("title") if isinstance(phase.get("title"), str) else ""
        if title:
            slides.add(title, 16)


def _answer(prs, page) -> None:
    """The answer page, every part of it, as the files print it."""
    from app.storyline.pdf import rests_line

    slides = _Slides(prs, page.question)
    for line in page.answer_lines:
        slides.add(line, 18)
    for number in page.numbers:
        slides.add(f"{number.display} ({number.tag})", 16, slides.accent)
    for label, said in (("What you believed", page.believed), ("What the test said", page.tested),
                        ("Monday", page.monday)):
        if said:
            slides.add(f"{label}: {said}", 14)
    if page.would_not:
        slides.add("What we would not do: " + " ".join(page.would_not), 14)
    rest = rests_line(page.rests_on)
    if rest:
        slides.add(rest, 13, slides.quiet)


def _register(prs, register, known) -> None:
    """The register as the blueprint prints it: each row's words, its range,
    its cost, its owner and timeframe and what it waits for, then the headline
    the ranges add up to and the footnotes."""
    from app.storyline.pdf import _after
    from app.storyline.register import table

    shown = table(register, known)
    slides = _Slides(prs, "The register", drawn_title=True)
    for row in shown["rows"]:
        facts = [f"What it changes: {row['changes']}" if row["changes"] else "",
                 f"Value: {row['value']}" if row["value"] else "",
                 f"Cost: {row['cost']}" if row["cost"] else "",
                 f"Owner: {row['owner']}" if row["owner"] else "",
                 f"When: {row['when']}" if row["when"] else ""]
        items = [(str(row["number"]), 16, slides.accent, True, 0.0),
                 (row["recommendation"], 16, slides.ink, False, 0.4),
                 (". ".join(fact.rstrip(".") for fact in facts if fact) + ".", 12, slides.quiet, False, 0.4)]
        if row["depends_on"]:
            items.append((_after(row["depends_on"]), 12, slides.quiet, True, 0.4))
        # the numeral sits beside the row's words, not above them
        _row(slides, items)
    if shown["total"]:
        slides.add(f"All together: {shown['total']}", 16)
    for note in shown["footnotes"]:
        slides.add(note, 11, slides.quiet)


def _row(slides, items) -> None:
    """One register row: its numeral at the left, its words beside it."""
    numeral, *words = items
    needed = sum(height(text, _WIDTH - indent, size) + _GAP for text, size, _c, _d, indent in words)
    if not slides.fits(needed):
        slides.new(continued=True)
    top = slides.top
    text, size, color, drawn, _indent = numeral
    slides.add_text(slides.slide, text, slides.margin, slides.Inches(top), slides.Inches(0.4),
                    slides.Inches(height(text, 0.4, size)), size=size, color=color, drawn=drawn)
    for text, size, color, drawn, indent in words:
        slides._box(text, size, color, drawn=drawn, indent=indent)


def _section(prs, section) -> None:
    """One proof section: its title, its exhibit (numbered, with its rows),
    its takeaway, then its foot, continued under the same title if it runs
    past the slide."""
    slides = _Slides(prs, section.title)
    if section.stamp:
        slides.stamp(section.stamp)
    exhibit = section.exhibit
    if exhibit is not None:
        slides.add(f"Exhibit {exhibit.id}: {exhibit.caption}", 16, slides.accent)
        if exhibit.takeaway:
            slides.add(exhibit.takeaway, 14)
        for row in (exhibit.data or {}).get("rows") or []:
            label = row.get("drawn") or row.get("label")
            if not isinstance(label, str) or not label:
                continue
            shown = " ".join(part for part in (label, row.get("display"), row.get("tag")) if part)
            slides.add(shown, 14, indent=0.2)
    if section.takeaway:
        slides.add(section.takeaway, 16)
    for line in section.foot:
        slides.add(line, 11, slides.quiet)
