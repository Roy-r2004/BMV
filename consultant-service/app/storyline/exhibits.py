"""Exhibits drawn from figures. The model never picks a chart or writes a number.

Which chart a section gets depends on the data the run stored. A section with
nothing to draw has no exhibit. When a chart would have more rows than the
bound, the rest are one group, "Other classes (n)", whose figure is their sum.
"""
from __future__ import annotations

import json
from decimal import Decimal

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.config import settings
from app.figures.calc import places_of
from app.figures.model import Figure, Proposal, Working, display, tag_word
from app.storyline.flex import flexed
from app.storyline.model import Exhibit

_FONT = "Helvetica"
_SIZE = 8
_BAR = "#0e7490"
_SECTIONS = ("week", "prize", "grid", "plan", "scoreboard")


def for_section(req, section_id: str) -> Exhibit | None:
    """The exhibit for this section, or None when the run has nothing to draw."""
    exhibit, _ = _built(req, section_id)
    return exhibit


def figures_for(req) -> list[Figure]:
    """Every figure an exhibit derives, so the known set owns the numbers it draws.

    Only the exhibits a stored proof section draws: an exhibit no page shows
    vouches for nothing. A run with no storyline has none.
    """
    figures: list[Figure] = []
    for section_id in _SECTIONS:
        if section_id not in _drawn_sections(req):
            continue
        _, made = _built(req, section_id)
        figures.extend(made)
    return figures


def available(req) -> list[tuple[str, str]]:
    """(section id, what its exhibit shows) for each exhibit this run has data
    for, in the order a prompt lists them."""
    out = []
    for section_id in _SECTIONS:
        try:
            exhibit, _ = _built(req, section_id)
        except Exception:
            exhibit = None
        if exhibit is not None:
            out.append((section_id, exhibit.caption))
    return out


def _drawn_sections(req) -> set[str]:
    raw = _loads(getattr(req, "storyline_json", None))
    sections = raw.get("sections") if isinstance(raw, dict) else None
    if not isinstance(sections, list):
        return set()
    return {s.get("id") for s in sections if isinstance(s, dict) and isinstance(s.get("id"), str)}


def draw_pdf(exhibit: Exhibit, width: float, height: float) -> Drawing:
    """The exhibit as a drawing that stays inside the box. The type size is fixed.

    Each row is its words, then its bar. Every string passes the number law
    (`law.check`) while a document is built, so a number the drawing prints is
    a figure or a finding. A chart whose rows carry no figure (the plan's
    phases) is drawn as its words alone.
    """
    from reportlab.lib import colors

    from app.figures import law

    drawing = Drawing(width, height)
    rows = list(exhibit.data.get("rows") or [])
    if not rows:
        return drawing
    top = height - 4
    row_h = (top - 4) / len(rows)
    largest = max((_decimal(row.get("value")) for row in rows), default=Decimal(1))
    if largest <= 0:
        largest = Decimal(1)
    bars = any(row.get("figure_id") for row in rows)
    bar_max = width - 16
    face = _face()
    for index, row in enumerate(rows):
        base = 4 + (len(rows) - 1 - index) * row_h
        bar_h = min(row_h * 0.4, 9.0) if bars else 0.0
        if bars and row.get("figure_id"):
            value = _decimal(row.get("value"))
            bar_w = min(max(float(value / largest) * float(bar_max), 1), bar_max)
            drawing.add(Rect(8, float(base), bar_w, float(bar_h), fillColor=colors.HexColor(_BAR),
                             strokeColor=None))
        words = " ".join(part for part in (str(row.get("drawn") or row.get("label") or ""),
                                           str(row.get("display") or ""), str(row.get("tag") or "")) if part)
        drawing.add(String(8, float(base) + float(bar_h) + 2, _fit(law.check(words), bar_max),
                           fontName=face, fontSize=_SIZE))
    return drawing


def _face() -> str:
    """The volumes' own body face, which the PDF embeds."""
    try:
        from app.pipeline.export_pdf import F_BODY

        return F_BODY
    except Exception:
        return _FONT


def height_for(exhibit: Exhibit) -> float:
    """The height, in points, `draw_pdf` needs for this exhibit's rows."""
    rows = len(exhibit.data.get("rows") or [])
    return 8 + rows * (2 * _SIZE + 8)


def draw_slide(exhibit: Exhibit, slide, box) -> None:
    """The same words, in the box the deck gives. The type size is not shrunk."""
    from pptx.util import Emu, Pt

    left, top, width, height = box
    shape = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
    frame = shape.text_frame
    frame.word_wrap = True
    lines = [exhibit.caption] if exhibit.caption else []
    for row in exhibit.data.get("rows") or []:
        lines.append(" ".join(part for part in (row.get("label"), row.get("display"), row.get("tag")) if part))
    frame.text = lines[0] if lines else ""
    for line in lines[1:]:
        frame.add_paragraph().text = line
    for paragraph in frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(_SIZE)
            run.font.name = "Calibri"


