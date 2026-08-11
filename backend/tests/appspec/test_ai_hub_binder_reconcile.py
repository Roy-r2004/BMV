"""The binder must see the spec's expression of the hub, not its own literals.

Two deaths, one guard shape (the one 62cb26d fixed for initial states):

Request 136 — the model wrote its own hub, `PAGE-AI-FEATURES-HUB`, at
`/ai-features`. The binder looked for the page id `PAGE-AI-FEATURES`, did not
find it, appended a second page at the same route, and the run died on
`duplicate_route` — a collision the binder created.

Request 130 — a model repair re-emitted the document and kept the injected
requirement `REQ-AI-SMART-PRICING-INSIGHTS` while dropping its traceability
row. `_feature_already_bound` treats "the requirement exists" as "the feature
is bound", so the binder never restored the trace, and the run died on
`requirement_unaccounted_for` after exhausting every repair on an error the
model could not legally fix (re-adding the trace was the binder's job).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import app.application.appspec  # noqa: F401  isort:skip  (import cycle: application first)

from app.application.services.ai_features import (
    AI_FEATURE_SOURCE_REF,
    PAGE_AI_HUB_ID,
    PAGE_AI_HUB_ROUTE,
    bind_ai_features_to_app_spec,
)


def _features() -> list[dict]:
    return [
        {
            "id": "smart-pricing-insights",
            "name": "Smart Pricing Insights",
            "description": "Suggests prices from demand.",
        }
    ]


def _base_spec(pages: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "pages": pages,
        "states": [],
        "requirements": [],
        "capabilities": [],
        "roles": [{"id": "ROLE-CUSTOMER", "name": "Customer"}],
        "evidence": [],
        "acceptance_tests": [],
        "traceability": [],
        "deferred_scope": [],
    }


def _routes(spec: dict) -> list[str]:
    return [str(p.get("route") or "") for p in spec["pages"]]


def test_request136_model_hub_at_the_route_is_adopted_not_duplicated():
    spec = _base_spec(
        [
            {
                "id": "PAGE-AI-FEATURES-HUB",
                "name": "AI Hub",
                "route": PAGE_AI_HUB_ROUTE,
                "state_ids": [],
                "capability_ids": [],
                "evidence_ids": [],
                "role_ids": ["ROLE-CUSTOMER"],
            }
        ]
    )
    bound = bind_ai_features_to_app_spec(spec, _features())
    owners = [r for r in _routes(bound) if r.rstrip("/") == PAGE_AI_HUB_ROUTE]
    assert len(owners) == 1, f"binder duplicated the hub route: {_routes(bound)}"
    # The adopted page carries the binding — trace, evidence and state all
    # anchor on the model's page id, not the literal the binder would mint.
    hub = bound["pages"][0]
    assert hub["id"] == "PAGE-AI-FEATURES-HUB"
    assert hub["capability_ids"], "adopted hub got no capability wiring"
    for link in bound["traceability"]:
        assert link["page_ids"] == ["PAGE-AI-FEATURES-HUB"]
    for item in bound["evidence"]:
        assert item["page_id"] == "PAGE-AI-FEATURES-HUB"
    for state in bound["states"]:
        assert state["page_id"] == "PAGE-AI-FEATURES-HUB"
    for test in bound["acceptance_tests"]:
        for assertion in test["assertions"]:
            assert assertion["page_id"] == "PAGE-AI-FEATURES-HUB"


def test_trailing_slash_route_still_matches():
    spec = _base_spec(
        [
            {
                "id": "PAGE-HUB",
                "name": "AI Hub",
                "route": PAGE_AI_HUB_ROUTE + "/",
                "state_ids": [],
                "capability_ids": [],
                "evidence_ids": [],
                "role_ids": ["ROLE-CUSTOMER"],
            }
        ]
    )
    bound = bind_ai_features_to_app_spec(spec, _features())
    assert len(bound["pages"]) == 1


def test_request130_stranded_requirement_is_retraced():
    """The repair kept the requirement and dropped the trace; the binder must
    rebuild the missing pieces instead of skipping the 'already bound' feature."""

    spec = _base_spec(
        [
            {
                "id": PAGE_AI_HUB_ID,
                "name": "AI features",
                "route": PAGE_AI_HUB_ROUTE,
                "state_ids": [],
                "capability_ids": [],
                "evidence_ids": [],
                "role_ids": ["ROLE-CUSTOMER"],
            }
        ]
    )
    spec["requirements"] = [
        {
            "id": "REQ-AI-SMART-PRICING-INSIGHTS",
            "title": "Smart Pricing Insights",
            "description": "The live product exposes the planned AI feature.",
            "priority": "must",
            "verification_mode": "content",
            "source_refs": [AI_FEATURE_SOURCE_REF],
        }
    ]
    bound = bind_ai_features_to_app_spec(spec, _features())
    traced = {t["requirement_id"] for t in bound["traceability"]}
    assert "REQ-AI-SMART-PRICING-INSIGHTS" in traced
    link = next(
        t
        for t in bound["traceability"]
        if t["requirement_id"] == "REQ-AI-SMART-PRICING-INSIGHTS"
    )
    # The rebuilt trace is fully proven: capability claims the requirement,
    # evidence sits on the traced page and carries the traced capability.
    cap = next(c for c in bound["capabilities"] if c["id"] == link["capability_ids"][0])
    assert "REQ-AI-SMART-PRICING-INSIGHTS" in cap["requirement_ids"]
    ev = next(e for e in bound["evidence"] if e["id"] == link["evidence_ids"][0])
    assert ev["page_id"] in link["page_ids"]
    assert set(ev["capability_ids"]) & set(link["capability_ids"])
    test = next(
        t for t in bound["acceptance_tests"] if t["id"] == link["acceptance_test_ids"][0]
    )
    assert "REQ-AI-SMART-PRICING-INSIGHTS" in test["requirement_ids"]


def test_retrace_reuses_surviving_capability_and_test():
    spec = _base_spec(
        [
            {
                "id": PAGE_AI_HUB_ID,
                "name": "AI features",
                "route": PAGE_AI_HUB_ROUTE,
                "state_ids": [],
                "capability_ids": [],
                "evidence_ids": [],
                "role_ids": ["ROLE-CUSTOMER"],
            }
        ]
    )
    spec["requirements"] = [
        {
            "id": "REQ-AI-CONCIERGE",
            "title": "Concierge",
            "description": "d",
            "priority": "must",
            "verification_mode": "content",
            "source_refs": [AI_FEATURE_SOURCE_REF],
        }
    ]
    spec["capabilities"] = [
        {
            "id": "CAP-AI-CONCIERGE",
            "name": "Concierge",
            "description": "d",
            "requirement_ids": ["REQ-AI-CONCIERGE"],
            "role_ids": ["ROLE-CUSTOMER"],
            "entity_ids": [],
        }
    ]
    bound = bind_ai_features_to_app_spec(
        spec,
        [{"id": "concierge", "name": "Concierge", "description": "d"}],
    )
    link = next(
        t for t in bound["traceability"] if t["requirement_id"] == "REQ-AI-CONCIERGE"
    )
    assert link["capability_ids"] == ["CAP-AI-CONCIERGE"]
    cap_ids = [c["id"] for c in bound["capabilities"]]
    assert cap_ids.count("CAP-AI-CONCIERGE") == 1, "binder minted a duplicate capability"


def test_a_foreign_state_ai_hub_ready_gets_a_sibling_id_not_a_collision():
    """A model may write STATE-AI-HUB-READY on its own page. Wiring the hub's
    assertions to it would be `assertion_state_page_mismatch` — the pipeline
    arguing with itself. The binder mints a sibling id on the hub instead."""

    spec = _base_spec(
        [
            {
                "id": "PAGE-DASH",
                "name": "Dashboard",
                "route": "/dash",
                "state_ids": ["STATE-AI-HUB-READY"],
                "capability_ids": [],
                "evidence_ids": [],
                "role_ids": ["ROLE-CUSTOMER"],
            }
        ]
    )
    spec["states"] = [
        {
            "id": "STATE-AI-HUB-READY",
            "page_id": "PAGE-DASH",
            "name": "Ready",
            "initial": True,
            "evidence_ids": [],
        }
    ]
    bound = bind_ai_features_to_app_spec(spec, _features())
    hub = next(p for p in bound["pages"] if p["id"] == PAGE_AI_HUB_ID)
    minted = [s for s in bound["states"] if str(s["page_id"]) == PAGE_AI_HUB_ID]
    assert minted, "no state minted on the hub"
    assert all(s["id"] != "STATE-AI-HUB-READY" for s in minted)
    assert minted[0]["id"].startswith("STATE-AI-HUB-READY-")
    assert minted[0]["id"] in hub["state_ids"]
    # The foreign page's state is untouched.
    foreign = next(s for s in bound["states"] if s["page_id"] == "PAGE-DASH")
    assert foreign["id"] == "STATE-AI-HUB-READY"
    # And every hub assertion binds the minted sibling, not the foreign state.
    for test in bound["acceptance_tests"]:
        for assertion in test["assertions"]:
            if assertion.get("page_id") == PAGE_AI_HUB_ID:
                assert assertion["state_id"] == minted[0]["id"]


def test_bound_and_traced_spec_is_untouched():
    """The early return must still fire when nothing is stranded."""

    spec = _base_spec(
        [
            {
                "id": PAGE_AI_HUB_ID,
                "name": "AI features",
                "route": PAGE_AI_HUB_ROUTE,
                "state_ids": ["STATE-AI-HUB-READY"],
                "capability_ids": ["CAP-AI-CONCIERGE"],
                "evidence_ids": ["EVIDENCE-AI-CONCIERGE"],
                "role_ids": ["ROLE-CUSTOMER"],
                "purpose": "Interactive hub for planned AI features: Concierge",
            }
        ]
    )
    spec["requirements"] = [
        {
            "id": "REQ-AI-CONCIERGE",
            "title": "Concierge",
            "description": "d",
            "priority": "must",
            "verification_mode": "content",
            "source_refs": [AI_FEATURE_SOURCE_REF],
        }
    ]
    spec["traceability"] = [
        {
            "requirement_id": "REQ-AI-CONCIERGE",
            "capability_ids": ["CAP-AI-CONCIERGE"],
            "page_ids": [PAGE_AI_HUB_ID],
            "evidence_ids": ["EVIDENCE-AI-CONCIERGE"],
            "journey_ids": [],
            "acceptance_test_ids": ["TEST-AI-CONCIERGE"],
        }
    ]
    bound = bind_ai_features_to_app_spec(
        spec,
        [{"id": "concierge", "name": "Concierge", "description": "d"}],
    )
    assert bound == spec
