"""Deterministic contract-render floor projection for accepted pages.

Phase 3B proves canonical hooks textually: it asserts that ``data-bmv-*``
markers and their canonical IDs appear in generated source. A generated
business component can still mount and render nothing at runtime -- for
example an early ``return null`` when a cold-route data lookup misses -- which
leaves the accepted contract markers out of the DOM even though the source
contains them. Phase 4 then observes zero component, action, state, evidence
and transition nodes on an otherwise healthy page.

This module projects, per accepted page, the visible and functional contract
content the shared scaffold must guarantee. The projection is derived only
from accepted contracts (page purpose, business component plan, interaction
contract and content data plan); it never invents commercial features or data.
"""
from __future__ import annotations

import json
import re

from app.application.candidate_generation.context import CandidateContext


CONTRACT_FLOOR_MODULE_PATH = "src/generated/contract-floor.ts"

_ID_PREFIXES = (
    "ACCEPTANCE-TEST-",
    "TRANSITION-",
    "COMPONENT-",
    "EVIDENCE-",
    "ACTION-",
    "STATE-",
    "COMP-",
    "PAGE-",
    "TEST-",
)


def humanize_contract_id(identifier: str) -> str:
    """Render a canonical ID as readable label text.

    The label is a presentation of the accepted identifier itself, never
    invented copy.
    """

    text = str(identifier or "").strip()
    if not text:
        return "Required content"
    upper = text.upper()
    for prefix in _ID_PREFIXES:
        if upper.startswith(prefix):
            text = text[len(prefix) :]
            break
    words = [word for word in re.split(r"[^A-Za-z0-9]+", text) if word]
    if not words:
        return "Required content"
    phrase = " ".join(word.lower() for word in words)
    return phrase[:1].upper() + phrase[1:]


def _seed_record_text(collection) -> str:
    """First seed record rendered as short readable text."""

    for record in getattr(collection, "seed_records", ()):
        parts: list[str] = []
        for item in getattr(record, "values", ()):
            value = getattr(item, "value", None)
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, (tuple, list)):
                value = value[0] if value else None
            text = "" if value is None else str(value).strip()
            if text:
                parts.append(text)
            if len(parts) == 3:
                break
        if parts:
            return " - ".join(parts)
    return ""


def _evidence_text(context: CandidateContext, evidence_id: str) -> str:
    """Resolve accepted evidence content from the content data plan.

    Static accepted routes resolve their seed record through the accepted
    contract rather than through a dynamic route parameter, so the floor stays
    correct on a cold route load.
    """

    content_by_id = {
        item.content_id: item for item in context.content_data.content_items
    }
    collection_by_id = {
        item.collection_id: item
        for item in context.content_data.data_collections
    }
    for binding in context.content_data.evidence_bindings:
        if binding.evidence_id != evidence_id:
            continue
        for content_id in binding.content_ids:
            item = content_by_id.get(content_id)
            value = str(getattr(item, "value", "") or "").strip()
            if value:
                return value
        for collection_id in binding.collection_ids:
            collection = collection_by_id.get(collection_id)
            if collection is None:
                continue
            text = _seed_record_text(collection)
            if text:
                return text
    return humanize_contract_id(evidence_id)


def _state_page_routes(context: CandidateContext) -> dict[str, str]:
    """Map every accepted state onto the route that renders it."""

    route_by_page = {
        item.page_id: item.route for item in context.page_purpose.pages
    }
    routes: dict[str, str] = {}
    ambiguous: set[str] = set()
    for payload in context.content_data.state_payloads:
        route = route_by_page.get(payload.page_id)
        if route is None:
            continue
        existing = routes.get(payload.state_id)
        if existing is not None and existing != route:
            ambiguous.add(payload.state_id)
            continue
        routes[payload.state_id] = route
    for state_id in ambiguous:
        # An ambiguous destination must not silently navigate anywhere.
        routes.pop(state_id, None)
    return routes


def _page_component_ids(context: CandidateContext) -> dict[str, tuple[str, ...]]:
    return {
        item.page_id: item.ordered_component_ids
        for item in context.business_components.page_compositions
    }


def _owning_component(
    *,
    action_id: str,
    trigger_component_id: str,
    page_component_ids: tuple[str, ...],
    components_by_id: dict[str, object],
) -> str | None:
    if trigger_component_id in page_component_ids:
        return trigger_component_id
    for component_id in page_component_ids:
        component = components_by_id.get(component_id)
        if action_id in getattr(component, "action_ids", ()):
            return component_id
    return None


