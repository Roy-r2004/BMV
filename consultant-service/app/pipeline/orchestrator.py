from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Request
from app.pipeline import analyze, blueprint, consult, decompose, extras, images, plan, playbook, qa_experts, research, ui_spec
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
        ) if decomposition else []
        if decomposition and not issues:
            return decomposition
        if not decomposition:
            return None
        feedback = [f"{i['where']}: {i['issue']} Fix: {i['fix']}" for i in issues]
    raise RuntimeError(
        f"structural preflight failed after {PREFLIGHT_ATTEMPTS} attempts: "
        + "; ".join(i["issue"][:80] for i in issues[:3]))
from app.pipeline._shared import emit


def run(request_id: int) -> None:
    """Entry point for the background thread — opens its own DB session,
    mirroring the pattern the existing pipeline uses for the same reason:
    never run this on the request-handling thread/session.
    """
    db: Session = SessionLocal()
    try:
        _run_inner(db, request_id)
    except Exception as exc:
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
    finally:
        db.close()


def _run_inner(db: Session, request_id: int) -> None:
    # A no-op in well under a second when no site_url was given — the guard
    # lives inside research_business so this stays unconditional, like every
    # other stage here.
    emit(db, request_id, "researching", "Reading your business...", 5)
    research.research_business(db, request_id)

    emit(db, request_id, "analyzing", "Analyzing your business...", 10)
    analysis_result = analyze.analyze_business(db, request_id)

    emit(
        db, request_id, "consulting", "Consulting on what your AI employees should do...", 25,
        detail=analysis_result.get("growth_opportunity"),
    )
    consult_result = consult.consult(db, request_id, analysis_result)

    emit(
        db, request_id, "planning", "Planning your roles and features...", 35,
        detail=consult_result.get("consulting_summary"),
    )
    plan_result = plan.plan_integration(db, request_id, consult_result)

    emit(db, request_id, "decomposing", "Breaking your business down, module by module...", 42)
    decomposition = _decompose_with_preflight(
        db, request_id, analysis_result, consult_result, plan_result,
    )

    emit(db, request_id, "shaping", "Mapping your journey, scoreboard and procedures...", 46)
    extras.build_extras(db, request_id, analysis_result, decomposition)

    emit(
        db, request_id, "blueprint", "Writing your blueprint...", 50,
        detail=f"Concept named: {plan_result.get('concept_name', '')}",
    )
    blueprint.write_blueprint(
        db, request_id, analysis_result, consult_result, plan_result, decomposition,
    )

    emit(db, request_id, "technical", "Writing your technical implementation plan...", 56)
    blueprint.write_technical_plan(db, request_id, consult_result, plan_result, decomposition)

    emit(db, request_id, "playbook", "Writing your step-by-step execution playbook...", 60)
    playbook.write_playbook(db, request_id, plan_result, decomposition)

    emit(db, request_id, "quality", "Expert auditors reviewing your documents...", 61)
    qa_experts.review_quality(db, request_id)

    # the integrity layer: every engagement's structured content and prose
    # are validated and corrected against the registry before rendering —
    # the release gate refuses FINAL without its clean, current report
    from app.pipeline import integrity

    integrity.enforce(db, request_id)

    emit(db, request_id, "directing", "Designing your product screens...", 62)
    archetype_id, specs = ui_spec.build_ui_specs(db, request_id, consult_result, plan_result)

    emit(db, request_id, "images", "Rendering your product screenshots...", 70)
    saved_images = images.generate_demo_screens(db, request_id, archetype_id, specs)

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

    if _settings.REVIEW_MODE in ("on", "gate") and _settings.REVIEW_TOKEN:
        req.review_status = "pending"
        from app import mailer

        mailer.notify_reviewer_pending(req.public_id or request_id, req.business_name or "")
    db.commit()
    emit(db, request_id, "done", "Done", 100, detail=f"{len(saved_images)} images ready")
