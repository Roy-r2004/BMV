"""Request 46: candidate component-repair response shape.

Production #46:
- AppSpec, Design, Phase 3A and primary component generation completed
- strict validation required one repair (component call 2/2)
- repair model z-ai/glm-5.2 returned no choices[0].message.content
- completion_tokens landed on the configured repair cap exactly (10000)
- the central provider parser recorded provider_response_shape_invalid
- Phase 4 and Phase 5 were never reached

This suite proves the before/after classification and the canonical repair
parser without any live provider call.
"""
from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

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
    REPAIR_ENVELOPE_INVALID,
    REPAIR_JSON_SYNTAX_INVALID,
    REPAIR_JSON_TRUNCATED,
    REPAIR_NO_JSON_PAYLOAD,
    REPAIR_RESPONSE_FIELD_MISSING,
    VIOLATION_BATCH_KIND_MISMATCH,
    VIOLATION_FILE_KIND_CHANGED,
    VIOLATION_OUTSIDE_SUBSET,
    VIOLATION_OWNERSHIP_CHANGED,
    VIOLATION_UNKNOWN_PATH,
    parse_candidate_repair_output,
)
from app.application.candidate_generation.service import (
    build_v2_candidate_revision,
)
from app.core.config import settings
from app.domain.schemas.preview_candidate import (
    GeneratedCandidateBatch,
    GeneratedCandidateFile,
)
from app.infrastructure.ai_providers.model_capabilities import (
    resolve_model_capability,
)
from app.infrastructure.ai_providers.response_parser import (
    parse_openai_compatible_chat_response,
)
from app.infrastructure.templating.renderer import JinjaTemplateRenderer
from app.shared.json_utils import extract_json_from_text
from tests.candidate_generation.helpers import (
    CandidateFixtureAI,
    prepare_phase3a,
)

FIXTURE = json.loads(
    (
        Path(__file__).resolve().parent / "request46_repair_response.json"
    ).read_text(encoding="utf-8")
)

HOME_PATH = "src/components/business/CompHomeComponent.tsx"
BOOK_PATH = "src/components/business/CompBookComponent.tsx"

# Stored source form after StrictDesignModel whitespace strip.
REPAIRED_HOME_SOURCE = (
    "export function CompHomeComponent() {\n"
    '  const label = "{ not json }";\n'
    '  return <div data-bmv-component-id="COMP-HOME">{label}</div>;\n'
    "}"
)


@pytest.fixture
def isolated_candidate_paths(monkeypatch):
    root = Path(__file__).resolve().parent / ".runtime" / uuid.uuid4().hex
    monkeypatch.setattr(settings, "PREVIEW_CANDIDATES_DIR", root / "candidates")
    monkeypatch.setattr(settings, "PREVIEW_APPS_DIR", root / "accepted")
    yield root
    if root.exists():
        shutil.rmtree(root)


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


def _repaired_file(**overrides) -> dict:
    payload = {
        "path": HOME_PATH,
        "file_kind": "business_component",
        "owner_contract_ids": ["COMP-HOME"],
        "source": REPAIRED_HOME_SOURCE,
    }
    payload.update(overrides)
    return payload


def _canonical_payload(**overrides) -> dict:
    payload = {
        "schema_version": "1.0",
        "batch_kind": "business_components",
        "files": [_repaired_file()],
    }
    payload.update(overrides)
    return payload


def _parse(raw, **kwargs):
    return parse_candidate_repair_output(
        raw,
        batch_kind="business_components",
        approved_files=_approved_files(),
        original_paths=(BOOK_PATH, HOME_PATH),
        **kwargs,
    )


def _legacy_parse_batch(raw: str) -> GeneratedCandidateBatch:
    """Pre-fix repair parse: extract JSON then validate the batch schema."""
    payload = extract_json_from_text(raw)
    if not isinstance(payload, dict):
        raise ValueError("Candidate output must be one JSON object.")
    return GeneratedCandidateBatch.model_validate(payload)


def test_request46_fixture_pins_the_production_evidence() -> None:
    observed = FIXTURE["observed"]
    assert FIXTURE["model"] == "z-ai/glm-5.2"
    assert FIXTURE["adapter_response_field"] == "choices[0].message.content"
    assert observed["recorded_error_code"] == "provider_response_shape_invalid"
    assert observed["content_present"] is False
    assert (
        observed["completion_tokens"] == FIXTURE["configured_repair_max_tokens"]
    )
    assert settings.V2_CANDIDATE_REPAIR_MAX_TOKENS == 10000


def test_request46_before_missing_content_without_cap_is_shape_invalid() -> None:
    body = json.loads(json.dumps(FIXTURE["provider_body"]))
    body["choices"][0]["finish_reason"] = "stop"
    body["choices"][0]["native_finish_reason"] = "stop"
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model=FIXTURE["model"],
        http_status=200,
        body=body,
        raw_text=json.dumps(body),
    )
    assert result.is_success is False
    assert result.error_code == "provider_response_shape_invalid"


