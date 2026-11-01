"""The figures a request knows: the one set every check reads.

`known_for(req)` is the union of

    theirs     the case file (`casefile.load`): every number in the client's own
               answers, free-text columns and files. Never our questions: a
               number that appears only in a question we asked is not theirs.
    derived    the capacity picture's computed figures (`capacity_json`, ids
               CAP-nn), and the registry's machine-computed claims mapped through
               `model.from_claim` (the client's own CF and CE claims are left out:
               the case file holds those numbers)
    ours       the registry's proposed claims, the answer's move (MOVE, ours when
               any of its terms is a number we propose, otherwise derived) and its
               proposals (PROP-n), the length of the plan the answer proposes
               (PLAN-WEEKS), and the roadmap's own figures
               (`action_plan_json["figures"]`: PLAN-WEEKS, PLAN-PHASE-n-WEEKS,
               PLAN-PHASES)

Every part is read from the stored JSON by key, so this module imports no stage
(the stages import it). A row from before any of these existed (no case file
column, no answer, no roadmap) still gives a set: the case file is built from its
columns, and a part that is missing or cannot be read adds nothing. A stored
figure that cannot be read is skipped, never raised; a stored figure whose id is
already held by a different figure is skipped too (the earlier part wins, so the
client's own figures are never displaced).

`known_for_texts(texts)` is the same reading of the client's words for the
interview, before any request row exists: pass it their answers only, never
"question: answer" lines.

A stage that has just computed figures the row cannot show yet (the answer's
move, before the answer is saved) passes them as `extra`, or adds them with
`with_extra`.
"""
from __future__ import annotations

import json
import logging
import math
from decimal import Decimal
from typing import Iterable, Sequence

from app.config import settings
from app.figures import casefile
from app.figures.model import (Figure, FigureSet, Proposal, Working, decimal_from_float, from_claim,
                               from_json)
from app.figures.read import mentions

logger = logging.getLogger("consultant.figures.known")

#: The parts of a request's known set, in the order they are added.
PARTS = ("case_file", "capacity", "registry", "answer", "roadmap")

#: The client's own claim ids in the registry; the case file holds their numbers.
_CLIENT_CLAIM_PREFIXES = ("CF-", "CE-")

MOVE_ID = "MOVE"
PLAN_WEEKS_ID = "PLAN-WEEKS"
PLAN_PHASES_ID = "PLAN-PHASES"


def phase_weeks_id(n: int) -> str:
    """The id of the n-th (1-based) roadmap phase's length in weeks."""
    return f"PLAN-PHASE-{n}-WEEKS"


# -- reading stored JSON ---------------------------------------------------------------

