"""The honest answer, shaped for the one screen that has to land.

`decide` writes a recommendation in prose. That is the right thing to reason
in and the wrong thing to lead with: the client reads a paragraph, and the
finding is somewhere in the third sentence. This stage turns the decision into
the few parts the answer screen is built from — a two-line finding, the
evidence in their figures, and what doing it is worth — and checks every part.

What it checks, and why it can:
  * every number in the headline, the evidence and the figures must name a
    figure the request knows (`app.figures.known`): one the owner gave in their
    own answers, one computed from theirs (`capacity`), or the move below. Each
    is bound (`app.figures.bind`), so it prints as that figure's own value; one
    that names no figure rejects the part it is in. There is no leniency: "one
    of 1 explanations" holds a number, and so does "twelve";
  * the value of the move is a product of terms, and each term is a cited
    figure, a calendar constant, or a number WE propose — labelled as ours.
    The product is computed here, never by the model, and the working is kept
    so the page can show it.

A model that invents "$32 at the studio down the road" is caught, because the
owner never said 32. If no answer can be made the run stops (`StageFailed`):
the page that follows would otherwise show the decision's own summary, as if
the stage had not been asked.
"""

import dataclasses
import json
import logging
import math
import re

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures import known as _known
from app.figures.bind import bind
from app.figures.calc import decimal_of, derive, places_of, round_half_up, unit_key
from app.figures.model import Figure, FigureSet, Proposal, _within, as_json, display_number, from_claim
from app.figures.read import mentions
from app.models import Request
from app.pipeline.figures import CONSTANTS
from app.pipeline._shared import ask_until_usable, ledger, reply_json
from app.pipeline.consult import NOT_TESTED
from app.pipeline.failure import StageFailed
from app.templating import render

logger = logging.getLogger("consultant.answer")

ANSWER_TOKENS = 3500
MAX_FIGURES = 2
MAX_TERMS = 5
#: The largest number one term of the move may hold. A real term is a count, a
#: price or a share of a small business's week; anything past a trillion is a
#: model's mistake, and refusing it keeps the product inside what the exact
#: arithmetic and the rounding can hold (five terms make at most 1e60).
MAX_TERM = 1e12
#: The registry's word for a claim whose time basis it could not find
#: (registry._infer_unit); it is no basis, not a period.
_NO_BASIS = "as stated"
# The length of the plan the answer proposes, and its bounds, are per business:
# settings.PLAN_WEEKS_DEFAULT / _MIN / _MAX (app/config.py).

#: Words that make a plan's name say how long it runs. A name that holds one (or
#: any number) is rendered from the plan's length in code, never the model's words.
_DURATION_WORDS = re.compile(
    r"\b(?:days?|weeks?|wks?|fortnights?|months?|quarters?|years?|yrs?)\b", re.I)


def _as_float(v) -> float | None:
    """The number as a float, or None: a bool, text that is not a number, and NaN or
    infinity (a model's JSON can say them) are not numbers a figure can rest on."""
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError, OverflowError):
        return None
    return f if math.isfinite(f) else None


def _claim_matches(v: float, claim: dict) -> bool:
    cv = _as_float(claim.get("value"))
    if cv is None:
        return False
    # A percentage is stored as a fraction (20% -> 0.2); a model may write 20.
    return _close(v, cv) or (cv < 1 and _close(v, cv * 100))


def _close(a: float, b: float) -> bool:
    """The same figure: the model's tolerance (half a percent), on the digits."""
    return _within(decimal_of(a), decimal_of(b))


def _is_money(claim: dict | None) -> bool:
    return bool(claim) and str(claim.get("unit") or "").upper() == "USD"


def _claim_figure(claim: dict, v: float) -> Figure | None:
    """The claim a term cites, at the value the term quotes, as the Figure `derive`
    works on. `from_claim` decides whose it is (a canonical_gate claim by its approval).
    None when the claim cannot be mapped: a claim that does not say whose it is is not
    a figure, so a term resting on it is not accepted."""
    try:
        figure = from_claim(claim)
    except ValueError as exc:
        logger.info("a cited claim is not a figure: %s", exc)
        return None
    d = decimal_of(v)
    # "as stated" is the registry saying it found no time basis: no period, which
    # any other period may be added to or taken from
    period = None if figure.period == _NO_BASIS else figure.period
    return dataclasses.replace(figure, value=d, precision=places_of(d), period=period)


