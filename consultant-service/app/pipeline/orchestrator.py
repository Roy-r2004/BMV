import json
import logging
import os
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Request
from app.pipeline import action_plan, analyze, answer, blueprint, capacity, consult, decide, decompose, diagnose, extras, images, plan, playbook, qa_experts, research, ui_spec
from app.pipeline.structural import engagement_subjects as _subjects_of
from app.pipeline.structural import preflight as _structural_preflight


PREFLIGHT_ATTEMPTS = 3


def _decompose_with_preflight(db, request_id, *args, **kwargs):
    """Structural preflight guards the prose spend: a decomposition whose
    scenarios, dependencies or pilot gate fail validation is retried — and
    each retry hands the model the exact failures of the previous attempt
    (a blind re-roll is a lottery; a targeted one is a correction). After
    PREFLIGHT_ATTEMPTS the run stops cleanly instead of generating volumes
    from a broken skeleton."""
    feedback = None
    issues = []
    for attempt in range(1, PREFLIGHT_ATTEMPTS + 1):
        decomposition = decompose.decompose_business(db, request_id, *args, feedback=feedback, **kwargs)
        issues = _structural_preflight(
            (decomposition or {}).get("business_case") or {},
            (decomposition or {}).get("modules") or [],
            (decomposition or {}).get("registry"),
            _engagement_subjects(db, request_id),
        ) if decomposition else []
        if decomposition and not issues:
            return decomposition
        if not decomposition:
            return None
        feedback = [f"{i['where']}: {i['issue']} Fix: {i['fix']}" for i in issues]
    # Out of attempts. Every other stage in this pipeline fails OPEN — a bad
    # call degrades the package instead of killing it — and the preflight was
    # the one place that did not, so requests 15, 16, 17 and 18 each cost real
    # money and delivered nothing at all.
    #
    # Carry on with the best skeleton we have. The same findings are recomputed
    # downstream by the integrity layer and the release gate, which refuse
    # FINAL while any of them stands: the client gets a DRAFT that names its
    # own defects, never a FINAL built over them. A partial deliverable that
    # says what is wrong with it beats an error message.
    logging.getLogger("consultant.orchestrator").warning(
        "structural preflight unresolved after %s attempts, continuing to a DRAFT: %s",
        PREFLIGHT_ATTEMPTS, "; ".join(i["issue"][:80] for i in issues[:3]))
    try:
        emit(db, request_id, "decomposing",
             "Some structural checks could not be satisfied — continuing to a draft", 42,
             detail="; ".join(i["issue"][:120] for i in issues[:3]))
    except Exception:
        # telling the client about the degradation must never itself end the
        # run — that would reintroduce the very failure this change removes
        logging.getLogger("consultant.orchestrator").warning("could not emit the degradation notice")
    return decomposition
def _engagement_subjects(db, request_id: int) -> set:
    """The distinct systems this engagement serves, taken from the client's own
    name for it. An estate named "Masar & MultiAI" legitimately gets one
    instance of a shared capability per system; without this the overlap rule
    reads them as one capability split in two and refuses the run."""
    from app.models import Request

    # Subjects only ever RELAX a rule, so failing to read them must never fail
    # the preflight — a caller with no session (or a stub one) simply gets the
    # stricter behaviour.
    if db is None or not hasattr(db, "get"):
        return set()
    try:
        row = db.get(Request, request_id)
    except Exception:
        return set()
    if row is None:
        return set()
    return _subjects_of(getattr(row, "business_name", "") or "", getattr(row, "concept_name", "") or "")


from app.pipeline._shared import emit


#: the client has a decision to read and has not answered it yet
AWAITING_APPROVAL = "awaiting_approval"
#: they approved it, and the build half is running
BUILDING = "building"
#: the answer was that a build will not fix the cause, and the client took it.
#: Terminal, and not a failure: the brief IS the deliverable for this one.
ADVISED = "advised"

#: where the diagnosis half ends and the client's decision begins
GATE_PCT = 30


def _leading_statement(diagnosis: dict) -> str | None:
    return next((h["statement"] for h in diagnosis.get("hypotheses") or []
                 if h.get("id") == diagnosis.get("leading")), None)


