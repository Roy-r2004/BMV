"""Force SaaS accounting briefs onto a real product workspace, not a marketing site."""
from __future__ import annotations

import copy
import re
from typing import Any

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

_PRODUCT_PAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "books-dashboard",
        "title": "Books overview",
        "page_type": "accounting-dashboard",
        "path": "/",
        "component_file": "src/pages/BooksDashboardPage.tsx",
        "purpose": "Daily accounting home — cash, AR, expenses MTD, unmatched bank lines.",
        "sample_data_notes": (
            "Cash 48,220; 26 open invoices (4 overdue); 12 unmatched bank; expenses MTD 12,840."
        ),
    },
    {
        "id": "invoices",
        "title": "Invoices",
        "page_type": "invoices",
        "path": "/invoices",
        "component_file": "src/pages/InvoicesPage.tsx",
        "purpose": "AR invoice list — draft/sent/overdue/paid with customer and amounts.",
        "sample_data_notes": (
            "INV-1042 Northwind 2480 Sent; INV-1041 Bright Labs 890 Overdue; 8+ rows."
        ),
    },
    {
        "id": "expenses",
        "title": "Expenses",
        "page_type": "expenses",
        "path": "/expenses",
        "component_file": "src/pages/ExpensesPage.tsx",
        "purpose": "Expense queue with categories, merchants, and uncategorized items.",
        "sample_data_notes": "Adobe 54.99 Software; Uber 38.20 Travel; AWS 210 Categorized.",
    },
    {
        "id": "reconciliation",
        "title": "Bank reconciliation",
        "page_type": "bank-reconciliation",
        "path": "/reconciliation",
        "component_file": "src/pages/BankReconciliationPage.tsx",
        "purpose": "Match bank feed lines to invoices and expenses.",
        "sample_data_notes": "Chase *4491 — 12 unmatched; deposit 2480 ↔ INV-1042.",
    },
    {
        "id": "reports",
        "title": "Reports",
        "page_type": "reports",
        "path": "/reports",
        "component_file": "src/pages/ReportsPage.tsx",
        "purpose": "P&L, balance sheet, and cash flow summary for the period.",
        "sample_data_notes": "MTD revenue 62k; expenses 12.8k; net 18.4k; cash trend chart.",
    },
    {
        "id": "customers",
        "title": "Customers",
        "page_type": "customers",
        "path": "/customers",
        "component_file": "src/pages/CustomersPage.tsx",
        "purpose": "Customer list with open balance and last invoice.",
        "sample_data_notes": "Northwind open 2480; Bright Labs overdue 890; Harbor Dental draft.",
    },
)


def is_saas_accounting_brief(*parts: str) -> bool:
    blob = " ".join(str(p or "") for p in parts).lower()
    hits = sum(1 for hint in _ACCOUNTING_HINTS if hint in blob)
    return hits >= 2


def _ops_dashboard_slots() -> list[str]:
    return ["header", "kpis", "filters", "table", "chart", "activity", "risk"]


def _ops_list_slots() -> list[str]:
    return ["header", "filters", "table"]


def _is_ai_hub_route(route: dict[str, Any]) -> bool:
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(
        route.get("page_id") or route.get("app_spec_page_id") or route.get("id") or ""
    ).casefold()
    component = str(route.get("component_file") or "").replace("\\", "/").lower()
    page_type = str(route.get("page_type") or "").casefold()
    return (
        path == "/ai-features"
        or page_id == "page-ai-features"
        or component.endswith("aifeaturespage.tsx")
        or page_type == "ai_hub"
    )


def _page_blueprint(spec: dict[str, Any]) -> dict[str, Any]:
    is_home = spec["path"] == "/"
    return {
        "id": spec["id"],
        "title": spec["title"],
        "page_type": spec["page_type"],
        "surface": "ops",
        "skeleton_id": "ops-dashboard" if is_home else "ops-list",
        "section_slots": _ops_dashboard_slots() if is_home else _ops_list_slots(),
        "purpose": spec["purpose"],
        "sections": [
            {
                "name": "Workspace",
                "description": spec["purpose"],
                "priority": "required",
            }
        ],
        "features_to_showcase": [spec["title"]],
        "layout_notes": "OpsShell product chrome — never a public marketing hero.",
        "sample_data_notes": spec["sample_data_notes"],
    }


