"""Run 133's coverage determinism trap: cosmetics coerce, the retry varies.

The florist run's coverage_review failed twice on byte-identical `stop`
outputs — four validation errors, all `unsupported_additions[*].source_path`
/ `.source_excerpt` sent as explicit null where the schema default is "".
Two defects, two fixes, both pinned here:

* A null on a DEFAULTED field is absence, not substance — it coerces to the
  default instead of failing the whole review. Required fields (verdict,
  score, summary, code/severity/message, and GoalCoverage's proof-ledger
  source_path/source_excerpt/covered) stay strict.
* The one-shot malformation retry in generation.py is no longer a verbatim
  temperature-0 re-ask (which reproduces the malformation byte-for-byte): it
  appends a compact corrective instruction naming the first failure and bumps
  the telemetry attempt to 2 so the two coverage rows stay distinguishable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.coverage import (
    AppSpecCoverageReview,
    coverage_retry_instruction,
    review_app_spec_coverage,
)
from app.application.appspec.generation import ensure_approved_app_spec
from app.application.services.ai_context import current_ai_call
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.infrastructure.db.base import Base
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"
VALID_FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"
)


def _healthy_review() -> dict:
    return {
        "verdict": "pass",
        "score": 100,
        "summary": "The explicit booking goal is represented and traceable.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Customers can submit a booking and see confirmation.",
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


# --- run 133's exact shape: nulls on defaulted fields are cosmetic ---


def test_run133_null_cosmetics_no_longer_fail() -> None:
    payload = _healthy_review()
    payload["unsupported_additions"] = [
        {
            "code": "unsupported_addition",
            "severity": "minor",
            "source_path": None,
            "source_excerpt": None,
            "message": "The spec adds a wishlist the brief never asked for.",
        },
        {
            "code": "unsupported_addition",
            "severity": "minor",
            "source_path": None,
            "source_excerpt": None,
            "message": "The spec adds gift cards the brief never asked for.",
        },
    ]
    review = AppSpecCoverageReview.model_validate(payload)
    assert review.unsupported_additions[0].source_path == ""
    assert review.unsupported_additions[1].source_excerpt == ""


def test_null_lists_coerce_to_empty() -> None:
    payload = _healthy_review()
    payload["omissions"] = None
    payload["goal_coverage"][0]["evidence_ids"] = None
    payload["unsupported_additions"] = [
        {
            "code": "x",
            "severity": "minor",
            "message": "m",
            "app_spec_ids": None,
            "repair_instruction": None,
        }
    ]
    review = AppSpecCoverageReview.model_validate(payload)
    assert review.omissions == []
    assert review.goal_coverage[0].evidence_ids == []
    assert review.unsupported_additions[0].app_spec_ids == []
    assert review.unsupported_additions[0].repair_instruction == ""


def test_required_fields_stay_strict() -> None:
    for mutate in (
        lambda p: p.update(verdict=None),
        lambda p: p.update(summary=None),
        lambda p: p["goal_coverage"][0].update(source_path=None),
        lambda p: p["goal_coverage"][0].update(source_excerpt=None),
        lambda p: p["goal_coverage"][0].update(covered=None),
    ):
        payload = _healthy_review()
        mutate(payload)
        with pytest.raises(ValidationError):
            AppSpecCoverageReview.model_validate(payload)


# --- the retry is a DIFFERENT ask with a distinguishable telemetry row ---


class _ScopeAI:
    """Answers in sequence; records every ask's messages and ai_call scope."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.asks: list[list[dict]] = []
        self.scopes: list[tuple[str | None, int | None]] = []

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, _model: str, messages: list[dict], **_kwargs: Any) -> str:
        self.asks.append([dict(m) for m in messages])
        scope = current_ai_call()
        self.scopes.append(
            (getattr(scope, "writer", None), getattr(scope, "attempt", None))
        )
        return self.responses.pop(0)

    def is_available(self) -> bool:
        return True


def test_corrective_instruction_and_attempt_are_threaded() -> None:
    from app.application.appspec.fallback import build_fallback_app_spec

    spec = build_fallback_app_spec({"customer_input": {"business_name": "Acme"}})
    ai = _ScopeAI([json.dumps(_healthy_review())])
    review_app_spec_coverage(
        source_snapshot={"brief": "x"},
        app_spec=spec,
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(TEMPLATES_DIR),
        model="google/gemini-2.5-flash",
        max_tokens=512,
        attempt=2,
        corrective_instruction="FIX THE NULLS",
    )
    assert ai.scopes == [("coverage_review", 2)]
    assert len(ai.asks[0]) == 2
    assert ai.asks[0][1]["content"] == "FIX THE NULLS"