def _sum(label: str, parts: list[tuple[int, dict]]) -> Figure | None:
    """The parts of one term as a Figure: what is added, less what is taken away.
    None when there is nothing to take it from (every part is taken away), when a
    calendar constant is among them (a constant multiplies, it is not added to a
    price), or when they are not one kind of number (units are compared as written
    ignoring case and the singular or plural of a time or count word)."""
    if any(sub.get("factor") for _, sub in parts):
        return None
    # A number we propose takes the unit of what it is added to or taken from.
    unit = next((sub["figure"].unit for _, sub in parts if sub["cited"]), None)
    if unit is None:
        unit = "USD" if any(unit_key(sub["figure"].unit) == "usd" for _, sub in parts) else ""
    figs = [(sign, sub["figure"] if sub["cited"] else dataclasses.replace(sub["figure"], unit=unit))
            for sign, sub in parts]
    added, taken = [f for sign, f in figs if sign > 0], [f for sign, f in figs if sign < 0]
    if not added:
        return None
    try:
        first = added[0] if len(added) == 1 else derive("total", added, id=f"{label or 'parts'} (added)", unit=unit)
        return derive("difference", [first] + taken, id=label or "parts", unit=unit) if taken else first
    except ValueError as exc:
        logger.info("move parts rejected: %s", exc)
        return None


def _stored_leaf(kind: str, value, label: str, source: str) -> dict:
    """One factor, as digits, so the range can be recomputed without the model."""
    leaf = {"kind": kind, "value": format(decimal_of(value), "f"), "sign": 1, "label": label}
    if kind == "claim":
        leaf["id"] = source
    return leaf


def _term(t: dict, by_id: dict, depth: int = 0) -> dict | None:
    """One verified factor: {label, value, money, proposed: [...], text}, with
    `figure` (a Figure, for `derive`) or, for a calendar constant, `factor`."""
    if not isinstance(t, dict) or depth > 1:
        return None
    label = str(t.get("label") or "").strip()[:60]
    parts = t.get("parts")
    if parts:
        money, cited, proposed, bits, cites, signed = False, False, [], [], [], []
        stored_parts = []
        for p in list(parts)[:4]:
            sub = _term({k: v for k, v in p.items() if k != "parts"}, by_id, depth + 1) if isinstance(p, dict) else None
            if sub is None:
                return None
            sign = -1 if str(p.get("sign")) in ("-1", "-") else 1
            signed.append((sign, sub))
            piece = dict(sub["stored"])
            piece["sign"] = sign
            stored_parts.append(piece)
            money = money or sub["money"]
            cited = cited or sub["cited"]
            cites += [sub["cite"]] if sub.get("cite") else []
            proposed += sub["proposed"]
            bits.append(("− " if sign < 0 else ("+ " if bits else "")) + sub["text"])
        total = _sum(label, signed)
        if total is None:
            return None
        # a number we propose is in the unit of what it is added to or taken from
        proposed = [{**p, "unit": total.unit} for p in proposed]
        return {"label": label, "value": float(total.value), "figure": total, "money": money,
                "proposed": proposed, "text": " ".join(bits), "parts": True, "cited": cited, "cites": cites,
                "stored": {"sign": 1, "label": label, "parts": stored_parts}}
    v = _as_float(t.get("value"))
    if v is None or v <= 0 or v > MAX_TERM:
        return None   # a term is a positive number of a size a business has; a part's sign says "less"
    source = str(t.get("from") or "").strip()
    if source == "proposed":
        unit = _known.proposal_unit(label)
        priced = unit == "USD"
        d = decimal_of(v)
        ours = Figure(f"proposed: {label}" if label else "proposed", d, unit, None, "ours",
                      Proposal(note=label or "proposed"), places_of(d))
        return {"label": label, "value": v, "figure": ours, "money": False,
                "proposed": [{"value": v, "label": label or "proposed", "unit": unit}],
                "text": f"{_money(v) if priced else _plain(v)} proposed",
                "cited": False, "stored": _stored_leaf("proposed", v, label, source)}
    if source == "constant":
        if not any(_close(v, c) for c in CONSTANTS):
            return None
        return {"label": label, "value": v, "factor": (decimal_of(v), label), "money": False, "proposed": [],
                "text": _plain(v), "cited": False, "stored": _stored_leaf("constant", v, label, source)}
    claim = by_id.get(source)
    if claim is None or not _claim_matches(v, claim):
        return None
    figure = _claim_figure(claim, v)
    if figure is None:
        return None
    shown = _money(v) if _is_money(claim) else _plain(v)
    return {"label": label, "value": v, "figure": figure, "money": _is_money(claim),
            "proposed": [], "text": f"{shown} now" if depth else shown, "cited": True, "cite": source,
            "stored": _stored_leaf("claim", v, label, source)}


