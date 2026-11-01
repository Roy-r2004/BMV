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

`prompt_lines(known)` is the set as a prompt shows it to the model, one bounded line
per figure ("Figures you may use").
"""
from __future__ import annotations

import json
import logging
import math
from decimal import Decimal
from typing import Iterable, Sequence

from app.config import settings
from app.figures import casefile
from app.figures.model import (Figure, FigureSet, Proposal, TheirsSource, Working, decimal_from_float, display,
                               from_claim, from_json, tag_word)
from app.figures.read import Mention, mentions

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
    """The client's own words on the row, exactly as the case file reads them
    (`casefile.client_words`): their answers, never our questions, and their
    free-text columns without the notes the intake adds."""
    return casefile.client_texts(req)


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
    return FigureSet(f for _, f in read_texts(texts))


def read_texts(texts: Sequence[str]) -> list[tuple[Mention, Figure]]:
    """`known_for_texts`, with the mention each figure was read from (its form
    says whether it was written as a count, money, a percent...)."""
    out: list[tuple[Mention, Figure]] = []
    for i, text in enumerate(texts or [], 1):
        if isinstance(text, str) and text.strip():
            out += casefile.read_text(text.strip(), f"A{i}", limit=settings.CASE_FILE_FIGURES_PER_TEXT)
    return out


# -- the parts a request stores --------------------------------------------------------

def capacity_figures(picture: object) -> list[Figure]:
    """The capacity picture's computed figures (CAP-nn), each a derived figure
    with its working. A figure's unit is the one stored with it, or the picture's
    unit when the row predates that."""
    if not isinstance(picture, dict):
        return []
    period = "week" if picture.get("shape") == "weekly_grid" else (picture.get("period") or None)
    fallback = picture["unit_plural"] if isinstance(picture.get("unit_plural"), str) else ""
    derived = picture.get("derived")
    out = []
    for d in derived if isinstance(derived, list) else []:
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
    stored, cites = move.get("proposed"), move.get("cites")
    proposed = [p for p in stored if isinstance(p, dict)] if isinstance(stored, list) else []
    cites = cites if isinstance(cites, list) else []
    value = _number(move.get("value"))
    if value is not None and value > 0:
        unit = move["unit"] if isinstance(move.get("unit"), str) else ""
        period = move.get("period") if isinstance(move.get("period"), str) and move.get("period") else None
        label = str(move.get("label") or "")
        working = str(move.get("working") or "")
        source = (Proposal(note=label or working or "the move we propose") if proposed else
                  Working(inputs=tuple(str(c) for c in cites), op="product", text=working))
        out += _made(lambda: Figure(MOVE_ID, value, unit, period, "ours" if proposed else "derived", source,
                                    said_precision(value)))
    for n, p in enumerate(proposed, 1):
        v = _number(p.get("value"))
        if v is None:
            continue
        label = str(p.get("label") or "proposed")
        # the unit the move stored with it; a move stored before it kept one is read from the label
        unit = p["unit"] if isinstance(p.get("unit"), str) else proposal_unit(label)
        out += _made(lambda: Figure(f"PROP-{n}", v, unit, None, "ours", Proposal(note=label), _places(v)))
    return out


def _made(build) -> list[Figure]:
    """[the figure `build` makes], or [] when what was stored cannot be a figure."""
    try:
        return [build()]
    except (TypeError, ValueError, ArithmeticError) as exc:
        logger.info("a stored figure could not be read: %s", exc)
        return []


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
    if isinstance(action.get("figure"), dict):
        out += _stored_figures([action["figure"]])
    else:
        # an answer stored before the length was a figure kept only its weeks
        weeks = _number(action.get("weeks"))
        if weeks is not None and weeks > 0 and weeks == weeks.to_integral_value():
            out += _made(lambda: plan_weeks_figure(int(weeks)))
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


# -- the set, as a prompt shows it ----------------------------------------------------------

#: The order a prompt lists figures in: what the client said, what we worked out from
#: it, what a publication says, and last what we only propose. When there are more
#: than the prompt may list, the end of this order is what is left out.
_PROMPT_ORDER = ("theirs", "derived", "reference", "ours")

#: A figure's period is said after it ("$22 a week") only when it is one of these.
_PROMPT_PERIODS = frozenset({"hour", "day", "week", "month", "quarter", "year"})

#: Characters of the words that say what a figure is, on its line.
PROMPT_NOTE_CHARS = 70


def _note(f: Figure) -> str:
    """What a figure is, in a few words: the client's own words for theirs, the
    working for a derived one, the proposal for ours, the publication for a reference."""
    s = f.source
    if isinstance(s, TheirsSource):
        text = s.quote
    elif isinstance(s, Working):
        text = s.text
    elif isinstance(s, Proposal):
        text = s.note
    else:
        text = f"{s.publication} {s.year}"
    text = " ".join(str(text or "").replace("|", "/").split())
    if len(text) > PROMPT_NOTE_CHARS:
        text = text[:PROMPT_NOTE_CHARS].rsplit(" ", 1)[0].rstrip(",;:-") + "\u2026"
    return text


def _prompt_line(f: Figure) -> str:
    """`CF-04 | $22 a week | yours | what the client said`: the id to cite, the
    figure as a client reads it, whose it is, and what it is."""
    shown = display(f)
    if f.period in _PROMPT_PERIODS:
        shown += f" a {f.period}"
    note = _note(f)
    return f"{f.id} | {shown} | {tag_word(f.kind)}" + (f" | {note}" if note else "")


def _is_proposal(f: Figure) -> bool:
    """The figures the plan stands on: the move, what we propose in it, and the plan's lengths."""
    return f.kind == "ours" and (f.id == MOVE_ID or f.id.startswith(("PROP-", "PLAN-")))


