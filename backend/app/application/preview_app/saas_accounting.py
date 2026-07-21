"""Legacy SaaS accounting forcer — delegates to product_kind (validator / last resort)."""
from __future__ import annotations

from typing import Any

from app.application.preview_app.product_kind import (
    apply_product_kind_to_architect,
    apply_product_kind_to_plan,
    classify_product_kind,
    resolve_product_kind_contract,
)

_ACCOUNTING_HINTS = (
    "accounting",
    "bookkeep",
    "bookkeeper",
    "invoice",
    "invoicing",
    "ledger",
    "expense",
    "reconcil",
    "chart of accounts",
    "quickbooks",
    "xero",
    "freshbooks",
    "cash flow",
    "cashflow",
    "p&l",
    "balance sheet",
    "accounts receivable",
    "accounts payable",
    "saas accounting",
    "fintech / saas accounting",
)


def is_saas_accounting_brief(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    hits = sum(1 for hint in _ACCOUNTING_HINTS if hint in blob)
    if hits >= 2:
        return True
    kind = classify_product_kind(*parts)
    return kind == "saas_workspace" and any(
        h in blob for h in ("account", "invoice", "ledger", "bookkeep", "expense")
    )


def ensure_saas_accounting_experience_plan(
    plan: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    if not is_saas_accounting_brief(context, (plan or {}).get("design_direction") or ""):
        return dict(plan or {})
    contract = resolve_product_kind_contract(
        context, (plan or {}).get("design_direction") or "",
        "accounting invoices expenses reconciliation",
    )
    return apply_product_kind_to_plan(plan, contract)


def ensure_saas_accounting_architect(
    architect: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    if not is_saas_accounting_brief(
        context, (architect or {}).get("design_direction") or ""
    ):
        return dict(architect or {})
    contract = resolve_product_kind_contract(
        context,
        (architect or {}).get("design_direction") or "",
        "accounting invoices expenses reconciliation",
    )
    return apply_product_kind_to_architect(architect, contract)


__all__ = [
    "ensure_saas_accounting_architect",
    "ensure_saas_accounting_experience_plan",
    "is_saas_accounting_brief",
]
