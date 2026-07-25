"""Deterministic Tier 1 page skeletons with protected business-component mounts."""
from __future__ import annotations

import re

from app.application.candidate_generation.deterministic import page_export_symbol
from app.domain.schemas.business_component_usage import (
    RequiredBusinessComponentBinding,
)
from app.domain.schemas.page_purpose_contract import PagePurpose


BMV_REQUIRED_BC_START = "{/* BMV_REQUIRED_BC_START */}"
BMV_REQUIRED_BC_END = "{/* BMV_REQUIRED_BC_END */}"

_PROTECTED_RE = re.compile(
    re.escape(BMV_REQUIRED_BC_START)
    + r"[\s\S]*?"
    + re.escape(BMV_REQUIRED_BC_END),
    re.MULTILINE,
)


def _relative_import_path(module_path: str) -> str:
    # Pages live under src/pages/; components under src/components/business/.
    stem = module_path.removeprefix("src/").removesuffix(".tsx")
    return "../" + stem


def _import_lines(
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in bindings:
        if item.component_symbol in seen:
            continue
        seen.add(item.component_symbol)
        rel = _relative_import_path(item.component_module_path)
        lines.append(f'import {{ {item.component_symbol} }} from "{rel}";')
    return lines


def _mount_block(
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> str:
    mounts = "\n".join(
        f"      <{item.component_symbol} />" for item in bindings
    )
    return (
        f"      {BMV_REQUIRED_BC_START}\n"
        f"{mounts}\n"
        f"      {BMV_REQUIRED_BC_END}"
    )


def build_page_skeleton_source(
    *,
    page: PagePurpose,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> str:
    symbol = page_export_symbol(page.page_id)
    imports = _import_lines(bindings)
    tests = "\n".join(
        f'      <span data-bmv-acceptance-test-id="{test_id}" hidden />'
        for test_id in page.acceptance_test_ids
    )
    return (
        "\n".join(imports)
        + ("\n\n" if imports else "")
        + f"export function {symbol}() {{\n"
        + "  return (\n"
        + f'    <main data-bmv-page-id="{page.page_id}"\n'
        + f'      data-bmv-mobile-navigation="{page.mobile.navigation}"\n'
        + f'      data-bmv-mobile-primary-action="{page.mobile.primary_action}"\n'
        + f'      data-bmv-mobile-data-presentation="{page.mobile.data_presentation}"\n'
        + f'      data-bmv-mobile-density="{page.mobile.density_adjustment}"\n'
        + "    >\n"
        + (f"{tests}\n" if tests else "")
        + f"{_mount_block(bindings)}\n"
        + "    </main>\n"
        + "  );\n"
        + "}\n"
    )


def extract_protected_region(source: str) -> str | None:
    match = _PROTECTED_RE.search(source)
    if not match:
        return None
    return match.group(0)


def _binding_already_satisfied(
    source: str,
    binding: RequiredBusinessComponentBinding,
) -> bool:
    has_import = (
        f"{{ {binding.component_symbol} }}" in source
        or f"{{{binding.component_symbol}}}" in source
    )
    has_mount = f"<{binding.component_symbol}" in source
    return has_import and has_mount


def ensure_protected_business_component_region(
    *,
    source: str,
    bindings: tuple[RequiredBusinessComponentBinding, ...],
) -> str:
    """Merge model output with the deterministic required mount region."""

    if not bindings:
        return source
    if all(_binding_already_satisfied(source, item) for item in bindings):
        return source

    required_region = _mount_block(bindings).strip()
    existing = extract_protected_region(source)
    if existing is not None:
        if all(
            f"<{item.component_symbol}" in existing for item in bindings
        ):
            return source
        return _PROTECTED_RE.sub(required_region, source, count=1)

    # Insert required imports if missing, then inject protected region.
    updated = source
    for line in _import_lines(bindings):
        symbol = line.split("{", 1)[1].split("}", 1)[0].strip()
        if f"{{{symbol}}}" not in updated and f"{{ {symbol} }}" not in updated:
            # Prefer placing imports at the top of the file.
            updated = line + "\n" + updated

    injection = f"\n{required_region}\n"
    main_close = re.search(r"</main>", updated)
    if main_close:
        idx = main_close.start()
        return updated[:idx] + injection + updated[idx:]
    return_match = re.search(r"return\s*\(", updated)
    if return_match:
        # Fallback: append region before final closing of return.
        close = updated.rfind(");")
        if close != -1:
            return updated[:close] + injection + updated[close:]
    return updated + "\n" + required_region + "\n"


__all__ = [
    "BMV_REQUIRED_BC_END",
    "BMV_REQUIRED_BC_START",
    "build_page_skeleton_source",
    "ensure_protected_business_component_region",
    "extract_protected_region",
]
