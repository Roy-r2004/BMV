"""What to do about the diagnosed cause — including "not software".

`consult` could only ever answer one question: which AI employees. Its output
shape said so (`recommended_ai_employees`, set by default on every path) and
its fallback hardcoded a front desk and an analyst for every business on
earth. A pipeline whose only available answer is the thing it sells is not
consulting, and the client can tell.

So this stage names the KIND of intervention first, and only then what to
build. When the kind is not `software` the engagement can end at the brief:
the client gets an answer worth more than a blueprint they did not need, and
it costs one model call instead of thirteen stages of generation.

It keeps `consulting_summary`, `recommended_ai_employees` and
`recommended_features` in its output, unchanged in name and meaning, because
stages 7-19 read them. Nothing downstream knows this stage replaced `consult`.

If the decision cannot be made the run stops (`StageFailed`). It no longer
falls back to `consult`: that answer was the same front desk and analyst for
every business, written as though it were this client's finding.

The prose a client reads (the summary, the central problem, why not the others,
what is unverified, the features and the AI employees' titles and reasons) is
checked against the figures the request knows: a sentence holding a number nobody
owns is dropped, its neighbours kept, and a list item left with nothing is dropped.
The summary is the one field the check can make unusable: a summary the model
wrote that loses every sentence is asked for again, and then stops the run. Any
other field that loses every sentence is stored empty, like one never written.
"""

import json
import logging

from sqlalchemy.orm import Session

from app.ai import provider
from app.config import settings
from app.figures.known import hours_for, known_for, prompt_lines
from app.figures.model import FigureSet
from app.models import Request
from app.pipeline import consult
from app.pipeline._shared import ask_until_usable, build_engagement_register, ledger, reply_json
from app.pipeline.analyze import clean_prose, has_text
from app.pipeline.failure import StageFailed
from app.templating import render

logger = logging.getLogger("consultant.decide")

#: What a row can hold at the moment `decide` runs that is not about this run: the
#: answer, the registry and the roadmap are written after it.
STALE_AT_DECISION = frozenset({"answer", "registry", "roadmap"})

#: The model-written text of the decision a client reads on the web. The claim ids
#: (`rests_on`) and the two enumerations (`intervention_kind`, `confidence`) are not
#: prose and are never checked.
PROSE_KEYS = ("consulting_summary", "central_problem", "why_not_the_others", "unverified",
              "recommended_features")
#: The text of each recommended AI employee.
EMPLOYEE_PROSE_KEYS = ("title", "why")
#: How much of each unverified item is kept.
UNVERIFIED_CHARS = 300

#: What actually fixes the diagnosed cause. `SOFTWARE` is the only one that
#: earns a build; the rest end at the brief unless the client overrides.
KINDS = ("software", "process", "pricing", "staffing", "none")
SOFTWARE = "software"

DECIDE_TOKENS = 4000


def builds(result: dict | None) -> bool:
    """Whether this decision justifies running the build half.

    A missing or unreadable `intervention_kind` builds, deliberately: this is
    the behaviour the pipeline had before the field existed, and a parse
    failure must not silently withhold the deliverable the client came for.
    Only an explicit non-software answer stops the build.
    """
    kind = (result or {}).get("intervention_kind")
    return kind not in [k for k in KINDS if k != SOFTWARE]


def _employees(employees: list, known: FigureSet, hours: set[int], removed: list[str]) -> list:
    """The recommended AI employees with the text of each checked. An employee whose
    title held text and has none left is dropped; one whose reason lost a sentence
    stays, with the sentences that remain."""
    kept = []
    for employee in employees:
        if not isinstance(employee, dict):
            cleaned = clean_prose(employee, known, hours, removed)
            if has_text(employee) and not has_text(cleaned):
                continue
            kept.append(cleaned)
            continue
        cleaned = {k: clean_prose(v, known, hours, removed) if k in EMPLOYEE_PROSE_KEYS else v
                   for k, v in employee.items()}
        if has_text(employee.get("title")) and not has_text(cleaned.get("title")):
            continue
        kept.append(cleaned)
    return kept


