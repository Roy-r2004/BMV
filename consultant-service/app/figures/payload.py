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
The text itself is unchanged: the stages stored it already bound. The request's known
set can change after a text is stored, so pieces that do not join back to the stored
text are not served (`[]`, and the page shows the plain text). The move and each
proposal also say which figure they are (`figure_id`: MOVE, PROP-n) so the page does
not have to build ids.

A payload that goes to someone who is not the owner (the shared link, a run anyone
can open) is built with `public=True`. The client's own words do not travel with it:
every theirs source reads "From the owner's answers." (no question, no quote, no file
name, no sheet, no cell), a working or note that happens to hold one of those strings
falls back to the general sentence, and a reference stays as it is. The tag and the
display are the same as for the owner.

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
#: What anyone but the owner reads where the owner's own words would be.
PUBLIC_THEIRS = "From the owner's answers."


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


def client_words(known: FigureSet, questions: Mapping[int, str] | None = None) -> list[str]:
    """The strings that are the client's own and that a public payload must not
    carry: the questions we asked them, the files they sent (name, sheet, cell) and
    the sentences they wrote that hold a number (a quote of three words or more; a
    bare number is already in the answer and is not "words")."""
    found = [q for q in (questions or {}).values()]
    for f in known.by_kind("theirs"):
        s = f.source
        if isinstance(s, TheirsSource):
            found += [s.file or "", (s.field or "") if s.file else "", s.cell or ""]
            if len(s.quote.split()) >= 3:
                found.append(s.quote)
    return sorted({" ".join(str(x).split()) for x in found if str(x).strip()})


def _holds_any(text: str, words: Iterable[str]) -> bool:
    return any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text, re.IGNORECASE) for w in words)


def public_sentence(f: Figure, words: Iterable[str] = ()) -> str:
    """The sentence a viewer who is not the owner reads for `f`: a theirs figure says
    only that it came from the owner's answers, a reference is shown as it is, and a
    working or an estimate is shown unless it holds one of the client's own `words`."""
    if f.kind == "theirs" or isinstance(f.source, TheirsSource):
        return PUBLIC_THEIRS
    sentence = source_sentence(f)
    if f.kind == "reference" or not _holds_any(sentence, words):
        return sentence
    return PLAIN_WORKING if f.kind == "derived" else PLAIN_ESTIMATE


def entry(f: Figure, questions: Mapping[int, str] | None = None, *, public: bool = False,
          words: Iterable[str] = ()) -> dict:
    """One entry of the map. `public` is for a payload that goes to someone who is
    not the owner (`public_sentence`); `words` are the client's own strings it keeps out."""
    return {"display": display(f), "kind": f.kind, "tag": tag_word(f.kind),
            "source": public_sentence(f, words) if public else source_sentence(f, questions)}


def figure_map(known: FigureSet, ids: Iterable[str], questions: Mapping[int, str] | None = None, *,
               public: bool = False) -> dict[str, dict]:
    """The entries for the figures in `ids` that `known` holds, in the order asked.
    With `public`, none of the client's own words is in any source."""
    words = client_words(known, questions) if public else ()
    out: dict[str, dict] = {}
    for fid in ids:
        if isinstance(fid, str) and fid not in out:
            f = known.get(fid)
            if f is None:
                continue
            try:
                out[fid] = entry(f, questions, public=public, words=words)
            except Exception:   # one figure that cannot be described is left out, not the whole map
                logger.warning("figure %s could not be described; it is left out of the payload", fid)
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
    """The text in pieces, or [] when it has none or when they would not join back to
    the stored text (the known set has changed since it was stored and now binds a
    number differently): the page then shows the text as stored."""
    if not isinstance(text, str) or not text.strip():
        return []
    pieces = segments(text, known)
    return pieces if "".join(p["text"] for p in pieces) == text else []


def answer_for_web(answer: object, known: FigureSet) -> object:
    """The stored answer with its prose also in pieces: `headline_segments`,
    `turn_segments`, `sub_segments`, and `value_segments` and `label_segments` on
    each headline figure; and the move and each of its proposals saying which figure
    they are. Nothing else changes. Anything that is not an answer is returned as it is."""
    if not isinstance(answer, dict):
        return answer
    out = dict(answer)
    move = out.get("move")
    if isinstance(move, dict):
        # numbered as `known.move_figures` numbers them: the n-th proposal that is an object
        n, proposed = 0, []
        for p in move.get("proposed") if isinstance(move.get("proposed"), list) else []:
            if isinstance(p, dict):
                n += 1
                p = dict(p, figure_id=f"PROP-{n}")
            proposed.append(p)
        out["move"] = dict(move, figure_id=_known.MOVE_ID, proposed=proposed)
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
    roadmap and the week name, each once, in the order met: the ones a page draws
    (the roadmap's own figures except its phase count)."""
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
            add(move.get("figure_id"))
            for p in move.get("proposed") if isinstance(move.get("proposed"), list) else []:
                if isinstance(p, dict):
                    add(p.get("figure_id"))
        action = answer.get("action")
        if isinstance(action, dict) and isinstance(action.get("figure"), dict):
            add(action["figure"].get("id"))
    if isinstance(capacity, dict):
        for d in capacity.get("derived") if isinstance(capacity.get("derived"), list) else []:
            if isinstance(d, dict):
                add(d.get("key"))
    if isinstance(plan, dict):
        for f in plan.get("figures") if isinstance(plan.get("figures"), list) else []:
            # the roadmap's phase count is not drawn anywhere, so it is not sent
            if isinstance(f, dict) and f.get("id") != _known.PLAN_PHASES_ID:
                add(f.get("id"))
    return list(ids)


def for_web(req, *, answer: object = None, plan: object = None, capacity: object = None,
            public: bool = False) -> tuple[object, dict]:
    """(the answer to serve, the figures map to serve) for a payload that carries
    the stored `answer`, roadmap `plan` and week `capacity`. `public` is for a payload
    that goes to someone who is not the owner: the map holds none of the client's
    own words. Never raises."""
    try:
        if not isinstance(answer, dict) and not referenced_ids(None, plan, capacity):
            return answer, {}
        known = _known.known_for(req)
        served = answer_for_web(answer, known)
        return served, figure_map(known, referenced_ids(served, plan, capacity), questions_for(req), public=public)
    except Exception:   # a courtesy to the page: whatever went wrong, the page still opens
        logger.warning("the figures for a payload could not be built; it is served without them", exc_info=True)
        return answer, {}
