"""Deterministic validation and minimal scaffolds for catalogue-owned pages."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.imports import normalize_catalogue_page_imports
from app.application.preview_app.catalogue_contract.repair import (
    enforce_catalogue_page_contract,
    repair_missing_catalogue_slots,
)
from app.application.preview_app.catalogue_contract.scaffold import (
    _safe_slot_jsx,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.slots import (
    assigned_non_shell_slots,
    catalogue_route_for_file,
    expected_shell,
    required_non_shell_slots,
)
from app.application.preview_app.catalogue_contract.tokenize import _source_tokens
from app.application.preview_app.catalogue_contract.validate import (
    blocking_contract_errors,
    validate_catalogue_page_content,
)

__all__ = [
    "assigned_non_shell_slots",
    "blocking_contract_errors",
    "catalogue_route_for_file",
    "enforce_catalogue_page_contract",
    "expected_shell",
    "minimal_catalogue_page_scaffold",
    "normalize_catalogue_page_imports",
    "repair_missing_catalogue_slots",
    "required_non_shell_slots",
    "validate_catalogue_page_content",
    "_safe_slot_jsx",
    "_source_tokens",
]