def test_request46_after_cap_exhausted_response_is_truncation() -> None:
    body = FIXTURE["provider_body"]
    result = parse_openai_compatible_chat_response(
        provider="openrouter",
        model=FIXTURE["model"],
        http_status=200,
        body=body,
        raw_text=json.dumps(body),
    )
    assert result.is_success is False
    assert result.error_code == "provider_truncated_output"
    assert result.truncated is True
    assert result.finish_reason == "length"
    assert result.output_tokens == FIXTURE["observed"]["completion_tokens"]
    assert result.input_tokens == FIXTURE["observed"]["prompt_tokens"]


def test_request46_empty_repair_text_at_cap_is_typed_truncation() -> None:
    result = _parse("", finish_reason="length")
    assert result.ok is False
    assert result.error_code == REPAIR_JSON_TRUNCATED
    assert result.diagnostics["finish_reason_truncating"] is True


def test_request46_missing_response_field_is_typed() -> None:
    result = _parse(None, response_field_present=False)
    assert result.ok is False
    assert result.error_code == REPAIR_RESPONSE_FIELD_MISSING


def test_direct_json_parses() -> None:
    result = _parse(json.dumps(_canonical_payload()))
    assert result.ok is True
    assert result.strategy == "direct"
    assert result.envelope == "canonical"
    assert [item.path for item in result.batch.files] == [HOME_PATH]


def test_fenced_json_parses() -> None:
    raw = "```json\n" + json.dumps(_canonical_payload()) + "\n```"
    result = _parse(raw)
    assert result.ok is True
    assert result.strategy == "markdown_fence"
    assert result.batch.files[0].source == REPAIRED_HOME_SOURCE


def test_unlabelled_fence_json_parses() -> None:
    raw = "```\n" + json.dumps(_canonical_payload()) + "\n```"
    result = _parse(raw)
    assert result.ok is True
    assert result.strategy == "markdown_fence"


def test_prose_wrapped_json_parses() -> None:
    raw = (
        "Here is the repaired file you asked for.\n"
        + json.dumps(_canonical_payload())
        + "\nLet me know if you need anything else."
    )
    result = _parse(raw)
    assert result.ok is True
    assert result.strategy == "balanced_scan"


def test_prose_with_stray_brace_before_json_parses() -> None:
    raw = (
        "I fixed the component { see below }\n"
        + json.dumps(_canonical_payload())
    )
    result = _parse(raw)
    assert result.ok is True
    assert result.strategy == "balanced_scan"


def test_balanced_nested_json_parses() -> None:
    nested_source = (
        "const config = [{ nested: [{ deep: [1, 2, 3] }] }];\n"
        "export function CompHomeComponent() {\n"
        '  return <div data-bmv-component-id="COMP-HOME">{config.length}</div>;\n'
        "}"
    )
    payload = _canonical_payload(files=[_repaired_file(source=nested_source)])
    result = _parse("prefix prose\n" + json.dumps(payload))
    assert result.ok is True
    assert result.batch.files[0].source == nested_source


def test_braces_and_escapes_inside_strings_do_not_break_extraction() -> None:
    tricky_source = (
        "export function CompHomeComponent() {\n"
        '  const brace = "}{ [ ] \\" not json \\\\";\n'
        '  return <div data-bmv-component-id="COMP-HOME">{brace}</div>;\n'
        "}"
    )
    payload = _canonical_payload(files=[_repaired_file(source=tricky_source)])
    result = _parse("Result:\n" + json.dumps(payload) + "\ntrailing }")
    assert result.ok is True
    assert result.batch.files[0].source == tricky_source


def test_provider_native_structured_payload_is_preferred() -> None:
    result = _parse(None, structured_payload=_canonical_payload())
    assert result.ok is True
    assert result.strategy == "provider_structured"


def test_wrong_provider_response_field_is_typed_not_guessed() -> None:
    raw = json.dumps(
        {
            "choices": [
                {"message": {"content": json.dumps(_canonical_payload())}}
            ]
        }
    )
    result = _parse(raw)
    assert result.ok is False
    assert result.error_code == REPAIR_ENVELOPE_INVALID


def test_bare_files_array_envelope_is_normalized() -> None:
    result = _parse(json.dumps([_repaired_file()]))
    assert result.ok is True
    assert result.envelope == "bare_files_array"
    assert result.batch.batch_kind == "business_components"
    assert result.batch.schema_version == "1.0"


def test_files_only_object_envelope_is_normalized() -> None:
    result = _parse(json.dumps({"files": [_repaired_file()]}))
    assert result.ok is True
    assert result.envelope == "files_only_object"
    assert result.batch.batch_kind == "business_components"


