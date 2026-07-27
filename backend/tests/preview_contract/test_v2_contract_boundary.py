from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.application.appspec.repository import load_json_object
from app.application.pipelines import orchestrator as full_orchestrator
from app.application.preview_app.pipeline import orchestrator
from app.application.preview_app.pipeline.versioning import (
    GENERATOR_V2,
    select_preview_generator,
)
from app.application.preview_contract.service import (
    V2_CONTRACT_READY,
    build_v2_app_spec_contract,
)
from app.core.config import settings
from app.domain.models import (  # noqa: F401
    AppSpecRevision,
    CustomerSourceArtifact,
    PreviewTierArtifactRecord,
    ProductStrategyRevision,
    Request,
)
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "app_spec"
    / "valid_booking.json"
)


class _FixtureAI:
    name = "local-fixture"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.models: list[str] = []

    def ask_chat(self, model: str, _messages: list[dict], **_kwargs) -> str:
        self.models.append(model)
        if not self.responses:
            raise AssertionError("unexpected provider call")
        return self.responses.pop(0)

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("fixture must not call vision")

    def is_available(self) -> bool:
        return True


def _request(request_id: int = 801) -> Request:
    return Request(
        id=request_id,
        business_name="Lumina Studio",
        industry="Wellness",
        business_description="Customers book treatments online.",
        target_customers="Studio customers",
        main_problem="Appointments are coordinated manually.",
        desired_outcome="Customers can book online.",
        project_type="new",
        email="owner@example.com",
        mvp_blueprint="A derived booking workflow with confirmation.",
        concept_name="Lumina Booking",
        preview_summary="A polished booking workflow.",
        preview_features=json.dumps(["Appointment booking"]),
        created_at=datetime(2026, 7, 24, 12, 0, 0),
    )


def _coverage() -> dict:
    return {
        "verdict": "pass",
        "score": 100,
        "summary": "The booking outcome is fully represented and proven.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Customers can book online.",
                "covered": True,
                "requirement_ids": ["REQ-BOOK"],
                "evidence_ids": ["EVIDENCE-CONFIRMATION"],
                "acceptance_test_ids": ["TEST-BOOK"],
                "notes": "",
            }
        ],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
    }


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_v2_boundary_persists_contract_and_never_reaches_generation_phases(
    monkeypatch,
) -> None:
    db = _db()
    try:
        req = _request()
        db.add(req)
        db.commit()
        spec_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        ai = _FixtureAI([json.dumps(spec_payload), json.dumps(_coverage())])

        monkeypatch.setattr(settings, "APPSPEC_MODEL", "google/gemini-2.5-flash")
        monkeypatch.setattr(
            settings,
            "APPSPEC_REPAIR_MODEL",
            "google/gemini-2.5-flash",
        )
        monkeypatch.setattr(
            settings,
            "APPSPEC_V2_COVERAGE_MODEL",
            "anthropic/claude-haiku-4.5",
        )
        monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
        monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 0)

        def forbidden(*_args, **_kwargs):
            raise AssertionError("v2 Phase 1B reached a downstream generation phase")

        monkeypatch.setattr(orchestrator, "run_plan_phase", forbidden)
        monkeypatch.setattr(orchestrator, "run_codegen_phase", forbidden)
        monkeypatch.setattr(orchestrator, "run_polish_phase", forbidden)
        monkeypatch.setattr(orchestrator, "run_build_phase", forbidden)
        monkeypatch.setattr(orchestrator, "run_finalize", forbidden)
        monkeypatch.setattr(
            "app.application.preview_app.workspace.get_workspace",
            forbidden,
        )
        result = build_v2_app_spec_contract(
            db,
            req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=req,
            app_spec_revision_id=None,
        )

        contract = result["preview_contract"]
        assert contract["status"] == V2_CONTRACT_READY
        assert list(contract["tier_artifact_refs"]) == [
            "tier_1",
            "tier_2",
            "tier_3",
        ]
        assert db.query(CustomerSourceArtifact).count() == 1
        assert db.query(ProductStrategyRevision).count() == 1
        tier_rows = (
            db.query(PreviewTierArtifactRecord)
            .order_by(PreviewTierArtifactRecord.tier)
            .all()
        )
        assert [row.tier for row in tier_rows] == [1, 2, 3]
        assert [row.parent_tier_artifact_id for row in tier_rows] == [
            None,
            tier_rows[0].id,
            tier_rows[1].id,
        ]
        revision = db.query(AppSpecRevision).one()
        metadata = load_json_object(revision.generation_metadata_json)
        assert metadata["customer_source_artifact_id"] == contract["customer_source_ref"]["id"]
        assert metadata["product_strategy_revision_id"] == contract["product_strategy_ref"]["id"]
        assert metadata["used_fallback"] is False
        assert metadata["complete"] is True
        assert metadata["model_families"] == {
            "author": "google",
            "repair": "google",
            "coverage": "anthropic",
        }
        assert ai.models == [
            "google/gemini-2.5-flash",
            "anthropic/claude-haiku-4.5",
        ]

        persisted = json.loads(req.generated_pages)
        assert persisted == result
        assert "preview_app" not in persisted
        assert (
            select_preview_generator(req, v2_enabled=True).version
            == GENERATOR_V2
        )
    finally:
        db.close()


