"""Competing explanations, tested against the client's own numbers, then attacked.

This stage exists because `analyze` could only ever produce one story, and
`analyze.j2` asks for "the single biggest growth opportunity an AI employee
could unlock" — the conclusion was inside the question. A pipeline that starts
there can do nothing but agree with itself, and with the owner.

So: several causes that genuinely compete, each tested against the figures the
client actually gave, and then the survivor handed to two skeptics whose brief
is to kill it. What reaches the client is what survived, carrying its own
weaknesses rather than hiding them.

Everything here fails open. A diagnosis that dies falls back to `analyze`'s
output, which is what the pipeline did before this stage existed — one bad
model call degrades the consultation, it does not end the engagement.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline._shared import (
    briefing_corrections, build_engagement_register, extract_json_from_text, log_usage,
)
from app.pipeline import evidence
from app.pipeline.registry import client_fact_claims
from app.templating import render

logger = logging.getLogger("consultant.diagnose")

MIN_HYPOTHESES = 2
MAX_HYPOTHESES = 5

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
    from app.pipeline import capacity as _capacity

    claims = client_fact_claims(ops, free) + evidence.load(req) + _capacity.as_claims(_capacity.load(req))
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


def _ask(db: Session, request_id: int, purpose: str, prompt: str, model: str,
         max_tokens: int) -> dict:
    """The single-threaded form: call and log in one step."""
    result, usage = _call(prompt, model, max_tokens)
    log_usage(db, request_id, provider="openrouter", model=model, purpose=purpose,
              usage=usage, success=True)
    return result


def _sanitize_hypotheses(raw: list, known_ids: set[str]) -> list[dict]:
    """Keep the shape honest and drop citations to claims that do not exist.

    A fabricated id is worse than no id: downstream it reads exactly like a
    real one, and the client is shown a conclusion resting on a number they
    never gave.
    """
    out = []
    for i, h in enumerate(raw or [], start=1):
        if not isinstance(h, dict) or not str(h.get("statement") or "").strip():
            continue
        cites = [c for c in (h.get("cites") or []) if isinstance(c, str) and c in known_ids]
        out.append({
            "id": str(h.get("id") or f"H{i}")[:8],
            "statement": str(h["statement"])[:400],
            "area": str(h.get("area") or "other")[:40],
            "software_can_fix": bool(h.get("software_can_fix")),
            "would_support": str(h.get("would_support") or "")[:300],
            "would_refute": str(h.get("would_refute") or "")[:300],
            "cites": cites,
            "from_owner": bool(h.get("from_owner")),
        })
        if len(out) >= MAX_HYPOTHESES:
            break
    return out


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
    """
    order = {"supported": 2, "untestable": 1, "refuted": 0}
    test = h.get("test") or {}
    rank = order.get(test.get("verdict"), 0)
    evidence = len(test.get("cites") or []) if test.get("verdict") == "supported" else 0
    return (rank, not h.get("from_owner"), evidence)


