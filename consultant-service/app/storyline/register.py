"""The recommendation register, checked in code.

The model may draft the words, the owner, the shares and which row depends on
which. It may not write an amount. Each share is a whole number, the shares
add to 100, and each row's range is that share of the headline, so the rows
add up to it exactly. A cost is a figure this engagement already has, or a
plain statement of what is still needed to price it.
"""
from __future__ import annotations

import json
from decimal import Decimal

from app.config import settings
from app.figures import known as figures_known
from app.figures.calc import places_of
from app.figures.model import Figure, Proposal, Working, display
from app.storyline.flex import NoTerms, flexed, note
from app.storyline.model import Cost, Range, Register, RegisterRow

_SHARES = "Shares are our estimate of where the gain comes from."
_NO_VALUE = "There is no range to show, because this answer has no value to share out."
_NO_TERMS = ("There is no range to show, because the value was saved without "
             "the workings that recompute it.")


class RegisterInvalid(Exception):
    """The drafted register cannot be shown. `reasons` are the plain sentences
    a retry is given."""

    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


def assemble(req, drafted: list[dict]) -> Register:
    """The register, or `RegisterInvalid` naming everything that does not check out."""
    if not isinstance(drafted, list):
        raise RegisterInvalid(["The register did not come back as a list."])
    reasons: list[str] = []
    low, high = settings.REGISTER_ROWS_MIN, settings.REGISTER_ROWS_MAX
    if not low <= len(drafted) <= high:
        reasons.append(f"The register needs between {low} and {high} recommendations; "
                       f"this one has {len(drafted)}.")
    known = figures_known.known_for(req, leave_out={"register"})
    phases = _phases(req)
    parsed: list[dict] = []
    shares = 0
    for index, raw in enumerate(drafted, 1):
        parsed.append(_row(raw, index, phases, known, reasons))
        share = parsed[-1].get("share")
        if isinstance(share, int):
            shares += share
    if parsed and shares != 100:
        reasons.append(f"The shares add up to {shares}, and they have to add up to 100.")
    if reasons:
        raise RegisterInvalid(reasons)

    headline, why = _headline(req)
    rows = tuple(_built(item, headline) for item in parsed)
    footnotes = _footnotes(req, why, rows)
    return Register(rows, headline, footnotes)


def extra_figures(register: Register) -> list[Figure]:
    """Every end of every range, so the number law can see the numbers the table prints."""
    return _figures(register)


def displays(register: Register) -> list[str]:
    """The line each range number is printed as."""
    return [_spoken(figure) for figure in _figures(register)]


def figures_for(req) -> list[Figure]:
    """The stored storyline's range numbers, for the known set. Empty when there
    is no storyline or it does not check out."""
    raw = _loads(getattr(req, "storyline_json", None))
    drafted = raw.get("register") if isinstance(raw, dict) else None
    if not isinstance(drafted, list) or not drafted:
        return []
    try:
        return extra_figures(assemble(req, drafted))
    except RegisterInvalid:
        return []


def _row(raw, index: int, phases: list, known, reasons: list[str]) -> dict:
    if not isinstance(raw, dict):
        reasons.append(f"Recommendation {index} is not a recommendation.")
        return {"share": None}
    share = raw.get("share_pct")
    if isinstance(share, bool) or not isinstance(share, int):
        reasons.append(f"Recommendation {index} needs a whole-number share.")
        share = None
    elif share < 0:
        reasons.append(f"Recommendation {index} has a share below zero.")
        share = None
    phase = raw.get("phase")
    when = ""
    if isinstance(phase, bool) or not isinstance(phase, int) or not 1 <= phase <= len(phases):
        reasons.append(f"Recommendation {index} names a phase this plan does not have.")
    else:
        stored = phases[phase - 1].get("when") if isinstance(phases[phase - 1], dict) else None
        when = stored if isinstance(stored, str) else ""
        if not when:
            reasons.append(f"Recommendation {index} names a phase with no timeframe.")
    depends: list[int] = []
    for dep in raw.get("depends_on") or []:
        if isinstance(dep, bool) or not isinstance(dep, int) or dep < 1 or dep >= index:
            reasons.append(f"Recommendation {index} depends on recommendation {dep}, which comes after it.")
        else:
            depends.append(dep)
    cost = _cost(raw, index, known, reasons)
    return {
        "id": str(index),
        "recommendation": _words(raw.get("recommendation")),
        "changes": _words(raw.get("changes")),
        "owner": _words(raw.get("owner")),
        "when": when,
        "depends_on": tuple(depends),
        "share": share,
        "cost": cost,
    }