def _built(req, section_id: str) -> tuple[Exhibit | None, list[Figure]]:
    if section_id == "week":
        return _bars(req)
    if section_id == "prize":
        return _waterfall(req)
    if section_id == "grid":
        return _grid(req)
    if section_id == "plan":
        return _plan(req)
    if section_id == "scoreboard":
        return _scoreboard(req)
    return None, []


def _bars(req) -> tuple[Exhibit | None, list[Figure]]:
    grid = _capacity(req)
    slots = _classes(grid)
    if not slots:
        return None, []
    # the week's own unit, as the client's grid names it
    unit = next((grid[key] for key in ("unit_plural", "unit") if isinstance(grid.get(key), str) and grid[key]), "")
    bound = settings.EXHIBIT_ROWS_MAX
    shown, grouped = slots[:bound], []
    if len(slots) > bound:
        shown, grouped = slots[: bound - 1], slots[bound - 1:]
    figures: list[Figure] = []
    rows = []
    for index, (label, value) in enumerate(shown, 1):
        figure = _count(f"EX-WEEK-{index}", value, unit, "taken in this class across the week")
        figures.append(figure)
        rows.append(_row(label, figure))
    if grouped:
        total = sum((value for _, value in grouped), Decimal(0))
        figure = _count("EX-WEEK-GROUP", total, unit, "taken in the other classes across the week")
        count = _count("EX-WEEK-COUNT", Decimal(len(grouped)), "classes", "how many classes are grouped")
        figures.append(figure)
        figures.append(count)
        row = _row(f"Other classes ({len(grouped)})", figure)
        # The name keeps the count. The drawn line says it as the figure prints,
        # so the number is one the law can see ("3 classes", not a bare 3).
        row["drawn"] = f"Other classes, {display(count)}"
        rows.append(row)
    exhibit = Exhibit("1.1", "bar", "How full each class is", "The classes, and how full each one is.",
                      {"rows": rows}, "Your week")
    return exhibit, figures


def _waterfall(req) -> tuple[Exhibit | None, list[Figure]]:
    """The prize, one term at a time. Each step is the product so far.

    A step is the figure it is: the client's own number when it is one of
    their terms alone, the move itself at the end, and otherwise a product we
    worked out (or our estimate, once an assumption of ours is in it), in the
    unit the product has. A step whose unit cannot be said gets no figure, and
    its row is drawn without a number.
    """
    move = _move(req)
    terms = move.get("terms") if isinstance(move, dict) else None
    if not isinstance(terms, list) or not terms:
        return None, []
    from app.figures import known as figures_known

    known = figures_known.known_for(req, leave_out={"exhibits", "register"})
    move_unit = move.get("unit") if isinstance(move.get("unit"), str) else ""
    running = Decimal(0)
    product = Decimal(1)
    units: list[str] = []
    ours = False
    figures: list[Figure] = []
    steps = []
    rows = []
    for index, term in enumerate(terms, 1):
        if not isinstance(term, dict):
            return None, []
        try:
            factor = flexed([term], 0)[1]
        except Exception:
            return None, []
        product *= factor
        amount = product - running
        running = product
        units.append(_term_unit(term, known))
        ours = ours or term.get("kind") == "proposed" or _proposed(term)
        figure = _step(index, term, running, units, ours, known, move_unit, last=index == len(terms))
        if figure is not None and figure.id.startswith("EX-"):
            figures.append(figure)
        label = term.get("label") if isinstance(term.get("label"), str) and term.get("label") else f"Step {index}"
        drawn = {"figure_id": figure.id if figure else "", "display": display(figure) if figure else "",
                 "tag": tag_word(figure.kind) if figure else ""}
        steps.append({"label": label, "amount": format(amount, "f"), "value": format(running, "f"), **drawn})
        rows.append({"label": label, "value": format(running, "f"), **drawn})
    exhibit = Exhibit("1.1", "waterfall", "Where the prize comes from",
                      "Each step is the prize once that part is counted.",
                      {"rows": rows, "steps": steps}, "Your figures")
    return exhibit, figures


def _step(index: int, term: dict, value: Decimal, units: list[str], ours: bool, known,
          move_unit: str, *, last: bool) -> Figure | None:
    from app.figures import known as figures_known

    if last:
        move = known.get(figures_known.MOVE_ID)
        # the move's own figure, when it is the same number and the same kind
        if move is not None and move.value == value and (move.kind == "ours") == ours:
            return move
    if index == 1 and term.get("kind") == "claim" and not term.get("parts"):
        theirs = known.get(term.get("id")) if isinstance(term.get("id"), str) else None
        if theirs is not None and theirs.value == value:
            return theirs
    unit = _running_unit(units, move_unit)
    if unit is None:
        return None
    if ours:
        return Figure(f"EX-PRIZE-{index}", value, unit, None, "ours",
                      Proposal(note="the prize so far, with our assumption in it"), places_of(value))
    return Figure(f"EX-PRIZE-{index}", value, unit, None, "derived",
                  Working((), "product", "the prize so far"), places_of(value))


