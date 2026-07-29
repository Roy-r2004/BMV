"""Catalogue page import normalization and slot repair."""
from __future__ import annotations

import json
import logging
import re

from app.application.preview_app.catalogue_contract.imports import normalize_catalogue_page_imports
from app.application.preview_app.catalogue_contract.scaffold import (
    _SLOT_COMPONENT,
    _is_directory_listing_route,
    _is_schedule_listing_route,
    _safe_slot_jsx,
    has_listing_face_component,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.slots import (
    assigned_non_shell_slots,
    catalogue_route_for_file,
)
from app.application.preview_app.catalogue_contract.validate import (
    _AI_HUB_FACE_MARKER,
    _CONFIRM_FACE_MARKER,
    _DIRECTORY_FACE_MARKER,
    _SCHEDULE_FACE_MARKER,
    blocking_contract_errors,
    validate_catalogue_page_content,
)
from app.application.preview_app.patterns import default_export_search_from
from app.application.services.ai_features import ai_feature_hub_page_source

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
_RECIPE_ORDER_RE = re.compile(
    r"const\s+RECIPE_ORDER\s*=\s*\[[^\]]*\]\s*as\s*const\s*;?",
    re.DOTALL,
)
_FACE_SKELETONS = frozenset(
    {"public-home", "public-service", "public-detail", "public-booking"}
)
_COMPOSER_FIXABLE = frozenset({"SkeletonComposer invocation", "assigned skeleton literal"})


def _named_ui_imports(clause: str) -> set[str]:
    return {
        token.strip().split(" as ")[0].replace("type ", "").strip()
        for token in clause.split(",")
        if token.strip()
    }


def _ensure_ui_import_names(content: str, needed: list[str]) -> str:
    """Add missing identifiers to an existing ``from '@/ui'`` import, if present."""
    ui_import = _UI_IMPORT_RE.search(content)
    if not ui_import or not needed:
        return content
    names = _named_ui_imports(ui_import.group(1))
    missing = [name for name in needed if name not in names]
    if not missing:
        return content
    current = ui_import.group(1).strip().rstrip(",").strip()
    merged = ", ".join(filter(None, [current, ", ".join(missing)]))
    return content.replace(
        ui_import.group(0),
        f"import {{ {merged} }} from '@/ui';",
        1,
    )


def lock_recipe_section_order(content: str, route: dict) -> str:
    """Force RECIPE_ORDER to the architect/recipe face — codegen must not rewrite it."""
    skeleton_id = str(route.get("skeleton_id") or "")
    if skeleton_id not in _FACE_SKELETONS:
        return content
    slots = assigned_non_shell_slots(route)
    if not slots:
        return content

    order_decl = f"const RECIPE_ORDER = {json.dumps(slots)} as const;"
    if _RECIPE_ORDER_RE.search(content):
        locked = _RECIPE_ORDER_RE.sub(order_decl, content, count=1)
    elif _SKELETON_CONST_RE.search(content):
        locked = _SKELETON_CONST_RE.sub(
            lambda m: f"{m.group(0)}\n{order_decl}",
            content,
            count=1,
        )
    else:
        locked = content

    if _COMPOSER_INVOCATION_RE.search(locked):
        locked = _COMPOSER_INVOCATION_RE.sub(
            "<SkeletonComposer skeletonId={SKELETON_ID} slots={slots} order={RECIPE_ORDER} />",
            locked,
            count=1,
        )
    return locked


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
        needed = ["getSkeleton", "SkeletonComposer"]
        if skeleton_id == "ops-dashboard":
            needed = ["getSkeleton", "composeSkeletonLayout"]
        repaired = _ensure_ui_import_names(repaired, needed)

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
        else:
            # Inject into the default-export return — never a helper above it.
            search_from = default_export_search_from(repaired)
            idx = repaired.find("return (", search_from)
            if idx >= 0:
                insert_at = idx + len("return (")
                repaired = (
                    repaired[:insert_at]
                    + f"\n      {composer_jsx}\n"
                    + repaired[insert_at:]
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
    skeleton_id = str(route.get("skeleton_id") or "")
    ordered_missing = [
        slot for slot in assigned_non_shell_slots(route) if slot in missing
    ]
    if set(ordered_missing) != missing:
        return content, False
    try:
        injected = "".join(
            f"\n    {slot}: (\n      {_safe_slot_jsx(slot, brand, title, skeleton_id=skeleton_id)}\n    ),"
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

    existing_named = _named_ui_imports(ui_import.group(1))
    needed = list(
        dict.fromkeys(
            component
            for slot in ordered_missing
            if (component := _SLOT_COMPONENT.get(slot))
            and component not in existing_named
        )
    )
    if needed:
        repaired = _ensure_ui_import_names(repaired, needed)

    needs_images = any(
        "images." in _safe_slot_jsx(slot, brand, title, skeleton_id=skeleton_id)
        for slot in ordered_missing
    )
    if needs_images and not _IMAGES_IMPORT_RE.search(repaired):
        repaired = "import { images } from '@/data/mock';\n" + repaired

    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):
        return content, False
    logger.info(
        "Catalogue page healed by slot injection route=%s slots=%s",
        route.get("path"),
        ordered_missing,
    )
    return repaired, True


def _is_dedicated_face_page(content: str) -> bool:
    """Listing / ConfirmStage / AI hub faces must not become SkeletonComposer pages."""
    text = content or ""
    return (
        _SCHEDULE_FACE_MARKER in text
        or _DIRECTORY_FACE_MARKER in text
        or _CONFIRM_FACE_MARKER in text
        or _AI_HUB_FACE_MARKER in text
        or ("AiFeatureDeck" in text and "aiFeatures" in text)
    )


def _is_ai_hub_file(file_path: str, route: dict) -> bool:
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "").casefold()
    rel = (file_path or "").replace("\\", "/").lower()
    return (
        path == "/ai-features"
        or page_id == "page-ai-features"
        or rel.endswith("aifeaturespage.tsx")
    )


def enforce_catalogue_page_contract(
    file_path: str,
    content: str,
    architect: dict | None,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    route = catalogue_route_for_file(file_path, architect)
    # AI hub: always restore AiFeatureDeck if missing (even with empty skeleton_id).
    if _is_ai_hub_file(file_path, route) and "AiFeatureDeck" not in (content or ""):
        return (
            ai_feature_hub_page_source(
                brand_name=brand_name or "Brand",
                features=[],
                page_id=str(
                    route.get("app_spec_page_id") or route.get("page_id") or "PAGE-AI-FEATURES"
                ),
                evidence_ids=list(route.get("evidence_ids") or []),
            ),
            True,
        )
    if not route.get("skeleton_id"):
        # Face pages without a skeleton still need protect-on-sight validation.
        if _is_dedicated_face_page(content or ""):
            if not blocking_contract_errors(
                validate_catalogue_page_content(content or "", route or {"path": "/ai-features"})
            ):
                return content, False
        return content, False
    # Listing routes must keep their dedicated face — AI catalog clones get replaced.
    if _is_schedule_listing_route(file_path, route) and "ScheduleRail" not in (content or ""):
        return (
            minimal_catalogue_page_scaffold(
                file_path, route, brand_name=brand_name
            ),
            True,
        )
    is_listing_face = (
        str(route.get("page_intent") or "").strip().lower() == "listing"
        or _is_directory_listing_route(file_path, route)
    )
    if is_listing_face and (
        not has_listing_face_component(content or "")
        or "seed.hero" in (content or "")
        or _DIRECTORY_FACE_MARKER not in (content or "")
    ):
        # Schedule listings (keyword, no intent) still use ScheduleRail — skip those.
        if (
            str(route.get("page_intent") or "").strip().lower() != "listing"
            and _is_schedule_listing_route(file_path, route)
        ):
            pass
        else:
            return (
                minimal_catalogue_page_scaffold(
                    file_path, route, brand_name=brand_name
                ),
                True,
            )
    # Dedicated faces already encode layout; only validate, never rewrite.
    if _is_dedicated_face_page(content):
        if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
            return content, False
        if _SCHEDULE_FACE_MARKER in (content or "") or _DIRECTORY_FACE_MARKER in (
            content or ""
        ):
            return (
                minimal_catalogue_page_scaffold(
                    file_path, route, brand_name=brand_name
                ),
                True,
            )
        if _is_ai_hub_file(file_path, route) or _AI_HUB_FACE_MARKER in (content or ""):
            return (
                ai_feature_hub_page_source(
                    brand_name=brand_name or "Brand",
                    features=[],
                    page_id=str(
                        route.get("app_spec_page_id")
                        or route.get("page_id")
                        or "PAGE-AI-FEATURES"
                    ),
                    evidence_ids=list(route.get("evidence_ids") or []),
                ),
                True,
            )
        return content, False
    content = normalize_catalogue_page_imports(content, route)
    # Always re-assert recipe face order, even when the page already compiles.
    content = lock_recipe_section_order(content, route)
    if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
        return content, False
    repaired, healed = repair_skeleton_composer_invocation(content, route)
    if healed:
        content = lock_recipe_section_order(repaired, route)
        if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
            return content, False
    repaired, healed = repair_missing_catalogue_slots(
        content,
        route,
        brand_name=brand_name,
    )
    if healed:
        return lock_recipe_section_order(repaired, route), False
    return (
        minimal_catalogue_page_scaffold(
            file_path,
            route,
            brand_name=brand_name,
        ),
        True,
    )

