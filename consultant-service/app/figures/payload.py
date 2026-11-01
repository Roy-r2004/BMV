"""What a web payload says about its figures.

The decision, preview, plan and shared-link payloads carry a `figures` map, one
entry per figure the payload names:

    {"display": "$28", "kind": "ours", "tag": "our estimate",
     "source": "Our estimate: proposed evening price"}

`display` is how the figure prints (`model.display`), `kind` whose it is, `tag` the
word the client sees beside it (`model.tag_word`, the same on every surface), and
`source` one plain sentence on where it came from, built here from the figure's own
source, never from an exception, a stage name or an id:

    theirs     From your answer to "<the question we asked>": "<their words>"
               From what you wrote about your <field>: "<their words>"
               From your file <file>, sheet <sheet>, cell <cell>
    derived    Worked out: <the working>
    ours       Our estimate: <what we propose>
    reference  Reference: <publication>, <year>

A working or a note that is only our own bookkeeping (a claim id, a path into the
financial model, a snake_case name) is not shown: the sentence falls back to a
general one that says the same thing in plain words.

The map is small: only the figures the payload names. They are found in the pieces
of the answer (`*_segments`, a headline figure's `ids`), in the move and its
proposals, the plan's length, the week's derived values and the roadmap's own
figures. A figure the request does not know is left out.

The answer's `headline`, `turn` and `sub` (and each headline figure's `value` and
`label`) also arrive as `*_segments` from `bind.segments`, the text in pieces with
each bound number carrying its figure's id, so a page can put the tag beside it.
The text itself is unchanged: the stages stored it already bound.

Building all of this is a courtesy to the page. `for_web` never raises: a payload
that cannot name its figures is served without them, as a row from before this step
is, and the page shows its numbers without tags.
"""
from __future__ import annotations

import logging
import re
from typing import Iterable, Mapping

from app.figures import casefile
from app.figures import known as _known
from app.figures.bind import segments
from app.figures.model import (Figure, FigureSet, Proposal, Reference, TheirsSource, Working, display,
                               tag_word)

logger = logging.getLogger("consultant.figures.payload")

#: The longest question quoted back to the client in a source, in characters.
QUESTION_MAX = 100
#: The longest stretch of their own words quoted back in a source.
QUOTE_MAX = 120
#: The longest working, note or publication shown in a source.
TEXT_MAX = 200
#: No source is longer than this.
SENTENCE_MAX = 280

_ELLIPSIS = "…"

#: What we say when a working or a note has nothing a client could read.
PLAIN_WORKING = "Worked out from your figures"
PLAIN_ESTIMATE = "Our estimate: a number we propose, not one you gave us"
PLAIN_REFERENCE = "Reference: a published source"


# -- plain words --------------------------------------------------------------------------

# Our own bookkeeping: a claim or figure id (CF-04, CAP-03a, TB-01-day, MOVE, PLAN-WEEKS,
# T2-1, F-main_problem-1), a snake_case name (financial_model), a subscript (lines[0]).
_INTERNAL = re.compile(
    r"\b[A-Z]{1,5}-\d+[a-z]?(?:-[A-Za-z0-9]+)*\b"
    r"|\b(?:MOVE|PROP-\d+|PLAN-[A-Z0-9-]+)\b"
    r"|\b[TEA]\d+-\d+(?:\.\d+)?\b|\bF-[a-z_]+-\d+\b"
    r"|\b[a-z]+(?:_[a-z]+)+\b"
    r"|\[\d+\]")
# "financial_model.lines[0]: 3 x 95 x 52": a path into one of our own records, then words
_PATH_PREFIX = re.compile(r"^(?=[^\s:]*[.\[])[A-Za-z_][\w.]*(?:\[[^\]]*\][\w.]*)*:\s+")


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + _ELLIPSIS


def _plain(text: object) -> str:
    """`text` as words a client can read, or "" when it is only our own bookkeeping."""
    words = " ".join(str(text or "").split())
    words = _PATH_PREFIX.sub("", words)
    if not words or _INTERNAL.search(words):
        return ""
    return _clip(words, TEXT_MAX)


def _theirs(s: TheirsSource, questions: Mapping[int, str]) -> str:
    if s.file:
        where = f"your file {s.file}"
        if s.field:
            where += f", sheet {s.field}"
        if s.cell:
            where += f", cell {s.cell}"
        return f"From {where}"
    quote = _clip(s.quote, QUOTE_MAX)
    if s.turn is not None:
        question = _clip(questions.get(s.turn, ""), QUESTION_MAX)
        head = f'From your answer to "{question}"' if question else "From one of your answers"
    elif s.field in casefile.FREE_TEXT_COLUMNS:
        head = f"From what you wrote about your {s.field.replace('_', ' ')}"
    else:
        head = "From what you told us"
    return f'{head}: "{quote}"' if quote else head


