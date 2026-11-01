import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, NamedTuple

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures.bind import bind, clean_sentences
from app.figures.known import hours_for, known_for, prompt_lines
from app.figures.model import FigureSet
from app.models import Request
from app.pipeline._shared import ask_until_usable, build_engagement_register, ledger, reply_json
from app.pipeline.failure import StageFailed
from app.templating import render

logger = logging.getLogger("consultant.analyze")

#: What a row can hold at the moment `analyze` runs that is not about this run: the
#: capacity picture is read after this stage, and the answer, the registry and the
#: roadmap are written after it, so on the row they are from an earlier run (if any).
STALE_AT_START = frozenset({"capacity", "answer", "registry", "roadmap"})

#: The model-written text of the analysis a client reads on the web.
PROSE_KEYS = ("target_customer_profile", "pain_points", "growth_opportunity")

#: How many of the numbers a check removed are named in the log line.
LOG_NUMBERS = 20

_SENTENCE_END = re.compile(r"[.!?][\"')\u201d\u2019\]]*(?=\s|$)")


def has_text(value) -> bool:
    """Whether a string, or a list or dict holding strings, has any text in it."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_text(v) for v in value)
    if isinstance(value, dict):
        return any(has_text(v) for v in value.values())
    return False


class NumberCheckFailed(ValueError):
    """A reply the number check left unusable: a field the stage needs lost every
    sentence. It is a ValueError, so `ask_until_usable` asks again exactly as it does
    for any unusable reply, and a provider error still goes straight up. `hint` is what
    to tell the model on the next ask: where the sentences were taken out and which
    numbers nobody owns (never the sentences), and the figures it may use."""

    def __init__(self, message: str, hint: str):
        super().__init__(message)
        self.hint = hint


class Checked(NamedTuple):
    """One text after the number check: what is left of it, how many sentences were
    taken out, and the numbers or figure tokens nobody owns that caused it (as the
    text wrote them)."""
    text: str
    sentences: int
    causes: list[str]


@dataclass
class Removed:
    """What the number check took out of a stage's text so far: how many sentences,
    and by field the numbers or tokens that caused it. Never the sentences."""
    sentences: int = 0
    causes: dict[str, list[str]] = field(default_factory=dict)

    def add(self, where: str, sentences: int, causes: list[str]) -> None:
        self.sentences += sentences
        held = self.causes.setdefault(where, [])
        held.extend(c for c in causes if c not in held)

    def __bool__(self) -> bool:
        return self.sentences > 0

    def clear(self) -> None:
        self.sentences = 0
        self.causes = {}


def check_text(text: str, known: FigureSet, hours: set[int]) -> Checked:
    """`text` bound to the figures, without each sentence that holds a number nobody
    owns (`bind.clean_sentences`), and the unresolved numbers and tokens behind each
    drop (`bind.bind`): every unresolved number sits in a sentence that is dropped."""
    cleaned, gone = clean_sentences(text, known, hours=hours)
    if not gone:
        return Checked(cleaned, 0, [])
    unresolved = bind(text, known, hours=hours).unresolved
    return Checked(cleaned, len(gone), list(dict.fromkeys(u.text for u in unresolved)))


def clean_prose(value, known: FigureSet, hours: set[int], removed: Removed, where: str = ""):
    """Model-written text with every number checked: each string is bound to the
    figures and loses each sentence that holds a number nobody owns
    (`check_text`); a list or dict is walked, and a list item that had text and has
    none left is dropped. Anything else is returned as it is. What was taken out is
    added to `removed` under `where` (the field), for the caller to log and to tell
    the model.

    The three stages that write the analysis, the decision and the diagnosis share
    this walk; each decides which of its fields are prose."""
    if isinstance(value, str):
        checked = check_text(value, known, hours)
        removed.add(where, checked.sentences, checked.causes)
        return checked.text
    if isinstance(value, list):
        kept = []
        for item in value:
            cleaned = clean_prose(item, known, hours, removed, where)
            if has_text(item) and not has_text(cleaned):
                continue
            kept.append(cleaned)
        return kept
    if isinstance(value, dict):
        return {k: clean_prose(v, known, hours, removed, where) for k, v in value.items()}
    return value


def _number_words(numbers: list[str]) -> str:
    """'the number 48', 'the numbers 48 and 15', 'the numbers 48, 15 and 200'."""
    listed = numbers[0] if len(numbers) == 1 else ", ".join(numbers[:-1]) + " and " + numbers[-1]
    return f"the number {listed}" if len(numbers) == 1 else f"the numbers {listed}"


def retry_hint(problem: str, causes: dict[str, list[str]], figures: str) -> str:
    """What to add to the prompt of the next ask after the number check left a reply
    unusable: `problem` in a sentence, then for each field in `causes` the numbers
    nobody owns, then the instruction and the figures that may be used. It names
    numbers and fields, never the sentences that were taken out."""
    lines = "\n".join(f"- {where}: {_number_words(numbers) if numbers else 'a number that is not listed'}"
                     for where, numbers in causes.items())
    return (
        f"YOUR LAST REPLY COULD NOT BE USED. {problem}\n{lines}\n"
        "Write the whole reply again. Do not use those numbers: say it in words, or use only a number "
        "from the figures list below, exactly as listed, or cite it as {{F:id}}.\n\n"
        f"FIGURES YOU MAY USE (id | number | whose it is | what it is)\n{figures}")


def remember_hint(use: Callable[[dict], object], hints: list[str]) -> Callable[[dict], object]:
    """`use` for `ask_until_usable`, noting in `hints` the hint of a `NumberCheckFailed`
    it raises (and raising it on), for the stage's next ask to add to its prompt."""
    def wrapped(body: dict):
        try:
            return use(body)
        except NumberCheckFailed as exc:
            hints[:] = [exc.hint]
            raise
    return wrapped


