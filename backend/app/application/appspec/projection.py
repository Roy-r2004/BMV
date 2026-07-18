"""Deterministic projections from canonical AppSpec into preview-stage contracts.

The AppSpec owns product semantics.  These helpers intentionally derive the
legacy experience-plan shape, architect worklist, per-page codegen contract,
runtime entities, and browser journeys without asking another model to rename
or reinterpret canonical IDs.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from app.domain.schemas.app_spec import AppSpec


class PreviewScopeError(ValueError):
    """The required customer journeys cannot fit the configured preview cap."""


@dataclass(frozen=True)
class PreviewScope:
    selected_journey_ids: tuple[str, ...]
    selected_page_ids: tuple[str, ...]
    deferred_page_ids: tuple[str, ...]
    covered_requirement_ids: tuple[str, ...]
    uncovered_required_requirement_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, list[str]]:
        return {
            "selected_journey_ids": list(self.selected_journey_ids),
            "selected_page_ids": list(self.selected_page_ids),
            "deferred_page_ids": list(self.deferred_page_ids),
            "covered_requirement_ids": list(self.covered_requirement_ids),
            "uncovered_required_requirement_ids": list(
                self.uncovered_required_requirement_ids
            ),
        }


def _spec(value: AppSpec | Mapping[str, Any]) -> AppSpec:
    return value if isinstance(value, AppSpec) else AppSpec.model_validate(value)


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _journey_page_ids(journey) -> list[str]:
    return _ordered_unique(
        [journey.start_page_id]
        + [step.expected_page_id for step in journey.steps]
    )


def _must_requirement_ids(app_spec: AppSpec) -> set[str]:
    return {item.id for item in app_spec.requirements if item.priority == "must"}


def select_preview_scope(
    value: AppSpec | Mapping[str, Any],
    *,
    target_pages: int = 6,
    max_pages: int = 8,
) -> PreviewScope:
    """Select whole required journeys, then useful canonical pages up to a cap.

    Required traceability is never truncated to satisfy the cap.  If a complete
    must-have proof path requires more pages than permitted, generation stops
    with ``PreviewScopeError`` instead of silently dropping customer scope.
    """

    app_spec = _spec(value)
    if max_pages < 1:
        raise ValueError("max_pages must be positive")
    target_pages = min(max_pages, max(1, target_pages))
    pages_by_id = {page.id: page for page in app_spec.pages}
    must_ids = _must_requirement_ids(app_spec)
    required_journeys = [
        journey
        for journey in app_spec.journeys
        if must_ids.intersection(journey.requirement_ids)
    ]

    selected_journeys = [journey.id for journey in required_journeys]
    selected_pages = _ordered_unique(
        page_id
        for journey in required_journeys
        for page_id in _journey_page_ids(journey)
    )

    # Content/data/integration requirements may have no interaction journey.
    trace_by_requirement = {
        link.requirement_id: link for link in app_spec.traceability
    }
    for requirement_id in must_ids:
        link = trace_by_requirement.get(requirement_id)
        if link:
            selected_pages = _ordered_unique([*selected_pages, *link.page_ids])

    # Role entry pages are part of making every selected role/journey reachable.
    relevant_role_ids = {
        journey.role_id for journey in required_journeys
    } or {role.id for role in app_spec.roles}
    selected_pages = _ordered_unique(
        [
            *selected_pages,
            *[
                role.default_page_id
                for role in app_spec.roles
                if role.id in relevant_role_ids
            ],
        ]
    )

    unknown = [page_id for page_id in selected_pages if page_id not in pages_by_id]
    if unknown:
        raise PreviewScopeError(
            "AppSpec preview scope references unknown pages: " + ", ".join(unknown)
        )
    if len(selected_pages) > max_pages:
        raise PreviewScopeError(
            f"Required journeys need {len(selected_pages)} pages, above the "
            f"preview maximum of {max_pages}: {', '.join(selected_pages)}"
        )

    # Enrich a small product with real canonical pages; never invent padding.
    ranked_remaining = sorted(
        (page for page in app_spec.pages if page.id not in selected_pages),
        key=lambda page: (
            0 if getattr(page, "primary", False) else 1,
            0 if page.route in {"/", "/home"} else 1,
            list(pages_by_id).index(page.id),
        ),
    )
    for page in ranked_remaining:
        if len(selected_pages) >= target_pages:
            break
        selected_pages.append(page.id)

    selected_set = set(selected_pages)
    covered: list[str] = []
    for requirement in app_spec.requirements:
        link = trace_by_requirement.get(requirement.id)
        if link and set(link.page_ids).issubset(selected_set):
            covered.append(requirement.id)

    uncovered_required = sorted(must_ids.difference(covered))
    if uncovered_required:
        raise PreviewScopeError(
            "Required requirements have no complete selected-page proof path: "
            + ", ".join(uncovered_required)
        )

    return PreviewScope(
        selected_journey_ids=tuple(selected_journeys),
        selected_page_ids=tuple(selected_pages),
        deferred_page_ids=tuple(
            page.id for page in app_spec.pages if page.id not in selected_set
        ),
        covered_requirement_ids=tuple(covered),
        uncovered_required_requirement_ids=(),
    )


def _page_contract_dict(app_spec: AppSpec, page_id: str) -> dict[str, Any]:
    pages = {item.id: item for item in app_spec.pages}
    if page_id not in pages:
        raise KeyError(f"Unknown AppSpec page: {page_id}")
    page = pages[page_id]
    state_ids = set(page.state_ids)
    action_ids = set(page.action_ids)
    evidence_ids = set(page.evidence_ids)
    capability_ids = set(page.capability_ids)
    journey_ids = {
        journey.id
        for journey in app_spec.journeys
        if page_id in _journey_page_ids(journey)
    }
    requirement_ids = _ordered_unique(
        requirement_id
        for capability in app_spec.capabilities
        if capability.id in capability_ids
        for requirement_id in capability.requirement_ids
    )
    acceptance_test_ids = _ordered_unique(
        test.id
        for test in app_spec.acceptance_tests
        if set(test.requirement_ids).intersection(requirement_ids)
        or (test.journey_id and test.journey_id in journey_ids)
    )
    transition_action_ids = {
        transition.action_id for transition in app_spec.transitions
    }
    return {
        "page": page.model_dump(mode="json"),
        "requirement_ids": requirement_ids,
        "states": [
            item.model_dump(mode="json")
            for item in app_spec.states
            if item.id in state_ids
        ],
        "actions": [
            item.model_dump(mode="json")
            for item in app_spec.actions
            if item.id in action_ids
        ],
        "transitions": [
            item.model_dump(mode="json")
            for item in app_spec.transitions
            if item.action_id in action_ids
        ],
        "evidence": [
            item.model_dump(mode="json")
            for item in app_spec.evidence
            if item.id in evidence_ids
        ],
        "journeys": [
            item.model_dump(mode="json")
            for item in app_spec.journeys
            if item.id in journey_ids
        ],
        "acceptance_tests": [
            item.model_dump(mode="json")
            for item in app_spec.acceptance_tests
            if item.id in acceptance_test_ids
        ],
        "untransitioned_action_ids": sorted(action_ids.difference(transition_action_ids)),
    }


def page_contract(
    value: AppSpec | Mapping[str, Any], page_id: str
) -> dict[str, Any]:
    return _page_contract_dict(_spec(value), page_id)


def to_experience_plan_seed(
    value: AppSpec | Mapping[str, Any], scope: PreviewScope
) -> dict[str, Any]:
    app_spec = _spec(value)
    selected = set(scope.selected_page_ids)
    capabilities = {item.id: item for item in app_spec.capabilities}
    pages = {item.id: item for item in app_spec.pages}

    role_rows: list[dict[str, Any]] = []
    for role in app_spec.roles:
        role_pages = [
            page for page in app_spec.pages
            if page.id in selected and role.id in page.role_ids
        ]
        if not role_pages:
            continue
        role_rows.append(
            {
                "id": role.id,
                "label": role.name,
                "tagline": role.description,
                "defaultPath": pages[role.default_page_id].route,
                "navigation": {
                    "type": "top_nav" if all(p.surface == "public" for p in role_pages) else "sidebar",
                    "links": [
                        {
                            "label": page.name,
                            "page_id": page.id,
                            "style": "link",
                        }
                        for page in role_pages
                    ],
                },
                "pages": [
                    {
                        "id": page.id,
                        "title": page.name,
                        "page_type": "canonical-product-surface",
                        "surface": page.surface,
                        "purpose": page.purpose,
                        "sections": [],
                        "features_to_showcase": [
                            capabilities[capability_id].name
                            for capability_id in page.capability_ids
                        ],
                        "layout_notes": "",
                        "sample_data_notes": "",
                        "app_spec_contract": _page_contract_dict(app_spec, page.id),
                    }
                    for page in role_pages
                ],
            }
        )

    return {
        "product_intent": app_spec.product_intent.model_dump(mode="json"),
        "design_system": {},
        "design_direction": "",
        "public_direction": "",
        "ops_direction": "",
        "consistency_rules": [],
        "feature_coverage": [
            {
                "requirement_id": link.requirement_id,
                "capability_ids": list(link.capability_ids),
                "page_ids": [page_id for page_id in link.page_ids if page_id in selected],
                "evidence_ids": list(link.evidence_ids),
                "acceptance_test_ids": list(link.acceptance_test_ids),
            }
            for link in app_spec.traceability
            if link.requirement_id in scope.covered_requirement_ids
        ],
        "roles": role_rows,
        "app_spec_scope": scope.as_dict(),
    }


def merge_experience_plan_enrichment(
    canonical_seed: Mapping[str, Any],
    enrichment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply visual/UX enrichment without allowing semantic plan drift.

    The planner is useful for skeleton selection, section composition, sample
    content, and art direction.  It is not allowed to add/drop/rename the roles
    and pages projected from AppSpec.  This merge is deliberately allow-listed
    so a plausible-looking planner response cannot become a second product
    specification.
    """

    proposed = dict(enrichment or {})
    result = dict(canonical_seed)
    for key in (
        "design_system",
        "design_direction",
        "public_direction",
        "ops_direction",
        "consistency_rules",
    ):
        if proposed.get(key):
            result[key] = proposed[key]

    proposed_roles = {
        str(role.get("id") or "").casefold(): role
        for role in proposed.get("roles") or []
        if isinstance(role, Mapping)
    }
    merged_roles: list[dict[str, Any]] = []
    for canonical_role in canonical_seed.get("roles") or []:
        role = dict(canonical_role)
        proposed_role = proposed_roles.get(str(role.get("id") or "").casefold(), {})
        for key in ("tagline",):
            if proposed_role.get(key):
                role[key] = proposed_role[key]

        canonical_nav = dict(role.get("navigation") or {})
        proposed_nav = proposed_role.get("navigation") or {}
        if proposed_nav.get("type"):
            canonical_nav["type"] = proposed_nav["type"]
        proposed_links = {
            str(link.get("page_id") or "").casefold(): link
            for link in proposed_nav.get("links") or []
            if isinstance(link, Mapping)
        }
        links: list[dict[str, Any]] = []
        for canonical_link in canonical_nav.get("links") or []:
            link = dict(canonical_link)
            proposed_link = proposed_links.get(
                str(link.get("page_id") or "").casefold(), {}
            )
            if proposed_link.get("style"):
                link["style"] = proposed_link["style"]
            links.append(link)
        canonical_nav["links"] = links
        role["navigation"] = canonical_nav

        proposed_pages = {
            str(page.get("id") or "").casefold(): page
            for page in proposed_role.get("pages") or []
            if isinstance(page, Mapping)
        }
        pages: list[dict[str, Any]] = []
        for canonical_page in role.get("pages") or []:
            page = dict(canonical_page)
            proposed_page = proposed_pages.get(
                str(page.get("id") or "").casefold(), {}
            )
            for key in (
                "page_type",
                "skeleton_id",
                "section_slots",
                "sections",
                "layout_notes",
                "sample_data_notes",
            ):
                if proposed_page.get(key):
                    page[key] = proposed_page[key]
            pages.append(page)
        role["pages"] = pages
        merged_roles.append(role)
    result["roles"] = merged_roles
    return result