def _ensure_role_pages(role: dict[str, Any]) -> bool:
    pages = [p for p in (role.get("pages") or []) if isinstance(p, dict)]
    by_id = {str(p.get("id") or ""): p for p in pages}
    by_title = {str(p.get("title") or "").casefold(): p for p in pages}
    touched = False

    for spec in _PRODUCT_PAGES:
        existing = by_id.get(spec["id"]) or by_title.get(str(spec["title"]).casefold())
        if existing is None:
            pages.append(_page_blueprint(spec))
            touched = True
            continue
        skeleton = str(existing.get("skeleton_id") or "")
        surface = str(existing.get("surface") or "")
        if surface == "public" or skeleton.startswith("public"):
            existing.update(_page_blueprint(spec))
            touched = True
        else:
            existing.setdefault("surface", "ops")
            if not existing.get("skeleton_id"):
                existing["skeleton_id"] = (
                    "ops-dashboard" if spec["path"] == "/" else "ops-list"
                )
                touched = True

    home = next(
        (
            p
            for p in pages
            if isinstance(p, dict)
            and (
                p.get("id") == "books-dashboard"
                or p.get("skeleton_id") == "ops-dashboard"
            )
        ),
        None,
    )
    if home is not None and pages and pages[0] is not home:
        pages = [home] + [p for p in pages if p is not home]
        touched = True

    role["pages"] = pages
    nav = dict(role.get("navigation") or {})
    links = [
        link
        for link in (nav.get("links") or [])
        if isinstance(link, dict)
        and not any(
            bad in str(link.get("label") or "").lower()
            for bad in (
                "get started",
                "explore forecasts",
                "access dashboard",
                "sign up",
                "book now",
            )
        )
    ]
    for page in pages:
        pid = page.get("id")
        if not pid or any(link.get("page_id") == pid for link in links):
            continue
        links.append(
            {
                "label": str(page.get("title") or pid),
                "page_id": pid,
                "style": "cta" if pid == "books-dashboard" else "link",
            }
        )
        touched = True
    if links:
        nav["links"] = links
        role["navigation"] = nav
    return touched


def ensure_saas_accounting_experience_plan(
    plan: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(plan or {}))
    if not is_saas_accounting_brief(context, updated.get("design_direction") or ""):
        return updated

    roles = list(updated.get("roles") or [])
    if not roles:
        return updated

    touched = False
    for role in roles:
        if not isinstance(role, dict):
            continue
        pages = list(role.get("pages") or [])
        if not pages:
            role["pages"] = [_page_blueprint(spec) for spec in _PRODUCT_PAGES]
            touched = True
        else:
            for page in pages:
                if not isinstance(page, dict):
                    continue
                skeleton = str(page.get("skeleton_id") or "")
                surface = str(page.get("surface") or "")
                title = str(page.get("title") or "")
                is_marketing = (
                    skeleton in {"public-home", "public-service"}
                    or surface == "public"
                    and bool(
                        re.search(
                            r"home|landing|marketing|foresight|forecast",
                            f"{title} {skeleton}",
                            re.I,
                        )
                    )
                )
                if is_marketing or skeleton.startswith("public"):
                    page.update(_page_blueprint(_PRODUCT_PAGES[0]))
                    touched = True
        if _ensure_role_pages(role):
            touched = True

    if touched:
        direction = str(updated.get("design_direction") or "").strip()
        updated["design_direction"] = (
            f"{direction} | SaaS accounting PRODUCT workspace — invoices, expenses, "
            "bank recon, reports; never a marketing foresight landing."
        ).strip(" |")
        updated["ops_direction"] = (
            "Dense QuickBooks/Xero-style product: books overview, invoices, expenses, "
            "bank reconciliation, reports, customers."
        )
        updated["public_direction"] = (
            "No consumer marketing site — the product is the accounting workspace."
        )
        updated["recipe_id"] = "dense-ops"
        updated["industry_template_id"] = "saas-accounting"
        updated["ops_template_id"] = "saas-accounting"
    updated["roles"] = roles
    return updated