def with_hint(prompt: str, hints: list[str]) -> str:
    """`prompt`, then the hint the last unusable reply left (none on the first ask)."""
    return f"{prompt}\n\n{hints[0]}" if hints else prompt


def cut_prose(text: str, limit: int) -> str:
    """`text` cut to at most `limit` characters, for text that has already been
    checked: at the last sentence end in its second half, else at the last word
    end, so the cut never falls inside a word or a figure ("$2200" is never cut to
    "$22"). A text that fits is returned as it is. Nothing is added. One word longer
    than the limit is not prose, and gives "" rather than a piece of it."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    if not text[limit].isspace():
        space = max(head.rfind(c) for c in " \t\n\u00a0")
        if space <= 0:
            return ""
        head = head[:space]
    ends = [m.end() for m in _SENTENCE_END.finditer(head)]
    if ends and ends[-1] >= limit // 2:
        head = head[:ends[-1]]
    return head.rstrip()


def log_removed(log: logging.Logger, what: str, removed: Removed) -> None:
    """Say at INFO what the number check took out of `what`: how many sentences, from
    which fields, and the numbers or tokens that caused it (the unresolved ones, not
    every number in the sentences). Never the sentences themselves. Called on every
    path, the retry and the failure included, so "what did it drop?" can be answered."""
    if not removed:
        return
    causes = list(dict.fromkeys(c for held in removed.causes.values() for c in held))
    named = ", ".join(causes[:LOG_NUMBERS]) + (", ..." if len(causes) > LOG_NUMBERS else "")
    fields = ", ".join(w for w in removed.causes if w)
    log.info("took %d sentence(s) out of the %s%s; numbers nobody gave: %s", removed.sentences, what,
             f" ({fields})" if fields else "", named or "none")


def _format_site_research(req: Request) -> str:
    """Flattens the research stage's JSON into one line for the prompt —
    same pre-formatted-string pattern plan.py already uses for its JSON
    context fields. "none given" when there is nothing to report, so the
    model reads it the same as any other unanswered intake field."""
    if not req.site_research_json:
        return "none given"
    try:
        data = json.loads(req.site_research_json)
    except (TypeError, ValueError):
        return "none given"
    parts = []
    if data.get("services"):
        parts.append(f"services mentioned: {', '.join(data['services'])}")
    if data.get("hours"):
        parts.append(f"hours: {data['hours']}")
    if data.get("tone"):
        parts.append(f"tone: {data['tone']}")
    if data.get("highlights"):
        parts.append(f"highlights: {', '.join(data['highlights'])}")
    return "; ".join(parts) if parts else "none given"


def _analysis(body: dict, known: FigureSet, hours: set[int], figures: str) -> dict:
    """The analysis in a reply, its prose checked against what the client gave.

    The findings are the pain points and the growth opportunity: when the model wrote
    any and the check leaves none of either, the reply is unusable (`NumberCheckFailed`,
    a ValueError that carries the hint for the next ask), so it is asked for again and
    then the stage stops, as for a reply that cannot be read. A reply that never had
    either is accepted as before, and nothing else is required: any other field that
    loses every sentence is left empty, like one the model did not write. `figures` is
    the figures list the prompt shows."""
    result = reply_json(body)
    findings_written = has_text(result.get("pain_points")) or has_text(result.get("growth_opportunity"))
    removed = Removed()
    for key in PROSE_KEYS:
        if key in result:
            result[key] = clean_prose(result[key], known, hours, removed, key)
    log_removed(logger, "analysis", removed)
    if findings_written and not (has_text(result.get("pain_points")) or has_text(result.get("growth_opportunity"))):
        numbers = list(dict.fromkeys(c for held in removed.causes.values() for c in held))
        raise NumberCheckFailed(
            "every pain point and the growth opportunity held a number nobody gave"
            + (f" ({', '.join(numbers)})" if numbers else ""),
            retry_hint("Sentences holding numbers that are not in the figures list were taken out of your "
                       "analysis, and no pain point or growth opportunity was left. Where they were, and the "
                       "numbers:", removed.causes, figures))
    result.setdefault("business_model", "Unknown")
    result.setdefault("pain_points", [])
    return result


def analyze_business(db: Session, request_id: int) -> dict:
    """Stage 1 of the consulting workflow: understand the business."""
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        # Only the client's own figures are known here: the model has been shown nothing else.
        known = known_for(req, leave_out=STALE_AT_START)
        hours = hours_for(req)
        figures = prompt_lines(known)
        prompt = render(
            "analyze.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            industry=req.industry or "unspecified",
            target_customers=req.target_customers or "unspecified",
            main_problem=req.main_problem or "unspecified",
            desired_outcome=req.desired_outcome or "unspecified",
            what_you_like=req.what_you_like or "none given",
            site_research=_format_site_research(req),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
            req.business_description,
            ),
            figures_block=figures,
        )
        # What the last unusable reply held that the check took out, told to the next ask.
        hints: list[str] = []
        result = ask_until_usable(
            lambda: provider.chat(settings.ANALYSIS_MODEL,
                                  [{"role": "user", "content": with_hint(prompt, hints)}]),
            remember_hint(lambda body: _analysis(body, known, hours, figures), hints),
            ledger(db, request_id, model=settings.ANALYSIS_MODEL, purpose="analyze"),
        )
    except Exception as exc:
        # No analysis was made, and nothing written in its place: every later
        # stage would build on a finding about a business nobody looked at.
        raise StageFailed("analyzing", exc) from exc

    req.business_analysis_json = json.dumps(result)
    db.commit()
    return result
