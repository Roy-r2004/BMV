"""Focused checks for deterministic AppSpec -> preview projections."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.appspec.projection import (  # noqa: E402
    PreviewScopeError,
    browser_projection,
    merge_architecture_enrichment,
    merge_experience_plan_enrichment,
    select_preview_scope,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.appspec.workspace_validation import (  # noqa: E402
    validate_app_spec_workspace,
)
from app.domain.schemas.app_spec import AppSpec  # noqa: E402


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "app_spec" / "valid_booking.json"


def _spec() -> AppSpec:
    return AppSpec.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


def _gallery_admin_ai_spec() -> AppSpec:
    """Jeanne-Kassab-shaped AppSpec: 4 public + 4 admin + 1 AI = 9 must pages."""

    def _req(req_id: str, title: str) -> dict[str, Any]:
        return {
            "id": req_id,
            "title": title,
            "description": f"{title} must work in the product.",
            "priority": "must",
            "verification_mode": "interaction",
            "source_refs": ["customer_input.desired_outcome"],
        }

    def _page(
        page_id: str,
        *,
        route: str,
        surface: str,
        role_id: str,
        cap_id: str,
        primary: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": page_id,
            "name": page_id.replace("PAGE-", "").replace("-", " ").title(),
            "purpose": f"Serve {page_id}.",
            "route": route,
            "surface": surface,
            "primary": primary,
            "role_ids": [role_id],
            "capability_ids": [cap_id],
            "state_ids": [f"STATE-{page_id}-READY"],
            "action_ids": [f"ACTION-{page_id}-NEXT"],
            "evidence_ids": [f"EVIDENCE-{page_id}"],
        }

    public_pages = [
        ("PAGE-HOME", "/", True),
        ("PAGE-GALLERY", "/gallery", False),
        ("PAGE-PAINTING-DETAIL", "/gallery/item", False),
        ("PAGE-ABOUT", "/about", False),
    ]
    admin_pages = [
        ("PAGE-ADMIN-LOGIN", "/admin/login"),
        ("PAGE-ADMIN-DASHBOARD", "/admin"),
        ("PAGE-ADMIN-PAINTINGS", "/admin/paintings"),
        ("PAGE-ADMIN-ABOUT", "/admin/about"),
    ]
    ai_pages = [("PAGE-AI-FEATURES", "/ai-features")]

    pages: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    for page_id, route, primary in public_pages:
        pages.append(
            _page(
                page_id,
                route=route,
                surface="public",
                role_id="ROLE-VISITOR",
                cap_id="CAP-PUBLIC",
                primary=primary,
            )
        )
    for page_id, route in admin_pages:
        pages.append(
            _page(
                page_id,
                route=route,
                surface="ops",
                role_id="ROLE-ADMIN",
                cap_id="CAP-ADMIN",
            )
        )
    for page_id, route in ai_pages:
        pages.append(
            _page(
                page_id,
                route=route,
                surface="public",
                role_id="ROLE-VISITOR",
                cap_id="CAP-AI",
            )
        )

    for page in pages:
        page_id = page["id"]
        states.append(
            {
                "id": f"STATE-{page_id}-READY",
                "page_id": page_id,
                "name": "Ready",
                "description": f"{page_id} is ready.",
                "initial": True,
                "terminal": True,
                "evidence_ids": [f"EVIDENCE-{page_id}"],
            }
        )
        actions.append(
            {
                "id": f"ACTION-{page_id}-NEXT",
                "page_id": page_id,
                "role_id": page["role_ids"][0],
                "name": "Continue",
                "description": f"Continue from {page_id}.",
                "kind": "navigate",
                "capability_ids": page["capability_ids"],
                "entity_id": None,
                "input_label": None,
            }
        )
        evidence.append(
            {
                "id": f"EVIDENCE-{page_id}",
                "page_id": page_id,
                "name": f"{page_id} evidence",
                "description": f"Visible proof for {page_id}.",
                "kind": "text",
                "capability_ids": page["capability_ids"],
            }
        )

    def _journey(
        journey_id: str,
        *,
        role_id: str,
        req_id: str,
        page_ids: list[str],
    ) -> dict[str, Any]:
        start = page_ids[0]
        steps = []
        for index, page_id in enumerate(page_ids[1:], start=1):
            prev = page_ids[index - 1]
            steps.append(
                {
                    "id": f"STEP-{journey_id}-{index}",
                    "action_id": f"ACTION-{prev}-NEXT",
                    "transition_id": f"TRANSITION-{prev}-NEXT",
                    "expected_page_id": page_id,
                    "expected_state_id": f"STATE-{page_id}-READY",
                    "evidence_ids": [f"EVIDENCE-{page_id}"],
                }
            )
        # Single-page journeys still need ≥1 step; self-navigate.
        if not steps:
            steps.append(
                {
                    "id": f"STEP-{journey_id}-1",
                    "action_id": f"ACTION-{start}-NEXT",
                    "transition_id": f"TRANSITION-{start}-NEXT",
                    "expected_page_id": start,
                    "expected_state_id": f"STATE-{start}-READY",
                    "evidence_ids": [f"EVIDENCE-{start}"],
                }
            )
        return {
            "id": journey_id,
            "name": journey_id,
            "description": f"Journey {journey_id}.",
            "role_id": role_id,
            "requirement_ids": [req_id],
            "start_page_id": start,
            "start_state_id": f"STATE-{start}-READY",
            "steps": steps,
        }

    transitions = [
        {
            "id": f"TRANSITION-{page['id']}-NEXT",
            "action_id": f"ACTION-{page['id']}-NEXT",
            "from_state_id": f"STATE-{page['id']}-READY",
            "to_state_id": f"STATE-{page['id']}-READY",
            "description": f"Stay ready on {page['id']}.",
            "preconditions": [],
            "postconditions": [],
            "effects": [],
        }
        for page in pages
    ]

    payload = {
        "schema_version": "1.0",
        "product_intent": {
            "name": "Jeanne Kassab Art",
            "summary": "Public gallery with admin and AI assistants.",
            "problem": "Collectors need a ready gallery face.",
            "desired_outcome": "Browse paintings and manage inventory.",
            "target_users": ["Collectors", "Artist admin"],
            "success_metrics": ["Public gallery is ready"],
        },
        "requirements": [
            _req("REQ-PUBLIC", "Public gallery"),
            _req("REQ-ADMIN", "Admin inventory"),
            _req("REQ-AI", "AI features"),
        ],
        "assumptions": [],
        "open_questions": [],
        "roles": [
            {
                "id": "ROLE-VISITOR",
                "name": "Visitor",
                "description": "Public gallery visitor.",
                "goals": ["Browse paintings"],
                "default_page_id": "PAGE-HOME",
            },
            {
                "id": "ROLE-ADMIN",
                "name": "Admin",
                "description": "Artist administrator.",
                "goals": ["Manage paintings"],
                "default_page_id": "PAGE-ADMIN-DASHBOARD",
            },
        ],
        "entities": [],
        "capabilities": [
            {
                "id": "CAP-PUBLIC",
                "name": "Public gallery",
                "description": "Browse the public gallery.",
                "requirement_ids": ["REQ-PUBLIC"],
                "role_ids": ["ROLE-VISITOR"],
                "entity_ids": [],
            },
            {
                "id": "CAP-ADMIN",
                "name": "Admin ops",
                "description": "Manage paintings.",
                "requirement_ids": ["REQ-ADMIN"],
                "role_ids": ["ROLE-ADMIN"],
                "entity_ids": [],
            },
            {
                "id": "CAP-AI",
                "name": "AI features",
                "description": "AI assistant surfaces.",
                "requirement_ids": ["REQ-AI"],
                "role_ids": ["ROLE-VISITOR"],
                "entity_ids": [],
            },
        ],
        "pages": pages,
        "states": states,
        "actions": actions,
        "transitions": transitions,
        "evidence": evidence,
        "journeys": [
            _journey(
                "JOURNEY-PUBLIC",
                role_id="ROLE-VISITOR",
                req_id="REQ-PUBLIC",
                page_ids=[pid for pid, *_ in public_pages],
            ),
            _journey(
                "JOURNEY-ADMIN",
                role_id="ROLE-ADMIN",
                req_id="REQ-ADMIN",
                page_ids=[pid for pid, *_ in admin_pages],
            ),
            _journey(
                "JOURNEY-AI",
                role_id="ROLE-VISITOR",
                req_id="REQ-AI",
                page_ids=[pid for pid, *_ in ai_pages],
            ),
        ],
        "acceptance_tests": [
            {
                "id": "TEST-PUBLIC",
                "name": "Public gallery works",
                "description": "Visitor can browse.",
                "requirement_ids": ["REQ-PUBLIC"],
                "journey_id": "JOURNEY-PUBLIC",
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Home is visible.",
                        "page_id": "PAGE-HOME",
                        "state_id": "STATE-PAGE-HOME-READY",
                        "evidence_id": "EVIDENCE-PAGE-HOME",
                        "expected": "ready",
                    }
                ],
            },
            {
                "id": "TEST-ADMIN",
                "name": "Admin works",
                "description": "Admin can manage.",
                "requirement_ids": ["REQ-ADMIN"],
                "journey_id": "JOURNEY-ADMIN",
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "Dashboard is visible.",
                        "page_id": "PAGE-ADMIN-DASHBOARD",
                        "state_id": "STATE-PAGE-ADMIN-DASHBOARD-READY",
                        "evidence_id": "EVIDENCE-PAGE-ADMIN-DASHBOARD",
                        "expected": "ready",
                    }
                ],
            },
            {
                "id": "TEST-AI",
                "name": "AI works",
                "description": "AI features are visible.",
                "requirement_ids": ["REQ-AI"],
                "journey_id": "JOURNEY-AI",
                "assertions": [
                    {
                        "kind": "visible",
                        "description": "AI page is visible.",
                        "page_id": "PAGE-AI-FEATURES",
                        "state_id": "STATE-PAGE-AI-FEATURES-READY",
                        "evidence_id": "EVIDENCE-PAGE-AI-FEATURES",
                        "expected": "ready",
                    }
                ],
            },
        ],
        "traceability": [
            {
                "requirement_id": "REQ-PUBLIC",
                "capability_ids": ["CAP-PUBLIC"],
                "page_ids": [pid for pid, *_ in public_pages],
                "evidence_ids": [f"EVIDENCE-{pid}" for pid, *_ in public_pages],
                "journey_ids": ["JOURNEY-PUBLIC"],
                "acceptance_test_ids": ["TEST-PUBLIC"],
            },
            {
                "requirement_id": "REQ-ADMIN",
                "capability_ids": ["CAP-ADMIN"],
                "page_ids": [pid for pid, *_ in admin_pages],
                "evidence_ids": [f"EVIDENCE-{pid}" for pid, *_ in admin_pages],
                "journey_ids": ["JOURNEY-ADMIN"],
                "acceptance_test_ids": ["TEST-ADMIN"],
            },
            {
                "requirement_id": "REQ-AI",
                "capability_ids": ["CAP-AI"],
                "page_ids": [pid for pid, *_ in ai_pages],
                "evidence_ids": [f"EVIDENCE-{pid}" for pid, *_ in ai_pages],
                "journey_ids": ["JOURNEY-AI"],
                "acceptance_test_ids": ["TEST-AI"],
            },
        ],
        "deferred_scope": [],
    }
    return AppSpec.model_validate(payload)


def test_scope_and_contract_projection() -> None:
    spec = _spec()
    scope = select_preview_scope(spec, target_pages=6, max_pages=8)
    assert scope.selected_page_ids == ("PAGE-BOOK",)
    assert scope.selected_journey_ids == ("JOURNEY-BOOK",)
    assert scope.covered_requirement_ids == ("REQ-BOOK",)

    plan = to_experience_plan_seed(spec, scope)
    page = plan["roles"][0]["pages"][0]
    assert page["id"] == "PAGE-BOOK"
    assert page["app_spec_contract"]["actions"][0]["id"] == "ACTION-SUBMIT"
    browser = browser_projection(spec, scope)
    assert browser["journeys"][0]["id"] == "JOURNEY-BOOK"
    assert browser["acceptance_tests"][0]["id"] == "TEST-BOOK"


def test_design_agents_cannot_change_product_semantics() -> None:
    spec = _spec()
    scope = select_preview_scope(spec)
    plan_seed = to_experience_plan_seed(spec, scope)
    enriched = merge_experience_plan_enrichment(
        plan_seed,
        {
            "design_direction": "Cinematic editorial motion with calm transitions.",
            "roles": [
                {
                    "id": "ROLE-CUSTOMER",
                    "pages": [
                        {
                            "id": "PAGE-BOOK",
                            "purpose": "Replace the customer's goal",
                            "skeleton_id": "public-booking",
                            "sections": [{"name": "Booking flow"}],
                        },
                        {"id": "PAGE-INVENTED", "title": "Invented"},
                    ],
                },
                {"id": "ROLE-INVENTED", "pages": []},
            ],
        },
    )
    assert [role["id"] for role in enriched["roles"]] == ["ROLE-CUSTOMER"]
    page = enriched["roles"][0]["pages"][0]
    assert page["purpose"] == "Let a customer submit an appointment booking."
    assert page["skeleton_id"] == "public-booking"
    assert page["sections"] == [{"name": "Booking flow"}]

    architecture_seed = to_architecture_seed(spec, scope)
    architecture = merge_architecture_enrichment(
        architecture_seed,
        {
            "design_direction": "High-touch appointment workspace.",
            "routes": [
                {
                    "page_id": "PAGE-BOOK",
                    "path": "/wrong",
                    "role_id": "ROLE-INVENTED",
                    "skeleton_id": "public-booking",
                    "section_slots": ["header", "workspace", "summary", "footer"],
                },
                {"page_id": "PAGE-INVENTED", "path": "/invented"},
            ],
        },
    )
    assert len(architecture["routes"]) == 1
    route = architecture["routes"][0]
    assert route["path"] == "/book"
    assert route["role_id"] == "ROLE-CUSTOMER"
    assert route["skeleton_id"] == "public-booking"


def test_nine_page_gallery_admin_ai_trims_under_max_eight() -> None:
    """Investor demo path: 9 must pages must not hard-kill preview scope."""
    spec = _gallery_admin_ai_spec()
    assert len(spec.pages) == 9

    scope = select_preview_scope(spec, target_pages=6, max_pages=8)

    selected = set(scope.selected_page_ids)
    assert len(scope.selected_page_ids) <= 8
    # Public gallery face stays ready.
    assert {
        "PAGE-HOME",
        "PAGE-GALLERY",
        "PAGE-PAINTING-DETAIL",
        "PAGE-ABOUT",
    }.issubset(selected)
    assert "JOURNEY-PUBLIC" in scope.selected_journey_ids
    assert "REQ-PUBLIC" in scope.covered_requirement_ids
    # AI (and possibly some admin) demoted rather than aborting generation.
    assert "PAGE-AI-FEATURES" in scope.deferred_page_ids
    assert "JOURNEY-AI" not in scope.selected_journey_ids
    assert "REQ-AI" in scope.uncovered_required_requirement_ids
    # Still room for the full admin journey under an 8-page cap.
    assert "JOURNEY-ADMIN" in scope.selected_journey_ids
    assert "REQ-ADMIN" in scope.covered_requirement_ids


def test_preview_scope_still_fails_on_unknown_pages() -> None:
    broken = json.loads(FIXTURE.read_text(encoding="utf-8"))
    broken["roles"][0]["default_page_id"] = "PAGE-MISSING"
    try:
        select_preview_scope(AppSpec.model_validate(broken), max_pages=8)
        raise AssertionError("expected PreviewScopeError")
    except PreviewScopeError as exc:
        assert "unknown pages" in str(exc).casefold()


def test_workspace_requires_browser_addressable_contract_hooks() -> None:
    spec = _spec()
    scope = select_preview_scope(spec)
    architecture = to_architecture_seed(spec, scope)
    component = architecture["routes"][0]["component_file"]
    with tempfile.TemporaryDirectory() as raw:
        workspace = Path(raw)
        path = workspace / component
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """
            export default function Page() {
              return <main data-appspec-page="PAGE-BOOK">
                <button data-appspec-action="ACTION-SUBMIT">Confirm</button>
                <form data-appspec-evidence="EVIDENCE-FORM" />
                <p data-appspec-evidence="EVIDENCE-CONFIRMATION">Confirmed</p>
              </main>
            }
            """,
            encoding="utf-8",
        )
        assert validate_app_spec_workspace(workspace, spec, scope, architecture) == []
        path.write_text(
            '<main data-appspec-page="PAGE-BOOK" data-appspec-action="ACTION-SUBMIT" />',
            encoding="utf-8",
        )
        issues = validate_app_spec_workspace(workspace, spec, scope, architecture)
        assert any("EVIDENCE-CONFIRMATION" in issue for issue in issues)


def main() -> None:
    test_scope_and_contract_projection()
    test_design_agents_cannot_change_product_semantics()
    test_nine_page_gallery_admin_ai_trims_under_max_eight()
    test_preview_scope_still_fails_on_unknown_pages()
    test_workspace_requires_browser_addressable_contract_hooks()
    print("AppSpec preview projection tests passed (5 tests)")


if __name__ == "__main__":
    main()
