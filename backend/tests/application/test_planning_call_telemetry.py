"""Every planning-phase model call must be scoped, so its cost lands on the
right stage.

`record_usage` derives a row's `stage` from the active `ai_call` scope and falls
back to the run **purpose** when there is none (`admin_ops.py:330`).
`generate_preview_app` runs the *whole* preview pipeline under
`ai_run_scope(purpose="codegen")` (`pipeline/orchestrator.py:39`), so an
unscoped ask anywhere in that pipeline is recorded as `stage = codegen,
writer = NULL`.

`services/page_experience.py` had no scopes. The bill, measured by
`scripts/measure/codegen_cost.py` over duo 1:

* **310.7 s across 11 calls — 41 % of the `codegen` stage total — was the plan
  phase**, not codegen: `build_experience_plan`, `validate_and_expand_plan` and
  `build_design_manifest`. Request 95 spent 143.7 s there, request 96 167.0 s.
* `validate_and_expand_plan` alone spent **69.9 s on 95 and 94.0 s on 96** in
  two asks apiece, and swallowed every exception with no log line, so neither
  the log nor the census carried one word about any of them.

That mis-attribution is not cosmetic: the roadmap's *"codegen is 315-437 s of AI
and therefore the p50 term"* was reading the plan phase's spend as codegen's.

These tests assert the scope is live at the moment the provider is called,
which is the only place it can be observed without a database.
"""
from __future__ import annotations

import json
from typing import Any

from app.application.services.ai_context import current_ai_call
from app.application.services.page_experience import (
    build_design_manifest,
    build_experience_plan,
    validate_and_expand_plan,
)
from app.domain.models.request import Request

_PLAN = {
    "roles": [
        {
            "id": "public",
            "label": "Visitor",
            "pages": [{"id": "home", "title": "Home", "route": "/"}],
            "navigation": {"links": [{"page_id": "home", "label": "Home"}]},
        }
    ],
    "design_system": {"primary_color": "#8b0000"},
}


class _StubRenderer:
    def render(self, *_args: Any, **_kwargs: Any) -> str:
        return "prompt"


class _ScopeRecordingAI:
    """Records the `ai_call` scope that was active during each ask."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.scopes: list[tuple[str | None, str | None, int]] = []

    def ask_chat(self, _model: str, _messages: list[dict], **_kwargs: Any) -> str:
        call = current_ai_call()
        self.scopes.append(
            (call.stage, call.writer, call.attempt) if call else (None, None, 0)
        )
        return self._responses.pop(0) if self._responses else json.dumps(_PLAN)


class _VerdictRecordingAI(_ScopeRecordingAI):
    """Also captures the scope object, so the usability verdict can be read
    after the scope has exited — the verdict is what separates a 35 s ask that
    bought a plan from a 35 s ask that bought nothing."""

    def __init__(self, responses: list[str]) -> None:
        super().__init__(responses)
        self.calls: list[Any] = []

    def ask_chat(self, model: str, messages: list[dict], **kwargs: Any) -> str:
        self.calls.append(current_ai_call())
        return super().ask_chat(model, messages, **kwargs)


def _request() -> Request:
    return Request(
        id=95,
        business_name="Osteria Vinci",
        industry="restaurant",
        mvp_blueprint="blueprint",
        preview_features="menu, reservations",
    )


def test_the_planner_is_scoped_to_planning_not_to_codegen() -> None:
    """The single most expensive unscoped ask in the pipeline: 55.98 s on
    request 95, 53.4 s on 96, both billed to `codegen`."""

    ai = _ScopeRecordingAI([json.dumps(_PLAN)])

    build_experience_plan(
        _request(), {}, "#8b0000", "#d35400", ai, _StubRenderer(),
        canonical_seed={"roles": _PLAN["roles"]},
    )

    assert ai.scopes == [("planning", "planner", 1)]


def test_the_second_model_in_the_planner_chain_is_attempt_two() -> None:
    """Both entries resolve to `google/gemini-2.5-flash` in this environment, so
    the "failover" is a re-ask. Recording both as attempt 1 is what made
    appspec's re-asks invisible for four trios; the same shape is here."""

    ai = _ScopeRecordingAI(["not json at all", json.dumps(_PLAN)])

    build_experience_plan(
        _request(), {}, "#8b0000", "#d35400", ai, _StubRenderer(),
        canonical_seed={"roles": _PLAN["roles"]},
    )

    assert ai.scopes == [
        ("planning", "planner", 1),
        ("planning", "planner", 2),
    ]


