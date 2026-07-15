"""Pure, deterministic semantic validation for the canonical AppSpec.

The schema rejects malformed values.  This module validates relationships that
span schema objects: references, state graphs, executable journeys, acceptance
proof, and requirement traceability.  It deliberately performs no I/O and has
no dependency on prompts, providers, persistence, configuration, or pipelines.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Literal, Optional, Sequence, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from app.domain.schemas.app_spec import AppSpec, EntityField


PathPart = Union[str, int]
IssuePath = Tuple[PathPart, ...]


class ValidationIssue(BaseModel):
    """One stable, machine-readable semantic validation finding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    severity: Literal["error", "warning"]
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    path: IssuePath = ()
    related_ids: Tuple[str, ...] = ()


class ValidationReport(BaseModel):
    """Deterministic validation result.  Warnings do not make a spec invalid."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_valid: bool
    issues: Tuple[ValidationIssue, ...] = ()

    @property
    def passed(self) -> bool:
        """Compatibility alias for integrations that call a valid report passed."""

        return self.is_valid

    @property
    def errors(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "error")

    @property
    def warnings(self) -> Tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warning")


def canonical_app_spec_json(spec: AppSpec) -> str:
    """Serialize an AppSpec canonically for comparison, storage, and hashing."""

    return json.dumps(
        spec.model_dump(mode="json", by_alias=True, exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def app_spec_sha256(spec: AppSpec) -> str:
    """Return the lowercase SHA-256 digest of canonical AppSpec JSON."""

    return hashlib.sha256(canonical_app_spec_json(spec).encode("utf-8")).hexdigest()


class _Collector:
    def __init__(self) -> None:
        self.issues: List[ValidationIssue] = []

    def add(
        self,
        code: str,
        message: str,
        path: Sequence[PathPart] = (),
        related_ids: Sequence[str] = (),
        *,
        severity: Literal["error", "warning"] = "error",
    ) -> None:
        self.issues.append(
            ValidationIssue(
                severity=severity,
                code=code,
                message=message,
                path=tuple(path),
                related_ids=tuple(related_ids),
            )
        )

    def report(self) -> ValidationReport:
        severity_rank = {"error": 0, "warning": 1}
        ordered = tuple(
            sorted(
                self.issues,
                key=lambda issue: (
                    tuple(f"{type(part).__name__}:{part}" for part in issue.path),
                    severity_rank[issue.severity],
                    issue.code,
                    issue.message,
                    tuple(value.casefold() for value in issue.related_ids),
                ),
            )
        )
        return ValidationReport(
            is_valid=not any(issue.severity == "error" for issue in ordered),
            issues=ordered,
        )


def _objects_by_id(items: Iterable[Any]) -> Dict[str, Any]:
    return {str(item.id): item for item in items}


def _require_reference(
    collector: _Collector,
    value: str,
    objects: Dict[str, Any],
    path: IssuePath,
    target: str,
) -> Optional[Any]:
    obj = objects.get(value)
    if obj is not None:
        return obj
    folded = value.casefold()
    case_matches = sorted(key for key in objects if key.casefold() == folded)
    if case_matches:
        collector.add(
            "reference_case_mismatch",
            f"{target} reference {value!r} must use canonical ID {case_matches[0]!r}.",
            path,
            (value, case_matches[0]),
        )
    else:
        collector.add(
            "missing_reference",
            f"{target} reference {value!r} does not exist.",
            path,
            (value,),
        )
    return None


def _reject_duplicate_references(
    collector: _Collector,
    values: Sequence[str],
    path: IssuePath,
) -> None:
    seen: Dict[str, str] = {}
    for index, value in enumerate(values):
        folded = value.casefold()
        if folded in seen:
            collector.add(
                "duplicate_reference",
                f"Reference {value!r} duplicates {seen[folded]!r} (IDs are case-insensitive).",
                path + (index,),
                (seen[folded], value),
            )
        else:
            seen[folded] = value


def _all_identified_objects(spec: AppSpec) -> Iterable[Tuple[str, IssuePath]]:
    collection_names = (
        "requirements",
        "assumptions",
        "open_questions",
        "roles",
        "entities",
        "capabilities",
        "pages",
        "states",
        "actions",
        "transitions",
        "evidence",
        "journeys",
        "acceptance_tests",
        "deferred_scope",
    )
    for name in collection_names:
        for index, item in enumerate(getattr(spec, name)):
            yield item.id, (name, index, "id")
    for entity_index, entity in enumerate(spec.entities):
        for field_index, field in enumerate(entity.fields):
            yield field.id, ("entities", entity_index, "fields", field_index, "id")
    for journey_index, journey in enumerate(spec.journeys):
        for step_index, step in enumerate(journey.steps):
            yield step.id, ("journeys", journey_index, "steps", step_index, "id")


def _validate_global_ids(spec: AppSpec, collector: _Collector) -> None:
    seen: Dict[str, Tuple[str, IssuePath]] = {}
    for value, path in _all_identified_objects(spec):
        folded = value.casefold()
        previous = seen.get(folded)
        if previous is None:
            seen[folded] = (value, path)
            continue
        previous_value, previous_path = previous
        collector.add(
            "duplicate_global_id",
            (
                f"ID {value!r} duplicates {previous_value!r}; every AppSpec ID must "
                "be globally unique, case-insensitively."
            ),
            path,
            (previous_value, value),
        )
        collector.add(
            "duplicate_global_id",
            f"ID {previous_value!r} is also used at {'.'.join(map(str, path))}.",
            previous_path,
            (previous_value, value),
        )


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


def _validate_effect(
    collector: _Collector,
    effect: Any,
    path: IssuePath,
    entities: Dict[str, Any],
    fields: Dict[str, EntityField],
) -> None:
    entity = _require_reference(
        collector, effect.entity_id, entities, path + ("entity_id",), "entity"
    )
    field = _require_reference(
        collector, effect.field_id, fields, path + ("field_id",), "entity field"
    )
    if entity is not None and field is not None and field not in entity.fields:
        collector.add(
            "effect_field_entity_mismatch",
            f"Field {field.id!r} does not belong to entity {entity.id!r}.",
            path + ("field_id",),
            (entity.id, field.id),
        )
    if effect.operation == "clear":
        if effect.value is not None:
            collector.add(
                "clear_effect_has_value",
                "A clear effect must not declare value.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
        return
    if effect.value is None:
        collector.add(
            "effect_value_required",
            f"Effect operation {effect.operation!r} requires value.",
            path + ("value",),
            (effect.entity_id, effect.field_id),
        )
        return
    if field is None:
        return
    value = effect.value
    if effect.operation in {"increment", "decrement"}:
        if field.type not in {"integer", "number"} or isinstance(value, bool) or not isinstance(value, (int, float)):
            collector.add(
                "numeric_effect_type_mismatch",
                f"{effect.operation.title()} requires a numeric field and numeric value.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
    elif effect.operation in {"append", "remove"}:
        if field.type != "list":
            collector.add(
                "collection_effect_type_mismatch",
                f"{effect.operation.title()} requires a list field.",
                path + ("field_id",),
                (effect.entity_id, effect.field_id),
            )
    elif effect.operation == "set":
        valid = True
        if field.type in {"string", "date", "datetime", "reference", "enum"}:
            valid = isinstance(value, str)
        elif field.type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif field.type == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif field.type == "boolean":
            valid = isinstance(value, bool)
        if not valid:
            collector.add(
                "set_effect_type_mismatch",
                f"Set value is incompatible with field {field.id!r} of type {field.type!r}.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )
        if field.type == "enum" and isinstance(value, str) and value not in field.enum_values:
            collector.add(
                "enum_effect_value_unknown",
                f"Value {value!r} is not allowed by enum field {field.id!r}.",
                path + ("value",),
                (effect.entity_id, effect.field_id),
            )


def _validate_transitions(
    spec: AppSpec,
    collector: _Collector,
    *,
    entities: Dict[str, Any],
    fields: Dict[str, EntityField],
    states: Dict[str, Any],
    actions: Dict[str, Any],
) -> None:
    outgoing: Dict[str, List[Any]] = defaultdict(list)
    transition_keys: Dict[Tuple[str, str], str] = {}
    actions_with_transition = set()
    for index, transition in enumerate(spec.transitions):
        base = ("transitions", index)
        action = _require_reference(
            collector,
            transition.action_id,
            actions,
            base + ("action_id",),
            "action",
        )
        source = _require_reference(
            collector,
            transition.from_state_id,
            states,
            base + ("from_state_id",),
            "state",
        )
        target = _require_reference(
            collector,
            transition.to_state_id,
            states,
            base + ("to_state_id",),
            "state",
        )
        key = (transition.from_state_id.casefold(), transition.action_id.casefold())
        previous = transition_keys.get(key)
        if previous:
            collector.add(
                "ambiguous_transition",
                f"State/action pair already has transition {previous!r}.",
                base,
                (previous, transition.id),
            )
        else:
            transition_keys[key] = transition.id
        if source is not None:
            outgoing[source.id].append(transition)
        if action is not None:
            actions_with_transition.add(action.id)
        if action is not None and source is not None and action.page_id != source.page_id:
            collector.add(
                "transition_action_page_mismatch",
                f"Action {action.id!r} is not on source state {source.id!r}'s page.",
                base + ("action_id",),
                (transition.id, action.id, source.id),
            )
        if action is not None and source is not None and target is not None:
            if action.kind != "navigate" and source.page_id != target.page_id:
                collector.add(
                    "cross_page_transition_requires_navigation",
                    "Only navigate actions may transition between pages.",
                    base + ("to_state_id",),
                    (transition.id, action.id, source.page_id, target.page_id),
                )
        for effect_index, effect in enumerate(transition.effects):
            _validate_effect(
                collector,
                effect,
                base + ("effects", effect_index),
                entities,
                fields,
            )

    for index, action in enumerate(spec.actions):
        if action.id not in actions_with_transition:
            collector.add(
                "action_without_transition",
                f"Action {action.id!r} has no state transition.",
                ("actions", index, "id"),
                (action.id,),
            )
    for index, state in enumerate(spec.states):
        if not state.terminal and not outgoing.get(state.id):
            collector.add(
                "nonterminal_state_dead_end",
                f"Nonterminal state {state.id!r} has no outgoing transition.",
                ("states", index, "terminal"),
                (state.id,),
            )

    initial_ids = [state.id for state in spec.states if state.initial]
    reachable = set(initial_ids)
    queue = deque(initial_ids)
    while queue:
        state_id = queue.popleft()
        for transition in outgoing.get(state_id, ()):
            if transition.to_state_id in states and transition.to_state_id not in reachable:
                reachable.add(transition.to_state_id)
                queue.append(transition.to_state_id)
    for index, state in enumerate(spec.states):
        if state.id not in reachable:
            collector.add(
                "unreachable_state",
                f"State {state.id!r} is unreachable from every page's initial state.",
                ("states", index, "id"),
                (state.id,),
            )


def _validate_journeys(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    roles: Dict[str, Any],
    pages: Dict[str, Any],
    states: Dict[str, Any],
    actions: Dict[str, Any],
    transitions: Dict[str, Any],
    evidence: Dict[str, Any],
) -> None:
    for index, journey in enumerate(spec.journeys):
        base = ("journeys", index)
        role = _require_reference(
            collector, journey.role_id, roles, base + ("role_id",), "role"
        )
        start_page = _require_reference(
            collector, journey.start_page_id, pages, base + ("start_page_id",), "page"
        )
        start_state = _require_reference(
            collector, journey.start_state_id, states, base + ("start_state_id",), "state"
        )
        if start_page is not None and start_state is not None and start_state.page_id != start_page.id:
            collector.add(
                "journey_start_mismatch",
                f"Journey start state {start_state.id!r} is not on page {start_page.id!r}.",
                base + ("start_state_id",),
                (journey.id, start_page.id, start_state.id),
            )
        if role is not None and start_page is not None and role.id not in start_page.role_ids:
            collector.add(
                "journey_role_page_mismatch",
                f"Journey role {role.id!r} cannot access start page {start_page.id!r}.",
                base + ("role_id",),
                (journey.id, role.id, start_page.id),
            )
        _reject_duplicate_references(
            collector, journey.requirement_ids, base + ("requirement_ids",)
        )
        for ref_index, value in enumerate(journey.requirement_ids):
            _require_reference(
                collector,
                value,
                requirements,
                base + ("requirement_ids", ref_index),
                "requirement",
            )
        current_state_id = journey.start_state_id
        for step_index, step in enumerate(journey.steps):
            step_base = base + ("steps", step_index)
            action = _require_reference(
                collector, step.action_id, actions, step_base + ("action_id",), "action"
            )
            transition = _require_reference(
                collector,
                step.transition_id,
                transitions,
                step_base + ("transition_id",),
                "transition",
            )
            expected_page = _require_reference(
                collector,
                step.expected_page_id,
                pages,
                step_base + ("expected_page_id",),
                "page",
            )
            expected_state = _require_reference(
                collector,
                step.expected_state_id,
                states,
                step_base + ("expected_state_id",),
                "state",
            )
            if transition is not None:
                if transition.action_id != step.action_id:
                    collector.add(
                        "journey_step_action_mismatch",
                        f"Transition {transition.id!r} uses action {transition.action_id!r}.",
                        step_base + ("action_id",),
                        (journey.id, step.id, transition.id),
                    )
                if transition.from_state_id != current_state_id:
                    collector.add(
                        "journey_step_chain_broken",
                        f"Transition starts at {transition.from_state_id!r}, expected {current_state_id!r}.",
                        step_base + ("transition_id",),
                        (journey.id, step.id, transition.id),
                    )
                if transition.to_state_id != step.expected_state_id:
                    collector.add(
                        "journey_step_state_mismatch",
                        f"Transition ends at {transition.to_state_id!r}, not {step.expected_state_id!r}.",
                        step_base + ("expected_state_id",),
                        (journey.id, step.id, transition.id),
                    )
            if action is not None and action.role_id != journey.role_id:
                collector.add(
                    "journey_step_role_mismatch",
                    f"Action {action.id!r} belongs to role {action.role_id!r}, not journey role {journey.role_id!r}.",
                    step_base + ("action_id",),
                    (journey.id, step.id, action.id),
                )
            if expected_page is not None and expected_state is not None and expected_state.page_id != expected_page.id:
                collector.add(
                    "journey_step_page_mismatch",
                    f"Expected state {expected_state.id!r} is not on expected page {expected_page.id!r}.",
                    step_base + ("expected_page_id",),
                    (journey.id, step.id, expected_page.id, expected_state.id),
                )
            _reject_duplicate_references(
                collector, step.evidence_ids, step_base + ("evidence_ids",)
            )
            for ref_index, value in enumerate(step.evidence_ids):
                item = _require_reference(
                    collector,
                    value,
                    evidence,
                    step_base + ("evidence_ids", ref_index),
                    "evidence",
                )
                if item is not None and item.page_id != step.expected_page_id:
                    collector.add(
                        "journey_evidence_page_mismatch",
                        f"Evidence {item.id!r} is not on expected page {step.expected_page_id!r}.",
                        step_base + ("evidence_ids", ref_index),
                        (journey.id, step.id, item.id),
                    )
            current_state_id = step.expected_state_id


def _validate_acceptance_tests(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    journeys: Dict[str, Any],
    pages: Dict[str, Any],
    states: Dict[str, Any],
    evidence: Dict[str, Any],
) -> None:
    for index, test in enumerate(spec.acceptance_tests):
        base = ("acceptance_tests", index)
        _reject_duplicate_references(
            collector, test.requirement_ids, base + ("requirement_ids",)
        )
        for ref_index, value in enumerate(test.requirement_ids):
            _require_reference(
                collector,
                value,
                requirements,
                base + ("requirement_ids", ref_index),
                "requirement",
            )
        journey = None
        if test.journey_id is not None:
            journey = _require_reference(
                collector, test.journey_id, journeys, base + ("journey_id",), "journey"
            )
            if journey is not None:
                unrelated = sorted(set(test.requirement_ids) - set(journey.requirement_ids))
                if unrelated:
                    collector.add(
                        "acceptance_journey_requirement_mismatch",
                        "Acceptance test claims requirements that its journey does not exercise.",
                        base + ("requirement_ids",),
                        (test.id, journey.id, *unrelated),
                    )
        for assertion_index, assertion in enumerate(test.assertions):
            assertion_base = base + ("assertions", assertion_index)
            if assertion.kind == "route" and assertion.page_id is None:
                collector.add(
                    "route_assertion_page_required",
                    "A route assertion requires page_id.",
                    assertion_base + ("page_id",),
                    (test.id,),
                )
            if assertion.kind == "visible" and assertion.evidence_id is None:
                collector.add(
                    "visible_assertion_evidence_required",
                    "A visible assertion requires evidence_id.",
                    assertion_base + ("evidence_id",),
                    (test.id,),
                )
            if assertion.kind == "state" and assertion.state_id is None:
                collector.add(
                    "state_assertion_state_required",
                    "A state assertion requires state_id.",
                    assertion_base + ("state_id",),
                    (test.id,),
                )
            page = None
            state = None
            item = None
            if assertion.page_id is not None:
                page = _require_reference(
                    collector,
                    assertion.page_id,
                    pages,
                    assertion_base + ("page_id",),
                    "page",
                )
            if assertion.state_id is not None:
                state = _require_reference(
                    collector,
                    assertion.state_id,
                    states,
                    assertion_base + ("state_id",),
                    "state",
                )
            if assertion.evidence_id is not None:
                item = _require_reference(
                    collector,
                    assertion.evidence_id,
                    evidence,
                    assertion_base + ("evidence_id",),
                    "evidence",
                )
            if page is not None and state is not None and state.page_id != page.id:
                collector.add(
                    "assertion_state_page_mismatch",
                    f"State {state.id!r} is not on asserted page {page.id!r}.",
                    assertion_base + ("state_id",),
                    (test.id, page.id, state.id),
                )
            if page is not None and item is not None and item.page_id != page.id:
                collector.add(
                    "assertion_evidence_page_mismatch",
                    f"Evidence {item.id!r} is not on asserted page {page.id!r}.",
                    assertion_base + ("evidence_id",),
                    (test.id, page.id, item.id),
                )


def _validate_traceability(
    spec: AppSpec,
    collector: _Collector,
    *,
    requirements: Dict[str, Any],
    capabilities: Dict[str, Any],
    pages: Dict[str, Any],
    evidence: Dict[str, Any],
    journeys: Dict[str, Any],
    acceptance_tests: Dict[str, Any],
) -> None:
    traced: Dict[str, int] = {}
    for index, link in enumerate(spec.traceability):
        base = ("traceability", index)
        requirement = _require_reference(
            collector,
            link.requirement_id,
            requirements,
            base + ("requirement_id",),
            "requirement",
        )
        folded = link.requirement_id.casefold()
        if folded in traced:
            collector.add(
                "duplicate_traceability_link",
                f"Requirement {link.requirement_id!r} has more than one traceability link.",
                base + ("requirement_id",),
                (link.requirement_id,),
            )
        else:
            traced[folded] = index
        resolved_capabilities = []
        resolved_pages = []
        resolved_evidence = []
        resolved_journeys = []
        resolved_tests = []
        groups = (
            ("capability_ids", link.capability_ids, capabilities, "capability", resolved_capabilities),
            ("page_ids", link.page_ids, pages, "page", resolved_pages),
            ("evidence_ids", link.evidence_ids, evidence, "evidence", resolved_evidence),
            ("journey_ids", link.journey_ids, journeys, "journey", resolved_journeys),
            ("acceptance_test_ids", link.acceptance_test_ids, acceptance_tests, "acceptance test", resolved_tests),
        )
        for field_name, values, objects, target, output in groups:
            _reject_duplicate_references(collector, values, base + (field_name,))
            for ref_index, value in enumerate(values):
                obj = _require_reference(
                    collector,
                    value,
                    objects,
                    base + (field_name, ref_index),
                    target,
                )
                if obj is not None:
                    output.append(obj)
        if requirement is None:
            continue
        for capability in resolved_capabilities:
            if requirement.id not in capability.requirement_ids:
                collector.add(
                    "trace_capability_requirement_mismatch",
                    f"Capability {capability.id!r} does not implement requirement {requirement.id!r}.",
                    base + ("capability_ids",),
                    (requirement.id, capability.id),
                )
        capability_ids = {item.id for item in resolved_capabilities}
        page_ids = {item.id for item in resolved_pages}
        for page in resolved_pages:
            if not capability_ids.intersection(page.capability_ids):
                collector.add(
                    "trace_page_capability_mismatch",
                    f"Page {page.id!r} exposes none of the traced capabilities.",
                    base + ("page_ids",),
                    (requirement.id, page.id),
                )
        for item in resolved_evidence:
            if item.page_id not in page_ids or not capability_ids.intersection(item.capability_ids):
                collector.add(
                    "trace_evidence_mismatch",
                    f"Evidence {item.id!r} is not attached to a traced page and capability.",
                    base + ("evidence_ids",),
                    (requirement.id, item.id),
                )
        for journey in resolved_journeys:
            if requirement.id not in journey.requirement_ids:
                collector.add(
                    "trace_journey_requirement_mismatch",
                    f"Journey {journey.id!r} does not exercise requirement {requirement.id!r}.",
                    base + ("journey_ids",),
                    (requirement.id, journey.id),
                )
        for test in resolved_tests:
            if requirement.id not in test.requirement_ids:
                collector.add(
                    "trace_test_requirement_mismatch",
                    f"Acceptance test {test.id!r} does not prove requirement {requirement.id!r}.",
                    base + ("acceptance_test_ids",),
                    (requirement.id, test.id),
                )
        if requirement.verification_mode == "interaction":
            if not resolved_journeys:
                collector.add(
                    "interaction_requirement_journey_required",
                    f"Interaction requirement {requirement.id!r} needs a traced journey.",
                    base + ("journey_ids",),
                    (requirement.id,),
                )
            if resolved_tests and not any(test.journey_id in {j.id for j in resolved_journeys} for test in resolved_tests):
                collector.add(
                    "interaction_requirement_journey_test_required",
                    f"Interaction requirement {requirement.id!r} needs a journey-backed acceptance test.",
                    base + ("acceptance_test_ids",),
                    (requirement.id,),
                )

    deferred: Dict[str, str] = {}
    for index, item in enumerate(spec.deferred_scope):
        base = ("deferred_scope", index, "requirement_ids")
        _reject_duplicate_references(collector, item.requirement_ids, base)
        for ref_index, value in enumerate(item.requirement_ids):
            requirement = _require_reference(
                collector, value, requirements, base + (ref_index,), "requirement"
            )
            folded = value.casefold()
            if folded in deferred:
                collector.add(
                    "requirement_deferred_multiple_times",
                    f"Requirement {value!r} is already deferred by {deferred[folded]!r}.",
                    base + (ref_index,),
                    (value, deferred[folded], item.id),
                )
            else:
                deferred[folded] = item.id
            if requirement is not None and requirement.priority == "must":
                collector.add(
                    "must_requirement_cannot_be_deferred",
                    f"Must requirement {requirement.id!r} cannot be deferred.",
                    base + (ref_index,),
                    (requirement.id, item.id),
                )

    for index, requirement in enumerate(spec.requirements):
        folded = requirement.id.casefold()
        is_traced = folded in traced
        is_deferred = folded in deferred
        if is_traced and is_deferred:
            collector.add(
                "requirement_traced_and_deferred",
                f"Requirement {requirement.id!r} cannot be both traced and deferred.",
                ("requirements", index, "id"),
                (requirement.id,),
            )
        elif not is_traced and not is_deferred:
            collector.add(
                "requirement_unaccounted_for",
                f"Requirement {requirement.id!r} must be traced or explicitly deferred.",
                ("requirements", index, "id"),
                (requirement.id,),
            )

    for index, question in enumerate(spec.open_questions):
        if question.blocking:
            collector.add(
                "blocking_open_question",
                f"Blocking question {question.id!r} must be resolved before approval.",
                ("open_questions", index, "blocking"),
                (question.id,),
            )


def validate_app_spec(spec: AppSpec) -> ValidationReport:
    """Validate cross-object AppSpec semantics without mutating state or doing I/O."""

    if not isinstance(spec, AppSpec):
        raise TypeError("validate_app_spec expects an AppSpec instance")
    collector = _Collector()
    _validate_global_ids(spec, collector)
    _validate_references_and_membership(spec, collector)
    return collector.report()


__all__ = [
    "ValidationIssue",
    "ValidationReport",
    "app_spec_sha256",
    "canonical_app_spec_json",
    "validate_app_spec",
]
