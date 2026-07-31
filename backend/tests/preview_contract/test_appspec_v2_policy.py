from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.appspec.generation import (
    AppSpecGenerationError,
    ensure_approved_app_spec,
)
from app.application.appspec.policy import (
    AppSpecGenerationPolicy,
    ModelFamilyPolicyError,
    model_family,
    resolve_model_assignment,
    v2_app_spec_policy,
)
from app.application.appspec.repository import (
    AppSpecRepository,
    app_spec_revision_is_complete,
)
from app.application.appspec.source import capture_request_source_v2
from app.application.preview_contract.product_strategy import (
    project_product_strategy,
)
from app.application.preview_contract.repository import (
    PreviewContractRepository,
    strategy_sha256,
)
from app.core.config import settings
from app.domain.models import (  # noqa: F401
    AppSpecRevision,
    CustomerSourceArtifact,
    ProductStrategyRevision,
    Request,
)
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


class _NeverPaidAI:
    name = "fixture-only"

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[str] = []

    def ask_chat(self, model: str, _messages: list[dict], **_kwargs) -> str:
        self.calls.append(model)
        if not self.responses:
            raise AssertionError("fixture attempted an unplanned provider call")
        return self.responses.pop(0)

    def ask_vision(self, *_args, **_kwargs) -> str:
        raise AssertionError("fixture attempted a vision provider call")

    def is_available(self) -> bool:
        return True


def _request(request_id: int = 701) -> Request:
    return Request(
        id=request_id,
        business_name="Lumina Studio",
        industry="Wellness",
        business_description="Customers book appointments online.",
        target_customers="Studio customers",
        main_problem="Booking is manual.",
        desired_outcome="Customers can book online.",
        project_type="new",
        email="owner@example.com",
        mvp_blueprint="A derived booking product.",
        created_at=datetime(2026, 7, 24, 11, 0, 0),
    )


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def _renderer() -> JinjaTemplateRenderer:
    return JinjaTemplateRenderer(settings.TEMPLATES_DIR)


@pytest.mark.parametrize(
    ("model", "family"),
    [
        ("google/gemini-2.5-flash", "google"),
        ("anthropic/claude-haiku-4.5", "anthropic"),
        ("openai/gpt-5", "openai"),
        ("qwen2.5-coder:7b", "qwen"),
        ("llama3.1:8b", "meta-llama"),
        ("z-ai/glm-5.2", "z-ai"),
    ],
)
def test_model_family_normalization(model: str, family: str) -> None:
    assert model_family(model) == family


def test_unknown_and_same_family_assignments_fail_closed() -> None:
    with pytest.raises(ModelFamilyPolicyError, match="Unknown"):
        resolve_model_assignment(
            AppSpecGenerationPolicy(
                name="v2_strict",
                require_distinct_coverage_family=True,
                author_model="vendor/mystery-model",
                repair_model="google/gemini-2.5-flash",
                coverage_model="anthropic/claude-haiku-4.5",
            )
        )
    with pytest.raises(ModelFamilyPolicyError, match="different model family"):
        resolve_model_assignment(
            AppSpecGenerationPolicy(
                name="v2_strict",
                require_distinct_coverage_family=True,
                author_model="google/gemini-2.5-flash",
                repair_model="google/gemini-2.5-flash",
                coverage_model="google/gemini-2.5-pro",
            )
        )


def test_unknown_family_is_rejected_before_any_provider_call() -> None:
    ai = _NeverPaidAI()
    with pytest.raises(ModelFamilyPolicyError, match="Unknown"):
        ensure_approved_app_spec(
            object(),  # family validation occurs before DB access
            999,
            ai,
            object(),
            policy=AppSpecGenerationPolicy(
                name="v2_strict",
                allow_fallback=False,
                require_complete=True,
                require_distinct_coverage_family=True,
                author_model="unknown/private-author",
                repair_model="google/gemini-2.5-flash",
                coverage_model="anthropic/claude-haiku-4.5",
                metadata={"product_strategy_sha256": "a" * 64},
            ),
        )
    assert ai.calls == []


def test_v2_generation_rejects_fallback_instead_of_marking_it_complete(
    monkeypatch,
) -> None:
    db = _db()
    try:
        req = _request()
        db.add(req)
        db.commit()
        source = capture_request_source_v2(req)
        strategy = project_product_strategy(req, source)
        inputs = PreviewContractRepository(db).stage_inputs(
            source=source,
            strategy=strategy,
        )

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
        # Two responses, not one: `APPSPEC_AUTHORING_MALFORMED_RETRY_MAX` gives the
        # authoring loop one re-ask on unparseable output, and that budget is
        # independent of `APPSPEC_MAX_REPAIR_ATTEMPTS` (which governs *repair* of a
        # parsed-but-invalid spec). Scripting one response made the fixture's own
        # "unplanned provider call" assertion fire before the policy under test
        # could, which is why this was the last row on KNOWN_TEST_FAILURES.md.
        ai = _NeverPaidAI(["not valid json", "still not valid json"])

        with pytest.raises(AppSpecGenerationError, match="fallback is disabled"):
            ensure_approved_app_spec(
                db,
                req.id,
                ai,
                _renderer(),
                source_snapshot_override=source.model_dump(mode="json"),
                derived_context_override={
                    "product_strategy": strategy.model_dump(mode="json")
                },
                policy=v2_app_spec_policy(
                    source_artifact_id=inputs.source.id,
                    product_strategy_revision_id=inputs.strategy.id,
                    product_strategy_sha256=strategy_sha256(strategy),
                ),
            )

        attempt = AppSpecRepository(db).latest_attempt(req.id)
        assert attempt is not None
        assert attempt.status == "rejected"
        assert app_spec_revision_is_complete(attempt) is False
        assert AppSpecRepository(db).latest_complete(
            req.id,
            source_sha256=inputs.source.sha256,
            schema_version=settings.APPSPEC_SCHEMA_VERSION,
            product_strategy_sha256=inputs.strategy.strategy_sha256,
        ) is None
        # The authoring model, then its one malformed-output re-ask. What matters
        # for this policy is that *no other* model was paid — no repair model, no
        # coverage model, no fallback — and that both calls went to the authoring
        # model the policy assigned.
        assert ai.calls == ["google/gemini-2.5-flash", "google/gemini-2.5-flash"]
    finally:
        db.close()