def _loads(raw: object) -> object:
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _number(value: object) -> Decimal | None:
    """A stored number as a Decimal, or None: a bool, text and a value that is not
    finite are not numbers a figure can hold."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return decimal_from_float(value)
    return Decimal(value)


def _places(value: Decimal) -> int:
    """Digits after the point needed to write `value` exactly (22.50 needs 1)."""
    if value == value.to_integral_value():
        return 0
    return max(0, -value.normalize().as_tuple().exponent)


def _stored_figures(items: object) -> list[Figure]:
    out = []
    for d in items if isinstance(items, list) else []:
        try:
            out.append(from_json(d))
        except (TypeError, ValueError) as exc:
            logger.info("a stored figure could not be read: %s", exc)
    return out


# -- the client's words ----------------------------------------------------------------

def client_texts(req) -> list[str]:
    """The client's own words on the row, as the case file reads them: each
    interview answer (never the question we asked), then each free-text column
    with the notes the intake adds cut out, skipping a column that repeats words
    already read or holds only the scope question we wrote."""
    out: list[str] = []
    for pair in casefile._loads_list(getattr(req, "ops_numbers_json", None)):
        answer = pair.get("answer") if isinstance(pair, dict) else None
        if isinstance(answer, str) and answer.strip():
            out.append(answer.strip())
    question, seen = casefile._scope_question(req), set()
    for field in casefile.FREE_TEXT_COLUMNS:
        text = getattr(req, field, None)
        if not isinstance(text, str):
            continue
        if field == "business_description":
            text = casefile._OUR_NOTES.sub("", text)
        words = " ".join(text.split())
        if not words or words in seen or (field == "desired_outcome" and words == question):
            continue
        seen.add(words)
        out.append(text.strip())
    return out


def hours_in(texts: Iterable[str]) -> set[int]:
    """Every clock time the texts name, as an hour on a 24-hour clock."""
    return {int(m.value) for t in texts or [] if isinstance(t, str) for m in mentions(t) if m.form == "time"}


def hours_for(req) -> set[int]:
    """The clock times the client named in their own words."""
    return hours_in(client_texts(req))


def known_for_texts(texts: Sequence[str]) -> FigureSet:
    """The client's numbers in `texts`, as theirs figures (ids A<i>-<n>: the n-th
    number of the i-th text), read the way the case file reads an answer. Pass the
    client's own words only, never our questions."""
    known = FigureSet()
    for i, text in enumerate(texts or [], 1):
        if not isinstance(text, str) or not text.strip():
            continue
        for f in casefile._text_figures(text.strip(), f"A{i}", turn=None, field=None,
                                        limit=settings.CASE_FILE_FIGURES_PER_TEXT):
            known.add(f)
    return known


# -- the parts a request stores --------------------------------------------------------

def capacity_figures(picture: object) -> list[Figure]:
    """The capacity picture's computed figures (CAP-nn), each a derived figure
    with its working. A figure's unit is the one stored with it, or the picture's
    unit when the row predates that."""
    if not isinstance(picture, dict):
        return []
    period = "week" if picture.get("shape") == "weekly_grid" else (picture.get("period") or None)
    fallback = str(picture.get("unit_plural") or "")
    out = []
    for d in picture.get("derived") or []:
        if not isinstance(d, dict) or not isinstance(d.get("key"), str) or not d["key"]:
            continue
        value = _number(d.get("value"))
        if value is None:
            continue
        unit = d.get("unit") if isinstance(d.get("unit"), str) else fallback
        try:
            out.append(Figure(d["key"], value, unit, period if isinstance(period, str) else None, "derived",
                              Working(inputs=(), op="capacity", text=str(d.get("working") or "")),
                              _places(value)))
        except (TypeError, ValueError) as exc:
            logger.info("a capacity figure could not be read: %s", exc)
    return out


def registry_figures(registry: object) -> list[Figure]:
    """The registry's machine-computed and proposed claims as figures. The client's
    own claims (CF, CE) are left out, since the case file holds them, and so is any
    other claim that maps to theirs: what the client said comes from their words
    only. A claim that cannot be mapped is skipped."""
    claims = registry.get("claims") if isinstance(registry, dict) else None
    out = []
    for c in claims if isinstance(claims, list) else []:
        if not isinstance(c, dict) or str(c.get("id") or "").startswith(_CLIENT_CLAIM_PREFIXES):
            continue
        try:
            f = from_claim(c)
        except (TypeError, ValueError):
            continue
        if f.kind in ("derived", "ours"):
            out.append(f)
    return out


def proposal_unit(label: str) -> str:
    """The unit of a number we propose, from its label: a price is in dollars."""
    label = str(label or "")
    return "USD" if "$" in label or "price" in label.lower() else ""


def said_precision(value: Decimal) -> int:
    """How a worked-out total is said out loud: to the thousand from ten thousand,
    the hundred from a thousand, the ten from a hundred (44,928 is ~45,000)."""
    a = abs(value)
    return -3 if a >= 10_000 else -2 if a >= 1000 else -1 if a >= 100 else 0