def _cost(raw: dict, index: int, known, reasons: list[str]) -> Cost:
    figure_id = raw.get("cost_figure")
    needs = raw.get("cost_needs")
    if isinstance(figure_id, str) and figure_id and known.get(figure_id) is not None:
        return Cost(figure_id, None)
    if isinstance(needs, str) and needs.strip():
        return Cost(None, " ".join(needs.split()))
    reasons.append(f"Recommendation {index} cites a cost this engagement does not have, "
                   f"and does not say what is needed to price it.")
    return Cost(None, None)


def _built(item: dict, headline: Range | None) -> RegisterRow:
    value = None
    if headline is not None and isinstance(item.get("share"), int):
        share = Decimal(item["share"]) / Decimal(100)
        value = Range(headline.low * share, headline.mid * share, headline.high * share,
                      headline.unit, headline.period)
    return RegisterRow(
        item["id"], item["recommendation"], item["changes"], value, item["cost"],
        item["owner"], item["when"], item["depends_on"],
    )


def _headline(req) -> tuple[Range | None, str | None]:
    answer = _loads(getattr(req, "answer_json", None))
    move = answer.get("move") if isinstance(answer, dict) else None
    if not isinstance(move, dict):
        return None, _NO_VALUE
    try:
        low, mid, high = flexed(move.get("terms"), settings.VALUE_FLEX_PCT)
    except NoTerms:
        return None, _NO_TERMS
    unit = move.get("unit") if isinstance(move.get("unit"), str) else ""
    period = move.get("period") if isinstance(move.get("period"), str) and move.get("period") else None
    return Range(low, mid, high, unit, period), None


def _footnotes(req, why: str | None, rows: tuple[RegisterRow, ...]) -> tuple[str, ...]:
    notes: list[str] = []
    if why:
        notes.append(why)
    else:
        flex = _flex_note(req)
        if flex:
            notes.append(flex)
    notes.append(_SHARES)
    needed = [row.cost.needs for row in rows if row.cost.needs]
    if needed:
        tail = needed[0] if len(needed) == 1 else " and ".join(needed)
        notes.append(f"Not priced yet: needs {tail}.")
    return tuple(notes)


def _flex_note(req) -> str | None:
    answer = _loads(getattr(req, "answer_json", None))
    move = answer.get("move") if isinstance(answer, dict) else None
    if not isinstance(move, dict):
        return None
    try:
        return note(move.get("terms"), settings.VALUE_FLEX_PCT)
    except Exception:
        return None


def _figures(register: Register) -> list[Figure]:
    ours = any(line.startswith("Flexes our assumption") for line in register.footnotes)
    kind = "ours" if ours else "derived"
    spans: list[tuple[str, Range]] = [(row.id, row.value) for row in register.rows if row.value is not None]
    if register.total is not None:
        spans.append(("TOTAL", register.total))
    figures: list[Figure] = []
    for row_id, span in spans:
        for end, value in (("LOW", span.low), ("MID", span.mid), ("HIGH", span.high)):
            figures.append(_figure(f"REG-{row_id}-{end}", value, span.unit, span.period, kind))
    return figures


def _figure(fid: str, value: Decimal, unit: str, period: str | None, kind: str) -> Figure:
    source = (Proposal(note="this row's share of the headline") if kind == "ours"
              else Working((), "product", "this row's share of the headline"))
    return Figure(fid, value, unit, period, kind, source, places_of(value))


def _spoken(figure: Figure) -> str:
    shown = display(figure)
    if figure.period:
        return f"{shown} a {figure.period}"
    return shown


def _phases(req) -> list:
    plan = _loads(getattr(req, "action_plan_json", None))
    phases = plan.get("phases") if isinstance(plan, dict) else None
    return [p for p in phases if isinstance(p, dict)] if isinstance(phases, list) else []


def _words(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _loads(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