def test_unknown_envelope_key_is_never_mapped_by_similarity() -> None:
    result = _parse(json.dumps({"repaired_files": [_repaired_file()]}))
    assert result.ok is False
    assert result.error_code == REPAIR_ENVELOPE_INVALID


def test_extra_top_level_prose_field_is_rejected() -> None:
    payload = _canonical_payload()
    payload["explanation"] = "I added the missing contract hook."
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.error_code == REPAIR_ENVELOPE_INVALID


def test_batch_kind_mismatch_is_an_ownership_violation() -> None:
    result = _parse(json.dumps(_canonical_payload(batch_kind="pages")))
    assert result.ok is False
    assert result.violation == VIOLATION_BATCH_KIND_MISMATCH
    assert result.is_ownership_violation is True


def test_truncated_json_is_typed_and_never_completed() -> None:
    raw = json.dumps(_canonical_payload())[:-40]
    result = _parse(raw, finish_reason="length")
    assert result.ok is False
    assert result.error_code == REPAIR_JSON_TRUNCATED
    assert result.batch is None


def test_truncated_json_without_finish_reason_is_still_truncation() -> None:
    result = _parse(json.dumps(_canonical_payload())[:-40])
    assert result.ok is False
    assert result.error_code == REPAIR_JSON_TRUNCATED


def test_unterminated_string_is_truncation_not_syntax_error() -> None:
    raw = json.dumps(_canonical_payload())
    result = _parse(raw[: raw.index("source") + 20])
    assert result.ok is False
    assert result.error_code == REPAIR_JSON_TRUNCATED


def test_mismatched_bracket_is_syntax_invalid() -> None:
    result = _parse('{"schema_version": "1.0", "files": [ } ]}')
    assert result.ok is False
    assert result.error_code == REPAIR_JSON_SYNTAX_INVALID


def test_no_json_payload_is_typed() -> None:
    result = _parse("I could not repair the component. Sorry!")
    assert result.ok is False
    assert result.error_code == REPAIR_NO_JSON_PAYLOAD


def test_duplicate_file_path_is_contract_invalid() -> None:
    payload = _canonical_payload(files=[_repaired_file(), _repaired_file()])
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.error_code == REPAIR_CONTRACT_INVALID
    assert result.is_ownership_violation is False


def test_unknown_file_is_rejected() -> None:
    payload = _canonical_payload(
        files=[_repaired_file(path="src/components/business/CompGhost.tsx")]
    )
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.violation == VIOLATION_UNKNOWN_PATH


def test_file_outside_repair_subset_is_rejected() -> None:
    payload = _canonical_payload(
        files=[_repaired_file(path=BOOK_PATH, owner_contract_ids=["COMP-BOOK"])]
    )
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.violation == VIOLATION_OUTSIDE_SUBSET


def test_ownership_change_is_rejected() -> None:
    payload = _canonical_payload(
        files=[_repaired_file(owner_contract_ids=["COMP-OTHER"])]
    )
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.violation == VIOLATION_OWNERSHIP_CHANGED


def test_file_kind_change_is_rejected() -> None:
    payload = _canonical_payload(files=[_repaired_file(file_kind="page")])
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.violation == VIOLATION_FILE_KIND_CHANGED


def test_missing_source_is_contract_invalid() -> None:
    payload = _canonical_payload(files=[_repaired_file(source="")])
    result = _parse(json.dumps(payload))
    assert result.ok is False
    assert result.error_code == REPAIR_CONTRACT_INVALID


def test_diagnostics_never_carry_generated_source() -> None:
    raw = "prose " + json.dumps(_canonical_payload())
    result = _parse(raw)
    blob = canonical_json(result.diagnostics)
    assert "CompHomeComponent" not in blob
    assert "data-bmv-component-id" not in blob
    assert result.diagnostics["raw_response_chars"] == len(raw)


def test_before_legacy_parser_rejects_the_documented_alternative_envelopes() -> None:
    raw = json.dumps([_repaired_file()])
    assert "files" not in extract_json_from_text(raw)
    with pytest.raises(ValueError):
        _legacy_parse_batch(raw)
    assert _parse(raw).ok is True


def test_before_legacy_parser_cannot_classify_truncation() -> None:
    truncated = json.dumps(_canonical_payload())[:-40]
    with pytest.raises(ValueError):
        _legacy_parse_batch(truncated)
    assert _parse(truncated).error_code == REPAIR_JSON_TRUNCATED


class _RepairAI:
    name = "openrouter"

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[dict] = []

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
    ) -> str:
        self.calls.append(
            {
                "model": model,
                "prompt": messages[0]["content"],
                "max_tokens": max_tokens,
                "response_format": response_format,
                "transport_attempts": transport_attempts,
            }
        )
        return self._response

    def last_completion_meta(self) -> dict:
        return {"finish_reason": "stop"}

    def is_available(self) -> bool:
        return True