# How a number prints in the move's words. A tie goes away from zero (2.5 is 3), the
# way `model.display` rounds, not to the even digit as Python's round() and float
# formatting do; a whole number prints whole.
def _plain(v: float) -> str:
    if not math.isfinite(v):
        return str(v)
    return f"{int(v):,}" if float(v).is_integer() else f"{round_half_up(v, 2):,.2f}".rstrip("0").rstrip(".")


def _money(v: float) -> str:
    if not math.isfinite(v):
        return str(v)
    return f"${int(v):,}" if float(v).is_integer() else f"${round_half_up(v):,.0f}"


def _said(v: float) -> int:
    """The figure a person would say out loud, 44,928 -> 45,000, a tie going away
    from zero: the precision the move's figure carries (`known.said_precision`)."""
    return int(round_half_up(v, _known.said_precision(decimal_of(v))))


def compute_move(raw: dict | None, claims: list[dict]) -> dict | None:
    """The value of the move, verified and multiplied here. Pure."""
    if not isinstance(raw, dict):
        return None
    by_id = {c["id"]: c for c in claims if isinstance(c, dict) and c.get("id")}
    terms = []
    for t in list(raw.get("terms") or [])[:MAX_TERMS]:
        term = _term(t, by_id)
        if term is None:
            logger.info("move term rejected: %s", str(t)[:160])
            return None
        terms.append(term)
    if len(terms) < 2:
        return None
    # At least one factor has to be theirs. A difference like "$28 proposed −
    # your $22" counts: it is arithmetic on something they said. A product of
    # proposals and constants is a guess with a dollar sign on it.
    if not any(t.get("cited") for t in terms):
        return None
    unit = str(raw.get("unit") or "").strip()[:16]
    money = unit.upper() == "USD" or any(t["money"] for t in terms)
    period = str(raw.get("period") or "year").strip().lower()
    period = period if period in ("week", "month", "year") else "year"
    try:
        product = derive("product", [t["figure"] for t in terms if "figure" in t], id="move",
                         unit="USD" if money else unit, period=period,
                         factors=[t["factor"] for t in terms if "factor" in t])
        value = float(product.value)
        if not math.isfinite(value) or value <= 0:
            return None
        shown = _said(value)
    except ValueError as exc:
        logger.info("move rejected: %s", exc)
        return None
    display = (f"≈ {_money(shown)} a {period}" if money
               else f"≈ {_plain(shown)} {unit or ''} a {period}".replace("  ", " "))
    working_terms = []
    for t in terms:
        if t.get("parts"):
            head = _money(t["value"]) if t["money"] else _plain(t["value"])
            working_terms.append(f"{head} {t['label']} ({t['text']})".replace("  ", " ").strip())
        else:
            working_terms.append(f"{t['text']} {t['label']}".strip())
    working = " × ".join(working_terms) + f" = {_money(value) if money else _plain(value)}"
    return {
        "label": str(raw.get("label") or "").strip()[:120],
        "value": value, "rounded": shown, "money": money, "unit": "USD" if money else unit,
        "period": period, "display": display, "working": working,
        "proposed": [p for t in terms for p in t["proposed"]],
        "cites": [c for t in terms for c in ([t["cite"]] if t.get("cite") else t.get("cites") or [])],
        "terms": [t["stored"] for t in terms],
    }


