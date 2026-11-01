"""The package is one list. The shelf, the zip, the share link and the
progress screen read it, so a file cannot be offered in one place and
missing from another.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.pipeline import decide

_DO_NOT_BUILD = "Your diagnosis says not to build, so there are no screens."

#: The stage name that means "this file is being written", for the progress screen.
_WRITING = {
    "blueprint": "blueprint",
    "technical": "technical",
    "operations": "playbook",
    "roadmap": "roadmap",
    "system": "screens",
}


class UnknownFile(Exception):
    """The key is not one of the package's files."""


@dataclass(frozen=True)
class PackageFile:
    key: str
    title: str
    filename: str
    kind: str
    available: bool
    reason: str | None = None


def files_for(req) -> list[PackageFile]:
    """Six files, then the zip, in the order the client reads them.

    A file with nothing behind it is on the list and not available. The
    system file says why when the diagnosis is not to build.
    """
    files = [
        _file("blueprint", "The blueprint", "Volume I - The Blueprint.pdf", "pdf", bool(getattr(req, "mvp_blueprint", None))),
        _file("technical", "The technical plan", "Volume II - The Technical Plan.pdf", "pdf", bool(getattr(req, "technical_plan", None))),
        _file("operations", "The operations manual", "Volume III - The Operations Manual.pdf", "pdf", _operations(req)),
        _file("roadmap", "The implementation roadmap", "The implementation roadmap.pdf", "pdf", _roadmap(req)),
        _system(req),
        _file("deck", "The deck", "The deck.pptx", "pptx", bool(getattr(req, "roles_json", None))),
    ]
    files.append(_file(
        "zip", "The whole package", "The package.zip", "zip", any(item.available for item in files),
    ))
    return files


def payload(req) -> list[dict]:
    """The list as the shelf and the progress screen print it."""
    stage = getattr(req, "stage", None)
    out = []
    for item in files_for(req):
        if item.available:
            state = "ready"
        elif _WRITING.get(item.key) == stage:
            state = "writing"
        else:
            state = "absent"
        out.append({
            "key": item.key, "title": item.title, "filename": item.filename,
            "kind": item.kind, "available": item.available, "reason": item.reason, "state": state,
        })
    return out


def render_file(req, key: str) -> str:
    """The file on disk. Unknown keys raise UnknownFile. A file the list
    marks unavailable is not built."""
    item = next((f for f in files_for(req) if f.key == key), None)
    if item is None or key == "zip":
        raise UnknownFile(key)
    if not item.available:
        from app.storyline.roadmap import NotReady

        raise NotReady(item.reason or "not ready")
    if key in ("blueprint", "technical", "operations"):
        from app.pipeline import export_pdf

        return export_pdf.build_pdf(req, key)
    if key == "system":
        from app.screens import export as screens_export

        return screens_export.build_system_pdf(req)
    if key == "roadmap":
        from app.storyline.roadmap import build_roadmap_pdf

        return build_roadmap_pdf(req)
    if key == "deck":
        return _deck(req)
    raise UnknownFile(key)


def _file(key: str, title: str, filename: str, kind: str, available: bool, reason: str | None = None) -> PackageFile:
    return PackageFile(key, title, filename, kind, available, reason)


def _system(req) -> PackageFile:
    title, filename = "Your system, screen by screen", "Volume IV - Your System, Screen by Screen.pdf"
    if not decide.builds(_decision(req)):
        return _file("system", title, filename, "pdf", False, _DO_NOT_BUILD)
    return _file("system", title, filename, "pdf", bool(getattr(req, "screens_json", None)))


def _operations(req) -> bool:
    procedures = _loads(getattr(req, "procedures_json", None))
    steps = procedures.get("procedures") if isinstance(procedures, dict) else None
    return bool(steps) or bool(_loads(getattr(req, "org_json", None))) or bool(_loads(getattr(req, "checklists_json", None)))


def _roadmap(req) -> bool:
    from app.pipeline import action_plan

    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if not isinstance(phases, list) or not phases:
        return False
    return plan.get("status") not in (action_plan.WRITING, action_plan.FAILED)


def _decision(req) -> dict | None:
    data = _loads(getattr(req, "consulting_recommendations_json", None))
    return data if isinstance(data, dict) else None


def _loads(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _deck(req) -> str:
    from app.pipeline import export_pptx

    inputs = export_pptx.deck_inputs(req)
    if inputs is None:
        from app.storyline.roadmap import NotReady

        raise NotReady("deck")
    presentation = export_pptx.build_presentation(req, *inputs, list(getattr(req, "images", None) or []))
    path = export_pptx.export_path_for(req.id)
    presentation.save(path)
    return path
