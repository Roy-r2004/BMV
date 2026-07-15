"""Focused checks for deterministic AppSpec -> preview projections."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.app_spec_projection import (  # noqa: E402
    browser_projection,
    merge_architecture_enrichment,
    merge_experience_plan_enrichment,
    select_preview_scope,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.preview_app.app_spec_workspace import (  # noqa: E402
    validate_app_spec_workspace,
)
from app.domain.schemas.app_spec import AppSpec  # noqa: E402


FIXTURE = Path(__file__).parent / "fixtures" / "app_spec" / "valid_booking.json"


def _spec() -> AppSpec:
    return AppSpec.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


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
    test_workspace_requires_browser_addressable_contract_hooks()
    print("AppSpec preview projection tests passed (3 tests)")


if __name__ == "__main__":
    main()
