"""Competing explanations, tested against the client's own numbers, then attacked.

This stage exists because `analyze` could only ever produce one story, and
`analyze.j2` asks for "the single biggest growth opportunity an AI employee
could unlock" — the conclusion was inside the question. A pipeline that starts
there can do nothing but agree with itself, and with the owner.

So: several causes that genuinely compete, each tested against the figures the
client actually gave, and then the survivor handed to two skeptics whose brief
is to kill it. What reaches the client is what survived, carrying its own
weaknesses rather than hiding them.

A diagnosis that cannot be made stops the run (`StageFailed("diagnosing")`):
a failed model call, an answer with too few usable explanations, a round in
which not one explanation could be tested, or one in which the only
explanation left standing is one whose test never ran. The recommendation is written to
answer this stage's finding, and `analyze`'s single story is not a stand-in
for it. What may fall short is only what is reported as having fallen short:
one test that crashed on our side stays in the diagnosis marked `not_tested`,
and a skeptic that never ran is recorded as such.

Every sentence the model writes for the client (the statements, the tests' reasons
and what they would need, the reviewers' objections) is checked against the figures
the request knows: a sentence holding a number nobody owns is dropped, its
neighbours kept. An explanation left with no statement is unusable like one that
never had one, so a reply made of them is asked for again, and then stops the run.
The claim ids a statement cites and the thinking trail's own counts are not prose.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures.known import hours_for, known_for, prompt_lines
from app.models import Request
from app.pipeline._shared import (
    ask_until_usable, briefing_corrections, build_engagement_register, extract_json_from_text, ledger,
    log_usage, reply_json,
)
from app.pipeline import evidence
from app.pipeline.analyze import (Checked, NumberCheckFailed, Removed, check_text, cut_prose, log_removed,
                                   remember_hint, retry_hint, with_hint)
from app.pipeline.failure import StageFailed
from app.pipeline.registry import client_fact_claims
from app.templating import render

logger = logging.getLogger("consultant.diagnose")

MIN_HYPOTHESES = 2
MAX_HYPOTHESES = 5

#: What a row can hold at the moment `diagnose` runs that is not about this run: the
#: answer, the registry and the roadmap are written after it. (The capacity picture
#: was read just before, and is kept: a hypothesis may cite it.)
STALE_AT_DIAGNOSIS = frozenset({"answer", "registry", "roadmap"})

#: How much of a test's or a reviewer's reason, and of their other notes, is kept.
BECAUSE_CHARS = 400
NOTE_CHARS = 300

#: Checks the text of one model-written field (`clean(text, where="")`): binds its numbers
#: to the figures the request knows and takes out each sentence that holds one nobody
#: owns. `where` names the field, for the log and the hint. `Check` gives the whole
#: result (what is left, how many sentences went, and the numbers that caused it).
Clean = Callable[..., str]
Check = Callable[..., Checked]

#: The two angles the skeptics attack from. Distinct on purpose: two
#: reviewers given the same brief agree with each other, which reads as
#: corroboration and is not.
CHALLENGE_ANGLES = (
    ("alternative",
     "Find a DIFFERENT cause that fits the same evidence at least as well. You are not "
     "arguing the diagnosis is impossible — you are showing it was not the only thing that "
     "explains these numbers, and therefore was not established."),
    ("confirmation",
     "Check whether this conclusion was reached because the OWNER said so. Owners describe "
     "symptoms accurately and causes badly. If the reasoning traces back to the owner's own "
     "words rather than to their numbers, this diagnosis has confirmed a belief rather than "
     "tested one."),
)


def _evidence_lines(req: Request) -> tuple[str, list[dict]]:
    """Their figures as citable claims — what they typed AND what they sent.

    The same `client_fact_claims` the registry and the integrity layer use, so
    a claim id in a diagnosis means the same thing it means in the blueprint —
    and a hypothesis resting on a number the client never gave is caught by
    machinery that already exists.

    File-derived figures (CE-xx) are marked as such in the line the model
    reads. They are stronger evidence than a typed answer: nobody rounds a
    spreadsheet cell from memory, and each one was checked against the cell it
    was cited from before it got here.
    """
    try:
        ops = json.loads(req.ops_numbers_json) if req.ops_numbers_json else []
    except (TypeError, ValueError):
        ops = []
    # De-duplicated. The launch now uses the client's opening paragraph as the
    # description when the conversation never asked for one, so the same text
    # arrives as both — and extracting figures from it twice would give every
    # number two ids, which a hypothesis could then cite as two independent
    # pieces of evidence for the same thing.
    free = list(dict.fromkeys(
        t.strip() for t in (req.business_description, req.main_problem, req.desired_outcome)
        if t and t.strip()))
    # The CAP- figures are their own multiplied out (12 reformers x 6 classes
    # x 6 days), computed in code with the working attached — so "you are at
    # your ceiling" can rest on a number instead of on the tester doing the
    # multiplication in its head, which it often did not.
    from app.figures import sums as _sums
    from app.pipeline import capacity as _capacity

    claims = (client_fact_claims(ops, free) + evidence.load(req) + _capacity.as_claims(_capacity.load(req))
              + _sums.as_claims(req))
    if not claims:
        return "none given — they have provided no figures at all", []
    lines = []
    for c in claims:
        basis = f"/{c['time_basis']}" if c.get("time_basis") not in (None, "", "n/a") else ""
        origin = (" [from their own file]" if c.get("origin") == "file"
                  else " [computed from their figures]" if c.get("provenance") == "machine_computed" else "")
        lines.append(f"[{c['id']}] {c['value']} {c['unit']}{basis} — "
                     f"\"{c['text']}\" ({c['source']}){origin}")
    return "\n".join(lines), claims


#: `provider.chat` defaults to 2000, which is right for a stage that returns a
#: handful of fields. Five hypotheses carrying two prose fields each do not fit
#: in it — and on a reasoning model the thinking is spent from the same budget,
#: so the first real run returned JSON that stopped mid-sentence. A truncated
#: response costs exactly as much as a complete one and yields nothing.
DIAGNOSE_TOKENS = 8000
TEST_TOKENS = 3000


def _call(prompt: str, model: str, max_tokens: int) -> tuple[dict, dict | None]:
    """One model call, with NO database touched.

    The session is not thread-safe, so nothing inside a worker may write to
    it: usage comes back with the result and is logged after the pool joins,
    the same way `qa_experts` does it. Logging from the threads left the
    session in a rolled-back state, every parallel call after the first one
    failed, and the stage reported its skeptics as never having run — which
    reads, downstream, exactly like a diagnosis nobody could challenge.
    """
    body = provider.chat(model, [{"role": "user", "content": prompt}], max_tokens=max_tokens)
    return extract_json_from_text(body["choices"][0]["message"]["content"]), body.get("usage")


def _ask(prompt: str, model: str, max_tokens: int, use, record, hints: list[str] | None = None):
    """One call whose reply must be usable, asked again when it is not (see
    `ask_until_usable`). Touches no session itself: `record` is told of each
    call, so it can run on a worker thread. When `use` raises `NumberCheckFailed`,
    its hint is added to the prompt of the next ask (`hints` is where it is kept)."""
    hints = [] if hints is None else hints
    return ask_until_usable(
        lambda: provider.chat(model, [{"role": "user", "content": with_hint(prompt, hints)}],
                              max_tokens=max_tokens),
        remember_hint(lambda body: use(reply_json(body)), hints),
        record,
    )


def _enough_explanations(known_ids: set[str], check: Check, figures: str):
    """The `use` for the diagnostician's reply: its usable explanations, or a
    ValueError when there are fewer than `MIN_HYPOTHESES`. One explanation is
    not a diagnosis, it is an opinion, and dressing a single guess up as a
    tested conclusion is the thing this stage exists to prevent.

    An explanation whose every sentence held a number nobody owns has no
    statement left and is not usable, so a reply made of them is asked for again,
    and when that is why there are too few the error is a `NumberCheckFailed`: its
    hint names those explanations by id and the numbers in each (never their
    sentences), and `figures` is the figures list the prompt shows."""

    def use(raw: dict) -> list[dict]:
        hypotheses, emptied = _sanitize_hypotheses(raw.get("hypotheses"), known_ids, check)
        if len(hypotheses) < MIN_HYPOTHESES:
            # the cause is recorded (failure_json, the team's email): say when it was the number check
            by_check = (f"; {len(emptied)} had no statement left once the sentences holding a number "
                        f"nobody gave were taken out" if emptied else "")
            message = (f"the model gave {len(hypotheses)} usable explanation{'' if len(hypotheses) == 1 else 's'}, "
                       f"and a diagnosis needs {MIN_HYPOTHESES}{by_check}")
            if not emptied:
                raise ValueError(message)
            causes: dict[str, list[str]] = {}
            for hid, numbers in emptied:
                held = causes.setdefault(hid, [])
                held.extend(n for n in numbers if n not in held)
            raise NumberCheckFailed(message, retry_hint(
                f"A diagnosis needs at least {MIN_HYPOTHESES} explanations, and these lost their statement "
                "because every sentence of it held a number that is not in the figures list. The explanation "
                "(by the id you gave it) and the numbers:", causes, figures))
        return hypotheses

    return use


def _sanitize_hypotheses(raw: list, known_ids: set[str],
                         check: Check) -> tuple[list[dict], list[tuple[str, list[str]]]]:
    """Keep the shape honest and drop citations to claims that do not exist.

    A fabricated id is worse than no id: downstream it reads exactly like a
    real one, and the client is shown a conclusion resting on a number they
    never gave. The same goes for a number in the prose: each text is checked
    (`check`) and only then cut to the length stored, at a word or sentence end,
    so a cut can never leave a piece of a figure that matches one the client
    gave. An explanation with no statement left is dropped like one that had
    none. Returns the explanations kept, and (id, the numbers that caused it) for
    each one the number check emptied.
    """
    out, emptied = [], []
    for i, h in enumerate(raw or [], start=1):
        if not isinstance(h, dict) or not str(h.get("statement") or "").strip():
            continue
        hid = str(h.get("id") or f"H{i}")[:8]
        checked = check(str(h["statement"]), f"{hid} statement")
        statement = cut_prose(checked.text, 400)
        if not statement.strip():
            if checked.sentences:
                emptied.append((hid, checked.causes))
            continue
        cites = [c for c in (h.get("cites") or []) if isinstance(c, str) and c in known_ids]
        out.append({
            "id": hid,
            "statement": statement,
            "area": str(h.get("area") or "other")[:40],
            "software_can_fix": bool(h.get("software_can_fix")),
            "would_support": cut_prose(check(str(h.get("would_support") or ""), f"{hid} would_support").text, 300),
            "would_refute": cut_prose(check(str(h.get("would_refute") or ""), f"{hid} would_refute").text, 300),
            "cites": cites,
            "from_owner": bool(h.get("from_owner")),
        })
        if len(out) >= MAX_HYPOTHESES:
            break
    return out, emptied


def _rank(h: dict) -> tuple:
    """Which surviving hypothesis leads.

    Supported beats untestable beats refuted. The owner's own stated problem
    is the tie-breaker LOSER, not winner: when two explanations are equally
    supported and one is simply what the owner already believed, leading with
    it is the confirmation this stage exists to prevent.

    Citations only count for a SUPPORTED verdict. On an untestable one they
    are figures the tester looked at and could not conclude from, and counting
    them ranked "we checked eight numbers and still cannot say" above "we
    checked four and still cannot say" — which is not more established, just
    wordier. A live run showed the cost: every verdict came back untestable,
    the owner's own belief led on citation count alone, and the confirmation
    reviewer then killed it for being the owner's own belief.

    A test that never ran (`not_tested`, a crash on our side) sits between
    untestable and refuted: nothing ruled it out, but nobody looked, so it does
    not lead over an explanation that was looked at and could not be settled.
    """
    order = {"supported": 2, "untestable": 1, "refuted": 0}
    test = h.get("test") or {}
    rank = 0.5 if test.get("not_tested") else order.get(test.get("verdict"), 0)
    evidence = len(test.get("cites") or []) if test.get("verdict") == "supported" else 0
    return (rank, not h.get("from_owner"), evidence)


def _stopped(db: Session, request_id: int, cause: str | BaseException) -> StageFailed:
    """The stop for a diagnosis that could not be made, for the caller to raise
    from its own thread once every call it paid for is on the ledger.

    The diagnosis an earlier pass left on the row is cleared first: it was made
    for a different reading of the business and must not stand in for this one.
    """
    persist(db, request_id, None)
    return StageFailed("diagnosing", cause)


def diagnose(db: Session, request_id: int, analysis: dict) -> dict:
    """Returns the diagnosis. Raises `StageFailed("diagnosing")` when it could
    not be made: the model call failed or came back unreadable, fewer than
    `MIN_HYPOTHESES` explanations were usable, or none could be tested.

    Up to two passes. When both skeptics kill the leading explanation, their
    objections go back to the diagnostician and it thinks again — a killed
    conclusion that reaches the client anyway is the same failure as never
    having challenged it, and the first real run did exactly that: two
    reviewers refuted the leading hypothesis and the recommendation opened by
    asserting it. So a second pass that cannot be made stops the run too: the
    reading it was meant to replace was refuted.

    The second pass is final. If it is killed too, that is reported honestly
    rather than retried until something survives — a hypothesis that only
    survives because we stopped attacking it has not survived.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    evidence, claims = _evidence_lines(req)
    known_ids = {c["id"] for c in claims}
    # Every sentence the model writes for the client is checked against the figures
    # the request knows: theirs, and their week as it was just worked out.
    try:
        known = known_for(req, leave_out=STALE_AT_DIAGNOSIS)
        hours = hours_for(req)
    except Exception as exc:
        # no check, no diagnosis: stopped like any other failure, and the old one cleared
        logger.warning("the figures a diagnosis is checked against could not be read: %s", str(exc)[:200])
        raise _stopped(db, request_id, exc) from exc
    removed = Removed()

    def check(text: str, where: str = "") -> Checked:
        checked = check_text(text, known, hours)
        removed.add(where, checked.sentences, checked.causes)
        return checked

    def clean(text: str, where: str = "") -> str:
        return check(text, where).text

    def report() -> None:
        """Say what the check took out so far, then forget it: the retry and the failure included."""
        log_removed(logger, "diagnosis", removed)
        removed.clear()

    register = build_engagement_register(
        req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
        req.business_description,
    )
    # Everything a worker thread needs, read off the row ONCE and copied into
    # plain strings. An attribute read on a live ORM object can go back to the
    # session, and two threads doing that at once is the same unsafe access as
    # writing to it.
    main_problem = req.main_problem or "unspecified"
    figures = prompt_lines(known)
    context = {
        "business_name": req.business_name or "",
        "business_description": req.business_description or "",
        "industry": req.industry or "unspecified",
        "site_research": (analysis.get("business_model") or "none given"),
        "evidence": evidence,
        # shared by the three prompts that write for the client, and shown the same figures the check reads
        "figures_block": figures,
    }

    corrections = briefing_corrections(req.business_description)
    target_customers = req.target_customers or "unspecified"
    desired_outcome = req.desired_outcome or "unspecified"

    objections = ""
    for attempt in (1, 2):
        # what the last unusable reply held that the check took out, told to this pass's next ask
        hints: list[str] = []
        try:
            hypotheses = _ask(render(
                "diagnose.j2",
                target_customers=target_customers,
                main_problem=main_problem,
                desired_outcome=desired_outcome,
                engagement_register=register,
                corrections=corrections,
                objections=objections,
                **context,
            ), settings.REASONING_MODEL, DIAGNOSE_TOKENS, _enough_explanations(known_ids, check, figures),
                ledger(db, request_id, model=settings.REASONING_MODEL, purpose=f"diagnose:{attempt}"),
                hints)
        except Exception as exc:
            # a failed call, or replies too thin to be a diagnosis every time
            report()
            logger.warning("diagnosis could not be formed: %s", str(exc)[:200])
            raise _stopped(db, request_id, exc) from exc
        report()

        # `retry` is a field, not a sentence the screen has to recognise. The
        # header used to carry "— thinking again, the first reading was
        # refuted" and the client matched on that prose, so rewording it
        # here would have silently broken the second-look view over there.
        # And "what this is costing them" assumed a business already losing
        # money — someone planning to open one has no such thing yet.
        narrate(db, request_id, CONSIDERING, f"{len(hypotheses)} possible explanations",
                count=len(hypotheses), retry=attempt > 1)
        for h in hypotheses:
            narrate(db, request_id, CONSIDERING, h["statement"], area=h["area"],
                    software=h["software_can_fix"], theirs=h["from_owner"])

        heard: list[dict] = []
        try:
            result = _test_and_challenge(db, request_id, hypotheses, context, known_ids,
                                         main_problem, clean=clean, heard=heard, narrator=(db, request_id))
        finally:
            report()
        if result["status"] != "killed" or attempt == 2:
            result["attempts"] = attempt
            result["evidence"] = claims
            return result

        # What goes back to the model is what the reviewers wrote, not the text stored for the
        # client: it is for the model (anything it echoes is checked again), and a reason the
        # check emptied must not leave an empty "- " line.
        objections = "\n".join(
            f"- {c['because']}" + (f" A better explanation may be: {c['better_explanation']}"
                                   if c.get("better_explanation") else "")
            for c in heard if c["kills"])
        logger.info("leading hypothesis killed; diagnosing again with the objections")