def _inject_routes(architect: dict[str, Any]) -> None:
    routes = [rt for rt in (architect.get("routes") or []) if isinstance(rt, dict)]
    role_id = "ROLE-PRIMARY-USER"
    for role in architect.get("roles") or []:
        if isinstance(role, dict) and role.get("id"):
            role_id = str(role["id"])
            break
    for rt in routes:
        if rt.get("role_id"):
            role_id = str(rt["role_id"])
            break

    existing_paths = {str(rt.get("path") or "") for rt in routes}
    files = [f for f in (architect.get("files_to_generate") or []) if isinstance(f, dict)]
    existing_files = {str(f.get("path") or "").replace("\\", "/") for f in files}

    for spec in _PRODUCT_PAGES:
        path = str(spec["path"])
        component = str(spec["component_file"])
        if path in existing_paths:
            for rt in routes:
                if str(rt.get("path") or "") != path or _is_ai_hub_route(rt):
                    continue
                rt["surface"] = "ops"
                rt["layout"] = "admin"
                rt["skeleton_id"] = "ops-dashboard" if path == "/" else "ops-list"
                rt["section_slots"] = (
                    _ops_dashboard_slots() if path == "/" else _ops_list_slots()
                )
                rt["title"] = spec["title"]
                rt["page_type"] = spec["page_type"]
                rt.setdefault("component_file", component)
                rt.setdefault("role_id", role_id)
            continue

        routes.append(
            {
                "path": path,
                "page_id": spec["id"],
                "role_id": role_id,
                "title": spec["title"],
                "component_file": component,
                "layout": "admin",
                "surface": "ops",
                "skeleton_id": "ops-dashboard" if path == "/" else "ops-list",
                "section_slots": (
                    _ops_dashboard_slots() if path == "/" else _ops_list_slots()
                ),
                "page_type": spec["page_type"],
                "purpose": spec["purpose"],
            }
        )
        if component not in existing_files:
            files.append(
                {
                    "type": "page",
                    "kind": "page",
                    "path": component,
                    "instructions": (
                        "SAAS ACCOUNTING PRODUCT page using OpsShell. "
                        f"{spec['purpose']} Dense invoice/expense/cash copy with realistic "
                        f"amounts — never a marketing hero or 'Explore Forecasts' CTA. "
                        f"Sample: {spec['sample_data_notes']}"
                    ),
                }
            )
            existing_files.add(component)

    architect["routes"] = routes
    architect["files_to_generate"] = files


def ensure_saas_accounting_architect(
    architect: dict[str, Any] | None,
    *,
    context: str = "",
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(architect or {}))
    if not is_saas_accounting_brief(context, updated.get("design_direction") or ""):
        return updated

    for route in updated.get("routes") or []:
        if not isinstance(route, dict) or _is_ai_hub_route(route):
            continue
        route["surface"] = "ops"
        route["layout"] = "admin"
        if not route.get("skeleton_id") or str(route.get("skeleton_id")).startswith(
            "public"
        ):
            route["skeleton_id"] = "ops-dashboard"
            route["section_slots"] = _ops_dashboard_slots()
        title = str(route.get("title") or "")
        if re.search(r"foresight|forecast|landing|marketing|get started", title, re.I):
            route["title"] = "Books overview"

    _inject_routes(updated)

    for item in updated.get("files_to_generate") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").replace("\\", "/").lower()
        if "aifeaturespage" in path:
            continue
        kind = str(item.get("kind") or item.get("type") or "").lower()
        if kind not in {"page", ""} and "page" not in path:
            continue
        instructions = str(item.get("instructions") or "")
        prefix = (
            "SAAS ACCOUNTING PRODUCT page using OpsShell (header, kpis, filters, table, "
            "chart, activity, risk). Invoices/expenses/bank/cash copy only — never a "
            "marketing foresight landing or Get Started hero. "
        )
        if "SAAS ACCOUNTING PRODUCT" not in instructions:
            item["instructions"] = (prefix + instructions).strip()

    direction = str(updated.get("design_direction") or "").strip()
    updated["design_direction"] = (
        f"{direction} | OpsShell accounting product — Books, Invoices, Expenses, "
        "Reconciliation, Reports, Customers."
    ).strip(" |")
    updated["recipe_id"] = "dense-ops"
    return updated


__all__ = [
    "ensure_saas_accounting_architect",
    "ensure_saas_accounting_experience_plan",
    "is_saas_accounting_brief",
]