def _fail(db: Session, request_id: int, exc: Exception) -> None:
    # The exception may have come from a commit — the session is then in
    # a failed state and every statement below would re-raise, leaving
    # the request stuck at is_generating=true forever (found in review).
    db.rollback()
    req = db.get(Request, request_id)
    if req is not None:
        req.status = "failed"
        req.is_failed = True
        req.is_generating = False
        db.commit()
    emit(
        db,
        request_id,
        "failed",
        f"Generation failed: {exc}",
        req.progress_pct if req else 0,
        detail=str(exc)[:300],
    )


class _Superseded(Exception):
    """This build is no longer the engagement's current one: the client
    pushed back (or sent a file) while the plans were being written, and a
    fresh diagnosis has taken the row. Not a failure — the run just stops."""


def _check_current(db: Session, request_id: int, token) -> None:
    """Raise `_Superseded` unless this build still owns the row.

    The token is the row's `phase_started_at` when the build began. Every
    restart (revise, evidence, approve) stamps a new one, so a mismatch — or
    a status other than BUILDING — means someone else's run is now current
    and anything this one writes would overwrite theirs."""
    db.expire_all()
    row = db.get(Request, request_id)
    if row is None or row.status != BUILDING or row.phase_started_at != token:
        raise _Superseded()


def run(request_id: int) -> None:
    """The whole engagement — entry point for the background thread.

    Opens its own DB session, mirroring the pattern the existing pipeline
    uses for the same reason: never run this on the request-handling
    thread/session.

    The diagnosis runs, the answer is saved, and the plans are written
    straight after — there is no approval gate. A client who pushes back
    while the plans are being written restarts the diagnosis; the build in
    flight notices through its token and stops quietly.
    """
    db: Session = SessionLocal()
    try:
        _run_diagnosis(db, request_id)
    except _Superseded:
        return
    except Exception as exc:
        _fail(db, request_id, exc)
    finally:
        db.close()


def run_build(request_id: int) -> None:
    """The build half on its own — the legacy approve path.

    The diagnosis is re-read from the row rather than carried in memory:
    this runs in a new thread, minutes or days after the half that produced
    it, and the row is the only thing that survives that gap.
    """
    db: Session = SessionLocal()
    try:
        _run_build(db, request_id)
    except _Superseded:
        return
    except Exception as exc:
        _fail(db, request_id, exc)
    finally:
        db.close()


def _run_diagnosis(db: Session, request_id: int) -> None:
    # A fresh trail for every diagnosis. "Not quite" and a file upload both
    # run this again on the same row, and without this the client watched the
    # new reasoning appended under the old — passes from a run they had
    # already read, presented as if they were part of this one.
    row = db.get(Request, request_id)
    if row is not None:
        row.thinking_json = None
        # The plan written for the last answer does not survive a new one: it
        # would tell them to act on a diagnosis they have just sent back.
        row.action_plan_json = None
        db.commit()

    # Files sent with the engagement are read FIRST, so the explanations are
    # formed with their booking export in hand rather than tested against it
    # afterwards. A no-op when nothing was sent.
    from app.pipeline import evidence as _evidence

    if os.path.isdir(_evidence.pending_dir(request_id)):
        emit(db, request_id, "reading", "Reading your file...", 3)
        for name, count in _evidence.ingest_pending(db, request_id):
            diagnose.narrate(db, request_id, "reading", name, count=count)

    # A no-op in well under a second when no site_url was given — the guard
    # lives inside research_business so this stays unconditional, like every
    # other stage here.
    emit(db, request_id, "researching", "Reading your business...", 5)
    research.research_business(db, request_id)

    emit(db, request_id, "analyzing", "Analyzing your business...", 10)
    analysis_result = analyze.analyze_business(db, request_id)

    # Their week, drawn from their answers. Before the diagnosis on purpose:
    # its totals become figures a hypothesis can cite. Fails open to nothing.
    _read_capacity(db, request_id)

    # Several explanations, tested against their own figures, then attacked.
    # Fails open to `analysis_result` alone: a diagnosis that could not be
    # made must not stop the engagement, and the brief says which it got.
    emit(db, request_id, "diagnosing", "Working out what's actually wrong...", 16)
    diagnosis_result = diagnose.diagnose(db, request_id, analysis_result)
    diagnose.persist(db, request_id, diagnosis_result)
    if diagnosis_result:
        emit(db, request_id, "challenging", "Testing that conclusion against the alternatives...", 22,
             detail=_leading_statement(diagnosis_result))

    emit(
        db, request_id, "consulting", "Working out what would actually help...", 25,
        detail=analysis_result.get("growth_opportunity"),
    )
    consult_result = decide.decide(db, request_id, analysis_result)

    # The answer screen's parts: the finding in two lines, the evidence in
    # their figures, and what the move is worth — each number checked.
    emit(db, request_id, "answering", "Writing your answer...", 28)
    answer.write(db, request_id, consult_result)

    # No gate. A firm does not hand over its answer and then wait to be asked
    # for the plans: the answer is saved (it is readable the moment this
    # commits) and the plans are written straight after. The build takes a
    # fresh phase_started_at — its token — so a client who pushes back while
    # the plans are being written supersedes it cleanly.
    req = db.get(Request, request_id)
    req.status = BUILDING
    req.is_generating = True
    req.is_failed = False
    req.phase_started_at = datetime.utcnow()
    db.commit()
    token = req.phase_started_at
    emit(db, request_id, "answer_ready", "Your answer is ready — writing your plans", GATE_PCT,
         detail=consult_result.get("consulting_summary"))

    req = db.get(Request, request_id)
    analysis_saved = json.loads(req.business_analysis_json) if req.business_analysis_json else analysis_result
    consult_saved = (json.loads(req.consulting_recommendations_json)
                     if req.consulting_recommendations_json else consult_result)
    _build_from(db, request_id, analysis_saved, consult_saved, token=token)


