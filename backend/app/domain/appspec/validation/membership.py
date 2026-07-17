"""AppSpec reference and membership checks."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from app.domain.appspec.validation.acceptance import _validate_acceptance_tests
from app.domain.appspec.validation.collector import (
    _Collector,
    _objects_by_id,
    _reject_duplicate_references,
    _require_reference,
)
from app.domain.appspec.validation.journeys import _validate_journeys
from app.domain.appspec.validation.traceability import _validate_traceability
from app.domain.appspec.validation.transitions import _validate_transitions
from app.domain.schemas.app_spec import AppSpec

def _validate_references_and_membership(spec: AppSpec, collector: _Collector) -> None:
    requirements = _objects_by_id(spec.requirements)
    roles = _objects_by_id(spec.roles)
    entities = _objects_by_id(spec.entities)
    capabilities = _objects_by_id(spec.capabilities)
    pages = _objects_by_id(spec.pages)
    states = _objects_by_id(spec.states)
    actions = _objects_by_id(spec.actions)
    transitions = _objects_by_id(spec.transitions)
    evidence = _objects_by_id(spec.evidence)
    journeys = _objects_by_id(spec.journeys)
    acceptance_tests = _objects_by_id(spec.acceptance_tests)
    fields = {
        field.id: field for entity in spec.entities for field in entity.fields
    }

    routes: Dict[str, Tuple[int, str]] = {}
    for index, page in enumerate(spec.pages):
        previous = routes.get(page.route)
        if previous:
            collector.add(
                "duplicate_route",
                f"Route {page.route!r} is already owned by page {previous[1]!r}.",
                ("pages", index, "route"),
                (previous[1], page.id),
            )
        else:
            routes[page.route] = (index, page.id)

    for index, role in enumerate(spec.roles):
        page = _require_reference(
            collector,
            role.default_page_id,
            pages,
            ("roles", index, "default_page_id"),
            "page",
        )
        if page is not None and role.id not in page.role_ids:
            collector.add(
                "role_default_page_inaccessible",
                f"Role {role.id!r} cannot access its default page {page.id!r}.",
                ("roles", index, "default_page_id"),
                (role.id, page.id),
            )

    for entity_index, entity in enumerate(spec.entities):
        for field_index, field in enumerate(entity.fields):
            base = ("entities", entity_index, "fields", field_index)
            if field.type == "enum" and not field.enum_values:
                collector.add(
                    "enum_values_required",
                    f"Enum field {field.id!r} must declare enum_values.",
                    base + ("enum_values",),
                    (entity.id, field.id),
                )
            if field.type != "enum" and field.enum_values:
                collector.add(
                    "enum_values_not_allowed",
                    f"Non-enum field {field.id!r} cannot declare enum_values.",
                    base + ("enum_values",),
                    (entity.id, field.id),
                )
            if field.type == "reference":
                if field.reference_entity_id is None:
                    collector.add(
                        "reference_entity_required",
                        f"Reference field {field.id!r} must declare reference_entity_id.",
                        base + ("reference_entity_id",),
                        (entity.id, field.id),
                    )
                else:
                    _require_reference(
                        collector,
                        field.reference_entity_id,
                        entities,
                        base + ("reference_entity_id",),
                        "entity",
                    )
            elif field.reference_entity_id is not None:
                collector.add(
                    "reference_entity_not_allowed",
                    f"Non-reference field {field.id!r} cannot declare reference_entity_id.",
                    base + ("reference_entity_id",),
                    (entity.id, field.id),
                )

    for index, capability in enumerate(spec.capabilities):
        for field_name, values, objects, target in (
            ("requirement_ids", capability.requirement_ids, requirements, "requirement"),
            ("role_ids", capability.role_ids, roles, "role"),
            ("entity_ids", capability.entity_ids, entities, "entity"),
        ):
            _reject_duplicate_references(collector, values, ("capabilities", index, field_name))
            for ref_index, value in enumerate(values):
                _require_reference(
                    collector,
                    value,
                    objects,
                    ("capabilities", index, field_name, ref_index),
                    target,
                )

    for index, page in enumerate(spec.pages):
        for field_name, values, objects, target in (
            ("role_ids", page.role_ids, roles, "role"),
            ("capability_ids", page.capability_ids, capabilities, "capability"),
            ("state_ids", page.state_ids, states, "state"),
            ("action_ids", page.action_ids, actions, "action"),
            ("evidence_ids", page.evidence_ids, evidence, "evidence"),
        ):
            _reject_duplicate_references(collector, values, ("pages", index, field_name))
            for ref_index, value in enumerate(values):
                obj = _require_reference(
                    collector,
                    value,
                    objects,
                    ("pages", index, field_name, ref_index),
                    target,
                )
                if obj is not None and hasattr(obj, "page_id") and obj.page_id != page.id:
                    collector.add(
                        "page_membership_mismatch",
                        f"{target.title()} {obj.id!r} belongs to page {obj.page_id!r}, not {page.id!r}.",
                        ("pages", index, field_name, ref_index),
                        (page.id, obj.id, obj.page_id),
                    )
        page_states = [states[value] for value in page.state_ids if value in states]
        initial_count = sum(bool(state.initial) for state in page_states)
        if initial_count != 1:
            collector.add(
                "page_initial_state_count",
                f"Page {page.id!r} must contain exactly one initial state; found {initial_count}.",
                ("pages", index, "state_ids"),
                (page.id,),
            )

    for index, state in enumerate(spec.states):
        page = _require_reference(
            collector,
            state.page_id,
            pages,
            ("states", index, "page_id"),
            "page",
        )
        if page is not None and state.id not in page.state_ids:
            collector.add(
                "state_missing_from_page",
                f"State {state.id!r} is not listed by page {page.id!r}.",
                ("states", index, "page_id"),
                (state.id, page.id),
            )
        _reject_duplicate_references(
            collector, state.evidence_ids, ("states", index, "evidence_ids")
        )
        for ref_index, value in enumerate(state.evidence_ids):
            item = _require_reference(
                collector,
                value,
                evidence,
                ("states", index, "evidence_ids", ref_index),
                "evidence",
            )
            if item is not None and item.page_id != state.page_id:
                collector.add(
                    "state_evidence_page_mismatch",
                    f"Evidence {item.id!r} is not on state {state.id!r}'s page.",
                    ("states", index, "evidence_ids", ref_index),
                    (state.id, item.id),
                )

    for index, action in enumerate(spec.actions):
        page = _require_reference(
            collector,
            action.page_id,
            pages,
            ("actions", index, "page_id"),
            "page",
        )
        role = _require_reference(
            collector,
            action.role_id,
            roles,
            ("actions", index, "role_id"),
            "role",
        )
        if page is not None:
            if action.id not in page.action_ids:
                collector.add(
                    "action_missing_from_page",
                    f"Action {action.id!r} is not listed by page {page.id!r}.",
                    ("actions", index, "page_id"),
                    (action.id, page.id),
                )
            if role is not None and action.role_id not in page.role_ids:
                collector.add(
                    "action_role_page_mismatch",
                    f"Action role {action.role_id!r} cannot access page {page.id!r}.",
                    ("actions", index, "role_id"),
                    (action.id, action.role_id, page.id),
                )
        _reject_duplicate_references(
            collector, action.capability_ids, ("actions", index, "capability_ids")
        )
        for ref_index, value in enumerate(action.capability_ids):
            capability = _require_reference(
                collector,
                value,
                capabilities,
                ("actions", index, "capability_ids", ref_index),
                "capability",
            )
            if capability is not None:
                if action.role_id not in capability.role_ids:
                    collector.add(
                        "action_capability_role_mismatch",
                        f"Capability {capability.id!r} does not grant role {action.role_id!r}.",
                        ("actions", index, "capability_ids", ref_index),
                        (action.id, capability.id, action.role_id),
                    )
                if page is not None and capability.id not in page.capability_ids:
                    collector.add(
                        "action_capability_page_mismatch",
                        f"Capability {capability.id!r} is not exposed by page {page.id!r}.",
                        ("actions", index, "capability_ids", ref_index),
                        (action.id, capability.id, page.id),
                    )
        if action.entity_id is not None:
            entity = _require_reference(
                collector,
                action.entity_id,
                entities,
                ("actions", index, "entity_id"),
                "entity",
            )
            if entity is not None:
                for capability_id in action.capability_ids:
                    capability = capabilities.get(capability_id)
                    if capability is not None and entity.id not in capability.entity_ids:
                        collector.add(
                            "action_entity_capability_mismatch",
                            f"Entity {entity.id!r} is not declared by capability {capability.id!r}.",
                            ("actions", index, "entity_id"),
                            (action.id, entity.id, capability.id),
                        )

    for index, item in enumerate(spec.evidence):
        page = _require_reference(
            collector,
            item.page_id,
            pages,
            ("evidence", index, "page_id"),
            "page",
        )
        if page is not None and item.id not in page.evidence_ids:
            collector.add(
                "evidence_missing_from_page",
                f"Evidence {item.id!r} is not listed by page {page.id!r}.",
                ("evidence", index, "page_id"),
                (item.id, page.id),
            )
        _reject_duplicate_references(
            collector, item.capability_ids, ("evidence", index, "capability_ids")
        )
        for ref_index, value in enumerate(item.capability_ids):
            capability = _require_reference(
                collector,
                value,
                capabilities,
                ("evidence", index, "capability_ids", ref_index),
                "capability",
            )
            if capability is not None and page is not None and value not in page.capability_ids:
                collector.add(
                    "evidence_capability_page_mismatch",
                    f"Evidence capability {value!r} is not exposed by page {page.id!r}.",
                    ("evidence", index, "capability_ids", ref_index),
                    (item.id, value, page.id),
                )

    _validate_transitions(
        spec,
        collector,
        entities=entities,
        fields=fields,
        states=states,
        actions=actions,
    )
    _validate_journeys(
        spec,
        collector,
        requirements=requirements,
        roles=roles,
        pages=pages,
        states=states,
        actions=actions,
        transitions=transitions,
        evidence=evidence,
    )
    _validate_acceptance_tests(
        spec,
        collector,
        requirements=requirements,
        journeys=journeys,
        pages=pages,
        states=states,
        evidence=evidence,
    )
    _validate_traceability(
        spec,
        collector,
        requirements=requirements,
        capabilities=capabilities,
        pages=pages,
        evidence=evidence,
        journeys=journeys,
        acceptance_tests=acceptance_tests,
    )
