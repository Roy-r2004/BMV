import json
import logging

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures.bind import clean_sentences
from app.figures.known import hours_for, known_for
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


def has_text(value) -> bool:
    """Whether a string, or a list or dict holding strings, has any text in it."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_text(v) for v in value)
    if isinstance(value, dict):
        return any(has_text(v) for v in value.values())
    return False


def clean_prose(value, known: FigureSet, hours: set[int], removed: list[str]):
    """Model-written text with every number checked: each string is bound to the
    figures and loses each sentence that holds a number nobody owns
    (`bind.clean_sentences`); a list or dict is walked, and a list item that had
    text and has none left is dropped. Anything else is returned as it is. The
    sentences taken out are appended to `removed`, for the caller to log.

    The three stages that write the analysis, the decision and the diagnosis share
    this walk; each decides which of its fields are prose."""
    if isinstance(value, str):
        text, gone = clean_sentences(value, known, hours=hours)
        removed.extend(gone)
        return text
    if isinstance(value, list):
        kept = []
        for item in value:
            cleaned = clean_prose(item, known, hours, removed)
            if has_text(item) and not has_text(cleaned):
                continue
            kept.append(cleaned)
        return kept
    if isinstance(value, dict):
        return {k: clean_prose(v, known, hours, removed) for k, v in value.items()}
    return value


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


def _analysis(body: dict, known: FigureSet, hours: set[int]) -> dict:
    """The analysis in a reply, its prose checked against what the client gave.

    The findings are the pain points and the growth opportunity: when the model wrote
    any and the check leaves none of either, the reply is unusable (ValueError), so it
    is asked for again and then the stage stops, as for a reply that cannot be read. A
    reply that never had either is accepted as before, and nothing else is required:
    any other field that loses every sentence is left empty, like one the model did
    not write."""
    result = reply_json(body)
    findings_written = has_text(result.get("pain_points")) or has_text(result.get("growth_opportunity"))
    removed: list[str] = []
    for key in PROSE_KEYS:
        if key in result:
            result[key] = clean_prose(result[key], known, hours, removed)
    if findings_written and not (has_text(result.get("pain_points")) or has_text(result.get("growth_opportunity"))):
        raise ValueError("every pain point and the growth opportunity held a number nobody gave")
    if removed:
        logger.info("took %d sentence(s) holding a number nobody gave out of the analysis", len(removed))
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
        )
        result = ask_until_usable(
            lambda: provider.chat(settings.ANALYSIS_MODEL, [{"role": "user", "content": prompt}]),
            lambda body: _analysis(body, known, hours),
            ledger(db, request_id, model=settings.ANALYSIS_MODEL, purpose="analyze"),
        )
    except Exception as exc:
        # No analysis was made, and nothing written in its place: every later
        # stage would build on a finding about a business nobody looked at.
        raise StageFailed("analyzing", exc) from exc

    req.business_analysis_json = json.dumps(result)
    db.commit()
    return result
