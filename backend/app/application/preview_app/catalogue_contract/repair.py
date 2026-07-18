"""Catalogue page import normalization and slot repair."""
from __future__ import annotations

import logging
import re

from app.application.preview_app.catalogue_contract.imports import normalize_catalogue_page_imports
from app.application.preview_app.catalogue_contract.scaffold import (
    _SLOT_COMPONENT,
    _safe_slot_jsx,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.slots import (
    assigned_non_shell_slots,
    catalogue_route_for_file,
)
from app.application.preview_app.catalogue_contract.validate import (
    blocking_contract_errors,
    validate_catalogue_page_content,
)

logger = logging.getLogger(__name__)

_SLOTS_DECL_RE = re.compile(r"const\s+slots\s*(?::\s*[\w$<>,.\s\[\]]+?)?=\s*\{")


_UI_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]@/ui['\"]\s*;?")


_IMAGES_IMPORT_RE = re.compile(
    r"import\s*\{[^}]*\bimages\b[^}]*\}\s*from\s*['\"]@/data/mock['\"]"
)


_COMPOSER_INVOCATION_RE = re.compile(
    r"<SkeletonComposer\b[^>]*?/?>",
    re.DOTALL,
)
_SKELETON_CONST_RE = re.compile(
    r"const\s+SKELETON_ID\s*=\s*(?:'[^']+'|\"[^\"]+\")\s*as\s+const\s*;?"
)
_COMPOSER_FIXABLE = frozenset({"SkeletonComposer invocation", "assigned skeleton literal"})


def _composer_errors_only(errors: list[str]) -> bool:
    if not errors:
        return False
    for error in errors:
        if error in _COMPOSER_FIXABLE:
            continue
        if error == "undefined JSX component:SkeletonComposer":
            continue
        return False
    return True


def repair_skeleton_composer_invocation(
    content: str,
    route: dict,
) -> tuple[str, bool]:
    """Patch SKELETON_ID / SkeletonComposer without replacing business slot JSX.

    Handles the common thrash where the model keeps a valid `slots` object but
    drops or mangled the composer invocation — avoid full scaffold fallback.
    """
    errors = blocking_contract_errors(validate_catalogue_page_content(content, route))
    if not _composer_errors_only(errors):
        return content, False
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id or not _SLOTS_DECL_RE.search(content):
        return content, False

    repaired = content
    skeleton_const = f'const SKELETON_ID = "{skeleton_id}" as const;'
    if not _SKELETON_CONST_RE.search(repaired):
        ui_import = _UI_IMPORT_RE.search(repaired)
        insert_at = ui_import.end() if ui_import else 0
        repaired = repaired[:insert_at] + f"\n\n{skeleton_const}\n" + repaired[insert_at:]
    else:
        repaired = _SKELETON_CONST_RE.sub(skeleton_const, repaired, count=1)

    ui_import = _UI_IMPORT_RE.search(repaired)
    if ui_import:
        names = {
            token.strip().split(" as ")[0].replace("type ", "").strip()
            for token in ui_import.group(1).split(",")
            if token.strip()
        }
        needed = ["getSkeleton", "SkeletonComposer"]
        if skeleton_id == "ops-dashboard":
            needed = ["getSkeleton", "composeSkeletonLayout"]
        missing = [name for name in needed if name not in names]
        if missing:
            current = ui_import.group(1).strip().rstrip(",").strip()
            merged = ", ".join(filter(None, [current, ", ".join(missing)]))
            repaired = repaired.replace(
                ui_import.group(0),
                f"import {{ {merged} }} from '@/ui';",
                1,
            )

    composer_jsx = None
    if skeleton_id != "ops-dashboard":
        # Preserve recipe order when the page already declares RECIPE_ORDER.
        if "RECIPE_ORDER" in repaired:
            composer_jsx = (
                "<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} order={RECIPE_ORDER} />"
            )
        else:
            composer_jsx = "<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />"
    if composer_jsx:
        if _COMPOSER_INVOCATION_RE.search(repaired):
            repaired = _COMPOSER_INVOCATION_RE.sub(composer_jsx, repaired, count=1)
        elif "return (" in repaired:
            repaired = repaired.replace(
                "return (",
                f"return (\n      {composer_jsx}\n",
                1,
            )

    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):
        return content, False
    logger.info(
        "Catalogue page healed by SkeletonComposer repair route=%s",
        route.get("path"),
    )
    return repaired, True


