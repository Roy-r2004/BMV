"""What the client's package holds so far, read from the run's row alone.

The progress screen shows the documents as they come to exist, and shows the
ones that did exist when a run stopped. Both are answered from the row: a
document is `ready` when what holds it is filled, `writing` when the run is at
the stage that writes it, and not listed otherwise. Pure: no database, no
clock, so a row that is half empty, or whose JSON is damaged, lists what it can
and never raises.
"""

import json

from app.pipeline import action_plan


def _filled(column: str):
    return lambda req: bool(getattr(req, column, None))


def _roadmap_ready(req) -> bool:
    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    return isinstance(phases, list) and bool(phases) and plan.get("status") not in (action_plan.WRITING, action_plan.FAILED)


def _has_ai_team(req) -> bool:
    try:
        raw = getattr(req, "consulting_recommendations_json", None)
        decision = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return False
    employees = decision.get("recommended_ai_employees") if isinstance(decision, dict) else None
    return isinstance(employees, list) and bool(employees)


#: (key, title, whether it exists, the stage that writes it), in the order the
#: client reads them.
_DOCUMENTS = (
    ("blueprint", "The blueprint", _filled("mvp_blueprint"), "blueprint"),
    ("technical", "The technical plan", _filled("technical_plan"), "technical"),
    ("operations", "The operations manual", _filled("playbook_json"), "playbook"),
    ("roadmap", "The implementation roadmap", _roadmap_ready, "roadmap"),
    ("system", "Your system, screen by screen", _filled("screens_json"), "screens"),
)


def documents_for(req) -> list[dict]:
    """`[{"key", "title", "state"}]` for the documents that exist or are being
    written, in reading order. It reflects the columns as they stand: a document
    whose column is filled is `ready`, even while its own stage is current (the
    run is then rewriting it). That is not a claim that it answers the latest
    diagnosis: a restarted diagnosis keeps the documents of the earlier one
    until each is rewritten. The AI team is not written by a stage of its own;
    it is listed, ready, when the decision recommended any."""
    stage = getattr(req, "stage", None)
    out = []
    for key, title, exists, writing_stage in _DOCUMENTS:
        if exists(req):
            out.append({"key": key, "title": title, "state": "ready"})
        elif stage == writing_stage:
            out.append({"key": key, "title": title, "state": "writing"})
    if _has_ai_team(req):
        out.append({"key": "ai_team", "title": "Your AI team", "state": "ready"})
    return out


def package_files(req) -> list[dict]:
    """The shelf: six files and the zip. The preview, the share link and the
    progress screen read this one list. `documents_for` stays the account of
    what a running engagement has written so far."""
    from app.storyline.files import payload

    return payload(req)
