"""Deterministic projection from request analysis into ProductStrategy."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.application.appspec.source import source_sha256
from app.application.services.ai_features import (
    extract_ai_features_from_blueprint,
    parse_ai_features,
)
from app.domain.models.request import Request
from app.domain.schemas.customer_source import CustomerSourceSnapshotV2
from app.domain.schemas.product_strategy import ProductStrategy


def _text(value: Any, fallback: str = "") -> str:
    rendered = re.sub(r"\s+", " ", str(value or "")).strip()
    return rendered or fallback


def _slug(value: str, *, prefix: str) -> str:
    # Truncate then re-strip: [:48] alone can leave a trailing hyphen and
    # fail ProductStrategy Identifier validation.
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    slug = slug[:48].strip("-")
    if not slug or not slug[0].isalpha():
        slug = f"{prefix}-{slug or 'item'}".strip("-")[:48].strip("-")
    return slug


def _json_items(raw: Any) -> list[Any]:
    if not raw:
        return []
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, Mapping):
        value = raw.get("features") or raw.get("items") or []
        return list(value) if isinstance(value, list) else []
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return [
            line.strip(" -*\t")
            for line in str(raw).splitlines()
            if line.strip(" -*\t")
        ]
    return _json_items(parsed)


def _feature_values(items: Iterable[Any]) -> list[tuple[str, str, str]]:
    values: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, Mapping):
            name = _text(item.get("name") or item.get("title"))
            description = _text(
                item.get("description") or item.get("summary"),
                name,
            )
            surface = _text(
                item.get("surface") or item.get("category"),
                "public",
            )
        else:
            name = _text(item)
            description = name
            surface = "public"
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        values.append((name[:240], description[:4000], surface))
    return values


def _surface_kind(value: str) -> str:
    folded = value.casefold()
    if any(
        marker in folded
        for marker in (
            "ops",
            "admin",
            "staff",
            "internal",
            "automation",
            "analytics",
            "scoring",
            "digest",
        )
    ):
        return "ops"
    return "public"


def _product_kind(req: Request, source: CustomerSourceSnapshotV2) -> str:
    customer = source.customer_input
    blob = " ".join(
        (
            _text(customer.industry),
            _text(customer.business_description),
            _text(customer.main_problem),
            _text(customer.desired_outcome),
            _text(getattr(req, "preview_summary", None)),
            _text(getattr(req, "mvp_blueprint", None))[:2500],
        )
    ).casefold()
    has_public = any(
        marker in blob
        for marker in (
            "customer",
            "client",
            "visitor",
            "public",
            "website",
            "shop",
            "store",
            "book",
            "reservation",
        )
    )
    has_ops = any(
        marker in blob
        for marker in (
            "admin",
            "staff",
            "operator",
            "operations",
            "workflow",
            "back office",
            "dashboard",
            "manage",
        )
    )
    if has_public and has_ops:
        return "hybrid"
    if any(marker in blob for marker in ("booking", "appointment", "reservation")):
        return "booking_service"
    if any(marker in blob for marker in ("storefront", "ecommerce", "e-commerce", "shop")):
        return "storefront"
    if any(
        marker in blob
        for marker in ("saas", "trading", "analytics", "data platform", "workspace")
    ):
        return "saas_workspace"
    if customer.project_type == "automate" or has_ops:
        return "internal_ops"
    return "public_website"


def _evidence_ref(
    source: CustomerSourceSnapshotV2,
    *preferred_fields: str,
) -> str:
    customer = source.customer_input
    for field in preferred_fields:
        if getattr(customer, field, None):
            return f"customer_input.{field}"
    return "customer_input.business_description"


def project_product_strategy(
    req: Request,
    source: CustomerSourceSnapshotV2,
) -> ProductStrategy:
    """Project already-inferred request fields without altering customer input."""

    source_payload = source.model_dump(mode="json")
    source_digest = source_sha256(source_payload)
    customer = source.customer_input
    product_kind = _product_kind(req, source)
    primary_outcome = _text(
        customer.desired_outcome,
        _text(
            getattr(req, "preview_summary", None),
            _text(customer.main_problem, customer.business_description),
        ),
    )
    positioning = _text(
        getattr(req, "preview_summary", None),
        _text(customer.business_description),
    )
    product_name = _text(
        getattr(req, "concept_name", None),
        customer.business_name,
    )[:240]

    audience_ref = _evidence_ref(source, "target_customers")
    audiences = [
        {
            "id": "audience-primary",
            "description": _text(
                customer.target_customers,
                f"People served by {customer.business_name}.",
            ),
            "confidence": "high" if customer.target_customers else "medium",
            "evidence_refs": [audience_ref],
        }
    ]

    outcome_ref = _evidence_ref(
        source,
        "desired_outcome",
        "main_problem",
        "business_description",
    )
    public_required = product_kind in {
        "public_website",
        "storefront",
        "booking_service",
        "hybrid",
    }
    ops_required = product_kind in {
        "internal_ops",
        "saas_workspace",
        "hybrid",
    }
    surfaces: list[dict[str, Any]] = []
    if public_required:
        surfaces.append(
            {
                "id": "surface-public",
                "kind": "public",
                "required": True,
                "purpose": f"Let the primary audience achieve: {primary_outcome}",
                "evidence_refs": [outcome_ref],
            }
        )
    if ops_required:
        surfaces.append(
            {
                "id": "surface-ops",
                "kind": "ops",
                "required": True,
                "purpose": (
                    "Support the operational workflow implied by the customer "
                    f"problem: {_text(customer.main_problem, primary_outcome)}"
                ),
                "evidence_refs": [
                    _evidence_ref(
                        source,
                        "main_problem",
                        "desired_outcome",
                        "business_description",
                    )
                ],
            }
        )
    if not surfaces:
        surfaces.append(
            {
                "id": "surface-public",
                "kind": "public",
                "required": True,
                "purpose": primary_outcome,
                "evidence_refs": [outcome_ref],
            }
        )

    preview_features = _feature_values(
        _json_items(getattr(req, "preview_features", None))
    )
    ai_items = parse_ai_features(getattr(req, "ai_features", None))
    if not ai_items:
        ai_items = extract_ai_features_from_blueprint(
            getattr(req, "mvp_blueprint", None) or ""
        )
    ai_features = _feature_values(ai_items)

    capabilities: list[dict[str, Any]] = []
    seen_capabilities: set[str] = set()
    for index, (name, description, raw_surface) in enumerate(
        [*preview_features, *ai_features]
    ):
        key = name.casefold()
        if key in seen_capabilities:
            continue
        seen_capabilities.add(key)
        capabilities.append(
            {
                "id": _slug(name, prefix="cap"),
                "name": name,
                "outcome": description,
                "surface": _surface_kind(raw_surface),
                "priority": "must" if index < 3 else "should",
                "confidence": "high" if preview_features else "medium",
                "evidence_refs": [outcome_ref],
            }
        )
    if not capabilities:
        capabilities.append(
            {
                "id": "cap-primary-outcome",
                "name": "Primary customer outcome",
                "outcome": primary_outcome,
                "surface": "ops" if product_kind == "internal_ops" else "public",
                "priority": "must",
                "confidence": "medium",
                "evidence_refs": [outcome_ref],
            }
        )

    ai_feature_hypotheses = [
        {
            "id": _slug(name, prefix="ai"),
            "name": name,
            "description": description,
            "surface": _surface_kind(raw_surface),
            "confidence": "medium",
            "evidence_refs": [outcome_ref],
        }
        for name, description, raw_surface in ai_features
    ]

    return ProductStrategy.model_validate(
        {
            "schema_version": "1.0",
            "source_sha256": source_digest,
            "origin": "legacy_blueprint_projection",
            "product_name": product_name,
            "product_kind": product_kind,
            "positioning": positioning,
            "primary_outcome": primary_outcome,
            "audience_hypotheses": audiences,
            "surfaces": surfaces,
            "capability_hypotheses": capabilities[:100],
            "ai_feature_hypotheses": ai_feature_hypotheses[:50],
            "assumptions": [
                {
                    "id": "assumption-product-kind",
                    "statement": (
                        f"The inferred product kind is {product_kind.replace('_', ' ')}."
                    ),
                    "rationale": (
                        "This is a deterministic interpretation of the customer "
                        "brief and existing blueprint, not customer-authored fact."
                    ),
                    "confidence": "medium",
                }
            ],
            "risks": [],
        }
    )


__all__ = ["project_product_strategy"]