def diagnose(db: Session, request_id: int, analysis: dict) -> dict | None:
    """Returns the diagnosis, or None when it could not be made.

    Up to two passes. When both skeptics kill the leading explanation, their
    objections go back to the diagnostician and it thinks again — a killed
    conclusion that reaches the client anyway is the same failure as never
    having challenged it, and the first real run did exactly that: two
    reviewers refuted the leading hypothesis and the recommendation opened by
    asserting it.

    The second pass is final. If it is killed too, that is reported honestly
    rather than retried until something survives — a hypothesis that only
    survives because we stopped attacking it has not survived.
    """
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    evidence, claims = _evidence_lines(req)
    known_ids = {c["id"] for c in claims}
    register = build_engagement_register(
        req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
        req.business_description,
    )
    # Everything a worker thread needs, read off the row ONCE and copied into
    # plain strings. An attribute read on a live ORM object can go back to the
    # session, and two threads doing that at once is the same unsafe access as
    # writing to it.
    main_problem = req.main_problem or "unspecified"
    context = {
        "business_name": req.business_name or "",
        "business_description": req.business_description or "",
        "industry": req.industry or "unspecified",
        "site_research": (analysis.get("business_model") or "none given"),
        "evidence": evidence,
    }

    corrections = briefing_corrections(req.business_description)
    target_customers = req.target_customers or "unspecified"
    desired_outcome = req.desired_outcome or "unspecified"

    objections = ""
    for attempt in (1, 2):
        try:
            raw = _ask(db, request_id, f"diagnose:{attempt}", render(
                "diagnose.j2",
                target_customers=target_customers,
                main_problem=main_problem,
                desired_outcome=desired_outcome,
                engagement_register=register,
                corrections=corrections,
                objections=objections,
                **context,
            ), settings.REASONING_MODEL, DIAGNOSE_TOKENS)
        except Exception as exc:
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"diagnose:{attempt}", success=False, error=str(exc)[:500])
            logger.warning("diagnosis could not be formed: %s", str(exc)[:200])
            return None

        hypotheses = _sanitize_hypotheses(raw.get("hypotheses"), known_ids)
        if len(hypotheses) < MIN_HYPOTHESES:
            # One explanation is not a diagnosis, it is an opinion. Better to
            # fall back to `analyze` — which is honestly presented as an
            # opinion — than to dress a single guess up as a tested conclusion.
            logger.warning("only %d usable hypotheses; not a diagnosis", len(hypotheses))
            return None

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

        result = _test_and_challenge(db, request_id, hypotheses, context, known_ids,
                                     main_problem, narrator=(db, request_id))
        if result["status"] != "killed" or attempt == 2:
            result["attempts"] = attempt
            result["evidence"] = claims
            return result

        objections = "\n".join(
            f"- {c['because']}" + (f" A better explanation may be: {c['better_explanation']}"
                                   if c.get("better_explanation") else "")
            for c in result["challenges"] if c.get("kills"))
        logger.info("leading hypothesis killed; diagnosing again with the objections")


def _test_and_challenge(db: Session, request_id: int, hypotheses: list[dict],
                        context: dict, known_ids: set[str], main_problem: str,
                        narrator: tuple | None = None) -> dict:
    """One pass: test every hypothesis, then attack whichever leads.

    `narrator` is the (session, id) to write the client-facing trail to, and
    is used only BETWEEN the parallel phases — never inside a worker, where
    touching this session is the bug that once made every skeptic look as
    though it had never run.
    """
    def say(kind: str, text: str, **extra) -> None:
        if narrator:
            narrate(narrator[0], narrator[1], kind, text, **extra)

    # Tested in parallel: each is a separate question about the same evidence,
    # and nothing one test concludes should reach another.
    def test(h: dict) -> tuple[dict, dict | None, str | None]:
        try:
            r, usage = _call(render(
                "test_hypothesis.j2", statement=h["statement"],
                would_support=h["would_support"], would_refute=h["would_refute"], **context,
            ), settings.ANALYSIS_MODEL, TEST_TOKENS)
            verdict = r.get("verdict") if r.get("verdict") in ("supported", "refuted", "untestable") else "untestable"
            return ({"verdict": verdict,
                     "because": str(r.get("because") or "")[:400],
                     "cites": [c for c in (r.get("cites") or []) if isinstance(c, str) and c in known_ids],
                     "would_need": str(r.get("would_need") or "")[:300]}, usage, None)
        except Exception as exc:
            logger.warning("hypothesis %s could not be tested: %s", h["id"], str(exc)[:160])
            # Untested is not the same as untestable, and must not be shown as
            # though a test had been run and come back inconclusive.
            return ({"verdict": "untestable", "because": "", "cites": [], "would_need": "",
                     "not_tested": True}, None, str(exc)[:500])

    say(TESTING, f"Testing all {len(hypotheses)} against their own figures")
    with ThreadPoolExecutor(max_workers=MAX_HYPOTHESES) as pool:
        tested = list(pool.map(test, hypotheses))
    for h, (result, usage, error) in zip(hypotheses, tested):
        h["test"] = result
        log_usage(db, request_id, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="test_hypothesis", usage=usage, success=error is None, error=error)
        say(VERDICT, h["statement"], verdict=result["verdict"],
            because=result["because"], cites=result["cites"])

    leading = max(hypotheses, key=_rank)
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
                     "because": str(r.get("because") or "")[:400],
                     "weakness": str(r.get("weakness") or "")[:300],
                     "better_explanation": str(r.get("better_explanation") or "")[:300]}, usage, None)
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