def _test_and_challenge(db: Session, request_id: int, hypotheses: list[dict],
                        context: dict, known_ids: set[str], main_problem: str,
                        *, clean: Clean, heard: list[dict], narrator: tuple | None = None) -> dict:
    """One pass: test every hypothesis, then attack whichever leads.

    `heard` is filled with what each reviewer that ran said, as written and only cut
    to length (kills, because, better_explanation): the objections the diagnostician
    is handed on a second pass are made from it, not from the checked text stored for
    the client.

    `narrator` is the (session, id) to write the client-facing trail to, and
    is used only BETWEEN the parallel phases — never inside a worker, where
    touching this session is the bug that once made every skeptic look as
    though it had never run. `clean` is used only there as well, since it
    appends to a list the workers must not share: they return their text as
    written, and it is checked once they have all returned.
    """
    def say(kind: str, text: str, **extra) -> None:
        if narrator:
            narrate(narrator[0], narrator[1], kind, text, **extra)

    # Tested in parallel: each is a separate question about the same evidence,
    # and nothing one test concludes should reach another.
    def test(h: dict) -> tuple[dict, list, str | None]:
        """(the test, its calls as (usage, error), the error that left it untested)."""
        calls: list = []
        try:
            r = _ask(render(
                "test_hypothesis.j2", statement=h["statement"],
                would_support=h["would_support"], would_refute=h["would_refute"], **context,
            ), settings.ANALYSIS_MODEL, TEST_TOKENS, lambda raw: raw,
                lambda usage, error: calls.append((usage, error)))
            verdict = r.get("verdict") if r.get("verdict") in ("supported", "refuted", "untestable") else "untestable"
            return ({"verdict": verdict,
                     "because": str(r.get("because") or ""),
                     "cites": [c for c in (r.get("cites") or []) if isinstance(c, str) and c in known_ids],
                     "would_need": str(r.get("would_need") or "")}, calls, None)
        except Exception as exc:
            logger.warning("hypothesis %s could not be tested: %s", h["id"], str(exc)[:160])
            # Untested is not the same as untestable, and must not be shown as
            # though a test had been run and come back inconclusive.
            return ({"verdict": "untestable", "because": "", "cites": [], "would_need": "",
                     "not_tested": True}, calls, str(exc)[:500])

    say(TESTING, f"Testing all {len(hypotheses)} against their own figures")
    with ThreadPoolExecutor(max_workers=MAX_HYPOTHESES) as pool:
        tested = list(pool.map(test, hypotheses))
    for h, (result, calls, error) in zip(hypotheses, tested):
        result["because"] = cut_prose(clean(result["because"], "test because"), BECAUSE_CHARS)
        result["would_need"] = cut_prose(clean(result["would_need"], "test would_need"), NOTE_CHARS)
        h["test"] = result
        for usage, call_error in calls or [(None, error)]:
            log_usage(db, request_id, provider="openrouter", model=settings.ANALYSIS_MODEL,
                      purpose="test_hypothesis", usage=usage, success=call_error is None, error=call_error)
        say(VERDICT, h["statement"], verdict=result["verdict"],
            because=result["because"], cites=result["cites"],
            not_tested=bool(result.get("not_tested")))

    # Raised here, from the calling thread and after every call is on the
    # ledger. One crash is kept and reported; all of them leave nothing to
    # attack and nothing to conclude from, and a list of untested guesses is
    # not a diagnosis.
    crashed = [error for _, _, error in tested if error is not None]
    if len(crashed) == len(hypotheses):
        raise _stopped(db, request_id,
                       f"none of the {len(hypotheses)} explanations could be tested: {crashed[0]}")

    leading = max(hypotheses, key=_rank)
    if (leading.get("test") or {}).get("not_tested"):
        # Every explanation that was tested was refuted, and the one left is
        # one nobody could test. Leading with it would hand every document
        # writer an untested guess as the established cause. Stopped here,
        # from the calling thread, with every test already on the ledger and
        # before any reviewer is paid to attack it.
        raise _stopped(db, request_id, "the leading explanation could not be tested")
    rejected = [h for h in hypotheses if h["id"] != leading["id"]]
    say(TESTING, leading["statement"], leading=True)

    # Attacked on two angles at once. Both run even when the first lands: the
    # client is owed every weakness found, not the first one.
    def attack(angle: tuple[str, str]) -> tuple[dict, dict | None, str | None]:
        name, brief = angle
        try:
            r, usage = _call(render(
                "challenge.j2", statement=leading["statement"],
                because=(leading["test"] or {}).get("because") or "",
                cites=", ".join((leading["test"] or {}).get("cites") or []) or "none",
                rejected="\n".join(f"- {h['statement']}" for h in rejected) or "none",
                brief=brief, main_problem=main_problem, **context,
            ), settings.QA_MODEL, TEST_TOKENS)
            return ({"angle": name, "kills": bool(r.get("kills")),
                     "because": str(r.get("because") or ""),
                     "weakness": str(r.get("weakness") or ""),
                     "better_explanation": str(r.get("better_explanation") or "")}, usage, None)
        except Exception as exc:
            logger.warning("challenge %s failed: %s", name, str(exc)[:160])
            # A skeptic that never ran has not approved anything. Recorded as
            # an absence so the brief can say the diagnosis went unchallenged
            # rather than implying it withstood something.
            return ({"angle": name, "ran": False, "kills": False, "because": "",
                     "weakness": "", "better_explanation": ""}, None, str(exc)[:500])

    say(CHALLENGE, "Two reviewers are trying to kill that conclusion")
    with ThreadPoolExecutor(max_workers=len(CHALLENGE_ANGLES)) as pool:
        attacked = list(pool.map(attack, CHALLENGE_ANGLES))
    challenges = []
    for result, usage, error in attacked:
        if result.get("ran", True):
            # as written, for the model's second pass (see `diagnose`); the stored text is checked
            heard.append({"kills": result["kills"],
                          "because": cut_prose(result["because"], BECAUSE_CHARS),
                          "better_explanation": cut_prose(result["better_explanation"], NOTE_CHARS)})
        for field, limit in (("because", BECAUSE_CHARS), ("weakness", NOTE_CHARS),
                             ("better_explanation", NOTE_CHARS)):
            result[field] = cut_prose(clean(result[field], f"reviewer {field}"), limit)
        challenges.append(result)
        log_usage(db, request_id, provider="openrouter", model=settings.QA_MODEL,
                  purpose=f"challenge:{result['angle']}", usage=usage,
                  success=error is None, error=error)
        if result.get("ran", True) and result["because"]:
            say(CHALLENGE, result["because"], angle=result["angle"], kills=result["kills"])

    ran = [c for c in challenges if c.get("ran", True)]
    killed = [c for c in ran if c["kills"]]
    say(SETTLED,
        "A reviewer found a hole in it" if killed
        else "Neither could bring it down" if ran
        else "The review could not be run — nothing has tested this but the evidence",
        status="killed" if killed else "survived" if ran else "unchallenged")

    return {
        "hypotheses": hypotheses,
        "leading": leading["id"],
        "challenges": challenges,
        # Three distinct states, and the brief must be able to tell them
        # apart: survived a real attack, was killed, or was never attacked.
        "status": "unchallenged" if not ran else ("killed" if killed else "survived"),
        # De-duplicated: two angles landing on the same limitation is one
        # limitation, and printing it twice reads as two separate problems.
        "weaknesses": list(dict.fromkeys(c["weakness"] for c in ran if c["weakness"])),
    }


