"""Discovery — the intake step that makes the numbers honest.

`/scope` agrees the question with the client and writes the list of facts we
need; `/interview` then asks, round by round, for what is still missing. The
answers flow into the decomposition stage, which is only allowed to compute
with numbers the owner gave.

When a model call fails, or comes back with nothing to show, there is no
stand-in. Stock questions would be a guess at their business, and an interview
that ended because a round failed would tell them "that's everything we need".
Both endpoints answer 503 in plain words instead, and tell the team.
"""

import json
import logging
import os
import re
from typing import NamedTuple

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import auth_client
from app.ai import provider
from app.config import settings
from app.database import get_db
from app.figures.model import tag_word
from app.pipeline import failure
from app.pipeline._shared import build_engagement_register, extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.discovery")

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

_ALLOWED_ENGAGEMENT_TYPES = {"full", "capability"}

#: What the client reads when a step stalls: the work we were doing, and what
#: of theirs is still on the page. Neither names a model, a stage or an error.
_STALL_COPY = {
    "scope": ("writing the questions we need to ask you", "What you wrote is still on this page."),
    "interview": ("preparing your next question", "Your answers so far are still on this page."),
}


def _stalled(kind: str, *, business: str | None, round: int | None, cause: BaseException | str) -> HTTPException:
    """The 503 for a step that could not be answered, once the team has been
    told. "We have been told" is in it only if the team was: the mail may be
    throttled behind one that went (true), or not sendable at all (not true).
    A mail that goes wrong cannot make this a 500."""
    try:
        told = failure.report_stall(kind, business=business, round=round, cause=str(cause) or type(cause).__name__)
    except Exception:
        logger.exception("could not tell the team that the %s stalled", kind)
        told = False
    work, kept = _STALL_COPY[kind]
    sentences = [f"Our side stalled while we were {work}."]
    if told:
        sentences.append("We have been told.")
    sentences.append(kept)
    return HTTPException(status_code=503, detail=" ".join(sentences))


def _sanitize(questions: list) -> list[dict]:
    """Keep only well-formed questions, clamped to the configured maximum."""
    cleaned = []
    for q in questions:
        if not isinstance(q, dict):
            continue
        label = str(q.get("label") or "").strip()
        if not label:
            continue
        cleaned.append(
            {
                "id": str(q.get("id") or f"q-{len(cleaned) + 1}").strip()[:60],
                "label": label[:200],
                "placeholder": str(q.get("placeholder") or "").strip()[:120],
                "why": str(q.get("why") or "").strip()[:200],
            }
        )
    return cleaned[: settings.MAX_DISCOVERY_QUESTIONS]


#: Intake fields the conversation can fill, and how to ask for each. The
#: front door now asks one question — what is going wrong — so everything
#: else that used to be a form field is collected here, as dialogue.
FILLABLE = {
    "business_name": "the business's name",
    "business_description": "what the business does or will do, how big it is or will be (staff, rooms, vans, seats), and its hours",
    "target_customers": "who their customers are",
    "industry": "what trade or sector they are in",
    "desired_outcome": "what fixing this would get them",
    "revenue_today": "how they make money — fees, packages, subscriptions, retainers",
}
# `needs_ai` is deliberately NOT here. It is an enum the engagement register
# compares against exactly ("no" suppresses every AI recommendation), and a
# conversational answer — "open to anything that works" — stored into it
# matches nothing and silently reads as the default. It is also no longer
# worth asking: `decide` reaches "your problem is not software" from the
# evidence now, which is a better answer than one the client pre-declared
# before anybody had looked at their business.
#: Without these two, `POST /api/requests` refuses the engagement — so the
#: interview is not allowed to decide it has enough while they are blank.
REQUIRED_FIELDS = ("business_name", "business_description")


# ── the brief and the fact list ──────────────────────────────────────────────
# A serious engagement agrees the question before it asks anything, and works
# from a data request list: every fact needed to answer it and to write plans
# a team could build from. The list is written per business — how many facts,
# and which, depend on what they asked — and bounded, never fixed.

FACTS_MIN, FACTS_MAX = 10, 30
#: How many facts one round of the interview may add, when an answer shows
#: the list missed something. The list can grow; it cannot run away.
FACTS_ADDED_PER_ROUND = 4
FACT_STATUSES = ("need", "got", "estimate", "file")

# The two facts the engagement cannot launch without (REQUIRED_FIELDS), worded
# for the stage. They are the only facts we write ourselves: every other fact
# on the list is the model's, from what this client said.
_FALLBACK_FACTS = {
    "operating": [
        ("business_name", "The business", "Name", "business_name"),
        ("what_you_do", "The business", "What you do, and how big", "business_description"),
    ],
    "opening": [
        ("business_name", "The business", "Name", "business_name"),
        ("what_you_do", "The business", "What it will do, and how big", "business_description"),
    ],
}