def move_figures(move: object) -> list[Figure]:
    """The answer's move (MOVE) and the numbers we propose in it (PROP-n), from the
    move as the answer stores it. The move is ours when any term is a proposal,
    otherwise derived, and is said rounded (`said_precision`)."""
    if not isinstance(move, dict):
        return []
    out: list[Figure] = []
    proposed = [p for p in move.get("proposed") or [] if isinstance(p, dict)]
    value = _number(move.get("value"))
    if value is not None and value > 0:
        unit = str(move.get("unit") or "")
        period = move.get("period") if isinstance(move.get("period"), str) and move.get("period") else None
        label = str(move.get("label") or "")
        working = str(move.get("working") or "")
        source = (Proposal(note=label or working or "the move we propose") if proposed else
                  Working(inputs=tuple(str(c) for c in move.get("cites") or []), op="product", text=working))
        out.append(Figure(MOVE_ID, value, unit, period, "ours" if proposed else "derived", source,
                          said_precision(value)))
    for n, p in enumerate(proposed, 1):
        v = _number(p.get("value"))
        if v is None:
            continue
        label = str(p.get("label") or "proposed")
        out.append(Figure(f"PROP-{n}", v, proposal_unit(label), None, "ours", Proposal(note=label), _places(v)))
    return out


def plan_weeks_figure(weeks: int) -> Figure:
    """The length of the plan we propose, in weeks (PLAN-WEEKS)."""
    return Figure(PLAN_WEEKS_ID, Decimal(int(weeks)), "week", None, "ours",
                  Proposal(note="the length of the plan we propose"), 0)


def answer_figures(answer: object) -> list[Figure]:
    """The figures the stored answer proposes: its move and proposals, and the
    length of its plan."""
    if not isinstance(answer, dict):
        return []
    out = move_figures(answer.get("move"))
    action = answer.get("action") if isinstance(answer.get("action"), dict) else {}
    out += _stored_figures([action["figure"]] if isinstance(action.get("figure"), dict) else [])
    return out


def roadmap_figures(plan: object) -> list[Figure]:
    """The roadmap's own figures, as the roadmap stage stored them."""
    return _stored_figures(plan.get("figures") if isinstance(plan, dict) else None)


# -- the set ----------------------------------------------------------------------------

def _add_kept(known: FigureSet, figures: Iterable[Figure]) -> None:
    """Add each figure; one whose id a different figure already holds is skipped."""
    for f in figures:
        held = known.get(f.id)
        if held is not None and held != f:
            logger.info("figure %s is already known as another value; the later one is not used", f.id)
            continue
        known.add(f)


def with_extra(known: FigureSet, figures: Iterable[Figure]) -> FigureSet:
    """A new set: `known` with `figures` added. A figure just computed replaces a
    stored one under the same id (a stage's fresh move replaces an old one)."""
    fresh = list(figures)
    ids = {f.id for f in fresh}
    return FigureSet([*(f for f in known if f.id not in ids), *fresh])


def known_for(req, extra: Iterable[Figure] = (), *, leave_out: Iterable[str] = ()) -> FigureSet:
    """Every figure the request knows (see the module docstring), then `extra`.

    `leave_out` names parts (from `PARTS`) not to read: a stage that is writing
    one of them again leaves its old version out, so a stale move or roadmap
    cannot vouch for a number in the new one."""
    skip = set(leave_out)
    unknown = skip - set(PARTS)
    if unknown:
        raise ValueError(f"unknown parts of the known set: {', '.join(sorted(unknown))}")
    known = FigureSet()
    if "case_file" not in skip:
        _add_kept(known, casefile.load(req))
    if "capacity" not in skip:
        _add_kept(known, capacity_figures(_loads(getattr(req, "capacity_json", None))))
    if "registry" not in skip:
        _add_kept(known, registry_figures(_loads(getattr(req, "registry_json", None))))
    if "answer" not in skip:
        _add_kept(known, answer_figures(_loads(getattr(req, "answer_json", None))))
    if "roadmap" not in skip:
        _add_kept(known, roadmap_figures(_loads(getattr(req, "action_plan_json", None))))
    extra = list(extra)
    return with_extra(known, extra) if extra else known
