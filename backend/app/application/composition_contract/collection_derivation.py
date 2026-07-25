"""Deterministic Tier 1 entity-collection derivation for content projection.

Does not mutate the accepted AppSpec. Derives a projection-local collection only
when Tier 1 business meaning unambiguously requires repeatable/selectable data.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from app.application.composition_contract.context import CompositionContext
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.content_data_plan import (
    DataCollection,
    SeedFieldValue,
    SeedRecord,
)
from app.domain.schemas.page_purpose_contract import PagePurposeContract

COLLECTION_PROJECTION_POLICY_REVISION = "2026-07-26.1"

CollectionDecisionCode = Literal[
    "collection_not_required",
    "collection_reused",
    "collection_derived",
    "collection_missing_required",
    "collection_ambiguous",
    "collection_missing_required_fields",
    "collection_unseedable",
    "collection_filtered_out_of_tier",
]

_WORD = re.compile(r"[a-z0-9]+")

# Repeatable / selectable business nouns that justify a Tier 1 collection.
_COLLECTION_NOUNS: dict[str, str] = {
    "service": "service",
    "services": "service",
    "product": "product",
    "products": "product",
    "listing": "listing",
    "listings": "listing",
    "course": "course",
    "courses": "course",
    "property": "property",
    "properties": "property",
    "provider": "provider",
    "providers": "provider",
    "appointment": "appointment",
    "appointments": "appointment",
    "menu": "menu_item",
    "menuitem": "menu_item",
    "menuitems": "menu_item",
    "article": "article",
    "articles": "article",
    "category": "category",
    "categories": "category",
    "inventory": "inventory_item",
    "inventoryitem": "inventory_item",
    "inventoryitems": "inventory_item",
}

# Nouns that must never alone force a Tier 1 collection.
_NON_COLLECTION_NOUNS = frozenset(
    {
        "customer",
        "customers",
        "client",
        "clients",
        "confirmation",
        "message",
        "availability",
        "calendar",
        "form",
        "profile",
        "setting",
        "settings",
        "about",
        "home",
        "contact",
        "payment",
        "checkout",
        "admin",
        "analytics",
        "seller",
        "sellers",
        "marketplace",
    }
)

_ENTITY_TYPE_META: dict[str, dict[str, str]] = {
    "service": {
        "entity_id": "ENTITY-SERVICE",
        "collection_prefix": "COLLECTION-SERVICES",
        "name": "Service",
        "description": "Selectable services offered in the Tier 1 booking journey.",
    },
    "product": {
        "entity_id": "ENTITY-PRODUCT",
        "collection_prefix": "COLLECTION-PRODUCTS",
        "name": "Product",
        "description": "Selectable products shown in the Tier 1 journey.",
    },
    "listing": {
        "entity_id": "ENTITY-LISTING",
        "collection_prefix": "COLLECTION-LISTINGS",
        "name": "Listing",
        "description": "Selectable listings shown in the Tier 1 journey.",
    },
    "course": {
        "entity_id": "ENTITY-COURSE",
        "collection_prefix": "COLLECTION-COURSES",
        "name": "Course",
        "description": "Selectable courses shown in the Tier 1 journey.",
    },
    "property": {
        "entity_id": "ENTITY-PROPERTY",
        "collection_prefix": "COLLECTION-PROPERTIES",
        "name": "Property",
        "description": "Selectable properties shown in the Tier 1 journey.",
    },
    "provider": {
        "entity_id": "ENTITY-PROVIDER",
        "collection_prefix": "COLLECTION-PROVIDERS",
        "name": "Provider",
        "description": "Selectable providers shown in the Tier 1 journey.",
    },
    "appointment": {
        "entity_id": "ENTITY-APPOINTMENT",
        "collection_prefix": "COLLECTION-APPOINTMENTS",
        "name": "Appointment",
        "description": "Appointment records for the Tier 1 journey.",
    },
    "menu_item": {
        "entity_id": "ENTITY-MENU-ITEM",
        "collection_prefix": "COLLECTION-MENU-ITEMS",
        "name": "Menu item",
        "description": "Selectable menu items shown in the Tier 1 journey.",
    },
    "article": {
        "entity_id": "ENTITY-ARTICLE",
        "collection_prefix": "COLLECTION-ARTICLES",
        "name": "Article",
        "description": "Selectable articles shown in the Tier 1 journey.",
    },
    "category": {
        "entity_id": "ENTITY-CATEGORY",
        "collection_prefix": "COLLECTION-CATEGORIES",
        "name": "Category",
        "description": "Selectable categories shown in the Tier 1 journey.",
    },
    "inventory_item": {
        "entity_id": "ENTITY-INVENTORY-ITEM",
        "collection_prefix": "COLLECTION-INVENTORY",
        "name": "Inventory item",
        "description": "Selectable inventory items shown in the Tier 1 journey.",
    },
}


@dataclass(frozen=True)
class DerivedEntityFieldSpec:
    id: str
    name: str
    type: str
    required: bool = True


@dataclass(frozen=True)
class DerivedEntitySpec:
    id: str
    name: str
    description: str
    fields: tuple[DerivedEntityFieldSpec, ...]


@dataclass
class CollectionProjectionDecision:
    """Immutable decision evidence for Tier 1 collection projection."""

    code: CollectionDecisionCode
    reason: str
    required: bool = False
    derived: bool = False
    heal_applied: bool = False
    entity_type: str | None = None
    collection: DataCollection | None = None
    derived_entity: DerivedEntitySpec | None = None
    source_references: list[str] = field(default_factory=list)
    policy_revision: str = COLLECTION_PROJECTION_POLICY_REVISION
    collection_schema_hash: str | None = None
    seed_hash: str | None = None
    before_projection_hash: str | None = None
    after_projection_hash: str | None = None
    app_spec_sha256: str | None = None
    tier1_contract_hash: str | None = None

    def to_evidence(self) -> dict[str, Any]:
        entity_payload = None
        if self.derived_entity is not None:
            entity_payload = {
                "id": self.derived_entity.id,
                "name": self.derived_entity.name,
                "description": self.derived_entity.description,
                "fields": [
                    {
                        "id": field.id,
                        "name": field.name,
                        "type": field.type,
                        "required": field.required,
                    }
                    for field in self.derived_entity.fields
                ],
            }
        return {
            "policy_revision": self.policy_revision,
            "decision": self.code,
            "reason": self.reason,
            "required": self.required,
            "derived": self.derived,
            "heal_applied": self.heal_applied,
            "entity_type": self.entity_type,
            "source_references": list(self.source_references)[:40],
            "collection_schema_hash": self.collection_schema_hash,
            "seed_hash": self.seed_hash,
            "before_projection_hash": self.before_projection_hash,
            "after_projection_hash": self.after_projection_hash,
            "app_spec_sha256": self.app_spec_sha256,
            "tier1_contract_hash": self.tier1_contract_hash,
            "derived_entity": entity_payload,
            "collection_id": (
                self.collection.collection_id if self.collection else None
            ),
            "minimum_seed_count": (
                len(self.collection.seed_records) if self.collection else 0
            ),
        }


def _canonical_hash(payload: Mapping[str, Any] | list[Any] | None) -> str:
    encoded = json.dumps(
        payload or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _stable_id(prefix: str, raw: str) -> str:
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for part in parts:
        out.update(_WORD.findall((part or "").casefold()))
    return out


def _gather_signal_text(
    context: CompositionContext,
    page_purpose: PagePurposeContract,
    component_plan: BusinessComponentPlan,
) -> tuple[str, list[str]]:
    """Return joined signal text and source reference paths."""

    spec = context.app_spec
    tier = context.tier_1.references
    page_ids = set(tier.page_ids)
    refs: list[str] = []
    chunks: list[str] = []

    for page in page_purpose.pages:
        chunks.extend([page.page_id, page.goal])
        refs.append(f"page_purpose.{page.page_id}")

    for page in spec.pages:
        if page.id not in page_ids:
            continue
        chunks.extend([page.id, page.name, page.purpose, page.route])
        refs.append(f"appspec.pages.{page.id}")

    for action in spec.actions:
        if action.id not in set(tier.action_ids):
            continue
        chunks.extend([action.id, action.name, action.description, action.kind])
        refs.append(f"appspec.actions.{action.id}")

    for requirement in spec.requirements:
        if requirement.id not in set(tier.requirement_ids):
            continue
        chunks.extend([requirement.id, requirement.title, requirement.description])
        refs.append(f"appspec.requirements.{requirement.id}")

    for test in spec.acceptance_tests:
        if test.id not in set(tier.acceptance_test_ids):
            continue
        chunks.extend([test.id, test.name, test.description])
        refs.append(f"appspec.acceptance_tests.{test.id}")

    for journey in spec.journeys:
        if journey.id not in set(tier.journey_ids):
            continue
        chunks.extend([journey.id, journey.name, journey.description])
        refs.append(f"appspec.journeys.{journey.id}")

    for component in component_plan.components:
        chunks.extend([component.component_id, component.name, component.purpose])
        refs.append(f"component_plan.{component.component_id}")

    return " ".join(chunks), refs


def detect_collection_entity_types(
    signal_text: str,
) -> tuple[str, ...]:
    """Return sorted unique entity types implied by Tier 1 signal text."""

    tokens = _tokens(signal_text)
    found: set[str] = set()
    for token in tokens:
        if token in _NON_COLLECTION_NOUNS:
            continue
        mapped = _COLLECTION_NOUNS.get(token)
        if mapped:
            found.add(mapped)
    return tuple(sorted(found))


def collection_is_required(
    *,
    entity_types: tuple[str, ...],
    signal_text: str,
    page_purpose: PagePurposeContract,
) -> bool:
    """True when Tier 1 contains repeatable/selectable business data."""

    if entity_types:
        return True
    tokens = _tokens(signal_text)
    page_ids = {page.page_id.casefold() for page in page_purpose.pages}
    # Booking/detail/list patterns without an explicit noun still imply services
    # when a service-detail style page is present with a booking page.
    has_service_page = any("service" in page_id for page_id in page_ids)
    has_booking_page = any("book" in page_id for page_id in page_ids)
    if has_service_page and has_booking_page:
        return True
    if {"select", "choose", "browse"} & tokens and has_service_page:
        return True
    return False


def _default_service_fields() -> tuple[DerivedEntityFieldSpec, ...]:
    return (
        DerivedEntityFieldSpec(
            id="FIELD-NAME",
            name="Name",
            type="string",
            required=True,
        ),
        DerivedEntityFieldSpec(
            id="FIELD-DESCRIPTION",
            name="Short description",
            type="string",
            required=True,
        ),
        DerivedEntityFieldSpec(
            id="FIELD-DURATION",
            name="Duration minutes",
            type="integer",
            required=True,
        ),
    )


def _fields_for_entity_type(entity_type: str) -> tuple[DerivedEntityFieldSpec, ...]:
    if entity_type == "service":
        return _default_service_fields()
    # Conservative shared seed shape for other unambiguous catalog types.
    return (
        DerivedEntityFieldSpec(
            id="FIELD-NAME",
            name="Name",
            type="string",
            required=True,
        ),
        DerivedEntityFieldSpec(
            id="FIELD-DESCRIPTION",
            name="Short description",
            type="string",
            required=True,
        ),
    )


def _seed_value_for_field(field: DerivedEntityFieldSpec, *, entity_type: str) -> object:
    if field.type == "integer":
        return 60 if "duration" in field.name.casefold() else 1
    if field.type == "number":
        return 125.0
    if field.type == "boolean":
        return True
    if "name" in field.name.casefold():
        labels = {
            "service": "Signature consultation",
            "product": "Starter product",
            "listing": "Featured listing",
            "course": "Intro course",
            "property": "Sample property",
            "provider": "Lead provider",
            "appointment": "Booked appointment",
            "menu_item": "Chef special",
            "article": "Featured article",
            "category": "Primary category",
            "inventory_item": "Stocked item",
        }
        return labels.get(entity_type, f"Sample {entity_type}")
    if "description" in field.name.casefold():
        return f"A realistic {entity_type.replace('_', ' ')} for the Tier 1 journey."
    return f"Realistic {field.name} value"


def build_derived_collection(
    *,
    entity_type: str,
    page_ids: tuple[str, ...],
    component_ids: tuple[str, ...],
    source_key: str,
) -> tuple[DataCollection, DerivedEntitySpec]:
    meta = _ENTITY_TYPE_META[entity_type]
    fields = _fields_for_entity_type(entity_type)
    entity = DerivedEntitySpec(
        id=meta["entity_id"],
        name=meta["name"],
        description=meta["description"],
        fields=fields,
    )
    collection_id = _stable_id("DATA", f"{meta['collection_prefix']}:{source_key}")
    record_id = _stable_id("RECORD", f"{meta['entity_id']}:{source_key}")
    field_ids = tuple(item.id for item in fields)
    seed = SeedRecord(
        record_id=record_id,
        values=tuple(
            SeedFieldValue(
                field_id=item.id,
                value=_seed_value_for_field(item, entity_type=entity_type),
            )
            for item in fields
        ),
    )
    collection = DataCollection(
        collection_id=collection_id,
        entity_id=entity.id,
        purpose=(
            f"Provide realistic {entity.name} records for the accepted "
            "Tier 1 workflow."
        ),
        page_ids=page_ids,
        component_ids=component_ids,
        field_ids=field_ids,
        seed_records=(seed,),
    )
    return collection, entity


def resolve_tier1_collection_decision(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    component_plan: BusinessComponentPlan,
    existing_collections: list[DataCollection] | None = None,
    before_projection_hash: str | None = None,
    heal_allowed: bool = True,
) -> CollectionProjectionDecision:
    """Decide whether Tier 1 needs a collection and optionally derive one."""

    existing = list(existing_collections or [])
    design_refs = context.refs.design_contract_refs
    app_spec_sha = design_refs.app_spec_ref.sha256
    tier_refs = tuple(design_refs.tier_refs or ())
    tier1_hash = tier_refs[0].sha256 if tier_refs else None
    signal_text, source_refs = _gather_signal_text(
        context, page_purpose, component_plan
    )
    entity_types = detect_collection_entity_types(signal_text)
    # Booking page pair without noun tokens still maps to services.
    page_ids = tuple(page.page_id for page in page_purpose.pages)
    page_id_folded = {item.casefold() for item in page_ids}
    if (
        not entity_types
        and any("service" in item for item in page_id_folded)
        and any("book" in item for item in page_id_folded)
    ):
        entity_types = ("service",)

    required = collection_is_required(
        entity_types=entity_types,
        signal_text=signal_text,
        page_purpose=page_purpose,
    )

    if existing:
        return CollectionProjectionDecision(
            code="collection_reused",
            reason="An existing Tier 1 seedable entity collection was preserved.",
            required=True,
            derived=False,
            collection=existing[0],
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            after_projection_hash=_canonical_hash(
                [item.model_dump(mode="json") for item in existing]
            ),
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
            collection_schema_hash=_canonical_hash(
                existing[0].model_dump(mode="json")
            ),
            seed_hash=_canonical_hash(
                [
                    record.model_dump(mode="json")
                    for record in existing[0].seed_records
                ]
            ),
        )

    tier_entity_ids = set(context.tier_1.references.entity_ids)

    def _match_entity_type(entity) -> str | None:
        entity_tokens = _tokens(entity.id, entity.name, entity.description)
        for token in entity_tokens:
            mapped = _COLLECTION_NOUNS.get(token)
            if mapped and (not entity_types or mapped in entity_types):
                return mapped
        return None

    # Restore: AppSpec has a fielded entity omitted from component projection
    # but still required by Tier 1 meaning — restore without mutating AppSpec.
    if required and heal_allowed and context.app_spec.entities:
        candidates = []
        fieldless_matches = []
        for entity in context.app_spec.entities:
            matched_type = _match_entity_type(entity)
            # Never restore Tier-2/3-only entities that do not match Tier 1
            # collection meaning. Allow tier-referenced entities even when the
            # noun match is weak if they are already in Tier 1 refs.
            in_tier = entity.id in tier_entity_ids
            if entity_types and matched_type is None and not in_tier:
                continue
            if not in_tier and matched_type is None and len(context.app_spec.entities) != 1:
                continue
            if not entity.fields:
                fieldless_matches.append(entity)
                continue
            candidates.append((entity, matched_type, in_tier))
        if not candidates and fieldless_matches:
            return CollectionProjectionDecision(
                code="collection_missing_required_fields",
                reason=(
                    "A Tier 1 collection is required but matching AppSpec "
                    "entities lack seedable fields."
                ),
                required=True,
                derived=False,
                source_references=source_refs
                + [f"appspec.entities.{item.id}" for item in fieldless_matches[:5]],
                before_projection_hash=before_projection_hash,
                app_spec_sha256=app_spec_sha,
                tier1_contract_hash=tier1_hash,
            )
        if len(candidates) > 1 and len({item[1] for item in candidates if item[1]}) > 1:
            return CollectionProjectionDecision(
                code="collection_ambiguous",
                reason=(
                    "Multiple AppSpec entities could restore a Tier 1 "
                    "collection; refusing to invent one."
                ),
                required=True,
                derived=False,
                source_references=source_refs,
                before_projection_hash=before_projection_hash,
                app_spec_sha256=app_spec_sha,
                tier1_contract_hash=tier1_hash,
            )
        if candidates:
            entity, matched_type, in_tier = candidates[0]
            component_ids = tuple(
                item.component_id for item in component_plan.components
            ) or ("COMP-DEFAULT",)
            field_ids = tuple(field.id for field in entity.fields)
            collection = DataCollection(
                collection_id=_stable_id("DATA", entity.id),
                entity_id=entity.id,
                purpose=(
                    f"Provide realistic {entity.name} records for the accepted "
                    "Tier 1 workflow."
                ),
                page_ids=page_ids or ("PAGE-HOME",),
                component_ids=component_ids,
                field_ids=field_ids,
                seed_records=(
                    SeedRecord(
                        record_id=_stable_id("RECORD", entity.id),
                        values=tuple(
                            SeedFieldValue(
                                field_id=field.id,
                                value=_seed_value_for_field(
                                    DerivedEntityFieldSpec(
                                        id=field.id,
                                        name=field.name,
                                        type=field.type,
                                        required=bool(field.required),
                                    ),
                                    entity_type=matched_type or "service",
                                ),
                            )
                            for field in entity.fields
                        ),
                    ),
                ),
            )
            return CollectionProjectionDecision(
                code="collection_filtered_out_of_tier",
                reason=(
                    "Restored a valid AppSpec entity into the Tier 1 content "
                    "projection after it was omitted from component/tier "
                    f"projection (in_tier_refs={in_tier})."
                ),
                required=True,
                derived=True,
                heal_applied=True,
                entity_type=matched_type,
                collection=collection,
                source_references=source_refs + [f"appspec.entities.{entity.id}"],
                before_projection_hash=before_projection_hash,
                after_projection_hash=_canonical_hash(
                    collection.model_dump(mode="json")
                ),
                app_spec_sha256=app_spec_sha,
                tier1_contract_hash=tier1_hash,
                collection_schema_hash=_canonical_hash(
                    {
                        "entity_id": entity.id,
                        "field_ids": list(field_ids),
                    }
                ),
                seed_hash=_canonical_hash(
                    [collection.seed_records[0].model_dump(mode="json")]
                ),
            )

    if not required:
        return CollectionProjectionDecision(
            code="collection_not_required",
            reason=(
                "Tier 1 journey has no unambiguous repeatable/selectable "
                "business data requiring an entity collection."
            ),
            required=False,
            derived=False,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            after_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    if len(entity_types) > 1:
        return CollectionProjectionDecision(
            code="collection_ambiguous",
            reason=(
                "Multiple candidate collection entity types were implied "
                f"({', '.join(entity_types)}); refusing to invent one."
            ),
            required=True,
            derived=False,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    if not entity_types:
        return CollectionProjectionDecision(
            code="collection_missing_required",
            reason=(
                "A Tier 1 collection is required but no unambiguous entity "
                "type could be derived from journey/page/action evidence."
            ),
            required=True,
            derived=False,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    if not heal_allowed:
        return CollectionProjectionDecision(
            code="collection_missing_required",
            reason="Collection heal already consumed; refusing a second inventing pass.",
            required=True,
            derived=False,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    entity_type = entity_types[0]
    if entity_type not in _ENTITY_TYPE_META:
        return CollectionProjectionDecision(
            code="collection_unseedable",
            reason=f"Entity type {entity_type!r} has no approved seed policy.",
            required=True,
            derived=False,
            entity_type=entity_type,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    component_ids = tuple(item.component_id for item in component_plan.components)
    if not component_ids:
        return CollectionProjectionDecision(
            code="collection_unseedable",
            reason="No business component is available to own the derived collection.",
            required=True,
            derived=False,
            entity_type=entity_type,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )
    if not page_ids:
        return CollectionProjectionDecision(
            code="collection_unseedable",
            reason="No Tier 1 pages are available for the derived collection.",
            required=True,
            derived=False,
            entity_type=entity_type,
            source_references=source_refs,
            before_projection_hash=before_projection_hash,
            app_spec_sha256=app_spec_sha,
            tier1_contract_hash=tier1_hash,
        )

    collection, derived_entity = build_derived_collection(
        entity_type=entity_type,
        page_ids=page_ids,
        component_ids=component_ids,
        source_key=f"{tier1_hash or 'tier1'}:{entity_type}",
    )
    return CollectionProjectionDecision(
        code="collection_derived",
        reason=(
            f"Deterministically derived a {entity_type} collection from "
            "unambiguous Tier 1 journey/page/action evidence."
        ),
        required=True,
        derived=True,
        heal_applied=True,
        entity_type=entity_type,
        collection=collection,
        derived_entity=derived_entity,
        source_references=source_refs,
        before_projection_hash=before_projection_hash,
        after_projection_hash=_canonical_hash(collection.model_dump(mode="json")),
        app_spec_sha256=app_spec_sha,
        tier1_contract_hash=tier1_hash,
        collection_schema_hash=_canonical_hash(
            {
                "entity_id": derived_entity.id,
                "fields": [
                    {"id": f.id, "type": f.type, "required": f.required}
                    for f in derived_entity.fields
                ],
            }
        ),
        seed_hash=_canonical_hash(
            [collection.seed_records[0].model_dump(mode="json")]
        ),
    )


__all__ = [
    "COLLECTION_PROJECTION_POLICY_REVISION",
    "CollectionProjectionDecision",
    "DerivedEntityFieldSpec",
    "DerivedEntitySpec",
    "build_derived_collection",
    "collection_is_required",
    "detect_collection_entity_types",
    "resolve_tier1_collection_decision",
]
