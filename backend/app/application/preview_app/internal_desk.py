"""Legacy trading-desk forcer — delegates to product_kind (validator / last resort)."""
from __future__ import annotations

from typing import Any

from app.application.preview_app.product_kind import (
    apply_product_kind_to_architect,
    apply_product_kind_to_plan,
    classify_product_kind,
    resolve_product_kind_contract,
)

_DESK_HINTS = (
    "hedge",
    "trading",
    "trader",
    "blotter",
    "oms",
    "execution",
    "portfolio manager",
    "risk officer",
    "fund book",
    "institutional",
    "internal desk",
    "internal trading",
    "not a saas",
    "not a retail",
    "not a client",
    "client portal",
)


def is_internal_desk_brief(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    hits = sum(1 for hint in _DESK_HINTS if hint in blob)
    return hits >= 2 or classify_product_kind(*parts) == "internal_ops"


def ensure_internal_desk_experience_plan(
    plan: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    """Validator: re-apply product_kind chrome when brief is an internal desk."""
    if not is_internal_desk_brief(context, (plan or {}).get("design_direction") or ""):
        return dict(plan or {})
    contract = resolve_product_kind_contract(
        context, (plan or {}).get("design_direction") or ""
    )
    if contract.kind != "internal_ops":
        contract = resolve_product_kind_contract(
            f"{context} trading blotter oms internal desk"
        )
    return apply_product_kind_to_plan(plan, contract)


def ensure_internal_desk_architect(
    architect: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    if not is_internal_desk_brief(
        context, (architect or {}).get("design_direction") or ""
    ):
        return dict(architect or {})
    contract = resolve_product_kind_contract(
        context, (architect or {}).get("design_direction") or ""
    )
    if contract.kind != "internal_ops":
        contract = resolve_product_kind_contract(
            f"{context} trading blotter oms internal desk"
        )
    return apply_product_kind_to_architect(architect, contract)


__all__ = [
    "ensure_internal_desk_architect",
    "ensure_internal_desk_experience_plan",
    "is_internal_desk_brief",
]
