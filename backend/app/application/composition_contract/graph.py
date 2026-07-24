"""Build a stable dependency DAG from accepted Phase 3A contracts."""
from __future__ import annotations

import hashlib

from app.application.appspec.source import canonical_json
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.component_dependency_graph import (
    ComponentDependencyGraph,
    DependencyEdge,
    DependencyNode,
    GenerationBatch,
)
from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
)
from app.domain.schemas.content_data_plan import ContentDataPlan
from app.domain.schemas.interaction_contract import InteractionContract
from app.domain.schemas.page_purpose_contract import PagePurposeContract


class DependencyGraphError(ValueError):
    """The declared composition dependencies cannot form a closed DAG."""


def _node_id(kind: str, contract_id: str) -> str:
    digest = hashlib.sha256(
        f"{kind}:{contract_id}".encode("utf-8")
    ).hexdigest()[:16]
    return f"NODE-{kind.upper()}-{digest}"


def _topological_batches(
    nodes: tuple[DependencyNode, ...],
    edges: tuple[DependencyEdge, ...],
) -> tuple[tuple[str, ...], tuple[GenerationBatch, ...]]:
    order_index = {node.node_id: index for index, node in enumerate(nodes)}
    incoming = {node.node_id: 0 for node in nodes}
    dependents: dict[str, list[str]] = {
        node.node_id: [] for node in nodes
    }
    for edge in edges:
        if (
            edge.prerequisite_node_id not in incoming
            or edge.dependent_node_id not in incoming
        ):
            raise DependencyGraphError("An edge references a missing node.")
        incoming[edge.dependent_node_id] += 1
        dependents[edge.prerequisite_node_id].append(
            edge.dependent_node_id
        )
    remaining = set(incoming)
    batches: list[GenerationBatch] = []
    flattened: list[str] = []
    batch_number = 1
    while remaining:
        ready = tuple(
            sorted(
                (
                    node_id
                    for node_id in remaining
                    if incoming[node_id] == 0
                ),
                key=order_index.__getitem__,
            )
        )
        if not ready:
            raise DependencyGraphError("Component dependencies contain a cycle.")
        batches.append(
            GenerationBatch(batch=batch_number, node_ids=ready)
        )
        batch_number += 1
        flattened.extend(ready)
        for node_id in ready:
            remaining.remove(node_id)
            for dependent in dependents[node_id]:
                incoming[dependent] -= 1
    return tuple(flattened), tuple(batches)


def build_component_dependency_graph(
    *,
    refs: CompositionContractRefs,
    page_purpose: PagePurposeContract,
    page_purpose_ref: CompositionArtifactRef,
    component_plan: BusinessComponentPlan,
    component_plan_ref: CompositionArtifactRef,
    content_data_plan: ContentDataPlan,
    content_data_plan_ref: CompositionArtifactRef,
    interaction_contract: InteractionContract,
    interaction_contract_ref: CompositionArtifactRef,
) -> ComponentDependencyGraph:
    nodes: list[DependencyNode] = []
    node_by_key: dict[tuple[str, str], str] = {}

    def add(kind: str, contract_id: str) -> None:
        node_id = _node_id(kind, contract_id)
        node_by_key[(kind, contract_id)] = node_id
        nodes.append(
            DependencyNode(
                node_id=node_id,
                kind=kind,
                contract_id=contract_id,
            )
        )

    for item in content_data_plan.content_items:
        add("content", item.content_id)
    for item in content_data_plan.data_collections:
        add("data", item.collection_id)
    for item in component_plan.components:
        add("business_component", item.component_id)
    for item in page_purpose.pages:
        add("page", item.page_id)
    for item in page_purpose.pages:
        add("route", item.page_id)

    edge_keys: list[tuple[str, str]] = []

    def edge(
        prerequisite_kind: str,
        prerequisite_id: str,
        dependent_kind: str,
        dependent_id: str,
    ) -> None:
        try:
            key = (
                node_by_key[(prerequisite_kind, prerequisite_id)],
                node_by_key[(dependent_kind, dependent_id)],
            )
        except KeyError as exc:
            raise DependencyGraphError(
                "A dependency references an unknown contract ID."
            ) from exc
        if key not in edge_keys:
            edge_keys.append(key)

    for content in content_data_plan.content_items:
        for component_id in content.component_ids:
            edge(
                "content",
                content.content_id,
                "business_component",
                component_id,
            )
    for collection in content_data_plan.data_collections:
        for component_id in collection.component_ids:
            edge(
                "data",
                collection.collection_id,
                "business_component",
                component_id,
            )
    for component in component_plan.components:
        for prerequisite_id in component.requires_component_ids:
            edge(
                "business_component",
                prerequisite_id,
                "business_component",
                component.component_id,
            )
    for composition in component_plan.page_compositions:
        for component_id in composition.ordered_component_ids:
            edge(
                "business_component",
                component_id,
                "page",
                composition.page_id,
            )
    route_nodes: list[str] = []
    for page in page_purpose.pages:
        edge("page", page.page_id, "route", page.page_id)
        route_nodes.append(node_by_key[("route", page.page_id)])

    typed_nodes = tuple(nodes)
    typed_edges = tuple(
        DependencyEdge(
            prerequisite_node_id=prerequisite,
            dependent_node_id=dependent,
        )
        for prerequisite, dependent in edge_keys
    )
    order, batches = _topological_batches(typed_nodes, typed_edges)
    return ComponentDependencyGraph(
        contract_refs=refs,
        page_purpose_ref=page_purpose_ref,
        business_component_plan_ref=component_plan_ref,
        content_data_plan_ref=content_data_plan_ref,
        interaction_contract_ref=interaction_contract_ref,
        nodes=typed_nodes,
        edges=typed_edges,
        topological_order=order,
        generation_batches=batches,
        route_entry_node_ids=tuple(route_nodes),
    )


def graph_sha256(graph: ComponentDependencyGraph) -> str:
    raw = canonical_json(graph.model_dump(mode="json"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "DependencyGraphError",
    "build_component_dependency_graph",
    "graph_sha256",
]
