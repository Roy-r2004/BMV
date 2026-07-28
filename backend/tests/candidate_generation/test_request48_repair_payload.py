"""Request 48: missing candidate-repair payload.

Production #48:
- AppSpec accepted, Design and Phase 3A completed
- primary business_components generation completed
- strict validation required one repair (component call 2/2)
- repair model z-ai/glm-5.2 through OpenRouter returned HTTP 200
- usage: 3987 prompt / 3100 completion / 7087 total tokens
- the adapter recorded provider_response_shape_invalid with the message
  "Provider choice message content was missing."
- TypeScript, Vite, Phase 4 and Phase 5 were never reached

The refusal branch and the #46 truncation branch both precede the missing
content branch and neither fired, so the response was a completed reasoning
turn that produced no assistant content: classification D, and no repair
payload in any field the old adapter could read.

This suite proves two things without any live provider call: every supported
payload location is now read, and a required ``submit_candidate_repair`` tool
call prevents the #48 response shape on a production-shaped adapter.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.builder import (
    CandidateStageError,
    repair_ai_batch,
)
from app.application.candidate_generation.call_budget import CandidateCallBudget
from app.application.candidate_generation.policy import repair_policy
from app.application.candidate_generation.repair_output import (
    REPAIR_CONTRACT_INVALID,
    parse_candidate_repair_output,
)
from app.application.candidate_generation.repair_payload import (
    REPAIR_CONTENT_PARTS_INVALID,
    REPAIR_MULTIPLE_TOOL_CALLS,
    REPAIR_PAYLOAD_MISSING,
    REPAIR_REFUSED,
    REPAIR_TOOL_ARGUMENTS_MISSING,
    REPAIR_TOOL_NAME,
    REPAIR_TOOL_NAME_INVALID,
    REPAIR_TOOL_SCHEMA,
    SOURCE_CONTENT_PARTS,
    SOURCE_CONTENT_STRING,
    SOURCE_PROVIDER_PARSED,
    SOURCE_TOOL_CALL,
    build_repair_tool_choice,
    build_repair_tool_spec,
    extract_candidate_repair_payload,
)
from app.core.config import settings
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.infrastructure.ai_providers.model_capabilities import (
    CAPABILITY_PROFILE_REVISION,
    resolve_model_capability,
)
from app.infrastructure.ai_providers.response_parser import (
    ChatMessageEnvelope,
    ProviderGenerationError,
    describe_chat_envelope,
    parse_openai_compatible_chat_response,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parent / "request48_repair_response.json"
    ).read_text(encoding="utf-8")
)

HOME_PATH = "src/components/business/CompHomeComponent.tsx"
BOOK_PATH = "src/components/business/CompBookComponent.tsx"

REPAIRED_HOME_SOURCE = (
    "export function CompHomeComponent() {\n"
    '  return <div data-bmv-component-id="COMP-HOME">Home</div>;\n'
    "}"
)


def _approved_files() -> tuple[GeneratedCandidateFile, ...]:
    return (
        GeneratedCandidateFile(
            path=HOME_PATH,
            file_kind="business_component",
            owner_contract_ids=["COMP-HOME"],
            source="export function CompHomeComponent() { return <div/>; }",
        ),
    )


def _original_batch() -> GeneratedCandidateBatch:
    return GeneratedCandidateBatch(
        schema_version="1.0",
        batch_kind="business_components",
        files=[
            GeneratedCandidateFile(
                path=BOOK_PATH,
                file_kind="business_component",
                owner_contract_ids=["COMP-BOOK"],
                source=(
                    "export function CompBookComponent() {\n"
                    '  return <div data-bmv-component-id="COMP-BOOK">Book</div>;\n'
                    "}"
                ),
            ),
            GeneratedCandidateFile(
                path=HOME_PATH,
                file_kind="business_component",
                owner_contract_ids=["COMP-HOME"],
                source=(
                    "export function CompHomeComponent() {\n"
                    "  return <div>Home without contract hook</div>;\n"
                    "}"
                ),
            ),
        ],
    )


def _canonical_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "batch_kind": "business_components",
        "files": [
            {
                "path": HOME_PATH,
                "file_kind": "business_component",
                "owner_contract_ids": ["COMP-HOME"],
                "source": REPAIRED_HOME_SOURCE,
            }
        ],
    }


def _tool_arguments(**overrides: Any) -> dict[str, Any]:
    payload = {
        "files": [
            {
                "path": HOME_PATH,
                "owner": "COMP-HOME",
                "source": REPAIRED_HOME_SOURCE,
            }
        ]
    }
    payload.update(overrides)
    return payload


def _body(message: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    body = {
        "id": "gen-test",
        "object": "chat.completion",
        "model": "z-ai/glm-5.2",
        "choices": [
            {"index": 0, "finish_reason": "stop", "message": message}
        ],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "total_tokens": 300,
        },
    }
    body.update(overrides)
    return body


def _tool_call_message(
    *,
    name: str = REPAIR_TOOL_NAME,
    arguments: Any = None,
    count: int = 1,
) -> dict[str, Any]:
    encoded = (
        arguments
        if isinstance(arguments, str) or arguments is None
        else json.dumps(arguments)
    )
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{index}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": "" if encoded is None else encoded,
                },
            }
            for index in range(count)
        ],
    }


def _envelope(message: dict[str, Any], **overrides: Any) -> ChatMessageEnvelope:
    return describe_chat_envelope(_body(message, **overrides))


def _extract(message: dict[str, Any], **kwargs: Any):
    supports_parsed = kwargs.pop("supports_provider_parsed", False)
    return extract_candidate_repair_payload(
        envelope=_envelope(message, **kwargs),
        batch_kind="business_components",
        approved_files=_approved_files(),
        supports_provider_parsed=supports_parsed,
    )


def _contract(extraction) -> Any:
    return parse_candidate_repair_output(
        extraction.text,
        batch_kind="business_components",
        approved_files=_approved_files(),
        original_paths=(BOOK_PATH, HOME_PATH),
        structured_payload=extraction.structured_payload,
        response_field_present=extraction.response_field_present,
    )


# --------------------------------------------------------------------------
# 1. Request #48 envelope classification
# --------------------------------------------------------------------------


def test_request48_fixture_pins_the_persisted_production_evidence() -> None:
    assert FIXTURE["model"] == "z-ai/glm-5.2"
    assert FIXTURE["id"] == "gen-1785235622-ZhzKJFqYsLDixAyZJiZN"
    assert FIXTURE["usage"] == {
        "prompt_tokens": 3987,
        "completion_tokens": 3100,
        "total_tokens": 7087,
    }
    assert sorted(key for key in FIXTURE if not key.startswith("_")) == [
        "choices",
        "created",
        "id",
        "model",
        "object",
        "provider",
        "service_tier",
        "system_fingerprint",
        "usage",
    ]


def test_request48_envelope_classifies_as_reasoning_only() -> None:
    envelope = describe_chat_envelope(FIXTURE)
    assert envelope.choice_count == 1
    assert envelope.finish_reason == "stop"
    assert envelope.content_kind == "null"
    assert envelope.content_text is None
    assert envelope.tool_calls == ()
    assert envelope.has_parsed is False
    assert envelope.refusal_text == ""
    assert envelope.has_reasoning is True
    assert envelope.has_structured_payload is False


def test_before_the_old_adapter_raised_provider_response_shape_invalid() -> None:
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="z-ai/glm-5.2",
        http_status=200,
        body=FIXTURE,
        raw_text=json.dumps(FIXTURE),
    )
    assert result.is_success is False
    assert result.error_code == "provider_response_shape_invalid"
    assert result.error_message_redacted == (
        "Provider choice message content was missing."
    )
    # The two branches that precede it did not fire.
    assert result.refusal is False
    assert result.truncated is False
    assert result.output_tokens == 3100
    with pytest.raises(ProviderGenerationError):
        raise ProviderGenerationError(result.error_message_redacted, result=result)


def test_after_request48_is_classified_as_payload_missing_not_shape_invalid() -> None:
    extraction = extract_candidate_repair_payload(
        envelope=describe_chat_envelope(FIXTURE),
        batch_kind="business_components",
        approved_files=_approved_files(),
    )
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_PAYLOAD_MISSING
    assert extraction.response_field_present is False
    assert extraction.diagnostics["reasoning_only"] is True


def test_request48_diagnostics_never_expose_reasoning_or_source() -> None:
    extraction = extract_candidate_repair_payload(
        envelope=describe_chat_envelope(FIXTURE),
        batch_kind="business_components",
        approved_files=_approved_files(),
    )
    blob = canonical_json(extraction.diagnostics)
    assert "redacted reasoning trace" not in blob
    assert "CompHomeComponent" not in blob
    assert extraction.diagnostics["envelope"]["has_reasoning"] is True
    assert extraction.diagnostics["envelope"]["reasoning_chars"] > 0


# --------------------------------------------------------------------------
# 2. Extraction order and every supported payload location
# --------------------------------------------------------------------------


def test_content_string_payload_is_extracted() -> None:
    extraction = _extract(
        {"role": "assistant", "content": json.dumps(_canonical_payload())}
    )
    assert extraction.ok is True
    assert extraction.source == SOURCE_CONTENT_STRING
    assert _contract(extraction).ok is True


def test_content_text_part_array_is_joined_in_order() -> None:
    payload = json.dumps(_canonical_payload())
    half = len(payload) // 2
    extraction = _extract(
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": payload[:half]},
                {"type": "text", "text": payload[half:]},
            ],
        }
    )
    assert extraction.ok is True
    assert extraction.source == SOURCE_CONTENT_PARTS
    assert extraction.text == payload
    assert _contract(extraction).ok is True


def test_approved_tool_call_arguments_are_extracted() -> None:
    extraction = _extract(_tool_call_message(arguments=_tool_arguments()))
    assert extraction.ok is True
    assert extraction.source == SOURCE_TOOL_CALL
    assert extraction.structured_payload["batch_kind"] == "business_components"
    parsed = _contract(extraction)
    assert parsed.ok is True
    assert [item.path for item in parsed.batch.files] == [HOME_PATH]
    assert parsed.batch.files[0].source == REPAIRED_HOME_SOURCE
    assert parsed.batch.files[0].owner_contract_ids == ("COMP-HOME",)


def test_missing_content_with_a_valid_tool_call_still_extracts() -> None:
    message = _tool_call_message(arguments=_tool_arguments())
    message.pop("content")
    extraction = _extract(message)
    assert extraction.ok is True
    assert extraction.source == SOURCE_TOOL_CALL
    assert _contract(extraction).ok is True


def test_provider_native_parsed_object_is_used_when_supported() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "parsed": _canonical_payload(),
    }
    extraction = _extract(message, supports_provider_parsed=True)
    assert extraction.ok is True
    assert extraction.source == SOURCE_PROVIDER_PARSED
    assert _contract(extraction).ok is True


def test_provider_native_parsed_object_is_ignored_when_unsupported() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "parsed": _canonical_payload(),
    }
    extraction = _extract(message, supports_provider_parsed=False)
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_PAYLOAD_MISSING


def test_tool_call_wins_over_content_when_both_are_present() -> None:
    message = _tool_call_message(arguments=_tool_arguments())
    message["content"] = json.dumps(_canonical_payload())
    extraction = _extract(message)
    assert extraction.source == SOURCE_TOOL_CALL


# --------------------------------------------------------------------------
# 3. Typed rejections
# --------------------------------------------------------------------------


def test_multiple_tool_calls_are_rejected_and_never_merged() -> None:
    extraction = _extract(_tool_call_message(arguments=_tool_arguments(), count=2))
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_MULTIPLE_TOOL_CALLS
    assert extraction.structured_payload is None


def test_incorrect_tool_name_is_rejected() -> None:
    extraction = _extract(
        _tool_call_message(name="write_files", arguments=_tool_arguments())
    )
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_TOOL_NAME_INVALID
    assert extraction.diagnostics["observed_tool_name"] == "write_files"


def test_missing_tool_arguments_are_rejected() -> None:
    extraction = _extract(_tool_call_message(arguments=""))
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_TOOL_ARGUMENTS_MISSING


def test_unparseable_tool_arguments_are_rejected_without_repairing_json() -> None:
    extraction = _extract(_tool_call_message(arguments='{"files": ['))
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_TOOL_ARGUMENTS_MISSING
    assert extraction.structured_payload is None


def test_refusal_is_rejected() -> None:
    extraction = _extract(
        {"role": "assistant", "content": None, "refusal": "I cannot help with that."}
    )
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_REFUSED


def test_reasoning_only_response_is_rejected() -> None:
    extraction = _extract(
        {
            "role": "assistant",
            "content": None,
            "reasoning": "thinking about the fix",
        }
    )
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_PAYLOAD_MISSING
    assert extraction.diagnostics["reasoning_only"] is True


def test_reasoning_content_parts_are_never_promoted_to_output() -> None:
    extraction = _extract(
        {
            "role": "assistant",
            "content": [
                {"type": "reasoning", "text": json.dumps(_canonical_payload())}
            ],
        }
    )
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_CONTENT_PARTS_INVALID


def test_content_parts_without_any_text_are_rejected() -> None:
    extraction = _extract({"role": "assistant", "content": [{"type": "image_url"}]})
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_CONTENT_PARTS_INVALID


def test_genuinely_empty_response_is_rejected() -> None:
    extraction = _extract({"role": "assistant", "content": ""})
    assert extraction.ok is False
    assert extraction.error_code == REPAIR_PAYLOAD_MISSING
    assert extraction.response_field_present is False


def test_invalid_repair_contract_is_rejected_on_the_tool_transport() -> None:
    arguments = {"files": [{"path": HOME_PATH, "owner": "COMP-HOME"}]}
    extraction = _extract(_tool_call_message(arguments=arguments))
    assert extraction.ok is True
    parsed = _contract(extraction)
    assert parsed.ok is False
    assert parsed.error_code == REPAIR_CONTRACT_INVALID


def test_unknown_file_is_rejected_on_the_tool_transport() -> None:
    arguments = _tool_arguments(
        files=[
            {
                "path": "src/components/business/CompGhost.tsx",
                "owner": "COMP-GHOST",
                "source": REPAIRED_HOME_SOURCE,
            }
        ]
    )
    extraction = _extract(_tool_call_message(arguments=arguments))
    parsed = _contract(extraction)
    assert parsed.ok is False
    assert parsed.violation == "unknown_path"
    assert parsed.is_ownership_violation is True


def test_ownership_transfer_is_rejected_on_the_tool_transport() -> None:
    arguments = _tool_arguments(
        files=[
            {
                "path": HOME_PATH,
                "owner": "COMP-BOOK",
                "source": REPAIRED_HOME_SOURCE,
            }
        ]
    )
    extraction = _extract(_tool_call_message(arguments=arguments))
    parsed = _contract(extraction)
    assert parsed.ok is False
    assert parsed.violation == "ownership_changed"


def test_file_outside_the_approved_subset_is_rejected_on_the_tool_transport() -> None:
    arguments = _tool_arguments(
        files=[
            {
                "path": BOOK_PATH,
                "owner": "COMP-BOOK",
                "source": REPAIRED_HOME_SOURCE,
            }
        ]
    )
    extraction = _extract(_tool_call_message(arguments=arguments))
    parsed = _contract(extraction)
    assert parsed.ok is False
    assert parsed.violation == "outside_repair_subset"


def test_duplicate_paths_are_rejected_on_the_tool_transport() -> None:
    row = {
        "path": HOME_PATH,
        "owner": "COMP-HOME",
        "source": REPAIRED_HOME_SOURCE,
    }
    extraction = _extract(_tool_call_message(arguments=_tool_arguments(files=[row, row])))
    parsed = _contract(extraction)
    assert parsed.ok is False
    assert parsed.error_code == REPAIR_CONTRACT_INVALID


# --------------------------------------------------------------------------
# 4. Capability profile and the required tool request
# --------------------------------------------------------------------------


def test_capability_profile_declares_repair_tool_support_explicitly() -> None:
    assert CAPABILITY_PROFILE_REVISION == "2026-07-28.candidate-provider.4"
    repair = resolve_model_capability(settings.V2_CANDIDATE_REPAIR_MODEL)
    assert repair.model == "z-ai/glm-5.2"
    assert repair.supports_tools is True
    assert repair.supports_repair_tool_calling is True
    unknown = resolve_model_capability("vendor/not-a-real-model")
    assert unknown.known is False
    assert unknown.supports_tools is False
    assert unknown.supports_repair_tool_calling is False


def test_repair_tool_spec_matches_the_required_schema() -> None:
    spec = build_repair_tool_spec()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == REPAIR_TOOL_NAME
    assert spec["function"]["parameters"] == REPAIR_TOOL_SCHEMA
    assert REPAIR_TOOL_SCHEMA["required"] == ["files"]
    item = REPAIR_TOOL_SCHEMA["properties"]["files"]["items"]
    assert item["required"] == ["path", "owner", "source"]
    assert item["additionalProperties"] is False
    assert REPAIR_TOOL_SCHEMA["additionalProperties"] is False
    assert build_repair_tool_choice() == {
        "type": "function",
        "function": {"name": REPAIR_TOOL_NAME},
    }


# --------------------------------------------------------------------------
# 5. Production-shaped adapter behaviour
# --------------------------------------------------------------------------


class _AdapterAI:
    """Fake OpenRouter adapter that runs the real central response parser."""

    name = "openrouter"

    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body
        self.calls: list[dict[str, Any]] = []
        self._envelope: ChatMessageEnvelope | None = None
        self._meta: dict[str, Any] | None = None

    def ask_chat(
        self,
        model,
        messages,
        max_tokens=None,
        temperature=None,
        *,
        timeout_seconds=None,
        transport_attempts=None,
        response_format=None,
        tools=None,
        tool_choice=None,
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "prompt": messages[0]["content"],
                "max_tokens": max_tokens,
                "response_format": response_format,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        parsed = parse_openai_compatible_chat_response(
            provider="openrouter",
            model=model,
            http_status=200,
            body=self._body,
            raw_text=json.dumps(self._body),
        )
        self._envelope = parsed.envelope
        self._meta = {"finish_reason": parsed.finish_reason}
        if not parsed.is_success:
            raise ProviderGenerationError(
                parsed.error_message_redacted, result=parsed
            )
        return parsed.text

    def last_completion_meta(self) -> dict[str, Any] | None:
        return dict(self._meta) if self._meta else None

    def last_response_envelope(self) -> ChatMessageEnvelope | None:
        return self._envelope

    def is_available(self) -> bool:
        return True


def _run_repair(ai) -> tuple[Any, CandidateCallBudget]:
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    built = repair_ai_batch(
        request_id=48,
        batch_stage="business_components",
        policy=repair_policy(),
        batch=_original_batch(),
        diagnostics=(
            canonical_json(
                {
                    "code": "missing_component_hook",
                    "path": HOME_PATH,
                    "related_ids": ["COMP-HOME"],
                }
            ),
        ),
        canonical_bindings={
            "business_component_plan": {
                "components": [
                    {"component_id": "COMP-HOME", "purpose": "home"},
                    {"component_id": "COMP-BOOK", "purpose": "book"},
                ]
            }
        },
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(settings.TEMPLATES_DIR),
        prompt_template="prompts/v2_candidate_repair.j2",
        phase_deadline=time.monotonic() + 60,
        call_budget=budget,
        candidate_revision_uuid="req48",
    )
    return built, budget


def test_repair_requires_the_submit_tool_on_a_supporting_model() -> None:
    ai = _AdapterAI(_body(_tool_call_message(arguments=_tool_arguments())))
    _built, _budget = _run_repair(ai)
    call = ai.calls[0]
    assert call["model"] == "z-ai/glm-5.2"
    assert call["tools"] == [build_repair_tool_spec()]
    assert call["tool_choice"] == build_repair_tool_choice()
    # Unsupported parameters are never combined with the required tool.
    assert call["response_format"] is None


def test_request48_regression_tool_call_repairs_and_merges_the_subset() -> None:
    ai = _AdapterAI(_body(_tool_call_message(arguments=_tool_arguments())))
    built, budget = _run_repair(ai)
    merged = {item.path: item.source for item in built.batch.files}
    assert set(merged) == {BOOK_PATH, HOME_PATH}
    assert merged[HOME_PATH] == REPAIRED_HOME_SOURCE
    assert 'data-bmv-component-id="COMP-BOOK"' in merged[BOOK_PATH]
    assert built.metrics.repair_call_count == 1
    assert len(ai.calls) == 1
    snapshot = budget.snapshot()
    assert snapshot["total_used"] == 2
    assert snapshot["substage_used"]["business_components"] == 2


def test_request48_response_shape_now_fails_as_payload_missing() -> None:
    ai = _AdapterAI(FIXTURE)
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    # The old adapter could not even reach the repair layer; the typed code is
    # now the accurate one and never the generic shape error.
    assert exc.value.provider_error_code == REPAIR_PAYLOAD_MISSING
    assert exc.value.provider_error_code != "provider_response_shape_invalid"
    assert len(ai.calls) == 1


def test_transport_failures_keep_their_own_provider_codes() -> None:
    ai = _AdapterAI(
        {
            "id": "gen-test",
            "object": "chat.completion",
            "model": "z-ai/glm-5.2",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "length",
                    "message": {"role": "assistant", "content": None},
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 10000,
                "total_tokens": 10100,
            },
        }
    )
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    assert exc.value.provider_error_code == "provider_truncated_output"


def test_required_tool_prevents_the_request48_shape_on_the_adapter() -> None:
    """The #48 body is what a model returns when nothing forces a payload.

    With the tool required, the same model's response carries the payload in
    ``tool_calls`` and the central parser no longer treats a null ``content``
    as an invalid shape.
    """

    with_tool = dict(FIXTURE)
    message = dict(FIXTURE["choices"][0]["message"])
    message["tool_calls"] = _tool_call_message(arguments=_tool_arguments())[
        "tool_calls"
    ]
    with_tool["choices"] = [
        {**FIXTURE["choices"][0], "finish_reason": "tool_calls", "message": message}
    ]
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model="z-ai/glm-5.2",
        http_status=200,
        body=with_tool,
        raw_text=json.dumps(with_tool),
    )
    assert result.is_success is True
    assert result.error_code == ""
    assert result.text == ""
    assert [call.name for call in result.tool_calls] == [REPAIR_TOOL_NAME]

    ai = _AdapterAI(with_tool)
    built, budget = _run_repair(ai)
    merged = {item.path: item.source for item in built.batch.files}
    assert merged[HOME_PATH] == REPAIRED_HOME_SOURCE
    assert budget.snapshot()["total_used"] == 2


def test_repair_falls_back_to_content_when_the_provider_ignores_the_tool() -> None:
    ai = _AdapterAI(
        _body(
            {"role": "assistant", "content": json.dumps(_canonical_payload())}
        )
    )
    built, _budget = _run_repair(ai)
    merged = {item.path: item.source for item in built.batch.files}
    assert merged[HOME_PATH] == REPAIRED_HOME_SOURCE


def test_repair_failure_keeps_caps_at_four_two_two_and_one_call() -> None:
    ai = _AdapterAI(FIXTURE)
    with pytest.raises(CandidateStageError):
        _run_repair(ai)
    assert len(ai.calls) == 1
    budget = CandidateCallBudget.create()
    assert budget.remaining_total() == 4
    snapshot = budget.snapshot()
    assert snapshot["substage_caps"]["business_components"] == 2
    assert snapshot["substage_caps"]["pages"] == 2


def test_repair_failure_diagnostics_stay_sanitized() -> None:
    ai = _AdapterAI(FIXTURE)
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    blob = " ".join(exc.value.diagnostics)
    assert "redacted reasoning trace" not in blob
    assert REPAIRED_HOME_SOURCE not in blob


def test_unsupported_model_receives_no_tool_parameters() -> None:
    profile = resolve_model_capability("vendor/not-a-real-model")
    assert profile.supports_repair_tool_calling is False
    assert profile.supports_json_object is False
