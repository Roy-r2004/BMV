"""Bounded entity-role classification for Tier 1 primary-collection selection.

Classifies implied entity nouns into roles (catalog vs transactional vs form /
supporting / static) and applies deterministic ranking so catalog→transaction
pairs do not raise false `collection_ambiguous` failures.

Does not invent missing entities. Does not mutate the accepted AppSpec.
Does not call models.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping

from app.application.composition_contract.context import CompositionContext
from app.domain.schemas.business_component_plan import BusinessComponentPlan
from app.domain.schemas.page_purpose_contract import PagePurposeContract

ENTITY_ROLE_POLICY_REVISION = "2026-07-26.2"

EntityRole = Literal[
    "catalog_collection",
    "selectable_collection",
    "transactional_entity",
    "singleton_entity",
    "actor_identity",
    "form_payload",
    "supporting_reference_data",
    "static_content",
    "derived_result",
]

RoleResultCode = Literal[
    "primary_collection_selected",
    "transaction_entity_excluded",
    "supporting_entity_excluded",
    "genuine_primary_collection_ambiguity",
    "no_primary_collection_required",
    "primary_collection_unseedable",
]

_WORD = re.compile(r"[a-z0-9]+")

# Catalog / selectable nouns that may become a Tier 1 primary collection.
_CATALOG_NOUNS: dict[str, str] = {
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
    "event": "event",
    "events": "event",
    "job": "job",
    "jobs": "job",
    "restaurant": "restaurant",
    "restaurants": "restaurant",
    "table": "table",
    "tables": "table",
}

# Transactional nouns: normally created by an action, not browsed as seed data.
_TRANSACTION_NOUNS: dict[str, str] = {
    "appointment": "appointment",
    "appointments": "appointment",
    "booking": "booking",
    "bookings": "booking",
    "order": "order",
    "orders": "order",
    "enrollment": "enrollment",
    "enrollments": "enrollment",
    "viewing": "viewing",
    "viewings": "viewing",
    "viewingrequest": "viewing",
    "inquiry": "inquiry",
    "inquiries": "inquiry",
    "reservation": "reservation",
    "reservations": "reservation",
    "registration": "registration",
    "registrations": "registration",
    "ticket": "ticket",
    "tickets": "ticket",
    "application": "application",
    "applications": "application",
    "consultation": "consultation",
    "consultations": "consultation",
}

# Guides role classification only; never invents missing entities.
CATALOG_TRANSACTION_REGISTRY: dict[str, frozenset[str]] = {
    "service": frozenset({"appointment", "booking"}),
    "product": frozenset({"order"}),
    "course": frozenset({"enrollment"}),
    "property": frozenset({"viewing", "inquiry"}),
    "restaurant": frozenset({"reservation"}),
    "table": frozenset({"reservation"}),
    "menu_item": frozenset({"reservation"}),
    "event": frozenset({"registration", "ticket"}),
    "job": frozenset({"application"}),
    "provider": frozenset({"consultation"}),
    "listing": frozenset({"inquiry"}),
}

_TRANSACTION_TO_CATALOGS: dict[str, frozenset[str]] = {}
for _catalog, _txns in CATALOG_TRANSACTION_REGISTRY.items():
    for _txn in _txns:
        existing = set(_TRANSACTION_TO_CATALOGS.get(_txn, frozenset()))
        existing.add(_catalog)
        _TRANSACTION_TO_CATALOGS[_txn] = frozenset(existing)

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
        "slot",
        "slots",
    }
)

_BROWSE_HINTS = frozenset(
    {
        "detail",
        "list",
        "catalog",
        "browse",
        "gallery",
        "menu",
        "cards",
        "items",
        "selectable",
        "select",
        "choose",
        "view",
        "open",
    }
)
_HISTORY_HINTS = frozenset(
    {
        "history",
        "manage",
        "upcoming",
        "past",
        "reschedule",
        "my",
        "records",
        "repeated",
    }
)
_CREATE_HINTS = frozenset(
    {
        "submit",
        "create",
        "book",
        "schedule",
        "enroll",
        "apply",
        "register",
        "order",
        "reserve",
        "confirm",
    }
)
_FORM_HINTS = frozenset({"form", "details", "customer", "client", "payload"})
_SUPPORT_HINTS = frozenset(
    {"availability", "calendar", "slot", "slots", "schedule"}
)
_STATIC_HINTS = frozenset(
    {"confirmation", "message", "success", "result", "status"}
)

PRIMARY_ROLES = frozenset({"catalog_collection", "selectable_collection"})


@dataclass(frozen=True)
class EntityRoleCandidate:
    entity_type: str
    normalized_entity_type: str
    roles: tuple[EntityRole, ...]
    positive_signals: tuple[str, ...]
    negative_signals: tuple[str, ...]
    score: int
    source_references: tuple[str, ...]
    result_code: RoleResultCode
    eligible_primary: bool

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EntityRoleRanking:
    candidates: list[EntityRoleCandidate] = field(default_factory=list)
    primary_entity_types: tuple[str, ...] = ()
    excluded_transaction_entity_types: tuple[str, ...] = ()
    ambiguity_candidates_after_classification: tuple[str, ...] = ()
    result_code: RoleResultCode = "no_primary_collection_required"
    decision_hash: str = ""
    policy_revision: str = ENTITY_ROLE_POLICY_REVISION
    source_references: list[str] = field(default_factory=list)
    raw_entity_types: tuple[str, ...] = ()

    def model_dump(self) -> dict[str, Any]:
        return {
            "candidates": [item.model_dump() for item in self.candidates],
            "primary_entity_types": list(self.primary_entity_types),
            "excluded_transaction_entity_types": list(
                self.excluded_transaction_entity_types
            ),
            "ambiguity_candidates_after_classification": list(
                self.ambiguity_candidates_after_classification
            ),
            "result_code": self.result_code,
            "decision_hash": self.decision_hash,
            "policy_revision": self.policy_revision,
            "source_references": list(self.source_references)[:80],
            "raw_entity_types": list(self.raw_entity_types),
        }


def _tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for part in parts:
        out.update(_WORD.findall((part or "").casefold()))
    return out


def _canonical_hash(payload: Mapping[str, Any] | list[Any] | None) -> str:
    encoded = json.dumps(
        payload or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def detect_raw_entity_types(signal_text: str) -> tuple[str, ...]:
    """Return sorted unique catalog+transaction entity types from signal text."""

    tokens = _tokens(signal_text)
    found: set[str] = set()
    for token in tokens:
        if token in _NON_COLLECTION_NOUNS:
            continue
        mapped = _CATALOG_NOUNS.get(token) or _TRANSACTION_NOUNS.get(token)
        if mapped:
            found.add(mapped)
    return tuple(sorted(found))


def _page_mentions_entity(page_id: str, page_text: str, entity_type: str) -> bool:
    """True when the page identity is about the entity (not a later-step mention)."""

    stem = entity_type.split("_")[0]
    return stem in _tokens(page_id)


def _score_entity(
    *,
    entity_type: str,
    is_transaction_noun: bool,
    page_blobs: list[tuple[str, str, str]],
    action_blobs: list[tuple[str, str, str]],
    journey_blobs: list[tuple[str, str]],
    evidence_blobs: list[tuple[str, str]],
    present_types: set[str],
) -> tuple[
    tuple[EntityRole, ...],
    list[str],
    list[str],
    int,
    list[str],
    bool,
    RoleResultCode,
]:
    positive: list[str] = []
    negative: list[str] = []
    refs: list[str] = []
    score = 0

    has_detail = False
    has_list = False
    has_history = False
    has_select = False
    created_by_action = False
    confirmation_only = False
    browse_before_create = False

    for page_id, purpose, ref in page_blobs:
        if not _page_mentions_entity(page_id, purpose, entity_type):
            continue
        refs.append(ref)
        page_tokens = _tokens(page_id, purpose)
        if "detail" in page_tokens or "summary" in page_tokens:
            has_detail = True
            score += 40
            positive.append(f"detail_page:{page_id}")
        if {"list", "catalog", "browse", "history", "menu", "gallery"} & page_tokens:
            has_list = True
            score += 30
            positive.append(f"list_or_catalog_page:{page_id}")
        if _HISTORY_HINTS & page_tokens:
            has_history = True
            score += 35
            positive.append(f"history_or_manage_page:{page_id}")
        if "confirmation" in page_tokens and not (
            has_detail or has_list or has_history
        ):
            confirmation_only = True
            score -= 40
            negative.append(f"confirmation_or_result_only:{page_id}")

    for action_id, action_text, ref in action_blobs:
        action_tokens = _tokens(action_id, action_text)
        stem = entity_type.split("_")[0]
        mentions = stem in action_tokens
        txn_named = any(
            token in action_tokens
            for token, mapped in _TRANSACTION_NOUNS.items()
            if mapped == entity_type
        )
        create_like = bool(_CREATE_HINTS & action_tokens)
        browse_like = bool(_BROWSE_HINTS & action_tokens) and not create_like

        if mentions or (is_transaction_noun and create_like and txn_named):
            refs.append(ref)
            if browse_like:
                has_select = True
                score += 25
                positive.append(f"select_or_view_action:{action_id}")
            if create_like and (mentions or txn_named or is_transaction_noun):
                if mentions or txn_named:
                    created_by_action = True
                    score -= 50
                    negative.append(
                        f"created_by_submit_or_book_action:{action_id}"
                    )

        # Create actions that explicitly create this transaction entity.
        if is_transaction_noun and create_like and txn_named and not mentions:
            refs.append(ref)
            created_by_action = True
            score -= 50
            negative.append(f"created_by_submit_or_book_action:{action_id}")

    if journey_blobs:
        first_ref, first_text = journey_blobs[0]
        first_tokens = _tokens(first_text)
        stem = entity_type.split("_")[0]
        if stem in first_tokens and (_BROWSE_HINTS & first_tokens):
            browse_before_create = True
            score += 20
            positive.append(f"journey_begins_browsing:{first_ref}")
            refs.append(first_ref)

    for evidence_id, evidence_text in evidence_blobs:
        tokens = _tokens(evidence_id, evidence_text)
        stem = entity_type.split("_")[0]
        if stem not in tokens:
            continue
        if _SUPPORT_HINTS & tokens:
            score -= 25
            negative.append(f"supporting_schedule_data:{evidence_id}")
        if _STATIC_HINTS & tokens and not (has_detail or has_list):
            score -= 30
            negative.append(f"static_or_result_content:{evidence_id}")

    if has_detail or has_list or has_select:
        score += 15
        positive.append("seedable_descriptive_catalog_signals")

    if not (has_detail or has_list or has_select or has_history):
        score -= 30
        negative.append("no_list_detail_browsing_behavior")

    partner_catalogs = _TRANSACTION_TO_CATALOGS.get(entity_type, frozenset())
    catalog_partner_present = bool(partner_catalogs & present_types)
    force_transaction = False
    if (
        is_transaction_noun
        and catalog_partner_present
        and not (has_history or (has_list and has_detail))
    ):
        force_transaction = True
        negative.append(
            "catalog_transaction_registry:"
            + ",".join(sorted(partner_catalogs & present_types))
        )
        score -= 20

    roles: list[EntityRole]
    eligible: bool
    result_code: RoleResultCode

    if force_transaction or (
        is_transaction_noun
        and created_by_action
        and not (has_history or (has_list and has_select))
    ):
        roles = ["transactional_entity"]
        if confirmation_only:
            roles = ["transactional_entity", "derived_result"]
        eligible = False
        result_code = "transaction_entity_excluded"
    elif has_history or (has_list and (has_detail or has_select)):
        roles = ["catalog_collection", "selectable_collection"]
        eligible = True
        result_code = "primary_collection_selected"
    elif has_detail or has_select or browse_before_create:
        roles = ["selectable_collection", "catalog_collection"]
        eligible = True
        result_code = "primary_collection_selected"
    elif is_transaction_noun:
        roles = ["transactional_entity"]
        eligible = False
        result_code = "transaction_entity_excluded"
    else:
        roles = ["catalog_collection"]
        eligible = score >= 10
        result_code = (
            "primary_collection_selected"
            if eligible
            else "supporting_entity_excluded"
        )

    if not eligible and result_code == "primary_collection_selected":
        result_code = "supporting_entity_excluded"

    return (
        tuple(roles),
        positive,
        negative,
        score,
        refs,
        eligible,
        result_code,
    )


def classify_entity_candidates(
    context: CompositionContext,
    *,
    page_purpose: PagePurposeContract,
    component_plan: BusinessComponentPlan,
    signal_text: str | None = None,
    source_references: list[str] | None = None,
) -> EntityRoleRanking:
    """Classify Tier 1 entity noun candidates with deterministic scores."""

    spec = context.app_spec
    tier = context.tier_1.references
    page_ids = set(tier.page_ids)
    refs: list[str] = list(source_references or [])

    page_blobs: list[tuple[str, str, str]] = []
    for page in page_purpose.pages:
        page_blobs.append(
            (page.page_id, page.goal, f"page_purpose.{page.page_id}")
        )
        refs.append(f"page_purpose.{page.page_id}")
    for page in spec.pages:
        if page.id not in page_ids:
            continue
        blob = " ".join([page.id, page.name, page.purpose, page.route])
        page_blobs.append((page.id, blob, f"appspec.pages.{page.id}"))
        refs.append(f"appspec.pages.{page.id}")

    action_blobs: list[tuple[str, str, str]] = []
    for action in spec.actions:
        if action.id not in set(tier.action_ids):
            continue
        blob = " ".join(
            [action.id, action.name, action.description, action.kind]
        )
        action_blobs.append((action.id, blob, f"appspec.actions.{action.id}"))
        refs.append(f"appspec.actions.{action.id}")

    journey_blobs: list[tuple[str, str]] = []
    for journey in spec.journeys:
        if journey.id not in set(tier.journey_ids):
            continue
        blob = " ".join([journey.id, journey.name, journey.description])
        journey_blobs.append((f"appspec.journeys.{journey.id}", blob))
        refs.append(f"appspec.journeys.{journey.id}")

    evidence_blobs: list[tuple[str, str]] = []
    for evidence in spec.evidence:
        if evidence.id not in set(tier.evidence_ids):
            continue
        evidence_blobs.append(
            (
                evidence.id,
                " ".join([evidence.id, evidence.name, evidence.description]),
            )
        )

    chunks: list[str] = []
    if signal_text:
        chunks.append(signal_text)
    else:
        for _, text, _ in page_blobs:
            chunks.append(text)
        for _, text, _ in action_blobs:
            chunks.append(text)
        for _, text in journey_blobs:
            chunks.append(text)
        for requirement in spec.requirements:
            if requirement.id not in set(tier.requirement_ids):
                continue
            chunks.extend(
                [requirement.id, requirement.title, requirement.description]
            )
            refs.append(f"appspec.requirements.{requirement.id}")
        for test in spec.acceptance_tests:
            if test.id not in set(tier.acceptance_test_ids):
                continue
            chunks.extend([test.id, test.name, test.description])
            refs.append(f"appspec.acceptance_tests.{test.id}")
        for component in component_plan.components:
            chunks.extend(
                [component.component_id, component.name, component.purpose]
            )
            refs.append(f"component_plan.{component.component_id}")

    joined = " ".join(chunks)
    raw_types = detect_raw_entity_types(joined)
    page_id_folded = {page.page_id.casefold() for page in page_purpose.pages}
    if (
        not raw_types
        and any("service" in item for item in page_id_folded)
        and any("book" in item for item in page_id_folded)
    ):
        raw_types = ("service",)

    present = set(raw_types)
    candidates: list[EntityRoleCandidate] = []
    txn_values = set(_TRANSACTION_NOUNS.values())
    for entity_type in raw_types:
        is_txn = entity_type in txn_values
        (
            roles,
            positive,
            negative,
            score,
            entity_refs,
            eligible,
            result_code,
        ) = _score_entity(
            entity_type=entity_type,
            is_transaction_noun=is_txn,
            page_blobs=page_blobs,
            action_blobs=action_blobs,
            journey_blobs=journey_blobs,
            evidence_blobs=evidence_blobs,
            present_types=present,
        )
        candidates.append(
            EntityRoleCandidate(
                entity_type=entity_type,
                normalized_entity_type=entity_type,
                roles=roles,
                positive_signals=tuple(positive),
                negative_signals=tuple(negative),
                score=score,
                source_references=tuple(dict.fromkeys(entity_refs)),
                result_code=result_code,
                eligible_primary=eligible
                and bool(PRIMARY_ROLES.intersection(roles)),
            )
        )

    candidates.sort(
        key=lambda item: (
            0 if item.eligible_primary else 1,
            -item.score,
            item.entity_type,
        )
    )

    primary = tuple(
        item.entity_type for item in candidates if item.eligible_primary
    )
    excluded_txn = tuple(
        item.entity_type
        for item in candidates
        if "transactional_entity" in item.roles and not item.eligible_primary
    )

    if len(primary) > 1:
        outcome: RoleResultCode = "genuine_primary_collection_ambiguity"
        ambiguity = primary
        selected: tuple[str, ...] = ()
    elif len(primary) == 1:
        outcome = "primary_collection_selected"
        ambiguity = ()
        selected = primary
    else:
        outcome = "no_primary_collection_required"
        ambiguity = ()
        selected = ()

    ranking = EntityRoleRanking(
        candidates=candidates,
        primary_entity_types=selected,
        excluded_transaction_entity_types=excluded_txn,
        ambiguity_candidates_after_classification=ambiguity,
        result_code=outcome,
        policy_revision=ENTITY_ROLE_POLICY_REVISION,
        source_references=list(dict.fromkeys(refs)),
        raw_entity_types=raw_types,
    )
    ranking.decision_hash = _canonical_hash(
        {
            "candidates": [item.model_dump() for item in ranking.candidates],
            "primary_entity_types": list(ranking.primary_entity_types),
            "excluded_transaction_entity_types": list(
                ranking.excluded_transaction_entity_types
            ),
            "ambiguity_candidates_after_classification": list(
                ranking.ambiguity_candidates_after_classification
            ),
            "result_code": ranking.result_code,
            "policy_revision": ranking.policy_revision,
            "raw_entity_types": list(ranking.raw_entity_types),
        }
    )
    return ranking


def select_primary_collection_types(
    ranking: EntityRoleRanking,
) -> tuple[str, ...]:
    """Return primary catalog entity types after role classification."""

    if ranking.result_code == "genuine_primary_collection_ambiguity":
        return ranking.ambiguity_candidates_after_classification
    return ranking.primary_entity_types


__all__ = [
    "CATALOG_TRANSACTION_REGISTRY",
    "ENTITY_ROLE_POLICY_REVISION",
    "EntityRole",
    "EntityRoleCandidate",
    "EntityRoleRanking",
    "RoleResultCode",
    "classify_entity_candidates",
    "detect_raw_entity_types",
    "select_primary_collection_types",
]