def test_a_planner_answer_with_no_roles_is_adjudicated_unusable() -> None:
    """Requests 95 and 96 each opened with one of these — 57 and 91 characters
    of a design system and no roles at all. Presumed usable, it is 7-15 s of
    spend the census reports as bought and used."""

    ai = _VerdictRecordingAI(['{"design_system": {"primary_color": "#8b0"}}', json.dumps(_PLAN)])

    build_experience_plan(
        _request(), {}, "#8b0000", "#d35400", ai, _StubRenderer(),
        canonical_seed={"roles": _PLAN["roles"]},
    )

    assert ai.calls[0].usable is False
    assert ai.calls[1].usable is True


def test_the_plan_validator_is_scoped_and_numbers_its_two_asks() -> None:
    """`validate_and_expand_plan` is the writer nothing knew existed: two asks
    of 34-48 s each on both duo runs, no log line, no census row of its own."""

    ai = _ScopeRecordingAI(['{"roles": []}', json.dumps(_PLAN)])

    validate_and_expand_plan(_request(), dict(_PLAN), ai, _StubRenderer(), {})

    assert ai.scopes == [
        ("planning", "plan_validation", 1),
        ("planning", "plan_validation", 2),
    ]


def test_the_validators_discarded_answer_is_adjudicated_unusable() -> None:
    """Scoping an ask is half the job; the verdict is the other half.

    A mutation that deleted only this `adjudicate` survived a sweep in which
    every scope assertion passed — the calls were named and their 34-48 s were
    reported as spent well. Request 96's first validator ask returned **zero
    characters** and would have been counted as useful work.
    """

    ai = _VerdictRecordingAI(['{"roles": []}', json.dumps(_PLAN)])

    validate_and_expand_plan(_request(), dict(_PLAN), ai, _StubRenderer(), {})

    assert ai.calls[0].usable is False
    assert ai.calls[1].usable is True


def test_the_validator_stops_at_the_first_usable_answer() -> None:
    """The second ask exists as a failover, not as a second opinion. A test that
    only ever drives the two-ask path would be green with the loop's `break`
    deleted."""

    ai = _ScopeRecordingAI([json.dumps(_PLAN)])

    validate_and_expand_plan(_request(), dict(_PLAN), ai, _StubRenderer(), {})

    assert ai.scopes == [("planning", "plan_validation", 1)]


def test_plan_expansion_is_scoped_and_is_reached_through_the_public_entry() -> None:
    """`_expand_plan` survived a first mutation sweep with its scope deleted,
    because nothing drove it.

    It is only reachable with **no** canonical seed and a plan that misses the
    feature-coverage minimum — which is to say, only when the AppSpec is not
    enforced. With `APPSPEC_MODE=shadow` that is every run, so this is a live
    path and not a legacy one.
    """

    thin = {**_PLAN, "feature_coverage": []}
    ai = _ScopeRecordingAI(
        [
            json.dumps(thin),   # planner
            json.dumps(thin),   # plan_validation
            json.dumps(thin),   # plan_expansion
            json.dumps(thin),   # plan_validation, re-run by the expander
        ]
    )
    req = Request(
        id=95,
        business_name="Osteria Vinci",
        industry="restaurant",
        mvp_blueprint="blueprint",
        preview_features="menu, reservations, ordering, loyalty",
    )

    build_experience_plan(req, {}, "#8b0000", "#d35400", ai, _StubRenderer())

    assert ("planning", "plan_expansion", 1) in ai.scopes
    assert all(stage == "planning" for stage, _w, _a in ai.scopes)


def test_the_design_manifest_is_scoped() -> None:
    ai = _ScopeRecordingAI(['{"brand_name": "Osteria Vinci", "accent": "#8b0000"}'])

    build_design_manifest("context", dict(_PLAN), ai, _StubRenderer())

    assert ai.scopes == [("planning", "design_manifest", 1)]


def test_no_planning_ask_is_left_billed_to_codegen() -> None:
    """The regression this whole file exists to prevent.

    A new ask added to this module without a scope is silently re-attributed to
    `codegen`, and the next person to read `codegen_cost.py` gets the same wrong
    answer this session started from.
    """

    ai = _ScopeRecordingAI(['{"roles": []}', json.dumps(_PLAN)])
    validate_and_expand_plan(_request(), dict(_PLAN), ai, _StubRenderer(), {})
    manifest_ai = _ScopeRecordingAI(['{"brand_name": "x"}'])
    build_design_manifest("context", dict(_PLAN), manifest_ai, _StubRenderer())
    planner_ai = _ScopeRecordingAI([json.dumps(_PLAN)])
    build_experience_plan(
        _request(), {}, "#8b0000", "#d35400", planner_ai, _StubRenderer(),
        canonical_seed={"roles": _PLAN["roles"]},
    )

    observed = ai.scopes + manifest_ai.scopes + planner_ai.scopes
    assert observed, "no asks were made — the test proves nothing"
    assert all(stage == "planning" for stage, _writer, _attempt in observed)
    assert all(writer for _stage, writer, _attempt in observed)