def _running_unit(units: list[str], move_unit: str) -> str | None:
    """The unit of a product of terms in these units: money once money is in
    it, the one unit when only one term has a unit, and None when it cannot be
    said (no unit at all, or two units multiplied)."""
    if move_unit and move_unit in units:
        return move_unit
    named = [unit for unit in units if unit]
    return named[0] if len(named) == 1 else None


def _term_unit(term: dict, known) -> str:
    """The unit a term is in: its figure's for a client's number, the unit a
    proposal names, none for a calendar constant; a sum of parts takes the one
    unit its parts share."""
    parts = term.get("parts")
    if isinstance(parts, list) and parts:
        found = {_term_unit(part, known) for part in parts if isinstance(part, dict)} - {""}
        return found.pop() if len(found) == 1 else ""
    kind = term.get("kind")
    if kind == "claim":
        figure = known.get(term.get("id")) if isinstance(term.get("id"), str) else None
        return figure.unit if figure is not None and figure.unit else ""
    if kind == "proposed":
        from app.figures.known import proposal_unit

        label = term.get("label") if isinstance(term.get("label"), str) else ""
        return proposal_unit(label)
    return ""


def _grid(req) -> tuple[Exhibit | None, list[Figure]]:
    return _bars(req)[0] and _as_kind(_bars(req), "week_grid") or (None, [])


def _plan(req) -> tuple[Exhibit | None, list[Figure]]:
    plan = _loads(getattr(req, "action_plan_json", None))
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if not isinstance(phases, list) or not phases:
        return None, []
    rows = []
    for phase in phases:
        if not isinstance(phase, dict):
            continue
        title = phase.get("title") if isinstance(phase.get("title"), str) else ""
        if title and not any(ch.isdigit() for ch in title):
            rows.append({"label": title, "value": "0", "figure_id": "", "display": "", "tag": ""})
    if not rows:
        return None, []
    return Exhibit("1.1", "plan_chart", "The plan", "The phases, in order.", {"rows": rows}, "The plan"), []


def _scoreboard(req) -> tuple[Exhibit | None, list[Figure]]:
    board = _loads(getattr(req, "scoreboard_json", None))
    if not isinstance(board, list) or not board:
        return None, []
    rows = []
    for item in board:
        if not isinstance(item, dict):
            continue
        metric = item.get("metric") if isinstance(item.get("metric"), str) else ""
        if metric and not any(ch.isdigit() for ch in metric):
            rows.append({"label": metric, "value": "0", "figure_id": "", "display": "", "tag": ""})
    if not rows:
        return None, []
    return Exhibit("1.1", "kpi_table", "From where it is to where it should be",
                   "Each measure, from today to the aim.", {"rows": rows}, "The scoreboard"), []


def _as_kind(built, kind: str):
    exhibit, figures = built
    if exhibit is None:
        return None, []
    return Exhibit(exhibit.id, kind, exhibit.caption, exhibit.takeaway, exhibit.data, exhibit.source), figures


def _classes(grid: dict | None) -> list[tuple[str, Decimal]]:
    if not isinstance(grid, dict):
        return []
    days = grid.get("grid") if isinstance(grid.get("grid"), list) else []
    totals: list[tuple[str, Decimal]] = []
    width = max((len(day.get("slots") or []) for day in days if isinstance(day, dict)), default=0)
    for index in range(width):
        taken = Decimal(0)
        label = ""
        seen = False
        for day in days:
            if not isinstance(day, dict):
                continue
            slots = day.get("slots") if isinstance(day.get("slots"), list) else []
            if index >= len(slots) or not isinstance(slots[index], dict):
                continue
            slot = slots[index]
            number = slot.get("taken")
            if isinstance(number, bool) or not isinstance(number, (int, Decimal)):
                continue
            taken += Decimal(number)
            seen = True
            if not label and isinstance(slot.get("time"), str):
                label = slot["time"]
        if seen:
            totals.append((label or f"Class {index + 1}", taken))
    return totals


def _count(fid: str, value: Decimal, unit: str, working: str) -> Figure:
    return Figure(fid, value, unit, None, "derived", Working((), "total", working), places_of(value))


def _row(label: str, figure: Figure) -> dict:
    return {"label": label, "value": format(figure.value, "f"), "figure_id": figure.id,
            "display": display(figure), "tag": tag_word(figure.kind)}


def _proposed(term: dict) -> bool:
    parts = term.get("parts")
    if not isinstance(parts, list):
        return False
    return any(isinstance(part, dict) and (part.get("kind") == "proposed" or _proposed(part)) for part in parts)


def _capacity(req) -> dict | None:
    data = _loads(getattr(req, "capacity_json", None))
    return data if isinstance(data, dict) else None


def _move(req) -> dict | None:
    answer = _loads(getattr(req, "answer_json", None))
    move = answer.get("move") if isinstance(answer, dict) else None
    return move if isinstance(move, dict) else None


def _fit(text: str, width: float) -> str:
    """The whole text. A line that does not fit is still the whole text: the
    drawing is asked for a box, and the caller widens the page rather than
    cutting the words."""
    return text


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(0)


def _loads(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