def test_full_v2_pipeline_returns_immediately_after_contract_boundary(
    monkeypatch,
) -> None:
    db = _db()
    try:
        req = _request(802)
        db.add(req)
        db.commit()
        expected = {
            "preview_contract": {
                "generator_version": "v2",
                "status": "candidate_build_pending",
            }
        }
        calls: list[str] = []

        monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
        monkeypatch.setattr(
            full_orchestrator.blueprint,
            "generate_mvp_blueprint",
            lambda *_args, **_kwargs: calls.append("blueprint"),
        )
        monkeypatch.setattr(
            full_orchestrator,
            "generate_preview_app",
            lambda *_args, **_kwargs: calls.append("contract") or expected,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "_emit",
            lambda *_args, **_kwargs: None,
        )

        def forbidden(*_args, **_kwargs):
            raise AssertionError("full v2 pipeline continued past Phase 3B")

        monkeypatch.setattr(
            full_orchestrator.visual_demo,
            "generate_visual_demo",
            forbidden,
        )
        monkeypatch.setattr(
            full_orchestrator.technical_plan,
            "generate_technical_plan",
            forbidden,
        )
        monkeypatch.setattr(
            full_orchestrator.proposal,
            "generate_proposal",
            forbidden,
        )
        monkeypatch.setattr(
            full_orchestrator.build_plans,
            "generate_build_plans",
            forbidden,
        )
        monkeypatch.setattr(
            full_orchestrator.role_pages,
            "generate_role_pages",
            forbidden,
        )

        result = full_orchestrator.GenerationPipeline(
            _FixtureAI([]),
            object(),
        )._run_inner(db, req.id)

        assert result is expected
        assert calls == ["blueprint", "contract"]
    finally:
        db.close()


def test_full_v2_pipeline_marks_request_failed_on_candidate_contract_failure(
    monkeypatch,
) -> None:
    db = _db()
    try:
        req = _request(804)
        req.status = "reviewing"
        db.add(req)
        db.commit()
        expected = {
            "preview_contract": {
                "generator_version": "v2",
                "status": "candidate_contract_failed",
            }
        }

        monkeypatch.setattr(settings, "PREVIEW_GENERATOR_V2", True)
        monkeypatch.setattr(
            full_orchestrator.blueprint,
            "generate_mvp_blueprint",
            lambda *_args, **_kwargs: None,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "generate_preview_app",
            lambda *_args, **_kwargs: expected,
        )
        monkeypatch.setattr(
            full_orchestrator,
            "_emit",
            lambda *_args, **_kwargs: None,
        )

        result = full_orchestrator.GenerationPipeline(
            _FixtureAI([]),
            object(),
        )._run_inner(db, req.id)

        db.refresh(req)
        assert result is expected
        assert req.status == "failed"
    finally:
        db.close()


def test_contract_ready_summary_failure_rolls_back_every_tier(
    monkeypatch,
) -> None:
    db = _db()
    try:
        req = _request(803)
        db.add(req)
        db.commit()
        spec_payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        ai = _FixtureAI([json.dumps(spec_payload), json.dumps(_coverage())])

        monkeypatch.setattr(settings, "APPSPEC_MODEL", "google/gemini-2.5-flash")
        monkeypatch.setattr(
            settings,
            "APPSPEC_REPAIR_MODEL",
            "google/gemini-2.5-flash",
        )
        monkeypatch.setattr(
            settings,
            "APPSPEC_V2_COVERAGE_MODEL",
            "anthropic/claude-haiku-4.5",
        )
        monkeypatch.setattr(settings, "APPSPEC_MAX_REPAIR_ATTEMPTS", 0)
        monkeypatch.setattr(settings, "APPSPEC_MAX_DETERMINISTIC_HEALS", 0)

        def fail_summary_update(_mapper, _connection, target) -> None:
            if target.generated_pages:
                raise RuntimeError("forced contract-ready summary failure")

        event.listen(Request, "before_update", fail_summary_update)
        try:
            with pytest.raises(RuntimeError, match="contract-ready summary"):
                build_v2_app_spec_contract(
                    db,
                    req.id,
                    ai,
                    JinjaTemplateRenderer(settings.TEMPLATES_DIR),
                    req=req,
                    app_spec_revision_id=None,
                )
        finally:
            event.remove(Request, "before_update", fail_summary_update)

        assert db.query(PreviewTierArtifactRecord).count() == 0
        db.refresh(req)
        assert req.generated_pages is None
    finally:
        db.close()