def repair_missing_catalogue_slots(
    content: str,
    route: dict,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    """Inject deterministic JSX for missing required slots into an AI page.

    Applies only when missing slots are the page's sole contract violations —
    a page that reasonably skipped optional-ish marketing sections keeps its
    business-specific content instead of being replaced by a generic scaffold.
    Structural, import, or prop errors still require regeneration.
    """
    errors = blocking_contract_errors(validate_catalogue_page_content(content, route))
    if not errors:
        return content, False
    missing = {error.split(":", 1)[1] for error in errors if error.startswith("slot:")}
    if not missing or any(not error.startswith("slot:") for error in errors):
        return content, False

    declaration = _SLOTS_DECL_RE.search(content)
    ui_import = _UI_IMPORT_RE.search(content)
    if not declaration or not ui_import:
        return content, False

    brand = brand_name or "Brand"
    title = str(route.get("title") or "Overview")
    ordered_missing = [
        slot for slot in assigned_non_shell_slots(route) if slot in missing
    ]
    if set(ordered_missing) != missing:
        return content, False
    try:
        injected = "".join(
            f"\n    {slot}: (\n      {_safe_slot_jsx(slot, brand, title)}\n    ),"
            for slot in ordered_missing
        )
    except ValueError:
        return content, False
    # A slot declared with an empty value (`cta: null,`) would shadow the
    # injected default (later key wins) — drop the dead declaration first.
    for slot in ordered_missing:
        content = re.sub(
            rf"\n\s*{re.escape(slot)}\s*:\s*(?:null|undefined|false|\{{\s*\}})\s*,?",
            "",
            content,
            count=1,
        )
    declaration = _SLOTS_DECL_RE.search(content)
    if not declaration:
        return content, False
    repaired = content[: declaration.end()] + injected + content[declaration.end():]

    existing_named = {
        token.strip().split(" as ")[0].replace("type ", "").strip()
        for token in ui_import.group(1).split(",")
        if token.strip()
    }
    needed = list(
        dict.fromkeys(
            component
            for slot in ordered_missing
            if (component := _SLOT_COMPONENT.get(slot))
            and component not in existing_named
        )
    )
    if needed:
        current = ui_import.group(1).strip().rstrip(",").strip()
        merged = ", ".join(filter(None, [current, ", ".join(needed)]))
        repaired = repaired.replace(
            ui_import.group(0),
            f"import {{ {merged} }} from '@/ui';",
            1,
        )

    needs_images = any(
        "images." in _safe_slot_jsx(slot, brand, title) for slot in ordered_missing
    )
    if needs_images and not _IMAGES_IMPORT_RE.search(repaired):
        repaired = "import { images } from '@/data/mock';\n" + repaired

    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):
        return content, False
    logging.getLogger(__name__).info(
        "Catalogue page healed by slot injection route=%s slots=%s",
        route.get("path"),
        ordered_missing,
    )
    return repaired, True


def enforce_catalogue_page_contract(
    file_path: str,
    content: str,
    architect: dict | None,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    route = catalogue_route_for_file(file_path, architect)
    if not route.get("skeleton_id"):
        return content, False
    content = normalize_catalogue_page_imports(content, route)
    if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
        return content, False
    repaired, healed = repair_skeleton_composer_invocation(content, route)
    if healed:
        content = repaired
        if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
            return content, False
    repaired, healed = repair_missing_catalogue_slots(
        content,
        route,
        brand_name=brand_name,
    )
    if healed:
        return repaired, False
    return (
        minimal_catalogue_page_scaffold(
            file_path,
            route,
            brand_name=brand_name,
        ),
        True,
    )

