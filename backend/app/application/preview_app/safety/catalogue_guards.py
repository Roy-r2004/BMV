"""Preview safety — Catalogue Guards."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract import (
    catalogue_route_for_file,
    enforce_catalogue_page_contract,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")


def _is_ai_hub_path(rel: str) -> bool:
    return (rel or "").replace("\\", "/").lower().endswith("aifeaturespage.tsx")


def _must_enforce_route(rel: str, route: dict) -> bool:
    if route.get("skeleton_id"):
        return True
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "").casefold()
    return (
        _is_ai_hub_path(rel)
        or path == "/ai-features"
        or page_id == "page-ai-features"
    )


def enforce_catalogue_workspace_contracts(
    workspace,
    architect: dict,
    brand_name: str,
) -> list[str]:
    """Replace only invalid assigned catalogue pages with deterministic scaffolds."""
    repaired: list[str] = []
    for rel in list_source_files(workspace):
        route = catalogue_route_for_file(rel, architect)
        if not _must_enforce_route(rel, route):
            continue
        enforce_architect = architect
        if _is_ai_hub_path(rel) and not route:
            # Orphan hub file — still heal utility stubs.
            enforce_architect = {
                **(architect or {}),
                "routes": list((architect or {}).get("routes") or [])
                + [
                    {
                        "path": "/ai-features",
                        "page_id": "PAGE-AI-FEATURES",
                        "component_file": rel,
                    }
                ],
            }
        content = read_file(workspace, rel)
        updated, replaced = enforce_catalogue_page_contract(
            rel,
            content,
            enforce_architect,
            brand_name=brand_name,
        )
        # Write whenever content changed — slot injection returns replaced=False
        # (not a full scaffold), but the healed page must still be persisted.
        if updated != content:
            write_file(workspace, rel, updated)
            repaired.append(rel)
            if replaced:
                guard_log.info("catalogue scaffold replaced %s", rel)
    return repaired