def test_generation_retry_varies_and_bumps_the_attempt() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    req = Request(
        business_name="Lumina Booking",
        business_description="A studio appointment booking product.",
        target_customers="Studio customers",
        main_problem="Appointments are arranged manually.",
        desired_outcome="Customers can submit a booking and see confirmation.",
        email="private@example.com",
        mvp_blueprint="Derived suggestion: add a booking flow.",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    # NON-cosmetic malformation: a null verdict is no review at all — leniency
    # must not save it, the varied retry must.
    broken_review = {**_healthy_review(), "verdict": None}
    ai = _ScopeAI(
        [
            json.dumps(spec_payload),
            json.dumps(broken_review),
            json.dumps(_healthy_review()),
        ]
    )
    result = ensure_approved_app_spec(
        db,
        req.id,
        ai,
        JinjaTemplateRenderer(TEMPLATES_DIR),
    )
    try:
        assert result.revision_record.status == "accepted"
        assert len(ai.asks) == 3
        coverage_scopes = [s for s in ai.scopes if s[0] == "coverage_review"]
        assert coverage_scopes == [("coverage_review", 1), ("coverage_review", 2)]
        # The retry is a different ask: original prompt PLUS the compact
        # corrective message naming the first failure.
        retry_messages = ai.asks[2]
        assert len(retry_messages) == 2
        assert "previous coverage review was rejected" in retry_messages[1]["content"]
        assert "validation error" in retry_messages[1]["content"]
        # The first coverage ask stays a single-message ask.
        assert len(ai.asks[1]) == 1
    finally:
        db.close()


def test_retry_instruction_names_the_failure() -> None:
    message = coverage_retry_instruction(Exception("boom went the verdict"))
    assert "boom went the verdict" in message
    assert '""' in message and "[]" in message  # the null guidance


# --- R1 at coverage_review: correlated transport gets ONE cross-provider ask ---


def _retryable_provider_error() -> Exception:
    from app.infrastructure.ai_providers.response_parser import (
        ProviderGenerationError,
        ProviderGenerationResult,
    )

    result = ProviderGenerationResult(
        provider="openrouter",
        model="google/gemini-2.5-flash",
        provider_request_id="req-x",
        response_format="unknown",
        text="",
        structured_payload=None,
        finish_reason="error",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        http_status=200,
        raw_payload_sha256="0" * 64,
        is_success=False,
        error_code="provider_empty_response",
        error_message_redacted="provider returned an empty error-cut stream",
        retryable=True,
        refusal=False,
        truncated=False,
        latency_ms=8,
    )
    error = ProviderGenerationError("stream cut in transit", result=result)
    assert error.retryable  # the fixture must be the retryable transport shape
    return error


class _WeatherAI:
    """Scripted provider whose asks can be cut in transit.

    "CUT" simulates the provider-error stream cut (finish_reason=error via
    last_completion_meta — request 118's shape); "RAISE" raises the retryable
    ProviderGenerationError (the in-transit cut — coverage's OTHER transport
    site); anything else is delivered healthy. Records model + scope per ask.
    """

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.models: list[str] = []
        self.scopes: list[tuple[str | None, int | None]] = []
        self._meta: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "test"

    def last_completion_meta(self) -> dict[str, Any]:
        return dict(self._meta)

    def ask_chat(self, model: str, messages: list[dict], **_kwargs: Any) -> str:
        self.models.append(model)
        scope = current_ai_call()
        self.scopes.append(
            (getattr(scope, "writer", None), getattr(scope, "attempt", None))
        )
        item = self.responses.pop(0)
        if item == "CUT":
            self._meta = {"finish_reason": "error"}
            return "{\"partial\": "
        if item == "RAISE":
            self._meta = {"finish_reason": "error"}
            raise _retryable_provider_error()
        self._meta = {"finish_reason": "stop"}
        return item

    def is_available(self) -> bool:
        return True


def _seed_generation_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    req = Request(
        business_name="Lumina Booking",
        business_description="A studio appointment booking product.",
        target_customers="Studio customers",
        main_problem="Appointments are arranged manually.",
        desired_outcome="Customers can submit a booking and see confirmation.",
        email="private@example.com",
        mvp_blueprint="Derived suggestion: add a booking flow.",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return db, req


def test_double_cut_coverage_takes_one_cross_provider_ask(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        settings,
        "APPSPEC_TRANSPORT_FALLBACK_MODEL",
        "anthropic/claude-haiku-4.5",
    )
    db, req = _seed_generation_db()
    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    ai = _WeatherAI(
        [
            json.dumps(spec_payload),
            "CUT",  # coverage attempt 1: cut in transit
            "CUT",  # attempt 2 (same model, varied): cut again — correlated
            json.dumps(_healthy_review()),  # attempt 3: the cross-provider rung
        ]
    )
    try:
        result = ensure_approved_app_spec(
            db, req.id, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
        )
        assert result.revision_record.status == "accepted"
        coverage_asks = [
            (model, scope)
            for model, scope in zip(ai.models, ai.scopes)
            if scope[0] == "coverage_review"
        ]
        assert [scope for _, scope in coverage_asks] == [
            ("coverage_review", 1),
            ("coverage_review", 2),
            ("coverage_review", 3),
        ]
        # Attempts 1-2 same model; attempt 3 is the fallback slot.
        assert coverage_asks[0][0] == coverage_asks[1][0]
        assert coverage_asks[2][0] == "anthropic/claude-haiku-4.5"
    finally:
        db.close()


def test_in_transit_raise_is_the_same_transport_class(monkeypatch) -> None:
    """Coverage's OTHER transport site — the retryable ProviderGenerationError
    re-raise — must classify identically: a RAISE then a CUT is two correlated
    cuts, and the rung fires."""

    from app.core.config import settings

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        settings,
        "APPSPEC_TRANSPORT_FALLBACK_MODEL",
        "anthropic/claude-haiku-4.5",
    )
    db, req = _seed_generation_db()
    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    ai = _WeatherAI(
        [
            json.dumps(spec_payload),
            "RAISE",  # attempt 1: retryable raise in transit
            "CUT",  # attempt 2: provider-error cut — correlated transport
            json.dumps(_healthy_review()),  # attempt 3: the rung
        ]
    )
    try:
        result = ensure_approved_app_spec(
            db, req.id, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
        )
        assert result.revision_record.status == "accepted"
        assert ai.models[-1] == "anthropic/claude-haiku-4.5"
        assert ai.scopes[-1] == ("coverage_review", 3)
    finally:
        db.close()


def test_triple_cut_coverage_fails_closed_with_the_transport_reason(
    monkeypatch,
) -> None:
    from app.application.appspec.generation import AppSpecGenerationError
    from app.core.config import settings

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    db, req = _seed_generation_db()
    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    ai = _WeatherAI([json.dumps(spec_payload), "CUT", "CUT", "CUT"])
    try:
        with pytest.raises(AppSpecGenerationError) as excinfo:
            ensure_approved_app_spec(
                db, req.id, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
            )
        assert "coverage_review_transport" in str(excinfo.value)
        assert len(ai.models) == 4  # authoring + exactly three coverage asks
    finally:
        db.close()


def test_double_malformation_never_reaches_the_rung(monkeypatch) -> None:
    """Quality failures never take a model fallback — two malformed reviews
    fail closed after attempt 2, no third ask, the malformed reason kept."""

    from app.application.appspec.generation import AppSpecGenerationError
    from app.core.config import settings

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    db, req = _seed_generation_db()
    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    broken_review = {**_healthy_review(), "verdict": None}
    ai = _WeatherAI(
        [
            json.dumps(spec_payload),
            json.dumps(broken_review),
            json.dumps(broken_review),
        ]
    )
    try:
        with pytest.raises(AppSpecGenerationError) as excinfo:
            ensure_approved_app_spec(
                db, req.id, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
            )
        assert "coverage_review_malformed" in str(excinfo.value)
        assert len(ai.models) == 3  # no rung ask
    finally:
        db.close()


def test_mixed_malformed_then_cut_fails_closed_without_the_rung(
    monkeypatch,
) -> None:
    """The rung needs transport proven CORRELATED — a quality failure followed
    by one cut is not two cuts, and the terminal reason names the cut."""

    from app.application.appspec.generation import AppSpecGenerationError
    from app.core.config import settings

    monkeypatch.setattr(settings, "APPSPEC_FALLBACK_ENABLED", False)
    db, req = _seed_generation_db()
    spec_payload = json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    broken_review = {**_healthy_review(), "verdict": None}
    ai = _WeatherAI([json.dumps(spec_payload), json.dumps(broken_review), "CUT"])
    try:
        with pytest.raises(AppSpecGenerationError) as excinfo:
            ensure_approved_app_spec(
                db, req.id, ai, JinjaTemplateRenderer(TEMPLATES_DIR)
            )
        assert "coverage_review_transport" in str(excinfo.value)
        assert len(ai.models) == 3  # no rung ask
    finally:
        db.close()