def _decision(body: dict, known: FigureSet, hours: set[int]) -> dict:
    """The decision in a reply, its prose checked against what the client gave and
    what we worked out.

    The summary is the recommendation to the owner: when the model wrote one and the
    check leaves nothing of it, the reply is unusable (ValueError), so it is asked for
    again and then the stage stops, as for a reply that cannot be read. A reply that
    never had a summary is accepted as before, and nothing else is required: any other
    field that loses every sentence is left empty, like one the model did not write."""
    result = reply_json(body)
    summary_written = has_text(result.get("consulting_summary"))
    removed: list[str] = []
    if isinstance(result.get("unverified"), list):
        # cut to the length stored BEFORE the check, so a number is never cut after it
        result["unverified"] = [u[:UNVERIFIED_CHARS] if isinstance(u, str) else u for u in result["unverified"]]
    for key in PROSE_KEYS:
        if key in result:
            result[key] = clean_prose(result[key], known, hours, removed)
    if isinstance(result.get("recommended_ai_employees"), list):
        result["recommended_ai_employees"] = _employees(result["recommended_ai_employees"], known, hours, removed)
    if summary_written and not has_text(result.get("consulting_summary")):
        raise ValueError("every sentence of the recommendation held a number nobody gave")
    if removed:
        logger.info("took %d sentence(s) holding a number nobody gave out of the decision", len(removed))
    return result


def decide(db: Session, request_id: int, analysis: dict) -> dict:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")

    try:
        # Their figures and the week worked out from them; the diagnosis was made from those.
        known = known_for(req, leave_out=STALE_AT_DECISION)
        hours = hours_for(req)
        prompt = render(
            "decide.j2",
            business_name=req.business_name or "",
            business_description=req.business_description or "",
            desired_outcome=req.desired_outcome or "unspecified",
            business_model=analysis.get("business_model", "Unknown"),
            target_customer_profile=analysis.get("target_customer_profile", ""),
            pain_points=json.dumps(analysis.get("pain_points", [])),
            diagnosis=consult._format_diagnosis(req),
            engagement_register=build_engagement_register(
                req.engagement_type, req.needs_ai, req.main_problem, req.desired_outcome,
                req.business_description,
            ),
            figures_block=prompt_lines(known),
        )
        result = ask_until_usable(
            lambda: provider.chat(settings.REASONING_MODEL, [{"role": "user", "content": prompt}],
                                  max_tokens=DECIDE_TOKENS),
            lambda body: _decision(body, known, hours),
            ledger(db, request_id, model=settings.REASONING_MODEL, purpose="decide"),
        )
    except Exception as exc:
        logger.warning("decision could not be made: %s", str(exc)[:200])
        raise StageFailed("consulting", exc) from exc

    kind = result.get("intervention_kind")
    if kind not in KINDS:
        # An unreadable kind must not be guessed into a refusal to build. It
        # is dropped, `builds()` then answers True, and the client gets their
        # deliverable — the failure mode of this stage has to be the old
        # behaviour, never a withheld engagement.
        logger.warning("unusable intervention_kind %r; treating as unset", kind)
        result.pop("intervention_kind", None)

    result.setdefault("recommended_ai_employees", [])
    result.setdefault("recommended_features", [])
    if result.get("confidence") not in ("high", "medium", "low"):
        # Not "medium": a middle nobody stated reads as a judgement weighed.
        result.pop("confidence", None)
    result["unverified"] = [u[:UNVERIFIED_CHARS] for u in (result.get("unverified") or [])
                            if isinstance(u, str) and u.strip()]

    req.consulting_analysis = result.get("consulting_summary")
    req.consulting_recommendations_json = json.dumps(result)
    db.commit()
    return result