def _pascal(value: str) -> str:
    # Split camelCase / kebab / snake so aboutPage → AboutPage (not Aboutpage).
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value or "")
    parts = re.findall(r"[A-Za-z0-9]+", spaced)
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) or "Page"


def _component_file(page, app_spec: AppSpec) -> str:
    stem = _pascal(page.id.removeprefix("PAGE-").removeprefix("page-"))
    if not stem.lower().endswith("page"):
        stem += "Page"
    elif stem.endswith("page"):
        stem = stem[:-4] + "Page"
    if page.surface == "public":
        return f"src/pages/{stem}.tsx"
    role_id = page.role_ids[0] if page.role_ids else "ops"
    folder = re.sub(r"[^a-z0-9]+", "-", role_id.lower()).strip("-") or "ops"
    return f"src/pages/{folder}/{stem}.tsx"


def to_architecture_seed(
    value: AppSpec | Mapping[str, Any], scope: PreviewScope
) -> dict[str, Any]:
    app_spec = _spec(value)
    selected = set(scope.selected_page_ids)
    pages_by_id = {item.id: item for item in app_spec.pages}
    routes: list[dict[str, Any]] = []
    for page_id in scope.selected_page_ids:
        page = pages_by_id[page_id]
        contract = _page_contract_dict(app_spec, page.id)
        routes.append(
            {
                "path": page.route,
                "page_id": page.id,
                "app_spec_page_id": page.id,
                "role_id": page.role_ids[0],
                "title": page.name,
                "component_file": _component_file(page, app_spec),
                "layout": "public" if page.surface == "public" else "admin",
                "surface": page.surface,
                "purpose": page.purpose,
                "features": [
                    capability.name
                    for capability in app_spec.capabilities
                    if capability.id in page.capability_ids
                ],
                "requirement_ids": contract["requirement_ids"],
                "journey_ids": [item["id"] for item in contract["journeys"]],
                "state_ids": list(page.state_ids),
                "action_ids": list(page.action_ids),
                "evidence_ids": list(page.evidence_ids),
                "acceptance_test_ids": [
                    item["id"] for item in contract["acceptance_tests"]
                ],
            }
        )
    roles = []
    for role in app_spec.roles:
        owned = [route for route in routes if role.id in pages_by_id[route["page_id"]].role_ids]
        if not owned:
            continue
        default_page = pages_by_id.get(role.default_page_id)
        default_path = (
            default_page.route
            if default_page and default_page.id in selected
            else owned[0]["path"]
        )
        roles.append(
            {
                "id": role.id,
                "label": role.name,
                "defaultPath": default_path,
                "route_prefix": "",
                "icon": "users",
            }
        )
    return {
        "app_name": re.sub(
            r"[^a-z0-9]+", "-", app_spec.product_intent.name.lower()
        ).strip("-") or "preview-app",
        "design_direction": "",
        "roles": roles,
        "routes": routes,
        "files_to_generate": [
            {
                "path": route["component_file"],
                "kind": "page",
                "instructions": route["purpose"],
                "app_spec_page_id": route["page_id"],
            }
            for route in routes
        ],
        "app_spec_scope": scope.as_dict(),
    }