#: What each narrated line is, so the client can style it without parsing
#: prose. Kept deliberately small: a vocabulary that grows per-case is one
#: the interface cannot render.
CONSIDERING, TESTING, VERDICT, CHALLENGE, SETTLED = (
    "considering", "testing", "verdict", "challenge", "settled")


def narrate(db: Session, request_id: int, kind: str, text: str, **extra) -> None:
    """Append one line of the consultant's thinking, for the client to watch.

    ONLY ever called from the thread that owns this session — never from
    inside a ThreadPoolExecutor worker. The session is not thread-safe, and
    this is decoration: it must not be able to break a diagnosis it exists
    only to describe. So every failure here is swallowed.
    """
    try:
        req = db.get(Request, request_id)
        if req is None:
            return
        try:
            trail = json.loads(req.thinking_json) if req.thinking_json else []
        except (TypeError, ValueError):
            trail = []
        if not isinstance(trail, list):
            trail = []
        trail.append({"kind": kind, "text": str(text)[:400], **extra})
        req.thinking_json = json.dumps(trail[-40:])
        db.commit()
    except Exception:
        logger.debug("could not narrate %s", kind, exc_info=True)


def persist(db: Session, request_id: int, result: dict | None) -> None:
    req = db.get(Request, request_id)
    if req is None:
        return
    req.diagnosis_json = json.dumps(result) if result else None
    db.commit()