def _theirs_rank(f: Figure) -> int:
    """How soon a figure of theirs is cut: 0 the form they filled in (F-...), kept
    longest; 1 an interview answer (T<turn>-<n>); 2 a cell of a file they sent
    (E<claim>-<n>), cut first."""
    if f.id[:1] == "E" and f.id[1:2].isdigit():
        return 2
    if f.id[:1] == "T" and f.id[1:2].isdigit():
        return 1
    return 0


def _kept_for_prompt(known: FigureSet, budget: int) -> set[str]:
    """The ids of the `budget` figures a prompt lists when they do not all fit.

    Our proposals and the references are never pushed out by the client's own and
    derived figures. They come first: the move, what it proposes and the plan's
    lengths, then the references, then our other proposals, but never more than half
    the budget, so the client's figures are not left with no room at all. The rest of
    the budget goes to derived and theirs: each may have half, and one that needs less
    lends what it does not use to the other. Of derived, the earliest are kept (their
    week first, then the registry's claims). Of theirs, what they typed in the form is
    kept longest, then the interview from its first answer on (the latest turns are cut
    last-first), and the cells of the files they sent go first."""
    ours = known.by_kind("ours")
    protected = [f for f in ours if _is_proposal(f)] + known.by_kind("reference") +         [f for f in ours if not _is_proposal(f)]
    protected = protected[:max(1, budget // 2)]
    room = budget - len(protected)
    derived, theirs = known.by_kind("derived"), sorted(known.by_kind("theirs"), key=_theirs_rank)
    take_derived = min(len(derived), max(room // 2, room - len(theirs)))
    take_theirs = min(len(theirs), room - take_derived)
    return {f.id for f in (*protected, *derived[:take_derived], *theirs[:take_theirs])}


def prompt_lines(known: FigureSet) -> str:
    """The known set as the lines a prompt lists under "Figures you may use": one
    line per figure, `id | figure | whose it is | what it is`, theirs first, then
    derived, reference and ours, each kind in the order its figures were added.

    At most `settings.PROMPT_FIGURE_LINES` lines. When the figures do not all fit,
    what is left out is theirs and derived (`_kept_for_prompt`: our proposals and the
    references stay, then the earliest of the others, the files' cells first to go),
    and the last line says how many more exist and whose they are. An empty set gives
    "none"."""
    ordered = [f for kind in _PROMPT_ORDER for f in known.by_kind(kind)]
    if not ordered:
        return "none"
    limit = settings.PROMPT_FIGURE_LINES
    if len(ordered) <= limit:
        return "\n".join(_prompt_line(f) for f in ordered)
    kept = _kept_for_prompt(known, limit - 1)
    shown, left = [f for f in ordered if f.id in kept], [f for f in ordered if f.id not in kept]
    whose = ", ".join(f"{n} {tag_word(k)}" for k in _PROMPT_ORDER if (n := sum(1 for f in left if f.kind == k)))
    more = f"... and {len(left)} more figures exist but are not listed here ({whose}); write only the numbers listed above"
    return "\n".join([*(_prompt_line(f) for f in shown), more])