def _read_capacity(db: Session, request_id: int) -> None:
    req = db.get(Request, request_id)
    if req is None:
        return
    picture, usage, error = capacity.read(
        capacity.owner_texts(req), "not launched yet — this is a plan"
        if req.operating_stage == "opening" else "already operating")
    from app.pipeline._shared import log_usage

    if usage is not None or error is not None:
        log_usage(db, request_id, provider="openrouter", model=settings.ANALYSIS_MODEL,
                  purpose="capacity", usage=usage, success=error is None, error=error)
    req = db.get(Request, request_id)
    req.capacity_json = json.dumps(picture) if picture else None
    db.commit()


def _run_build(db: Session, request_id: int) -> None:
    req = db.get(Request, request_id)
    if req is None:
        raise ValueError(f"Request {request_id} not found")
    analysis_result = json.loads(req.business_analysis_json) if req.business_analysis_json else {}
    consult_result = json.loads(req.consulting_recommendations_json) if req.consulting_recommendations_json else {}
    # The approve route already flipped the row to BUILDING and stamped
    # phase_started_at; a row reached some other way is claimed here.
    if req.status != BUILDING or req.phase_started_at is None:
        req.status = BUILDING
        req.is_generating = True
        req.phase_started_at = datetime.utcnow()
        db.commit()
    _build_from(db, request_id, analysis_result, consult_result, token=req.phase_started_at)


def _build_from(db: Session, request_id: int, analysis_result: dict, consult_result: dict,
                token=None) -> None:
    """Write every plan. `token` is the row's phase_started_at when this build
    began; each stage first checks the row still carries it, so a build the
    client has superseded (by pushing back) stops instead of writing over the
    new diagnosis. A stage that raises after being superseded is reported as
    superseded too — the failure belongs to a run nobody is waiting on."""
    req = db.get(Request, request_id)
    if token is None:
        req.status = BUILDING
        req.is_generating = True
        req.phase_started_at = datetime.utcnow()
        db.commit()
        token = req.phase_started_at

    def current() -> None:
        _check_current(db, request_id, token)

    try:
        _build_stages(db, request_id, analysis_result, consult_result, current)
    except _Superseded:
        raise
    except Exception:
        # A stage that broke because the row changed under it is not a
        # failure of the engagement the client is now looking at.
        db.rollback()
        current()
        raise