def source_sentence(f: Figure, questions: Mapping[int, str] | None = None) -> str:
    """The one sentence that says where `f` came from. `questions` are the
    interview questions by turn (`questions_for`), which a theirs figure from an
    answer is described by."""
    s = f.source
    if isinstance(s, TheirsSource):
        sentence = _theirs(s, questions or {})
    elif isinstance(s, Working):
        text = _plain(s.text)
        sentence = f"Worked out: {text}" if text else PLAIN_WORKING
    elif isinstance(s, Proposal):
        text = _plain(s.note)
        sentence = f"Our estimate: {text}" if text else PLAIN_ESTIMATE
    elif isinstance(s, Reference):
        publication = _plain(s.publication)
        sentence = f"Reference: {publication}, {s.year}" if publication else PLAIN_REFERENCE
    else:
        sentence = "From what you told us"
    return _clip(sentence, SENTENCE_MAX)


def entry(f: Figure, questions: Mapping[int, str] | None = None) -> dict:
    """One entry of the map."""
    return {"display": display(f), "kind": f.kind, "tag": tag_word(f.kind),
            "source": source_sentence(f, questions)}


def figure_map(known: FigureSet, ids: Iterable[str], questions: Mapping[int, str] | None = None) -> dict[str, dict]:
    """The entries for the figures in `ids` that `known` holds, in the order asked."""
    out: dict[str, dict] = {}
    for fid in ids:
        if isinstance(fid, str) and fid not in out:
            f = known.get(fid)
            if f is not None:
                out[fid] = entry(f, questions)
    return out


def questions_for(req) -> dict[int, str]:
    """The question we asked at each interview turn (1-based, as the case file
    numbers them), so an answer's figure can say which question it answered."""
    out: dict[int, str] = {}
    for turn, pair in enumerate(casefile._loads_list(getattr(req, "ops_numbers_json", None)), 1):
        question = pair.get("question") if isinstance(pair, dict) else None
        if isinstance(question, str) and question.strip():
            out[turn] = " ".join(question.split())
    return out


# -- the answer in pieces ----------------------------------------------------------------------

_PROSE = ("headline", "turn", "sub")


def _pieces(text: object, known: FigureSet) -> list[dict]:
    return segments(text, known) if isinstance(text, str) and text.strip() else []


def answer_for_web(answer: object, known: FigureSet) -> object:
    """The stored answer with its prose also in pieces: `headline_segments`,
    `turn_segments`, `sub_segments`, and `value_segments` and `label_segments` on
    each headline figure. Nothing else changes. Anything that is not an answer is
    returned as it is."""
    if not isinstance(answer, dict):
        return answer
    out = dict(answer)
    for field in _PROSE:
        out[f"{field}_segments"] = _pieces(out.get(field), known)
    if isinstance(out.get("figures"), list):
        shown = []
        for f in out["figures"]:
            if isinstance(f, dict):
                f = dict(f, **{f"{key}_segments": _pieces(f.get(key), known) for key in ("value", "label")})
            shown.append(f)
        out["figures"] = shown
    return out


# -- which figures a payload names ---------------------------------------------------------------

def _segment_ids(pieces: object) -> Iterable[str]:
    for p in pieces if isinstance(pieces, list) else []:
        if isinstance(p, dict) and isinstance(p.get("figure"), str):
            yield p["figure"]


def referenced_ids(answer: object, plan: object, capacity: object) -> list[str]:
    """The ids of the figures the answer (as `answer_for_web` serves it), the
    roadmap and the week name, each once, in the order met."""
    ids: dict[str, None] = {}

    def add(fid: object) -> None:
        if isinstance(fid, str) and fid:
            ids.setdefault(fid)

    if isinstance(answer, dict):
        for field in _PROSE:
            for fid in _segment_ids(answer.get(f"{field}_segments")):
                add(fid)
        for f in answer.get("figures") if isinstance(answer.get("figures"), list) else []:
            if not isinstance(f, dict):
                continue
            for fid in f.get("ids") if isinstance(f.get("ids"), list) else []:
                add(fid)
            for key in ("value_segments", "label_segments"):
                for fid in _segment_ids(f.get(key)):
                    add(fid)
        move = answer.get("move")
        if isinstance(move, dict):
            add(_known.MOVE_ID)
            for n, _ in enumerate([p for p in move.get("proposed") or [] if isinstance(p, dict)], 1):
                add(f"PROP-{n}")
        action = answer.get("action")
        if isinstance(action, dict) and isinstance(action.get("figure"), dict):
            add(action["figure"].get("id"))
    if isinstance(capacity, dict):
        for d in capacity.get("derived") if isinstance(capacity.get("derived"), list) else []:
            if isinstance(d, dict):
                add(d.get("key"))
    if isinstance(plan, dict):
        for f in plan.get("figures") if isinstance(plan.get("figures"), list) else []:
            if isinstance(f, dict):
                add(f.get("id"))
    return list(ids)


def for_web(req, *, answer: object = None, plan: object = None, capacity: object = None) -> tuple[object, dict]:
    """(the answer to serve, the figures map to serve) for a payload that carries
    the stored `answer`, roadmap `plan` and week `capacity`. Never raises."""
    try:
        if not isinstance(answer, dict) and not referenced_ids(None, plan, capacity):
            return answer, {}
        known = _known.known_for(req)
        served = answer_for_web(answer, known)
        return served, figure_map(known, referenced_ids(served, plan, capacity), questions_for(req))
    except Exception:   # a courtesy to the page: whatever went wrong, the page still opens
        logger.warning("the figures for a payload could not be built; it is served without them", exc_info=True)
        return answer, {}