def _slug(text: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", (text or "").casefold())).strip("_")[:40]


def fallback_facts(stage: str | None) -> list[dict]:
    """The two facts the engagement cannot launch without, as open entries."""
    rows = _FALLBACK_FACTS["opening" if stage == "opening" else "operating"]
    return [{"key": k, "group": g, "label": lbl, "field": f, "status": "need", "value": ""}
            for k, g, lbl, f in rows]


_DIGITS = re.compile(r"\d+(?:[.,]\d+)*")


class _TheirWords:
    """Their words, read once, for checking the short values read off them (a fact,
    a case-file figure, its label). Pass their own words only, never our questions.

    `missing(value)` lists every number in the value the words do not hold, as
    written. A number must bind to a figure of theirs (`bind`, the rule every stage
    uses: a count is not backed by money, a price by a count, and words, ordinals and
    small numbers count); a clock time must be one they named; a date one they wrote,
    as a date or as a bare year ("we started 2019" backs "since 2019"). Digits the
    reader passes over as a label or an identifier ("Phase 2", "Q3") must still stand
    in their words outside a time or a date ("We open at 6pm" does not back "Phase 6"),
    so a value is held to every digit it shows."""

    def __init__(self, texts: list[str]) -> None:
        from app.figures.known import hours_in, known_for_texts
        from app.figures.read import mentions

        texts = [t for t in texts if isinstance(t, str)]
        self.known, self.hours = known_for_texts(texts), hours_in(texts)
        self.dates: set = set()
        self.digits: set[str] = set()
        for t in texts:
            found = mentions(t)
            self.dates |= {m.value for m in found if m.form == "date" or (
                m.form == "digit" and len(m.text) == 4 and 1900 <= m.value <= 2100)}
            clock = [(m.start, m.end) for m in found if m.form in ("time", "date")]
            self.digits |= {d.group().replace(",", "") for d in _DIGITS.finditer(t)
                            if not any(s <= d.start() and d.end() <= e for s, e in clock)}

    def missing(self, value: str) -> list[str]:
        from app.figures.bind import bind
        from app.figures.read import mentions

        found = mentions(value)
        if not found and not _DIGITS.search(value):
            return []
        bad = [u.text for u in bind(value, self.known, hours=self.hours).unresolved]
        bad += [m.text for m in found if m.form == "date" and m.value not in self.dates]
        covered = [(m.start, m.end) for m in found]
        for d in _DIGITS.finditer(value):
            inside = any(s <= d.start() and d.end() <= e for s, e in covered)
            if not inside and d.group().replace(",", "") not in self.digits:
                bad.append(d.group())
        return bad


def _not_in_their_words(value: str, texts: list[str]) -> list[str]:
    """`_TheirWords(texts).missing(value)`, for a single value."""
    return _TheirWords(texts).missing(value)


def _figures_in(value: str) -> bool:
    """Whether the value holds a number that is not a clock time or a date."""
    from app.figures.read import mentions

    return any(m.form not in ("time", "date") for m in mentions(value))


def _answers(ops_numbers: str | None) -> list[str]:
    """Their answers alone, never the questions we asked (`casefile.answers`, the
    same reading the case file makes)."""
    from app.figures.casefile import answers

    return answers(ops_numbers)


def _fact_value(value, quote, texts: list[str]) -> str:
    """A value read off their words, kept only when the words say it: the
    quote must be theirs, and every number in the value must be in the quote."""
    from app.pipeline import figures

    value = str(value or "").strip()[:60]
    quote = str(quote or "").strip()
    if not value or not quote or not figures.quoted(quote, texts):
        return ""
    if _not_in_their_words(value, [quote]):
        return ""
    return value


def shape_scope(raw: dict, main_problem: str) -> dict:
    """The brief and its fact list, bounded and checked. Pure.

    The list is what the model wrote and nothing else: a reply with few facts
    gives few, and is not topped up from a generic list. The two facts the
    engagement cannot launch without are always on it.
    """
    raw = raw if isinstance(raw, dict) else {}

    def text(v, limit: int) -> str:
        return re.sub(r"\s+", " ", str(v or "")).strip()[:limit]

    stage = text(raw.get("operating_stage"), 12).lower()
    stage = stage if stage in ("operating", "opening") else None
    kind = text(raw.get("engagement_type"), 12).lower()
    kind = kind if kind in ("capability", "full") else None

    question = text(raw.get("question"), 240)
    if len(question) < 15 or not question.endswith("?"):
        question = ""
    lets_raw = raw.get("lets") if isinstance(raw.get("lets"), dict) else {}
    lets = {k: text(lets_raw.get(k), 120) for k in ("know", "see", "have")}
    in_scope = [s for s in (text(x, 90) for x in (raw.get("in_scope") or [])[:5]) if s]
    out_scope = [s for s in (text(x, 90) for x in (raw.get("out_scope") or [])[:4]) if s]

    facts: list[dict] = []
    seen_keys: set[str] = set()
    seen_fields: set[str] = set()
    for f in raw.get("facts") or []:
        if not isinstance(f, dict) or len(facts) >= FACTS_MAX:
            continue
        label = text(f.get("label"), 60)
        key = _slug(str(f.get("key") or label))
        if not label or not key or key in seen_keys:
            continue
        field = text(f.get("field"), 30)
        field = field if field in FILLABLE and field not in seen_fields else ""
        value = _fact_value(f.get("value"), f.get("quote"), [main_problem])
        facts.append({"key": key, "group": text(f.get("group"), 30) or "The business",
                      "label": label, "field": field,
                      "status": "got" if value else "need", "value": value})
        seen_keys.add(key)
        if field:
            seen_fields.add(field)

    # The engagement cannot launch without these two, so they are on the list
    # whatever the model wrote — first, where a person would expect them.
    for base in reversed(fallback_facts(stage)):
        if base["field"] not in seen_fields:
            key = base["key"] if base["key"] not in seen_keys else f"{base['key']}_1"
            facts.insert(0, {**base, "key": key})
            seen_keys.add(key)
            seen_fields.add(base["field"])

    return {
        "question": question,
        "lets": lets,
        "in_scope": in_scope,
        "out_scope": out_scope,
        "facts": facts[:FACTS_MAX],
        "inferred": {"operating_stage": stage, "engagement_type": kind},
        # The page still reads this. A brief is the model's or there is none.
        "source": "ai",
    }


@router.post("/scope")
def scope(
    main_problem: str = Form(...),
    site_url: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The brief: the question we will answer, and the list of facts we need.

    Shown to them before the first question, the way a serious engagement
    agrees its problem statement before any analysis. When the call fails, the
    reply cannot be read, or it holds neither a question nor a fact, there is
    no brief to show: 503, with the team told. No generic list stands in.
    """
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    problem = (main_problem or "").strip()[:2000]
    if len(problem) < 10:
        raise HTTPException(status_code=422, detail="Tell us what you're trying to work out first")
    try:
        prompt = render("scope.j2", main_problem=problem, site_url=(site_url or "").strip()[:200],
                        facts_min=FACTS_MIN, facts_max=FACTS_MAX, fields=FILLABLE)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=3000)
        raw = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="scope", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="scope", success=False, error=str(exc)[:500])
        logger.warning("scope stalled: %s", str(exc)[:200])
        raise _stalled("scope", business=None, round=None, cause=exc) from exc
    brief = shape_scope(raw, problem)
    if not brief["question"] and len(brief["facts"]) <= len(REQUIRED_FIELDS):
        # No question, and nothing on the list but the two facts we always add:
        # the model read the problem and gave us nothing.
        logger.warning("scope stalled: the reply held no question and no facts")
        raise _stalled("scope", business=None, round=None, cause="the reply held no question and no facts")
    return brief


@router.post("/read-file")
async def read_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Read the figures out of a file dropped in during the interview, so the
    fact list fills from it at once instead of after launch. Every figure is
    checked against the cell it came from (`evidence.extract`); the same file
    is sent again with the engagement and read as evidence there."""
    from app.pipeline import evidence

    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    name = os.path.basename(file.filename or "upload")[:120]
    if not name.lower().endswith(evidence.SUPPORTED):
        raise HTTPException(status_code=422, detail=f"We can't read {name}. Send a spreadsheet, CSV or PDF.")
    data = await file.read(evidence.MAX_FILE_BYTES + 1)
    if len(data) > evidence.MAX_FILE_BYTES:
        raise HTTPException(status_code=422, detail=f"{name} is larger than 8 MB.")
    try:
        tables = evidence.read_tables(data, name)
    except evidence.UnreadableFile as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    found, _ = evidence.extract(db, None, tables, name) if tables else ([], 0)
    lines = []
    for c in found:
        value = c.get("value")
        shown = f"{value:,.0f}" if isinstance(value, (int, float)) and float(value).is_integer() else str(value)
        lines.append(f"{shown} {c.get('unit') or ''}".strip() + (f": {c['text']}" if c.get("text") else "") + f" (from {name})")
    return {"file": name, "figures": lines[:40]}


def parse_facts(raw: str | None) -> list[dict]:
    """The fact list as the client sends it back: bounded, statuses checked."""
    try:
        items = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    out, seen = [], set()
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict):
            continue
        key = _slug(str(f.get("key") or ""))
        label = str(f.get("label") or "").strip()[:60]
        if not key or not label or key in seen:
            continue
        status = str(f.get("status") or "need")
        out.append({"key": key, "group": str(f.get("group") or "").strip()[:30], "label": label,
                    "field": str(f.get("field") or "") if f.get("field") in FILLABLE else "",
                    "status": status if status in FACT_STATUSES else "need",
                    "value": str(f.get("value") or "").strip()[:60]})
        seen.add(key)
        if len(out) >= FACTS_MAX + FACTS_ADDED_PER_ROUND * 4:
            break
    return out


def shape_fact_updates(raw_updates, raw_new, facts: list[dict], texts: list[str]) -> tuple[list[dict], list[dict]]:
    """What their latest answers settled, and what the list was missing. Pure.

    A value is kept only when every number in it is one they gave — in an
    answer, a file, or what they first wrote (`texts`: their words only, never
    our questions). A fact they told us they don't know stays ours to estimate;
    an answer never overwrites that silently.
    """
    by_key = {f["key"]: f for f in facts}
    theirs = _TheirWords(texts)   # read once, not once per update
    updates = []
    for u in raw_updates if isinstance(raw_updates, list) else []:
        if not isinstance(u, dict):
            continue
        key = _slug(str(u.get("key") or ""))
        value = re.sub(r"\s+", " ", str(u.get("value") or "")).strip()[:60]
        if key not in by_key or not value or by_key[key]["status"] == "estimate":
            continue
        # The prompt marks what we lack as "NOT KNOWN YET"; a model that
        # echoes that back has not learned the fact, it has read our note.
        if re.search(r"\b(not known|unknown|not (yet )?(given|stated|provided)|n/?a)\b", value, re.I):
            continue
        if theirs.missing(value):
            continue
        updates.append({"key": key, "value": value})
    added = []
    room = max(0, min(FACTS_ADDED_PER_ROUND, FACTS_MAX + FACTS_ADDED_PER_ROUND * 4 - len(facts)))
    for n in raw_new if isinstance(raw_new, list) else []:
        if not isinstance(n, dict) or len(added) >= room:
            continue
        label = re.sub(r"\s+", " ", str(n.get("label") or "")).strip()[:60]
        key = _slug(str(n.get("key") or label))
        if not label or not key or key in by_key or any(a["key"] == key for a in added):
            continue
        added.append({"key": key, "group": str(n.get("group") or "More we need").strip()[:30],
                      "label": label, "field": "", "status": "need", "value": ""})
    return updates, added


def _key(label: str) -> str:
    """A question's wording, reduced to what it is actually asking."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (label or "").casefold())).strip()


#: Words that carry no subject matter. Removed before comparing questions, so
#: "What is the typical length" and "what's the typical length" reduce to the
#: same thing — the contraction alone defeated plain substring matching.
_FILLER = frozenset(
    "a an and are as at be by can could do does for from give got had has have how "
    "i in is it its many me much of on or our roughly s so such that the their them "
    "then there these they this to typically us was we what when where which who why "
    "will with would you your about average".split())


def _content(key: str) -> frozenset[str]:
    return frozenset(w for w in key.split() if w not in _FILLER and len(w) > 2)


def _repeats(key: str, seen: set[str]) -> bool:
    """Is this the same question again, dressed differently?

    Exact matching is not enough. A round-2 question that went unanswered came
    back in round 3 with a clause bolted on the front — "You mentioned turning
    away work and a waitlist. To understand capacity, what's the typical
    length of an appointment?" — word-for-word the earlier question apart from
    a contraction, and it sailed straight past an equality check.

    So a question whose subject matter is wholly contained in one already
    asked is a repeat. The four-word floor stops a genuinely short question
    ("How many rooms?") from being swallowed by any long one that happens to
    mention rooms.
    """
    if not key:
        return True
    tokens = _content(key)
    for prior in seen:
        if key == prior:
            return True
        prior_tokens = _content(prior)
        if not tokens or not prior_tokens:
            continue
        smaller, larger = sorted((tokens, prior_tokens), key=len)
        if len(smaller) >= 4 and smaller <= larger:
            return True
    return False


@router.post("/interview")
def interview(
    # Optional: the front door asks what is going wrong and nothing else, so on
    # the first round the business does not have a name yet. Finding that out
    # is this endpoint's job.
    business_name: str | None = Form(None),
    business_description: str | None = Form(None),
    industry: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    needs_ai: str | None = Form(None),
    main_problem: str | None = Form(None),
    desired_outcome: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    asked: str | None = Form(None),
    known: str | None = Form(None),
    round: int = Form(1),
    facts: str | None = Form(None),
    file_facts: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """The next questions worth asking — or none, which ends the interview.

    With a fact list (the brief's data request list), the interview works
    through it: each round reads what their answers settled, asks about what
    is still needed, and ends only when nothing is — every fact gathered, or
    marked as one they don't know and we will estimate. That is the point of
    the list: we keep asking until we have what the plans need, and the
    owner never has to go and fetch anything.

    Replaces the one-shot tailored set with a loop that reads what they have
    already answered. The static set asked four questions whatever you said;
    this one can follow "340 visits a month at $85" with "what caps that
    number", which is the question that decides whether their problem is
    demand or capacity.

    `done` is authoritative and the client stops on it. It goes true when the
    model says it has enough, when the round cap is reached, or when a later
    round has nothing left worth asking.

    A round that FAILS is not "nothing left to ask": a failed call, a reply
    that cannot be read, or a first round with no usable question is a 503,
    and the team is told. The client is neither handed stock questions nor
    told that is everything we need, and their answers stay on their page.
    """
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")

    operating = operating_stage != "opening"

    round = max(1, min(int(round or 1), settings.INTERVIEW_MAX_ROUNDS))
    answered = _format_numbers(ops_numbers)

    answered_ids, answered_labels = set(), set()
    try:
        for p in json.loads(ops_numbers or "[]"):
            if isinstance(p, dict):
                answered_ids.add(str(p.get("id") or ""))
                answered_labels.add(str(p.get("question") or "").strip().casefold())
    except (TypeError, ValueError):
        pass

    # Questions they SKIPPED are the ones that get re-asked: the model sees
    # only the answers, so an unanswered question is invisible to it and comes
    # back every round under a fresh id. Filtering by id alone never caught it
    # — one run asked for the receptionist's hours three times in three
    # different wordings. The model is told what it already asked instead.
    skipped = []
    try:
        for label in json.loads(asked or "[]"):
            text = str(label).strip()
            if text and text.casefold() not in answered_labels:
                skipped.append(text)
    except (TypeError, ValueError):
        pass

    # What the conversation has not learned about them yet. Sent by the
    # client so one builder decides it, rather than the prompt guessing from
    # whichever fields happened to be passed as arguments.
    filled = {}
    try:
        raw_known = json.loads(known or "{}")
        if isinstance(raw_known, dict):
            filled = {k: str(v or "").strip() for k, v in raw_known.items()}
    except (TypeError, ValueError):
        pass
    missing = {k: v for k, v in FILLABLE.items() if not filled.get(k)}

    fact_list = parse_facts(facts)
    try:
        from_files = [str(x).strip()[:200] for x in json.loads(file_facts or "[]") if str(x).strip()][:40]
    except (TypeError, ValueError):
        from_files = []
    # A question that fills a form field leaves its answer in that field, not in
    # the fact list, so the fact still read as needed and came back as a fresh
    # question ("What's the name?" twice on the first real run).
    answered_fields = {f["key"]: filled[f["field"]] for f in fact_list
                       if f["status"] == "need" and f["field"] and filled.get(f["field"])}
    fact_lines = "\n".join(
        f"- {f['key']} [{f['group']}] {f['label']}: "
        + (f"ANSWERED, in their words: {answered_fields[f['key']][:200]} — do not ask again; return it in \"updates\" "
           "as the value alone (a name alone, not the sentence it came in)"
           if f["key"] in answered_fields else
           {"got": f"GOT — {f['value']}", "file": f"GOT FROM THEIR FILE — {f['value']}",
            "estimate": "THEY DON'T KNOW — we will estimate it; do not ask again"}.get(f["status"], "STILL NEEDED"))
        for f in fact_list)

    business = filled.get("business_name") or business_name or None
    try:
        prompt = render(
            "interview.j2",
            business_name=business or "",
            business_description=filled.get("business_description") or business_description or "",
            industry=filled.get("industry") or industry or "unspecified",
            stage="not launched yet — this is a plan" if not operating else "already operating",
            main_problem=main_problem,
            desired_outcome=desired_outcome,
            engagement_register=build_engagement_register(
                engagement_type if engagement_type in _ALLOWED_ENGAGEMENT_TYPES else None,
                needs_ai, main_problem, desired_outcome,
            ),
            answered=answered,
            skipped="\n".join(f"- {s}" for s in skipped[:12]),
            missing="\n".join(f"- {k}: {v}" for k, v in missing.items()),
            round=round,
            max_rounds=settings.INTERVIEW_MAX_ROUNDS,
            max_questions=settings.INTERVIEW_MAX_PER_ROUND,
            facts=fact_lines,
            file_facts="\n".join(f"- {x}" for x in from_files),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=2200)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose=f"interview:{round}", usage=body.get("usage"), success=True)
    except Exception as exc:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose=f"interview:{round}", success=False, error=str(exc)[:500])
        logger.warning("interview round %s stalled: %s", round, exc)
        raise _stalled("interview", business=business, round=round, cause=exc) from exc

    # Belt and braces behind the prompt: an id or a wording already put to
    # them cannot come back, whatever the model returns.
    seen = {_key(s) for s in skipped} | {_key(s) for s in answered_labels}
    questions = []
    for q in _sanitize(result.get("questions") or []):
        if q["id"] in answered_ids or _repeats(_key(q["label"]), seen):
            continue
        questions.append(q)
        seen.add(_key(q["label"]))
        if len(questions) >= settings.INTERVIEW_MAX_PER_ROUND:
            break

    if round == 1 and not questions:
        # Nothing to ask before anything has been asked is not a consultant
        # who has enough — it is a call that produced nothing.
        logger.warning("interview round 1 stalled: no usable question in the reply")
        raise _stalled("interview", business=business, round=round,
                       cause="round 1 came back with no usable question")

    # Which intake field each question fills, where it fills one. Anything
    # not in FILLABLE is dropped rather than trusted — a `field` we do not
    # recognise would write an arbitrary key into the client's form.
    by_id = {q.get("id"): q for q in (result.get("questions") or []) if isinstance(q, dict)}
    for q in questions:
        field = str((by_id.get(q["id"]) or {}).get("field") or "").strip()
        q["field"] = field if field in FILLABLE else ""
    questions = [q for q in questions if not (q["field"] and filled.get(q["field"]))]

    # What their answers settled, and what the list turned out to be missing.
    # Checked in their words alone: a number only our question holds is not theirs.
    texts = [main_problem or "", *_answers(ops_numbers), *from_files, *[v for v in filled.values() if v]]
    updates, added = shape_fact_updates(result.get("updates"), result.get("new_facts"), fact_list, texts)
    have = {u["key"] for u in updates}
    updates += [{"key": key, "value": re.sub(r"\s+", " ", words).strip()[:60]}
                for key, words in answered_fields.items() if key not in have]
    keys = {f["key"] for f in fact_list} | {a["key"] for a in added}
    for q in questions:
        src = by_id.get(q["id"]) or {}
        q["fills"] = [k for k in (_slug(str(x)) for x in (src.get("fills") or [])[:4]) if k in keys]
        q["options"] = [o for o in (re.sub(r"\s+", " ", str(x)).strip()[:40] for x in (src.get("options") or [])[:5]) if o]

    def choice(key: str, allowed: tuple[str, ...]) -> str | None:
        value = str(result.get(key) or "").strip().lower()
        return value if value in allowed else None

    # An engagement still missing a name or a description cannot be launched
    # at all, so the interview does not get to call itself finished while one
    # is blank — whatever it thinks about having enough numbers.
    blocked = [f for f in REQUIRED_FIELDS if not filled.get(f)]
    if fact_list:
        # With a list, the list decides: done when nothing on it is still
        # needed. The model saying "enough" is not enough while facts remain —
        # but a model with nothing left worth asking, or the round cap, ends
        # it, and whatever is still open becomes ours to estimate and label.
        settled = {u["key"] for u in updates}
        still = [f["key"] for f in fact_list if f["status"] == "need" and f["key"] not in settled]
        still += [a["key"] for a in added]
        done = not still or not questions or round >= settings.INTERVIEW_MAX_ROUNDS
    else:
        still = []
        done = (bool(result.get("enough")) or not questions
                or round >= settings.INTERVIEW_MAX_ROUNDS)
    if blocked and round < settings.INTERVIEW_MAX_ROUNDS:
        done = False

    return {"questions": [] if done and not blocked else questions, "done": done, "source": "ai",
            "because": str(result.get("because") or "")[:200],
            "inferred": {"engagement_type": choice("engagement_type", ("capability", "full")),
                         "operating_stage": choice("operating_stage", ("operating", "opening"))},
            "still_needed": blocked,
            "updates": updates, "new_facts": added,
            # Open when the interview ends: ours to estimate, labelled as ours.
            "estimate_rest": still if done else []}


CASEFILE_MAX_FIGURES = 8


#: The longest question quoted back to them in a figure's plain source.
ORIGIN_QUESTION_MAX = 100


def _origin(kind: str, name: str = "") -> str:
    """Where a figure came from, in the words they would use. `kind` is what sort
    of line it was quoted from, known by the code that built the line (see
    casefile_lines), never read back out of an id the page sent: "problem", "field"
    (`name` is the form field) or "answer" (`name` is the question)."""
    if kind == "problem":
        return "From what you told us about the problem"
    if kind == "field":
        return f"From what you wrote about your {name.replace('_', ' ')}"
    if kind == "answer":
        question = " ".join(name.split())
        if not question:
            return "From one of your answers"
        if len(question) > ORIGIN_QUESTION_MAX:
            question = question[:ORIGIN_QUESTION_MAX].rstrip() + "\u2026"
        return f'From your answer to "{question}"'
    return "From what you told us"


class CaseFileLines(NamedTuple):
    """What they have said, each line under an id. `sources` are the lines the
    model reads and a figure has to be in; an interview line is "<our question> -
    <their answer>". `theirs` is the part of each line that is their own words (the
    answer alone for an interview line), the only part a figure may be quoted
    from, since a number in our question is not theirs. `origins` say where each
    line came from in plain words."""
    sources: dict[str, str]
    theirs: dict[str, str]
    origins: dict[str, str]


def casefile_lines(main_problem: str | None, ops_numbers: str | None,
                   known: str | None) -> CaseFileLines:
    """Everything they have said, by id."""
    sources: dict[str, str] = {}
    theirs: dict[str, str] = {}
    origins: dict[str, str] = {}
    if (main_problem or "").strip():
        sources["main_problem"] = theirs["main_problem"] = main_problem.strip()[:2000]
        origins["main_problem"] = _origin("problem")
    try:
        for p in json.loads(ops_numbers or "[]"):
            if isinstance(p, dict) and str(p.get("answer") or "").strip():
                qid = str(p.get("id") or f"q{len(sources)}")[:40]
                question = str(p.get("question") or "").strip()[:200]
                answer = str(p["answer"]).strip()[:600]
                sources[qid] = f"{question} — {answer}"
                theirs[qid] = answer
                origins[qid] = _origin("answer", question)
    except (TypeError, ValueError):
        pass
    try:
        raw_known = json.loads(known or "{}")
        if isinstance(raw_known, dict):
            for k, v in raw_known.items():
                if k in FILLABLE and str(v or "").strip():
                    sources[f"field:{k}"] = theirs[f"field:{k}"] = str(v).strip()[:1000]
                    origins[f"field:{k}"] = _origin("field", k)
    except (TypeError, ValueError):
        pass
    return CaseFileLines(sources, theirs, origins)


def casefile_sources(main_problem: str | None, ops_numbers: str | None,
                     known: str | None) -> dict[str, str]:
    """Everything they have said, by id — the lines a figure has to be in."""
    return casefile_lines(main_problem, ops_numbers, known).sources


def shape_casefile(raw: dict, sources: dict[str, str], playback: bool,
                   derived: list | None = None,
                   origins: dict[str, str] | None = None,
                   theirs: dict[str, str] | None = None) -> dict:
    """Keep only what is really in their words. Pure. `derived` are the
    capacity figures computed from those words (`known.capacity_figures`), which
    the summary may use.

    Every figure kept was quoted from their own words, so each says `kind:
    "theirs"` and carries `source`, where it came from in plain words (from
    `origins`, which `casefile_lines` builds); `source_id` is the id of the line.
    `theirs` is the part of each line that is their own words (an interview line
    also holds our question, and a number only our question has is not theirs); a
    line with no entry there is taken to be theirs throughout."""
    from app.figures.bind import bind, clean_sentences
    from app.figures.known import hours_in, known_for_texts, with_extra
    from app.pipeline import figures

    out: dict = {"figures": []}
    lines: dict[str, _TheirWords] = {}
    seen = set()
    for f in (raw.get("figures") or []) if isinstance(raw, dict) else []:
        if not isinstance(f, dict):
            continue
        src = str(f.get("source") or "")
        text = (theirs or {}).get(src) or sources.get(src)
        token = str(f.get("token") or "").strip()
        value = str(f.get("value") or "").strip()[:24]
        label = str(f.get("label") or "").strip()[:60]
        if not text or not token or not value or not figures.quoted(token, [text]):
            continue
        # A time on its own ("6pm — classes") is not a figure about the
        # business; it filled half the case file with clock faces.
        if not _figures_in(value):
            continue
        # every number in the value is in the words it was quoted from, a time one they named there
        if _not_in_their_words(value, [token]):
            continue
        reader = lines.get(src) or lines.setdefault(src, _TheirWords([text]))   # each line read once
        if reader.missing(label):
            continue
        key = (src, value.casefold())
        if key in seen:
            continue
        seen.add(key)
        # `display` and `tag` are what the page shows beside it, as on a payload's figures map
        out["figures"].append({"kind": "theirs", "tag": tag_word("theirs"), "display": value,
                               "source": (origins or {}).get(src) or _origin(""),
                               "source_id": src, "token": token, "value": value, "label": label})
        if len(out["figures"]) >= CASEFILE_MAX_FIGURES:
            break
    if playback and isinstance(raw, dict):
        # their words only: a number only our question holds is not theirs
        their_text = [(theirs or {}).get(k) or v for k, v in sources.items()]
        known, hours = known_for_texts(their_text), hours_in(their_text)
        summary = str(raw.get("summary") or "").strip()[:600]
        # the summary is bound to their figures and the week worked out from them;
        # a sentence holding a number that names none is dropped
        out["summary"] = (clean_sentences(summary, with_extra(known, derived or []), hours=hours)[0].strip()
                          if summary else "")
        words = str(raw.get("their_words") or "").strip()[:400]
        out["their_words"] = words if words and figures.quoted(words, their_text) else ""
        fix = raw.get("their_fix")
        fix = str(fix).strip().rstrip(".")[:80] if fix else ""
        # their fix is in their words: what our question suggested ("a 3-month app") is not
        bound = bind(fix, known, hours=hours) if fix else None
        out["their_fix"] = bound.text if bound and not bound.unresolved else None
    return out


@router.post("/casefile")
def casefile(
    main_problem: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    known: str | None = Form(None),
    operating_stage: str | None = Form(None),
    playback: bool = Form(False),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """What they have told us so far, as figures — and their week, if it can
    be drawn yet. Called as they answer, so the case file on screen fills in
    while they talk; and once more before the diagnosis, to play it back.

    Two fast calls, in parallel. Every figure is checked against the line it
    was quoted from, and the week against their words (`capacity.shape`).
    Fails open to an empty file: this is a courtesy on screen, and a failure
    here must never stop the conversation.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.pipeline import capacity

    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    sources, theirs, origins = casefile_lines(main_problem, ops_numbers, known)
    if not sources:
        return {"figures": [], "capacity": None}

    def read_figures():
        prompt = render("casefile.j2", sources="\n".join(f"[{k}] {v}" for k, v in sources.items()),
                        max_figures=CASEFILE_MAX_FIGURES, playback=playback)
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}],
                             max_tokens=1600 if playback else 1100)
        return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage")

    stage = "not launched yet — this is a plan" if operating_stage == "opening" else "already operating"
    with ThreadPoolExecutor(max_workers=2) as pool:
        fig_future = pool.submit(read_figures)
        cap_earlier: list = []
        # the week is checked in their words; our questions are only context for the reading
        cap_future = pool.submit(capacity.read, list(theirs.values()), stage, cap_earlier,
                                 context=list(sources.values()))
        try:
            raw, usage = fig_future.result()
            log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                      purpose="casefile", usage=usage, success=True)
        except Exception as exc:
            log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                      purpose="casefile", success=False, error=str(exc)[:500])
            logger.warning("casefile failed open: %s", str(exc)[:200])
            raw = {}
        picture, cap_usage, cap_error = cap_future.result()
    for unread_usage, unread_error in cap_earlier:  # replies that could not be read
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="casefile:capacity", usage=unread_usage, success=False, error=unread_error)
    if cap_usage is not None or cap_error is not None:
        log_usage(db, None, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="casefile:capacity", usage=cap_usage, success=cap_error is None, error=cap_error)

    from app.figures.known import capacity_figures

    out = shape_casefile(raw, sources, playback, capacity_figures(picture), origins, theirs)
    out["capacity"] = picture
    return out


