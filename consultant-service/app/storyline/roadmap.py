"""The roadmap file: as long as the plan, and it says so.

The length is the plan's own figure. A plan of six weeks is six weeks, never
ninety days. A baseline the owner has not measured yet is printed as stored.
Metrics that share a review rhythm are listed under that rhythm once.

It is a document of the release law, like the volumes: every piece of content
passes the volumes' choke point inside a law scope, its findings are kept
beside the file, and a file on disk is served only while the status it was
stamped with is still the package's.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from app.config import settings
from app.figures import law
from app.pipeline import action_plan

#: The release law's name for the roadmap (`law.DOCUMENTS`).
WHERE = "The roadmap"


class NotReady(Exception):
    """The roadmap has no plan to print. `key` is the file that is missing."""

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


def build_roadmap_pdf(req) -> str:
    """A PDF at uploads/exports/{id}-roadmap.pdf. Raises NotReady("roadmap")
    when the run has no action plan to base it on."""
    plan = _ready_plan(req)
    if plan is None:
        raise NotReady("roadmap")

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Frame, PageTemplate

    from app.pipeline.export_pdf import (_EngagementDoc, _page_chrome, document_known, document_phrases,
                                         release_status)

    started = datetime.utcnow()
    law.ensure_records(req)
    out_dir = os.path.join(settings.UPLOADS_DIR, "exports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{getattr(req, 'id', None)}-roadmap.pdf")
    updated = getattr(req, "updated_at", None)
    kept = law.record(getattr(req, "id", None), WHERE, updated)
    if os.path.isfile(path) and updated is not None and kept is not None and kept["stamped"] is not None:
        if (datetime.utcfromtimestamp(os.path.getmtime(path)) > updated
                and kept["stamped"] == release_status(req)["status"]):
            return path

    known, hours = document_known(req)
    with law.scope(known, where=WHERE, hours=hours, request_id=getattr(req, "id", None),
                   phrases=document_phrases(req)) as found:
        flows = _flows(req, plan)
        stamped = release_status(req)["status"]

    name = getattr(req, "concept_name", None) or getattr(req, "business_name", None) or ""
    doc = _EngagementDoc(
        path, pagesize=A4,
        title=f"{name} — The implementation roadmap",
        author="Build My Version",
    )
    width, height = A4
    frame = Frame(18 * mm, 20 * mm, width - 36 * mm, height - 36 * mm, id="content")
    doc.addPageTemplates([
        PageTemplate(id="body", frames=[frame],
                     onPage=_page_chrome("The roadmap", name, draft=stamped == "draft", stamp="DRAFT")),
    ])
    doc.build(flows)
    # the running header and the footer are drawn in these bands, as on the volumes
    law.save(getattr(req, "id", None), WHERE, law.locate_pages(path, found.findings, margins=(15 * mm, 19 * mm)),
             built_at=started, data_at=updated, stamped=stamped)
    return path


def roadmap_ready(req) -> bool:
    """Whether the row holds a plan the roadmap is built from."""
    return _ready_plan(req) is not None


def check_roadmap(req) -> None:
    """The roadmap's law-only pass (`law.ensure_records`): its content made
    inside the law, nothing printed. A package with no plan yet is recorded as
    having no roadmap."""
    started = datetime.utcnow()
    request_id = getattr(req, "id", None)
    updated = getattr(req, "updated_at", None)
    plan = _ready_plan(req)
    if plan is None:
        law.save(request_id, WHERE, [], built_at=started, data_at=updated, absent=True)
        return
    from app.pipeline.export_pdf import document_known, document_phrases

    known, hours = document_known(req)
    with law.scope(known, where=WHERE, hours=hours, request_id=request_id,
                   phrases=document_phrases(req)) as found:
        _flows(req, plan)
    law.save(request_id, WHERE, found.findings, built_at=started, data_at=updated)


def _ready_plan(req) -> dict | None:
    plan = action_plan.load(req)
    phases = plan.get("phases") if isinstance(plan, dict) else None
    if (not isinstance(phases, list) or not phases
            or plan.get("status") in (action_plan.WRITING, action_plan.FAILED)):
        return None
    return plan


def _flows(req, plan: dict) -> list:
    """Every flowable of the roadmap, in reading order."""
    from reportlab.platypus import PageBreak

    from app.figures.known import known_for
    from app.storyline.build import build as build_story
    from app.storyline.pdf import answer_page_flowables, register_reference

    story = build_story(req)
    flows: list = []
    if story is not None:
        flows += answer_page_flowables(story)
        if story.register is not None:
            flows += register_reference()
    flows += _plan(plan, story, known_for(req))
    flows += _measures(_loads(getattr(req, "scoreboard_json", None)))
    flows += _risks(_loads(getattr(req, "risks_json", None)))
    flows += _decisions(plan.get("decisions"))
    flows += _cadence(_loads(getattr(req, "scoreboard_json", None)))
    if flows and isinstance(flows[-1], PageBreak):
        flows = flows[:-1]
    return flows


def _plan(plan: dict, story, known) -> list:
    from reportlab.platypus import KeepTogether, Paragraph

    from app.figures.known import PLAN_WEEKS_ID
    from app.figures.model import display
    from app.pipeline.export_pdf import _S

    figure = known.get(PLAN_WEEKS_ID)
    length = f"This plan runs for {display(figure)}." if figure is not None else "This plan runs for as long as its phases."
    owners = _owners(story)
    flows = [Paragraph("The plan", _S["h1toc"]), Paragraph(_rich(length), _S["body"])]
    for index, phase in enumerate(plan.get("phases") or [], 1):
        if not isinstance(phase, dict):
            continue
        when = _words(phase.get("when"))
        title = _words(phase.get("title"))
        do = _words(phase.get("do"))
        you = _words(phase.get("you"))
        owner = owners.get(when) or ""
        sentence = ". ".join(part for part in (when, title, do, you, owner) if part)
        if sentence:
            flows.append(Paragraph(_rich(sentence + "."), _S["body"]))
    if len(flows) > 2:
        flows = [KeepTogether(flows[:3]), *flows[3:]]
    return flows


def _measures(board) -> list:
    from reportlab.platypus import Paragraph

    from app.pipeline.export_pdf import _S

    if not isinstance(board, list) or not board:
        return []
    flows = [Paragraph("The measures", _S["h1toc"])]
    for item in board:
        if not isinstance(item, dict):
            continue
        metric = _words(item.get("metric"))
        baseline = _words(item.get("baseline"))
        target = _words(item.get("target"))
        owner = _words(item.get("owner"))
        if not metric:
            continue
        # A part with nothing behind it is left out, never said as an empty "From".
        if baseline and target:
            sentence = f"{metric}. From {baseline} to {target}."
        elif target:
            sentence = f"{metric}. Aim: {target}."
        elif baseline:
            sentence = f"{metric}. Today: {baseline}."
        else:
            sentence = f"{metric}."
        if owner:
            sentence += f" {owner} watches it."
        flows.append(Paragraph(_rich(sentence), _S["body"]))
    return flows


def _risks(risks) -> list:
    from reportlab.platypus import Paragraph

    from app.pipeline.export_pdf import _S

    if not isinstance(risks, list) or not risks:
        return []
    flows = [Paragraph("The risks", _S["h1toc"])]
    for item in risks:
        if not isinstance(item, dict):
            continue
        risk = _words(item.get("risk"))
        mitigation = _words(item.get("mitigation"))
        who = _words(item.get("who_feels_it"))
        if not risk:
            continue
        sentence = risk
        if mitigation:
            sentence += f". {mitigation}"
        if who:
            sentence += f". {who} feels it"
        flows.append(Paragraph(_rich(sentence + "."), _S["body"]))
    return flows


def _decisions(decisions) -> list:
    from reportlab.platypus import Paragraph

    from app.pipeline.export_pdf import _S

    if not isinstance(decisions, list) or not decisions:
        return []
    flows = [Paragraph("Decisions only you can make", _S["h1toc"])]
    for item in decisions:
        if not isinstance(item, dict):
            continue
        question = _words(item.get("question"))
        if not question:
            continue
        options = [_words(option) for option in (item.get("options") or [])]
        options = [option for option in options if option]
        sentence = question if question.endswith("?") else question + "."
        if options:
            sentence += " " + " ".join(options)
        flows.append(Paragraph(_rich(sentence), _S["body"]))
    return flows


def _cadence(board) -> list:
    from reportlab.platypus import Paragraph

    from app.pipeline.export_pdf import _S

    if not isinstance(board, list):
        return []
    groups: dict[str, list[str]] = {}
    for item in board:
        if not isinstance(item, dict):
            continue
        metric = _words(item.get("metric"))
        rhythm = _words(item.get("review"))
        if not metric or not rhythm:
            continue
        groups.setdefault(rhythm, []).append(metric)
    if not groups:
        return []
    flows = [Paragraph("The cadence", _S["h1toc"])]
    for rhythm, metrics in groups.items():
        flows.append(Paragraph(_rich(rhythm), _S["h2toc"]))
        for metric in metrics:
            flows.append(Paragraph(_rich(metric), _S["body"]))
    return flows


def _owners(story) -> dict[str, str]:
    """The register's role words, keyed by the phase timeframe they belong to."""
    if story is None or story.register is None:
        return {}
    found: dict[str, str] = {}
    for row in story.register.rows:
        when = _words(row.when)
        owner = _words(row.owner)
        if when and owner and when not in found:
            found[when] = owner
    return found


def _rich(text: str) -> str:
    """The volumes' content choke point (`export_pdf._rich`)."""
    from app.pipeline.export_pdf import _rich as rich

    return rich(text)


def _words(value) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _loads(raw):
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None
