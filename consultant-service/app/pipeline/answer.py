"""The honest answer, shaped for the one screen that has to land.

`decide` writes a recommendation in prose. That is the right thing to reason
in and the wrong thing to lead with: the client reads a paragraph, and the
finding is somewhere in the third sentence. This stage turns the decision into
the few parts the answer screen is built from — a two-line finding, the
evidence in their figures, and what doing it is worth — and checks every part.

What it checks, and why it can:
  * every number in the headline, the evidence and the figures must be one the
    owner gave, one computed from theirs (`capacity`), or the value below;
  * the value of the move is a product of terms, and each term is a cited
    figure, a calendar constant, or a number WE propose — labelled as ours.
    The product is computed here, never by the model, and the working is kept
    so the page can show it.

A model that invents "$32 at the studio down the road" is caught, because the
owner never said 32. Fails open to None: the screen then shows the decision's
own summary, which is what it showed before this stage existed.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.models import Request
from app.pipeline import capacity as _capacity
from app.pipeline import figures
from app.pipeline._shared import extract_json_from_text, log_usage
from app.templating import render

logger = logging.getLogger("consultant.answer")

ANSWER_TOKENS = 3500
MAX_FIGURES = 2
MAX_TERMS = 5
_WEEK_WORDS = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight",
               9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def _as_float(v) -> float | None:
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _claim_matches(v: float, claim: dict) -> bool:
    cv = _as_float(claim.get("value"))
    if cv is None:
        return False
    # A percentage is stored as a fraction (20% -> 0.2); a model may write 20.
    return figures.close(v, cv) or (cv < 1 and figures.close(v, cv * 100))


def _is_money(claim: dict | None) -> bool:
    return bool(claim) and str(claim.get("unit") or "").upper() == "USD"


def _term(t: dict, by_id: dict, depth: int = 0) -> dict | None:
    """One verified factor: {label, value, money, proposed: [...], text}."""
    if not isinstance(t, dict) or depth > 1:
        return None
    label = str(t.get("label") or "").strip()[:60]
    parts = t.get("parts")
    if parts:
        total, money, cited, proposed, bits, cites = 0.0, False, False, [], [], []
        for p in list(parts)[:4]:
            sub = _term({k: v for k, v in p.items() if k != "parts"}, by_id, depth + 1) if isinstance(p, dict) else None
            if sub is None:
                return None
            sign = -1 if str(p.get("sign")) in ("-1", "-") else 1
            total += sign * sub["value"]
            money = money or sub["money"]
            cited = cited or sub["cited"]
            cites += [sub["cite"]] if sub.get("cite") else []
            proposed += sub["proposed"]
            bits.append(("− " if sign < 0 else ("+ " if bits else "")) + sub["text"])
        return {"label": label, "value": total, "money": money, "proposed": proposed,
                "text": " ".join(bits), "parts": True, "cited": cited, "cites": cites}
    v = _as_float(t.get("value"))
    if v is None:
        return None
    source = str(t.get("from") or "").strip()
    if source == "proposed":
        return {"label": label, "value": v, "money": False,
                "proposed": [{"value": v, "label": label or "proposed"}],
                "text": f"{figures.money(v) if '$' in label or 'price' in label.lower() else _plain(v)} proposed",
                "cited": False}
    if source == "constant":
        if not figures.holds(v, figures.CONSTANTS):
            return None
        return {"label": label, "value": v, "money": False, "proposed": [], "text": _plain(v),
                "cited": False}
    claim = by_id.get(source)
    if claim is None or not _claim_matches(v, claim):
        return None
    shown = figures.money(v) if _is_money(claim) else _plain(v)
    return {"label": label, "value": v, "money": _is_money(claim), "proposed": [],
            "text": f"{shown} now" if depth else shown, "cited": True, "cite": source}


def _plain(v: float) -> str:
    return f"{int(v):,}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0").rstrip(".")


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
    value = 1.0
    for t in terms:
        value *= t["value"]
    if value <= 0:
        return None
    unit = str(raw.get("unit") or "").strip()[:16]
    money = unit.upper() == "USD" or any(t["money"] for t in terms)
    period = str(raw.get("period") or "year").strip().lower()
    period = period if period in ("week", "month", "year") else "year"
    shown = figures.rounded(value)
    display = (f"≈ {figures.money(shown)} a {period}" if money
               else f"≈ {_plain(shown)} {unit or ''} a {period}".replace("  ", " "))
    working_terms = []
    for t in terms:
        if t.get("parts"):
            head = figures.money(t["value"]) if t["money"] else _plain(t["value"])
            working_terms.append(f"{head} {t['label']} ({t['text']})".replace("  ", " ").strip())
        else:
            working_terms.append(f"{t['text']} {t['label']}".strip())
    working = " × ".join(working_terms) + f" = {figures.money(value) if money else _plain(value)}"
    return {
        "label": str(raw.get("label") or "").strip()[:120],
        "value": value, "rounded": shown, "money": money, "unit": "USD" if money else unit,
        "period": period, "display": display, "working": working,
        "proposed": [p for t in terms for p in t["proposed"]],
        "cites": [c for t in terms for c in ([t["cite"]] if t.get("cite") else t.get("cites") or [])],
    }


def allowed_numbers(texts: list[str], claims: list[dict], move: dict | None) -> set[float]:
    allowed = set(figures.given(texts))
    for c in claims:
        v = _as_float(c.get("value"))
        if v is not None:
            allowed.add(v)
            if 0 < v < 1:
                allowed.add(round(v * 100, 6))
    if move:
        allowed.update({move["value"], move["rounded"]})
        allowed.update(p["value"] for p in move.get("proposed") or [])
    return allowed


def shape(raw: dict, claims: list[dict], texts: list[str]) -> tuple[dict | None, list[str]]:
    """(answer, problems). Pure. `problems` names what failed, for a retry."""
    if not isinstance(raw, dict):
        return None, ["the response was not an object"]
    problems = []
    move = compute_move(raw.get("move"), claims)
    if raw.get("move") and move is None:
        problems.append("the move's terms did not check out against the figures — "
                        "cite ids exactly and use the cited values")
    allowed = allowed_numbers(texts, claims, move)
    hours = figures.given_hours(texts)

    def clean(text: str, what: str, limit: int) -> str:
        text = str(text or "").strip()[:limit]
        bad = figures.unsupported(text, allowed, hours=hours)
        if bad:
            problems.append(f"{what} uses numbers they never gave: {', '.join(_plain(b) for b in bad)}")
            return ""
        return text

    headline = clean(raw.get("headline"), "the headline", 80)
    turn = clean(raw.get("turn"), "the turn", 80)
    sub = clean(raw.get("sub"), "the sub", 420)
    emphasis = str(raw.get("emphasis") or "").strip()
    if emphasis and emphasis not in sub:
        emphasis = ""

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
        if figures.unsupported(f"{value} {label}", allowed, hours=hours):
            problems.append(f"the figure '{value}' is not in the figures you cited")
            continue
        shown.append({"value": value, "label": label, "cites": cites})
        if len(shown) >= MAX_FIGURES:
            break

    action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
    weeks = int(_as_float(action.get("weeks")) or 6)
    weeks = max(2, min(12, weeks))
    name = str(action.get("name") or "").strip()[:40]
    if not name or figures.unsupported(name, set(range(2, 13))):
        name = f"{_WEEK_WORDS.get(weeks, str(weeks))}-week plan"

    if not headline:
        return None, problems or ["no headline"]
    return {
        "headline": headline, "turn": turn, "sub": sub, "emphasis": emphasis,
        "figures": shown, "move": move, "action": {"weeks": weeks, "name": name},
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
    return f"{lead.get('statement')} — {test.get('verdict', 'untested')}: {test.get('because', '')}"


def write(db: Session, request_id: int, decision: dict) -> dict | None:
    """Write, verify and persist the answer. Never raises."""
    from app.pipeline import diagnose

    req = db.get(Request, request_id)
    if req is None:
        return None
    try:
        _, claims = diagnose._evidence_lines(req)
        texts = _capacity.owner_texts(req)
        base = dict(
            business_name=req.business_name or "",
            main_problem=req.main_problem or "unspecified",
            kind=decision.get("intervention_kind") or "unspecified",
            central_problem=decision.get("central_problem") or "",
            summary=decision.get("consulting_summary") or "",
            why_not=decision.get("why_not_the_others") or "",
            confidence=decision.get("confidence") or "medium",
            unverified="; ".join(decision.get("unverified") or []) or "nothing listed",
            leading=_leading(req),
            claims=_claim_lines(claims),
        )
    except Exception as exc:
        logger.warning("answer could not be prepared: %s", str(exc)[:200])
        return None

    feedback = ""
    result = None
    for attempt in (1, 2):
        try:
            prompt = render("answer.j2", **base)
            if feedback:
                prompt += ("\n\nYOUR LAST ATTEMPT WAS REJECTED FOR THESE REASONS — fix exactly these:\n"
                           + feedback)
            body = provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                 max_tokens=ANSWER_TOKENS)
            raw = extract_json_from_text(body["choices"][0]["message"]["content"])
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"answer:{attempt}", usage=body.get("usage"), success=True)
        except Exception as exc:
            log_usage(db, request_id, provider="openrouter", model=settings.REASONING_MODEL,
                      purpose=f"answer:{attempt}", success=False, error=str(exc)[:500])
            logger.warning("answer call failed: %s", str(exc)[:200])
            break
        candidate, problems = shape(raw, claims, texts)
        if candidate:
            result = candidate
        if not problems:
            break
        logger.info("answer attempt %d rejected in part: %s", attempt, "; ".join(problems)[:400])
        feedback = "\n".join(f"- {p}" for p in problems)

    req = db.get(Request, request_id)
    req.answer_json = json.dumps(result) if result else None
    db.commit()
    return result


def load(req) -> dict | None:
    try:
        return json.loads(req.answer_json) if getattr(req, "answer_json", None) else None
    except (TypeError, ValueError):
        return None
