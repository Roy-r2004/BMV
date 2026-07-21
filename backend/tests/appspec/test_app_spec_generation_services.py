"""Focused contract tests for AppSpec AI authoring and semantic review services."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import build_app_spec
from app.application.appspec.coverage import (
    coverage_requires_repair,
    review_app_spec_coverage,
)
from app.application.appspec.generation import (
    AppSpecCallBudgetExceeded,
    AppSpecGenerationError,
    _StageLimitedAIProvider,
    _source_reference_issues,
    app_spec_is_required,
    app_spec_should_run,
    app_spec_should_run_for_request,
    ensure_approved_app_spec,
)
from app.domain.models.app_spec import AppSpecRevision  # noqa: F401
from app.domain.models.request import Request
from app.domain.schemas.app_spec import AppSpec
from app.infrastructure.db.base import Base
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "app" / "templates"
VALID_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"


class _SequenceAI:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, _model: str, messages: list[dict], **_kwargs) -> str:
        self.calls += 1
        self.prompts.append(messages[-1]["content"])
        return self.responses.pop(0)

    def ask_vision(self, _model: str, _prompt: str, _image_path: str) -> str:
        self.calls += 1
        return self.responses.pop(0)

    def is_available(self) -> bool:
        return True


def _minimal_spec() -> dict:
    return {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Lumina Booking",
            "summary": "A booking product for Lumina Studio customers and staff.",
            "problem": "Customers currently arrange every appointment manually.",
            "desired_outcome": "Customers can confirm appointments without staff messages.",
            "target_users": ["Studio customers", "Reception staff"],
            "success_metrics": ["Customers see a durable booking confirmation"],
        },
        "requirements": [
            {
                "id": "req-book",
                "title": "Book an appointment",
                "description": "A customer can choose a service and confirm an appointment.",
                "priority": "must",
                "verification_mode": "interaction",
                "source_refs": ["customer_input.desired_outcome"],
            }
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "role-customer",
                "name": "Customer",
                "description": "A person booking a studio appointment.",
                "goals": ["Confirm an available appointment"],
                "default_page_id": "page-book",
            }
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "cap-book",
                "name": "Appointment booking",
                "description": "Choose and confirm an appointment.",
                "requirement_ids": ["req-book"],
                "role_ids": ["role-customer"],
                "entity_ids": [],
            }
        ],
        "pages": [
            {
                "id": "page-book",
                "name": "Book",
                "purpose": "Let a customer complete an appointment booking.",
                "route": "/book",
                "surface": "public",
                "primary": True,
                "role_ids": ["role-customer"],
                "capability_ids": ["cap-book"],
                "state_ids": ["state-confirmed"],
                "action_ids": [],
                "evidence_ids": ["evidence-confirmation"],
            }
        ],
        "states": [
            {
                "id": "state-confirmed",
                "page_id": "page-book",
                "name": "Confirmed",
                "description": "The confirmed appointment is visible.",
                "initial": True,
                "terminal": True,
                "evidence_ids": ["evidence-confirmation"],
            }
        ],
        "actions": [],
        "transitions": [],
        "evidence": [
            {
                "id": "evidence-confirmation",
                "page_id": "page-book",
                "name": "Booking confirmation",
                "description": "A confirmation reference and appointment details are visible.",
                "kind": "status",
                "capability_ids": ["cap-book"],
            }
        ],
        "journeys": [],
        "acceptance_tests": [
            {
                "id": "test-book",
                "name": "Booking confirmation is visible",
                "description": "Prove that the customer can see the confirmed appointment.",
                "requirement_ids": ["req-book"],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "The booking confirmation reference is visible.",
                        "page_id": "page-book",
                        "state_id": "state-confirmed",
                        "evidence_id": "evidence-confirmation",
                        "expected": "Booking reference",
                    }
                ],
            }
        ],
        "traceability": [
            {
                "requirement_id": "req-book",
                "capability_ids": ["cap-book"],
                "page_ids": ["page-book"],
                "evidence_ids": ["evidence-confirmation"],
                "journey_ids": [],
                "acceptance_test_ids": ["test-book"],
            }
        ],
        "deferred_scope": [],
    }


def _coverage(verdict: str = "pass", score: int = 100) -> dict:
    return {
        "verdict": verdict,
        "score": score,
        "summary": "The explicit booking goal is represented and traceable.",
        "goal_coverage": [
            {
                "source_path": "customer_input.desired_outcome",
                "source_excerpt": "Customers can book online",
                "covered": verdict == "pass",
                "requirement_ids": ["req-book"],
                "evidence_ids": ["evidence-confirmation"],
                "acceptance_test_ids": ["test-book"],
                "notes": "",
            }
        ],
        "omissions": [],
        "contradictions": [],
        "unsupported_additions": [],
        "mislabeled_assumptions": [],
        "open_question_gaps": [],
    }


def test_builder_uses_live_schema_and_separates_source_from_derived_context() -> None:
    ai = _SequenceAI([json.dumps(_minimal_spec())])
    spec = build_app_spec(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        derived_context={"derived_context": {"mvp_blueprint": "Suggested booking pages"}},
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(TEMPLATES_DIR),
    )
    assert spec.schema_version == "1.0"
    assert spec.requirements[0].id == "req-book"
    assert "IMMUTABLE CUSTOMER SOURCE" in ai.prompts[0]
    assert "DERIVED ANALYSIS (HELPFUL, NEVER AUTHORITATIVE)" in ai.prompts[0]
    assert '"$defs"' in ai.prompts[0], "the prompt must include AppSpec.model_json_schema()"


def test_coverage_ignores_explicitly_deferred_requirements() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    spec_ai = _SequenceAI([json.dumps(_minimal_spec())])
    spec = build_app_spec(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        derived_context={},
        ai_provider=spec_ai,
        template_renderer=renderer,
    )
    deferred_spec = AppSpec.model_validate(
        {
            **_minimal_spec(),
            "requirements": [
                *_minimal_spec()["requirements"],
                {
                    "id": "req-payment",
                    "title": "Online payment",
                    "description": "Pay during booking.",
                    "priority": "should",
                    "verification_mode": "integration",
                    "source_refs": ["customer_input.desired_outcome"],
                },
            ],
            "deferred_scope": [
                {
                    "id": "defer-payment",
                    "name": "Online payment",
                    "description": "Deferred payment integration.",
                    "reason": "Not in MVP.",
                    "requirement_ids": ["req-payment"],
                    "target_release": "Later",
                }
            ],
            "traceability": _minimal_spec()["traceability"],
        }
    )
    coverage_payload = _coverage()
    pass_ai = _SequenceAI([json.dumps(coverage_payload)])
    passed = review_app_spec_coverage(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        app_spec=deferred_spec,
        ai_provider=pass_ai,
        template_renderer=renderer,
    )
    assert coverage_requires_repair(
        passed,
        app_spec=deferred_spec,
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
    ) is False


def test_independent_coverage_review_fails_closed_on_uncovered_goal() -> None:
    renderer = JinjaTemplateRenderer(TEMPLATES_DIR)
    spec_ai = _SequenceAI([json.dumps(_minimal_spec())])
    spec = build_app_spec(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        derived_context={},
        ai_provider=spec_ai,
        template_renderer=renderer,
    )
    pass_ai = _SequenceAI([json.dumps(_coverage())])
    passed = review_app_spec_coverage(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        app_spec=spec,
        ai_provider=pass_ai,
        template_renderer=renderer,
    )
    assert coverage_requires_repair(passed) is False
    assert "ONLY SOURCE OF CONFIRMED INTENT" in pass_ai.prompts[0]

    empty_ledger_payload = _coverage()
    empty_ledger_payload["goal_coverage"] = []
    empty_ledger_ai = _SequenceAI([json.dumps(empty_ledger_payload)])
    empty_ledger = review_app_spec_coverage(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        app_spec=spec,
        ai_provider=empty_ledger_ai,
        template_renderer=renderer,
    )
    assert coverage_requires_repair(empty_ledger) is True

    failed_payload = _coverage("repair", 80)
    failed_payload["omissions"] = [
        {
            "code": "goal-omitted",
            "severity": "blocking",
            "source_path": "customer_input.desired_outcome",
            "source_excerpt": "Customers can book online",
            "app_spec_ids": [],
            "message": "No executable booking outcome is represented.",
            "repair_instruction": "Restore the booking requirement and proof chain.",
        }
    ]
    failed_ai = _SequenceAI([json.dumps(failed_payload)])
    failed = review_app_spec_coverage(
        source_snapshot={"customer_input": {"desired_outcome": "Customers can book online"}},
        app_spec=spec,
        ai_provider=failed_ai,
        template_renderer=renderer,
    )
    assert coverage_requires_repair(failed) is True


def test_stage_call_ceiling_and_rollout_policy() -> None:
    underlying = _SequenceAI(["one", "two"])
    limited = _StageLimitedAIProvider(underlying, max_calls=1)
    assert limited.ask_chat("model", [{"role": "user", "content": "one"}]) == "one"
    try:
        limited.ask_chat("model", [{"role": "user", "content": "two"}])
    except AppSpecCallBudgetExceeded:
        pass
    else:
        raise AssertionError("AppSpec stage call ceiling did not fail closed")
    assert underlying.calls == 1

    assert app_spec_should_run(mode="off") is False
    assert app_spec_should_run(mode="on") is True
    # Shadow still authors AppSpec, but must not enforce / block preview.
    assert app_spec_should_run(mode="shadow") is True
    assert app_spec_is_required(mode="shadow", is_new_request=True) is False
    assert app_spec_is_required(mode="on", is_new_request=True) is True
    assert app_spec_is_required(mode="on", is_new_request=False) is True
    assert app_spec_is_required(mode="off", is_new_request=True) is False
    assert app_spec_should_run_for_request(mode="on", is_new_request=True) is True
    assert app_spec_should_run_for_request(mode="shadow", is_new_request=True) is True
    assert app_spec_should_run_for_request(mode="on", is_new_request=False) is True
    assert app_spec_should_run_for_request(mode="off", is_new_request=True) is False

    source_spec = AppSpec.model_validate(
        json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))
    )
    assert _source_reference_issues(
        source_spec,
        {"customer_input": {"desired_outcome": "Book online"}},
    ) == []
    missing_source = _source_reference_issues(
        source_spec,
        {"customer_input": {"desired_outcome": None}},
    )
    assert missing_source[0]["code"] == "unresolved_requirement_source_ref"


def test_end_to_end_generation_accepts_persists_and_reuses() -> None:
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
    coverage_payload = _coverage()
    coverage_payload["goal_coverage"][0].update(
        {
            "source_excerpt": "Customers can submit a booking and see confirmation.",
            "requirement_ids": ["REQ-BOOK"],
            "evidence_ids": ["EVIDENCE-CONFIRMATION"],
            "acceptance_test_ids": ["TEST-BOOK"],
        }
    )
    ai = _SequenceAI([json.dumps(spec_payload), json.dumps(coverage_payload)])
    first = ensure_approved_app_spec(
        db,
        req.id,
        ai,
        JinjaTemplateRenderer(TEMPLATES_DIR),
    )
    assert first.reused is False
    assert first.revision_record.status == "accepted"
    assert first.revision_record.validation_passed is True
    assert first.revision_record.coverage_passed is True
    assert ai.calls == 2
    assert "private@example.com" not in first.revision_record.source_snapshot_json

    second_ai = _SequenceAI([])
    second = ensure_approved_app_spec(
        db,
        req.id,
        second_ai,
        JinjaTemplateRenderer(TEMPLATES_DIR),
    )
    assert second.reused is True
    assert second.revision_record.id == first.revision_record.id
    assert second_ai.calls == 0
    db.close()


def test_invalid_contract_exhausts_repairs_and_persists_rejection() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    req = Request(
        business_name="Broken Contract",
        business_description="A product request that still needs a valid contract.",
        desired_outcome="Users complete the main workflow.",
        email="private@example.com",
        mvp_blueprint="Derived workflow notes.",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    invalid = json.dumps({"schema_version": "1.0", "product_intent": {}})
    previous_repairs = settings.APPSPEC_MAX_REPAIR_ATTEMPTS
    previous_fallback = settings.APPSPEC_FALLBACK_ENABLED
    previous_heals = settings.APPSPEC_MAX_DETERMINISTIC_HEALS
    settings.APPSPEC_MAX_REPAIR_ATTEMPTS = 2
    settings.APPSPEC_FALLBACK_ENABLED = False
    settings.APPSPEC_MAX_DETERMINISTIC_HEALS = 0
    try:
        ai = _SequenceAI([invalid, invalid, invalid])
        try:
            ensure_approved_app_spec(
                db,
                req.id,
                ai,
                JinjaTemplateRenderer(TEMPLATES_DIR),
            )
        except AppSpecGenerationError as exc:
            assert "fallback is disabled" in str(exc).lower() or exc.revision_record is not None
        else:
            raise AssertionError("Invalid AppSpec was not rejected")
        assert ai.calls == 3
    finally:
        settings.APPSPEC_MAX_REPAIR_ATTEMPTS = previous_repairs
        settings.APPSPEC_FALLBACK_ENABLED = previous_fallback
        settings.APPSPEC_MAX_DETERMINISTIC_HEALS = previous_heals
        db.close()


def test_invalid_contract_accepts_fallback_when_enabled() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    req = Request(
        business_name="TradeForge",
        business_description="Retail stock trading desk.",
        desired_outcome="Traders place simulated orders and see P&L.",
        email="private@example.com",
        mvp_blueprint="Derived workflow notes.",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    invalid = json.dumps({"schema_version": "1.0", "product_intent": {}})
    previous_repairs = settings.APPSPEC_MAX_REPAIR_ATTEMPTS
    previous_fallback = settings.APPSPEC_FALLBACK_ENABLED
    previous_heals = settings.APPSPEC_MAX_DETERMINISTIC_HEALS
    settings.APPSPEC_MAX_REPAIR_ATTEMPTS = 1
    settings.APPSPEC_FALLBACK_ENABLED = True
    settings.APPSPEC_MAX_DETERMINISTIC_HEALS = 0
    try:
        ai = _SequenceAI([invalid, invalid])
        result = ensure_approved_app_spec(
            db,
            req.id,
            ai,
            JinjaTemplateRenderer(TEMPLATES_DIR),
        )
        assert result.revision_record.status == "accepted"
        meta = json.loads(result.revision_record.generation_metadata_json)
        assert meta.get("used_fallback") is True
        assert meta.get("terminal_reason") == "accepted_fallback"
        assert result.spec.product_intent.name == "TradeForge"
    finally:
        settings.APPSPEC_MAX_REPAIR_ATTEMPTS = previous_repairs
        settings.APPSPEC_FALLBACK_ENABLED = previous_fallback
        settings.APPSPEC_MAX_DETERMINISTIC_HEALS = previous_heals
        db.close()


if __name__ == "__main__":
    test_builder_uses_live_schema_and_separates_source_from_derived_context()
    test_coverage_ignores_explicitly_deferred_requirements()
    test_independent_coverage_review_fails_closed_on_uncovered_goal()
    test_stage_call_ceiling_and_rollout_policy()
    test_end_to_end_generation_accepts_persists_and_reuses()
    test_invalid_contract_exhausts_repairs_and_persists_rejection()
    test_invalid_contract_accepts_fallback_when_enabled()
    print("AppSpec generation service tests passed (7 tests)")
