"""The AI hub must not inject a second initial state onto its own page.

Requests 137, 138 and 139 all died on the identical validator message:

    Page 'PAGE-AI-FEATURES' must contain exactly one initial state; found 2.

Both states were `initial: true` — `STATE-AI-FEATURES-LOADED`, written by the
model, and `STATE-AI-HUB-READY`, injected by `ai_features.py` with a hardcoded
`"initial": True`. The guard in front of it asked *"is this id already
present?"*, which cannot see a state the model wrote under a different name, and
the model writes one routinely: a page with content has an initial state by
definition.

**The pipeline injected the second initial state and then failed the run for
having two**, on a page the pipeline itself requires. Three requests, one
literal.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import app.application.appspec  # noqa: F401  isort:skip  (import cycle: application first)

from app.application.services.ai_features import PAGE_AI_HUB_ID, bind_ai_features_to_app_spec


def _spec(hub_states: list[dict], hub_state_ids: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "pages": [
            {"id": PAGE_AI_HUB_ID, "name": "AI features", "state_ids": list(hub_state_ids)},
        ],
        "states": list(hub_states),
        "requirements": [],
        "capabilities": [],
        # A role is required: `bind_ai_features_to_app_spec` returns the spec
        # untouched without one, and an earlier version of this fixture omitted
        # it — so every test passed while exercising nothing.
        "roles": [{"id": "ROLE-CUSTOMER", "name": "Customer"}],
        "evidence": [],
        "acceptance_tests": [],
        "traceability": [],
        "deferred_scope": [],
    }


def _hub_initials(spec: dict) -> list[str]:
    hub = next(p for p in spec["pages"] if p["id"] == PAGE_AI_HUB_ID)
    ids = {str(s).casefold() for s in hub.get("state_ids") or []}
    return [
        s["id"]
        for s in spec["states"]
        if str(s.get("id", "")).casefold() in ids and s.get("initial")
    ]


def _features() -> list[dict]:
    return [{"id": "concierge", "name": "Concierge", "description": "Answers questions."}]


def test_the_hub_state_is_not_initial_when_the_model_wrote_one():
    """137/138/139's exact shape."""

    spec = _spec(
        [
            {
                "id": "STATE-AI-FEATURES-LOADED",
                "page_id": PAGE_AI_HUB_ID,
                "name": "Loaded",
                "description": "The AI features showcase page displays all capabilities.",
                "initial": True,
                "evidence_ids": [],
            }
        ],
        ["STATE-AI-FEATURES-LOADED"],
    )

    out = bind_ai_features_to_app_spec(spec, _features())

    assert len(_hub_initials(out)) == 1, _hub_initials(out)
    assert "STATE-AI-HUB-READY" not in _hub_initials(out)


def test_the_hub_state_is_initial_when_the_page_has_none():
    """The injected state is still what makes an empty hub page valid."""

    out = bind_ai_features_to_app_spec(_spec([], []), _features())

    assert _hub_initials(out) == ["STATE-AI-HUB-READY"]


def test_a_model_state_that_is_not_initial_does_not_suppress_ours():
    """Only an *initial* state counts — a page of non-initial states still needs one."""

    spec = _spec(
        [
            {
                "id": "STATE-AI-FEATURES-BUSY",
                "page_id": PAGE_AI_HUB_ID,
                "name": "Busy",
                "description": "A capability is running.",
                "initial": False,
                "evidence_ids": [],
            }
        ],
        ["STATE-AI-FEATURES-BUSY"],
    )

    out = bind_ai_features_to_app_spec(spec, _features())

    assert _hub_initials(out) == ["STATE-AI-HUB-READY"]


def test_a_state_on_another_page_never_suppresses_the_hub_state():
    """`initial` is per page — another page's initial state is irrelevant here."""

    spec = _spec([], [])
    spec["pages"].append({"id": "PAGE-HOME", "name": "Home", "state_ids": ["STATE-HOME"]})
    spec["states"].append(
        {
            "id": "STATE-HOME",
            "page_id": "PAGE-HOME",
            "name": "Home",
            "description": "Home page loaded.",
            "initial": True,
            "evidence_ids": [],
        }
    )

    out = bind_ai_features_to_app_spec(spec, _features())

    assert _hub_initials(out) == ["STATE-AI-HUB-READY"]
