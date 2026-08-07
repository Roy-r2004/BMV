"""The authoring and repair prompts must teach the shapes the validator rejects.

Sessions 18-19, transport artifacts excluded, the recurring quality-reject
shapes were: two initial states on one page (114), state assertions without
`state_id` (116), empty minItems collections outside traceability —
`capability.role_ids` (123), `pages[].capability_ids`/`evidence_ids` (115) —
requirements neither traced nor deferred (114), and evidence IDs cited but
never declared (127). The prompt taught none of them precisely (the session-20
analysis quotes every gap), and `app_spec_repair.j2` handed the raw validator
codes to the repair model with no translation. These tests read the wording off
the REAL rendered prompts — a fake provider records what the model was sent —
so a reverted or reworded rule that no longer reaches the model fails here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.builder import (
    build_app_spec_candidate,
    repair_app_spec_candidate,
)
from app.application.appspec.schema_repair import repair_app_spec_schema_candidate
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = BACKEND_DIR / "app" / "templates"

_VALID = json.dumps({"schema_version": "1", "product_intent": {"summary": "ok"}})


class _PromptRecorder:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "test"

    def ask_chat(self, _model: str, messages: list[dict], **_kwargs: Any) -> str:
        self.prompts.append(messages[0]["content"])
        return _VALID

    def is_available(self) -> bool:
        return True


def _authoring_prompt() -> str:
    ai = _PromptRecorder()
    build_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(TEMPLATES_DIR),
        model="google/gemini-2.5-flash",
    )
    return ai.prompts[0]


def _repair_prompt() -> str:
    ai = _PromptRecorder()
    repair_app_spec_candidate(
        source_snapshot={"business_name": "Test"},
        derived_context={},
        candidate={"schema_version": "1"},
        deterministic_report={"issues": []},
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(TEMPLATES_DIR),
        model="google/gemini-2.5-flash",
    )
    return ai.prompts[0]


def test_authoring_prompt_teaches_exactly_one_initial_state() -> None:
    prompt = _authoring_prompt()
    assert "EXACTLY ONE initial state" in prompt
    assert '`"initial": true`' in prompt


def test_authoring_prompt_teaches_per_kind_assertion_references() -> None:
    prompt = _authoring_prompt()
    assert "a `state` assertion requires `state_id`" in prompt
    assert "never emit a state assertion" in prompt


def test_authoring_prompt_teaches_declare_before_cite() -> None:
    prompt = _authoring_prompt()
    assert "DECLARE BEFORE YOU CITE" in prompt
    assert "adding the matching item to the" in prompt


def test_authoring_prompt_extends_the_min_items_floor() -> None:
    prompt = _authoring_prompt()
    assert "capability's `role_ids`" in prompt


def test_authoring_prompt_demands_trace_or_defer() -> None:
    prompt = _authoring_prompt()
    assert "EITHER traced in `traceability` OR listed in" in prompt
    assert "a requirement in neither place is a validation failure" in prompt


def test_repair_prompt_translates_the_recurring_codes() -> None:
    prompt = _repair_prompt()
    for code in (
        "state_assertion_state_required",
        "missing_reference",
        "page_initial_state_count",
    ):
        assert code in prompt, code


def _schema_repair_prompt() -> str:
    ai = _PromptRecorder()
    repair_app_spec_schema_candidate(
        candidate={"schema_version": "1", "pages": []},
        schema_issue={"code": "app_spec_schema_parse_failed", "issues": []},
        ai_provider=ai,
        template_renderer=JinjaTemplateRenderer(TEMPLATES_DIR),
        model="google/gemini-2.5-flash",
    )
    return ai.prompts[0]


# Request 143's empty-tuple reject class (2-for-2 sessions with session 19).
# The mined shapes: rev 4-5's placeholder page `{"id": "Page1", "state_ids":
# []}` beside one well-formed page, and rev 1's collapse — the repair returned
# a single acceptance-test object in place of a 6-page spec.


def test_authoring_prompt_teaches_the_stateless_page_floor() -> None:
    prompt = _authoring_prompt()
    assert "There is no stateless page" in prompt
    assert '`{"id": "Page1", "state_ids": []}`' in prompt
    assert '`{"id": "PAGE-MENU", "state_ids": ["STATE-MENU-READY"]}`' in prompt


def test_repair_prompt_forbids_collapse_to_a_fragment() -> None:
    prompt = _repair_prompt()
    assert "is a collapse, not a repair" in prompt
    assert "must survive verbatim" in prompt


def test_schema_repair_prompt_translates_the_stateless_page_fix() -> None:
    prompt = _schema_repair_prompt()
    assert "that page is stateless: author its default state" in prompt
    assert "Never resend the page unchanged" in prompt
    assert '`"id": "Page1"`' in prompt
