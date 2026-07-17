"""Preview safety — Catalogue Guards."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract import (
    catalogue_route_for_file,
    enforce_catalogue_page_contract,
)
from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def enforce_catalogue_workspace_contracts(
    workspace,
    architect: dict,
    brand_name: str,
) -> list[str]:
    """Replace only invalid assigned catalogue pages with deterministic scaffolds."""
    repaired: list[str] = []
    for rel in list_source_files(workspace):
        route = catalogue_route_for_file(rel, architect)
        if not route.get("skeleton_id"):
            continue
        content = read_file(workspace, rel)
        updated, replaced = enforce_catalogue_page_contract(
            rel,
            content,
            architect,
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