def build_contract_floor_hooks(
    context: CandidateContext,
) -> dict[str, list[dict[str, object]]]:
    """Project the required visible contract content for every accepted page.

    The projection is grouped by business component. Phase 4 supplements a
    group only when that component rendered no contract root at all, so a
    component that renders its own conditional states is never duplicated.
    """

    components_by_id: dict[str, object] = {
        item.component_id: item
        for item in context.business_components.components
    }
    trigger_labels = {
        item.action_id: item.trigger_label
        for item in context.business_components.action_trigger_bindings
    }
    page_components = _page_component_ids(context)
    state_routes = _state_page_routes(context)
    interactions_by_page: dict[str, list] = {}
    for interaction in context.interactions.interactions:
        interactions_by_page.setdefault(interaction.page_id, []).append(
            interaction
        )

    projection: dict[str, list[dict[str, object]]] = {}
    for page in context.page_purpose.pages:
        component_ids = page_components.get(page.page_id, ())
        hooks_by_component: dict[str, list[dict[str, str]]] = {
            component_id: [] for component_id in component_ids
        }
        page_evidence = set(page.evidence_ids)
        claimed_states: set[str] = set()
        claimed_evidence: set[str] = set()
        for component_id in component_ids:
            component = components_by_id.get(component_id)
            hooks = hooks_by_component[component_id]
            for state_id in getattr(component, "state_ids", ()):
                if state_id in claimed_states:
                    continue
                claimed_states.add(state_id)
                hooks.append(
                    {
                        "kind": "state",
                        "id": state_id,
                        "label": humanize_contract_id(state_id),
                    }
                )
            for evidence_id in getattr(component, "evidence_ids", ()):
                if evidence_id in claimed_evidence:
                    continue
                claimed_evidence.add(evidence_id)
                hooks.append(
                    {
                        "kind": "evidence",
                        "id": evidence_id,
                        "label": _evidence_text(context, evidence_id),
                    }
                )
        # Page evidence that no component claimed still belongs to the page's
        # first component so an empty component cannot drop it.
        if component_ids:
            orphan_evidence = [
                evidence_id
                for evidence_id in page.evidence_ids
                if evidence_id not in claimed_evidence
            ]
            for evidence_id in orphan_evidence:
                hooks_by_component[component_ids[0]].append(
                    {
                        "kind": "evidence",
                        "id": evidence_id,
                        "label": _evidence_text(context, evidence_id),
                    }
                )
        for interaction in interactions_by_page.get(page.page_id, []):
            owner = _owning_component(
                action_id=interaction.action_id,
                trigger_component_id=interaction.trigger_component_id,
                page_component_ids=component_ids,
                components_by_id=components_by_id,
            )
            if owner is None:
                continue
            transition = interaction.transitions[0]
            destination = state_routes.get(transition.to_state_id, "")
            action_hook: dict[str, str] = {
                "kind": "action",
                "id": interaction.action_id,
                "label": str(
                    trigger_labels.get(interaction.action_id)
                    or humanize_contract_id(interaction.action_id)
                ),
                "transitionId": transition.transition_id,
            }
            if destination and destination != page.route:
                action_hook["targetRoute"] = destination
            hooks_by_component[owner].append(action_hook)
            for evidence_id in transition.success_evidence_ids:
                if evidence_id in claimed_evidence or evidence_id in page_evidence:
                    continue
                claimed_evidence.add(evidence_id)
                hooks_by_component[owner].append(
                    {
                        "kind": "evidence",
                        "id": evidence_id,
                        "label": _evidence_text(context, evidence_id),
                    }
                )
        projection[page.page_id] = [
            {
                "componentId": component_id,
                "label": str(
                    getattr(components_by_id.get(component_id), "name", "")
                    or humanize_contract_id(component_id)
                ),
                "hooks": hooks_by_component[component_id],
            }
            for component_id in component_ids
        ]
    return projection


def render_contract_floor_projection(
    projection: dict[str, list[dict[str, object]]],
) -> str:
    """Emit the ``contract-floor.ts`` module for an already-built projection."""

    payload = json.dumps(
        projection,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=False,
    )
    return (
        'export type ContractFloorHookKind = "state" | "evidence" | "action";\n\n'
        "export type ContractFloorHook = {\n"
        "  kind: ContractFloorHookKind;\n"
        "  id: string;\n"
        "  label: string;\n"
        "  transitionId?: string;\n"
        "  targetRoute?: string;\n"
        "};\n\n"
        "export type ContractFloorComponent = {\n"
        "  componentId: string;\n"
        "  label: string;\n"
        "  hooks: readonly ContractFloorHook[];\n"
        "};\n\n"
        "export const contractFloorHooks: Readonly<\n"
        "  Record<string, readonly ContractFloorComponent[]>\n"
        f"> = {payload};\n"
    )


def render_contract_floor_module(context: CandidateContext) -> str:
    """Emit the deterministic ``contract-floor.ts`` projection module."""

    return render_contract_floor_projection(build_contract_floor_hooks(context))


__all__ = [
    "CONTRACT_FLOOR_MODULE_PATH",
    "build_contract_floor_hooks",
    "humanize_contract_id",
    "render_contract_floor_module",
    "render_contract_floor_projection",
]