def merge_architecture_enrichment(
    canonical_seed: Mapping[str, Any],
    enrichment: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Keep the canonical route/file worklist while accepting design choices."""

    proposed = dict(enrichment or {})
    result = dict(canonical_seed)
    if proposed.get("design_direction"):
        result["design_direction"] = proposed["design_direction"]

    proposed_roles = {
        str(role.get("id") or "").casefold(): role
        for role in proposed.get("roles") or []
        if isinstance(role, Mapping)
    }
    roles: list[dict[str, Any]] = []
    for canonical_role in canonical_seed.get("roles") or []:
        role = dict(canonical_role)
        proposed_role = proposed_roles.get(str(role.get("id") or "").casefold(), {})
        if proposed_role.get("icon"):
            role["icon"] = proposed_role["icon"]
        roles.append(role)
    result["roles"] = roles

    def _route_key(route: Mapping[str, Any]) -> str:
        return str(
            route.get("app_spec_page_id") or route.get("page_id") or ""
        ).casefold()

    proposed_routes = {
        _route_key(route): route
        for route in proposed.get("routes") or []
        if isinstance(route, Mapping) and _route_key(route)
    }
    routes: list[dict[str, Any]] = []
    for canonical_route in canonical_seed.get("routes") or []:
        route = dict(canonical_route)
        proposed_route = proposed_routes.get(_route_key(route), {})
        # These fields describe presentation inside a canonical route. Paths,
        # ownership, purpose, features, and proof IDs always remain canonical.
        for key in ("skeleton_id", "section_slots"):
            if proposed_route.get(key):
                route[key] = proposed_route[key]
        routes.append(route)
    result["routes"] = routes

    proposed_files_by_page = {
        str(item.get("app_spec_page_id") or "").casefold(): item
        for item in proposed.get("files_to_generate") or []
        if isinstance(item, Mapping) and item.get("app_spec_page_id")
    }
    proposed_files_by_path = {
        str(item.get("path") or "").replace("\\", "/").casefold(): item
        for item in proposed.get("files_to_generate") or []
        if isinstance(item, Mapping) and item.get("path")
    }
    files: list[dict[str, Any]] = []
    for canonical_file in canonical_seed.get("files_to_generate") or []:
        item = dict(canonical_file)
        proposed_file = proposed_files_by_page.get(
            str(item.get("app_spec_page_id") or "").casefold()
        ) or proposed_files_by_path.get(
            str(item.get("path") or "").replace("\\", "/").casefold()
        )
        if proposed_file and proposed_file.get("instructions"):
            item["instructions"] = proposed_file["instructions"]
        files.append(item)
    result["files_to_generate"] = files
    return result


def brand_projection(value: AppSpec | Mapping[str, Any]) -> dict[str, Any]:
    app_spec = _spec(value)
    return {
        "product_intent": app_spec.product_intent.model_dump(mode="json"),
        "roles": [item.model_dump(mode="json") for item in app_spec.roles],
        "capabilities": [
            item.model_dump(mode="json") for item in app_spec.capabilities
        ],
        "assumptions": [item.model_dump(mode="json") for item in app_spec.assumptions],
    }


def runtime_projection(
    value: AppSpec | Mapping[str, Any], scope: PreviewScope
) -> dict[str, Any]:
    app_spec = _spec(value)
    selected = set(scope.selected_page_ids)
    action_ids = {
        action.id for action in app_spec.actions if action.page_id in selected
    }
    affected_entity_ids = {
        action.entity_id for action in app_spec.actions
        if action.id in action_ids and action.entity_id
    }
    affected_entity_ids.update(
        effect.entity_id
        for transition in app_spec.transitions
        if transition.action_id in action_ids
        for effect in transition.effects
    )
    return {
        "entities": [
            item.model_dump(mode="json")
            for item in app_spec.entities
            if item.id in affected_entity_ids
        ],
        "actions": [
            item.model_dump(mode="json")
            for item in app_spec.actions
            if item.id in action_ids
        ],
        "transitions": [
            item.model_dump(mode="json")
            for item in app_spec.transitions
            if item.action_id in action_ids
        ],
    }


def browser_projection(
    value: AppSpec | Mapping[str, Any], scope: PreviewScope
) -> dict[str, Any]:
    app_spec = _spec(value)
    selected_journeys = set(scope.selected_journey_ids)
    covered_requirements = set(scope.covered_requirement_ids)
    return {
        "schema_version": app_spec.schema_version,
        "hooks": {
            "page_attribute": "data-appspec-page",
            "action_attribute": "data-appspec-action",
            "evidence_attribute": "data-appspec-evidence",
        },
        "journeys": [
            item.model_dump(mode="json")
            for item in app_spec.journeys
            if item.id in selected_journeys
        ],
        "acceptance_tests": [
            item.model_dump(mode="json")
            for item in app_spec.acceptance_tests
            if set(item.requirement_ids).intersection(covered_requirements)
        ],
    }


__all__ = [
    "PreviewScope",
    "PreviewScopeError",
    "brand_projection",
    "browser_projection",
    "merge_architecture_enrichment",
    "merge_experience_plan_enrichment",
    "page_contract",
    "runtime_projection",
    "select_preview_scope",
    "to_architecture_seed",
    "to_experience_plan_seed",
]