def _run_repair(ai) -> tuple[object, CandidateCallBudget]:
    budget = CandidateCallBudget.create()
    assert budget.approve("business_components")[0]
    built = repair_ai_batch(
        request_id=46,
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
        candidate_revision_uuid="req46",
    )
    return built, budget


def test_repair_requests_json_object_mode_for_the_configured_model() -> None:
    assert (
        resolve_model_capability(
            settings.V2_CANDIDATE_REPAIR_MODEL
        ).supports_json_object
        is True
    )
    ai = _RepairAI("```json\n" + json.dumps(_canonical_payload()) + "\n```")
    built, budget = _run_repair(ai)
    assert len(ai.calls) == 1
    assert ai.calls[0]["response_format"] == {"type": "json_object"}
    assert ai.calls[0]["max_tokens"] == 10000
    assert built.metrics.repair_call_count == 1
    assert budget.snapshot()["substage_used"]["business_components"] == 2
    assert budget.snapshot()["total_used"] == 2


def test_repair_prompt_forbids_prose_and_requires_compact_json() -> None:
    ai = _RepairAI(json.dumps(_canonical_payload()))
    _run_repair(ai)
    prompt = ai.calls[0]["prompt"]
    assert "No prose, no markdown, no code fences." in prompt
    assert "No explanations" in prompt
    assert "compact JSON" in prompt
    assert "CompHomeComponent" in prompt
    assert "CompBookComponent" not in prompt


def test_fenced_repair_response_merges_only_the_approved_file() -> None:
    ai = _RepairAI(
        "Sure!\n```json\n" + json.dumps(_canonical_payload()) + "\n```"
    )
    built, _budget = _run_repair(ai)
    merged = {item.path: item.source for item in built.batch.files}
    assert set(merged) == {BOOK_PATH, HOME_PATH}
    assert merged[HOME_PATH] == REPAIRED_HOME_SOURCE
    assert 'data-bmv-component-id="COMP-BOOK"' in merged[BOOK_PATH]


def test_repair_that_leaves_its_subset_fails_closed_as_ownership() -> None:
    payload = _canonical_payload(
        files=[_repaired_file(path=BOOK_PATH, owner_contract_ids=["COMP-BOOK"])]
    )
    ai = _RepairAI(json.dumps(payload))
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    assert exc.value.provider_error_code == "candidate_repair_ownership_violation"
    assert "batch ownership" in str(exc.value)


def test_truncated_repair_response_reports_typed_truncation() -> None:
    ai = _RepairAI(json.dumps(_canonical_payload())[:-40])
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    assert exc.value.provider_error_code == REPAIR_JSON_TRUNCATED


def test_repair_failure_diagnostics_stay_sanitized() -> None:
    ai = _RepairAI("no json here at all")
    with pytest.raises(CandidateStageError) as exc:
        _run_repair(ai)
    assert exc.value.provider_error_code == REPAIR_NO_JSON_PAYLOAD
    blob = " ".join(exc.value.diagnostics)
    assert "no json here at all" not in blob


def test_repair_never_adds_a_provider_call_beyond_the_cap() -> None:
    ai = _RepairAI(json.dumps(_canonical_payload()))
    _built, budget = _run_repair(ai)
    assert len(ai.calls) == 1
    ok, code = budget.approve("business_components")
    assert ok is False
    assert code == "candidate_substage_call_budget_exhausted"


def test_request46_after_repair_resumes_pages_within_call_caps(
    isolated_candidate_paths,
) -> None:
    def _remove_action_hook(payload):
        payload["files"][0]["source"] = payload["files"][0]["source"].replace(
            "data-bmv-action-id",
            "data-bmv-action-removed",
        )
        return payload

    prepared = prepare_phase3a(request_id=4601)
    ai = CandidateFixtureAI()
    ai.stage_mutators["business_components"] = [_remove_action_hook]
    try:
        result = build_v2_candidate_revision(
            prepared.db,
            prepared.req.id,
            ai,
            JinjaTemplateRenderer(settings.TEMPLATES_DIR),
            req=prepared.req,
            phase3a_result=prepared.phase3a_result,
        )
        contract = result["preview_contract"]
        assert contract["status"] == "candidate_build_pending"
        assert [item[0] for item in ai.calls] == [
            "business_components",
            "business_components_repair",
            "pages",
        ]
        ledger = contract["candidate_call_ledger"]
        assert ledger["total_used"] <= 4
        assert ledger["substage_used"]["business_components"] == 2
        assert ledger["substage_used"]["pages"] >= 1
    finally:
        prepared.db.close()