def _build_stages(db: Session, request_id: int, analysis_result: dict, consult_result: dict,
                  current) -> None:
    current()
    emit(
        db, request_id, "planning", "Planning your roles and features...", 35,
        detail=consult_result.get("consulting_summary"),
    )
    plan_result = plan.plan_integration(db, request_id, consult_result)

    current()
    emit(db, request_id, "decomposing", "Breaking your business down, module by module...", 42)
    decomposition = _decompose_with_preflight(
        db, request_id, analysis_result, consult_result, plan_result,
    )

    current()
    emit(db, request_id, "shaping", "Mapping your journey, scoreboard and procedures...", 46)
    extras.build_extras(db, request_id, analysis_result, decomposition)

    current()
    emit(
        db, request_id, "blueprint", "Writing your blueprint...", 50,
        detail=f"Concept named: {plan_result.get('concept_name', '')}",
    )
    blueprint.write_blueprint(
        db, request_id, analysis_result, consult_result, plan_result, decomposition,
    )

    current()
    emit(db, request_id, "technical", "Writing your technical implementation plan...", 56)
    blueprint.write_technical_plan(db, request_id, consult_result, plan_result, decomposition)

    current()
    emit(db, request_id, "playbook", "Writing your step-by-step execution playbook...", 60)
    playbook.write_playbook(db, request_id, plan_result, decomposition)

    # The roadmap: the phases we carry out and the few decisions only the
    # owner can make. Written after the playbook so it can lean on the
    # modules the decomposition settled. Fails open to {"status": "failed"}.
    current()
    emit(db, request_id, "roadmap", "Writing your implementation roadmap...", 61)
    action_plan.write(db, request_id)

    current()
    emit(db, request_id, "quality", "Expert auditors reviewing your documents...", 61)
    qa_experts.review_quality(db, request_id)

    # the integrity layer: every engagement's structured content and prose
    # are validated and corrected against the registry before rendering —
    # the release gate refuses FINAL without its clean, current report
    from app.pipeline import integrity

    current()
    integrity.enforce(db, request_id)

    current()
    emit(db, request_id, "directing", "Designing your product screens...", 62)
    archetype_id, specs = ui_spec.build_ui_specs(db, request_id, consult_result, plan_result)

    current()
    emit(db, request_id, "images", "Rendering your product screenshots...", 70)
    saved_images = images.generate_demo_screens(db, request_id, archetype_id, specs)

    current()
    if not saved_images:
        req = db.get(Request, request_id)
        req.status = "failed"
        req.is_failed = True
        req.is_generating = False
        db.commit()
        emit(db, request_id, "failed", "Screenshot generation failed for every screen", 70)
        return

    req = db.get(Request, request_id)
    # A run with neither written volume produced no deliverable, whatever else
    # survived. Every document stage fails OPEN so one bad call degrades the
    # package instead of killing it — but when the whole spine fails (run 58
    # lost DNS mid-flight and lost analyze, consult, plan, decompose, blueprint
    # and technical_plan) the request still reported "done" over an empty
    # record. A status has to be backed by the thing it claims.
    if not (req.mvp_blueprint or req.technical_plan):
        req.status = "failed"
        req.is_failed = True
        req.is_generating = False
        db.commit()
        emit(db, request_id, "failed",
             "No blueprint and no technical plan were produced — nothing to deliver", 70)
        return

    req.status = "done"
    req.is_generating = False
    req.is_failed = False
    # The human review gate: when armed, a finished engagement waits for
    # the reviewer's approval before the client sees it.
    from app.config import settings as _settings

    from app import mailer

    if _settings.REVIEW_MODE in ("on", "gate") and _settings.REVIEW_TOKEN:
        req.review_status = "pending"
        mailer.notify_reviewer_pending(req.public_id or request_id, req.business_name or "")
    db.commit()
    # The building screen tells them they can close the page and we will
    # write when it is ready. A gated run is released later, and THAT sends
    # the mail — telling them now would send them to a page that holds it.
    if not (_settings.REVIEW_MODE == "gate" and req.review_status == "pending"):
        mailer.notify_owner_ready(req.public_id or request_id, req.owner_email or req.email,
                                  req.business_name or "")
    emit(db, request_id, "done", "Done", 100, detail=f"{len(saved_images)} images ready")
