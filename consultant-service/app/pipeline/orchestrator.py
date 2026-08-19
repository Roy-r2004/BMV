from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Request
from app.pipeline import analyze, blueprint, consult, decompose, extras, images, plan, playbook, qa_experts, research, ui_spec
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
    decomposition = decompose.decompose_business(
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
    req.status = "done"
    req.is_generating = False
    req.is_failed = False
    # The human review gate: when armed, a finished engagement waits for
    # the reviewer's approval before the client sees it.
    from app.config import settings as _settings

    if _settings.REVIEW_MODE == "on" and _settings.REVIEW_TOKEN:
        req.review_status = "pending"
        from app import mailer

        mailer.notify_reviewer_pending(request_id, req.business_name or "")
    db.commit()
    emit(db, request_id, "done", "Done", 100, detail=f"{len(saved_images)} images ready")
