"""Deterministic component dependency DAG for Phase 3A."""
from __future__ import annotations

from typing import Literal, Tuple

from pydantic import Field, StrictInt, model_validator

from app.domain.schemas.composition_contract import (
    CompositionArtifactRef,
    CompositionContractRefs,
    Identifier,
)
from app.domain.schemas.design_contract import StrictDesignModel


COMPONENT_DEPENDENCY_GRAPH_SCHEMA_VERSION = "1.0"


class DependencyNode(StrictDesignModel):
    node_id: Identifier
    kind: Literal[
        "content",
        "data",
        "business_component",
        "page",
        "route",
    ]
    contract_id: Identifier


class DependencyEdge(StrictDesignModel):
    prerequisite_node_id: Identifier
    dependent_node_id: Identifier

    @model_validator(mode="after")
    def _not_self_referential(self) -> "DependencyEdge":
        if self.prerequisite_node_id == self.dependent_node_id:
            raise ValueError("Dependency edges cannot point to themselves")
        return self


class GenerationBatch(StrictDesignModel):
    batch: StrictInt = Field(ge=1, le=1000)
    node_ids: Tuple[Identifier, ...] = Field(min_length=1, max_length=1000)


class ComponentDependencyGraph(StrictDesignModel):
    schema_version: str = Field(
        default=COMPONENT_DEPENDENCY_GRAPH_SCHEMA_VERSION,
        pattern=r"^1\.0$",
    )
    contract_refs: CompositionContractRefs
    page_purpose_ref: CompositionArtifactRef
    business_component_plan_ref: CompositionArtifactRef
    content_data_plan_ref: CompositionArtifactRef
    interaction_contract_ref: CompositionArtifactRef
    nodes: Tuple[DependencyNode, ...] = Field(min_length=1, max_length=3000)
    edges: Tuple[DependencyEdge, ...] = Field(default=(), max_length=10000)
    topological_order: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=3000,
    )
    generation_batches: Tuple[GenerationBatch, ...] = Field(
        min_length=1,
        max_length=1000,
    )
    route_entry_node_ids: Tuple[Identifier, ...] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def _local_uniqueness_and_kinds(self) -> "ComponentDependencyGraph":
        expected = (
            (self.page_purpose_ref, "page_purpose_contract"),
            (
                self.business_component_plan_ref,
                "business_component_plan",
            ),
            (self.content_data_plan_ref, "content_data_plan"),
            (self.interaction_contract_ref, "interaction_contract"),
        )
        if any(ref.artifact_kind != kind for ref, kind in expected):
            raise ValueError("Dependency graph upstream kind is invalid")
        node_ids = tuple(node.node_id for node in self.nodes)
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("nodes cannot repeat node IDs")
        edges = tuple(
            (edge.prerequisite_node_id, edge.dependent_node_id)
            for edge in self.edges
        )
        if len(edges) != len(set(edges)):
            raise ValueError("edges cannot repeat")
        if len(self.topological_order) != len(set(self.topological_order)):
            raise ValueError("topological_order cannot repeat nodes")
        return self


__all__ = [
    "COMPONENT_DEPENDENCY_GRAPH_SCHEMA_VERSION",
    "ComponentDependencyGraph",
    "DependencyEdge",
    "DependencyNode",
    "GenerationBatch",
]