def plan_name(name: str, duration: Figure) -> str:
    """The plan's name. A name that says how long the plan runs is not the model's
    to write: one holding a number (a digit the reader passes over, a label or a plan
    position, counts too) or a duration word ("one-month pilot", "a fortnight
    sprint") is rendered here from the duration figure ("6-week plan"), as is a
    missing one. A name with neither ("Booking pilot") is kept."""
    name = str(name or "").strip()[:40]
    if not name or mentions(name) or any(ch.isdigit() for ch in name) or _DURATION_WORDS.search(name):
        return f"{display_number(duration)}-week plan"
    return name


def shape(raw: dict, claims: list[dict], known: FigureSet,
          hours: set[int] | None = None) -> tuple[dict | None, list[str]]:
    """(answer, problems). Pure. `problems` names what failed, for a retry.

    `known` is what the request knows (`known.known_for`); the move worked out
    here is added to it before anything is checked. `hours` are the clock times
    the client named; a time they did not name is unresolved."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    problems = []
    move = compute_move(raw.get("move"), claims)
    if raw.get("move") and move is None:
        problems.append("the move's terms did not check out against the figures — "
                        "cite ids exactly and use the cited values")
    known = _known.with_extra(known, _known.move_figures(move))

    def bound(text: str):
        """The bound text and the ids of the figures it names, or None when a
        number in it names no figure."""
        r = bind(text, known, hours=hours)
        return None if r.unresolved else (r.text, [f.id for f in r.bound])

    def clean(text: str, what: str, limit: int) -> str:
        text = str(text or "").strip()[:limit]
        r = bind(text, known, hours=hours)
        if r.unresolved:
            problems.append(f"{what} uses numbers they never gave: {', '.join(u.text for u in r.unresolved)}")
            return ""
        return r.text

    headline = clean(raw.get("headline"), "the headline", 80)
    turn = clean(raw.get("turn"), "the turn", 80)
    sub = clean(raw.get("sub"), "the sub", 420)
    emphasis = bound(str(raw.get("emphasis") or "").strip())
    emphasis = emphasis[0] if emphasis and emphasis[0] in sub else ""

    ids = {c["id"] for c in claims if c.get("id")}
    shown = []
    for f in list(raw.get("figures") or [])[:4]:
        if not isinstance(f, dict):
            continue
        value = str(f.get("value") or "").strip()[:32]
        label = str(f.get("label") or "").strip()[:80]
        cites = [c for c in (f.get("cites") or []) if c in ids]
        if not value or not cites or not any(ch.isdigit() for ch in value):
            continue
        b_value, b_label = bound(value), bound(label)
        # A headline figure IS a figure: its value must name at least one, and
        # nothing in it or its label may name none. "Week 4", "Phase 2", "Q3" are a
        # plan position, a label and an identifier to the reader, and name nothing.
        if b_value is None or not b_value[1] or b_label is None:
            problems.append(f"the figure '{value}' is not in the figures you cited")
            continue
        # `ids` are the figures the value names, for the page's tags
        shown.append({"value": b_value[0], "label": b_label[0], "cites": cites,
                      "ids": list(dict.fromkeys(b_value[1]))})
        if len(shown) >= MAX_FIGURES:
            break

    action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
    weeks = int(_as_float(action.get("weeks")) or settings.PLAN_WEEKS_DEFAULT)
    weeks = max(settings.PLAN_WEEKS_MIN, min(settings.PLAN_WEEKS_MAX, weeks))
    duration = _known.plan_weeks_figure(weeks)

    if not headline:
        return None, problems or ["no headline"]
    return {
        "headline": headline, "turn": turn, "sub": sub, "emphasis": emphasis,
        "figures": shown, "move": move,
        "action": {"weeks": weeks, "name": plan_name(action.get("name"), duration), "figure": as_json(duration)},
    }, problems


def _claim_lines(claims: list[dict]) -> str:
    lines = []
    for c in claims:
        basis = f"/{c['time_basis']}" if c.get("time_basis") not in (None, "", "n/a", "as stated") else ""
        lines.append(f"[{c['id']}] {c['value']} {c.get('unit', '')}{basis} — \"{c.get('text', '')}\"")
    return "\n".join(lines) or "none"


def _leading(req: Request) -> str:
    try:
        d = json.loads(req.diagnosis_json) if req.diagnosis_json else {}
    except (TypeError, ValueError):
        return "none"
    lead = next((h for h in d.get("hypotheses") or [] if h.get("id") == d.get("leading")), None)
    if not lead:
        return "none"
    test = lead.get("test") or {}
    if test.get("not_tested"):
        return f"{lead.get('statement')} — {NOT_TESTED}"
    return f"{lead.get('statement')} — {test.get('verdict', 'untested')}: {test.get('because', '')}"


def settled(req, decision: dict) -> bool:
    """Whether the leading explanation was actually proven. Worked out in code,
    because the wording of the answer must not run ahead of it: on the first real
    run an explanation the test called untestable was printed as fact."""
    try:
        d = json.loads(req.diagnosis_json) if req.diagnosis_json else {}
    except (TypeError, ValueError):
        return False
    lead = next((h for h in d.get("hypotheses") or [] if h.get("id") == d.get("leading")), None)
    return bool(lead) and (lead.get("test") or {}).get("verdict") == "supported" and decision.get("confidence") != "low"


def write(db: Session, request_id: int, decision: dict) -> dict | None:
    """Write, verify and persist the answer. Raises `StageFailed("answering")`
    when its inputs cannot be read, when the model call fails, or when no
    attempt gives an answer that checks out; an answer left from an earlier
    diagnosis is cleared first, never kept in its place. Returns None only when
    the request does not exist."""
    from app.pipeline import diagnose

    req = db.get(Request, request_id)
    if req is None:
        return None
    try:
        _, claims = diagnose._evidence_lines(req)
        # The answer is written before the registry and the roadmap; any of them on
        # the row now (and an earlier answer) are from an earlier run, and vouch for nothing.
        known = _known.known_for(req, leave_out={"answer", "registry", "roadmap"})
        hours = _known.hours_for(req)
        base = dict(
            business_name=req.business_name or "",
            main_problem=req.main_problem or "unspecified",
            kind=decision.get("intervention_kind") or "unspecified",
            central_problem=decision.get("central_problem") or "",
            summary=decision.get("consulting_summary") or "",
            why_not=decision.get("why_not_the_others") or "",
            confidence=decision.get("confidence"),
            settled=settled(req, decision),
            unverified="; ".join(decision.get("unverified") or []) or "nothing listed",
            leading=_leading(req),
            claims=_claim_lines(claims),
            figures_block=_known.prompt_lines(known),
        )
    except Exception as exc:
        logger.warning("answer could not be prepared: %s", str(exc)[:200])
        req.answer_json = None
        db.commit()
        raise StageFailed("answering", exc) from exc

    feedback = ""
    result = None
    cause: str | BaseException = "no answer came back usable"
    for attempt in (1, 2):
        try:
            prompt = render("answer.j2", **base)
            if feedback:
                prompt += ("\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n"
                           + feedback)
            # A reply that is not JSON is asked for again here; this loop's
            # second attempt is for a reply that read but was wrong.
            raw = ask_until_usable(
                lambda: provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                      max_tokens=ANSWER_TOKENS),
                reply_json,
                ledger(db, request_id, model=settings.REASONING_MODEL, purpose=f"answer:{attempt}"),
            )
        except Exception as exc:
            logger.warning("answer call failed: %s", str(exc)[:200])
            cause = exc
            break
        candidate, problems = shape(raw, claims, known, hours)
        if candidate:
            result = candidate
        if not problems:
            break
        logger.info("answer attempt %d rejected in part: %s", attempt, "; ".join(problems)[:400])
        feedback = "\n".join(f"- {p}" for p in problems)
        cause = "no usable answer: " + "; ".join(problems)

    req = db.get(Request, request_id)
    req.answer_json = json.dumps(result) if result else None
    db.commit()
    if result is None:
        raise StageFailed("answering", cause)
    return result


def load(req) -> dict | None:
    try:
        return json.loads(req.answer_json) if getattr(req, "answer_json", None) else None
    except (TypeError, ValueError):
        return None