def _format_numbers(raw: str | None) -> str:
    """The discovery answers as prompt lines — same tolerance as the intake:
    malformed client JSON reads as 'none given', never a 500."""
    if not raw:
        return "none given"
    try:
        pairs = json.loads(raw)
    except ValueError:
        return "none given"
    if not isinstance(pairs, list):
        return "none given"
    lines = [
        f"- {p.get('question')}: {p.get('answer')}"
        for p in pairs
        if isinstance(p, dict) and p.get("question") and p.get("answer")
    ]
    return "\n".join(lines) or "none given"


def _format_conversation(raw: str | None) -> str:
    if not raw:
        return "(empty)"
    try:
        messages = json.loads(raw)
    except ValueError:
        return "(empty)"
    if not isinstance(messages, list):
        return "(empty)"
    lines = []
    for m in messages[-10:]:
        if not (isinstance(m, dict) and m.get("content")):
            continue
        who = "CLIENT" if m.get("role") == "user" else "YOU"
        lines.append(f"{who}: {str(m['content'])[:600]}")
    return "\n".join(lines) or "(empty)"


@router.post("/brief")
def discovery_brief(
    business_name: str = Form(...),
    business_description: str = Form(...),
    industry: str | None = Form(None),
    target_customers: str | None = Form(None),
    main_problem: str | None = Form(None),
    desired_outcome: str | None = Form(None),
    operating_stage: str | None = Form(None),
    engagement_type: str | None = Form(None),
    needs_ai: str | None = Form(None),
    ops_numbers: str | None = Form(None),
    messages: str | None = Form(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    if auth_client.resolve_user(authorization) is None:
        raise HTTPException(status_code=401, detail="Sign in to start your engagement")
    """The pre-launch briefing chat: the consultant plays back the brief and
    absorbs corrections. One fast call per turn. Fails open with ok=false —
    the frontend then launches directly; this chat may never block a run."""
    try:
        prompt = render(
            "brief.j2",
            engagement_register=build_engagement_register(
                engagement_type if engagement_type in _ALLOWED_ENGAGEMENT_TYPES else None,
                needs_ai, main_problem, desired_outcome,
            ),
            business_name=business_name,
            business_description=business_description,
            industry=industry or "unspecified",
            target_customers=target_customers or "unspecified",
            main_problem=main_problem or "unspecified",
            desired_outcome=desired_outcome or "unspecified",
            operating_stage="not launched yet — this is a plan" if operating_stage == "opening" else "already operating",
            owner_numbers=_format_numbers(ops_numbers),
            conversation=_format_conversation(messages),
        )
        body = provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}], max_tokens=900)
        result = extract_json_from_text(body["choices"][0]["message"]["content"])
        reply = str(result.get("reply") or "").strip()
        if not reply:
            raise ValueError("brief turn had no reply")
        addendum = result.get("brief_addendum")
        addendum = str(addendum).strip() if addendum else None
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="brief",
            usage=body.get("usage"), success=True,
        )
        return {"ok": True, "reply": reply[:2500], "brief_addendum": addendum[:2000] if addendum else None}
    except Exception as exc:
        log_usage(
            db, None,
            provider="openrouter", model=settings.ANALYSIS_MODEL, purpose="brief",
            success=False, error=str(exc)[:500],
        )
        logger.warning("brief turn failed open: %s", exc)
        return {"ok": False}
