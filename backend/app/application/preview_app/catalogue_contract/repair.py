"""Catalogue page import normalization and slot repair."""
from __future__ import annotations

import json
import logging
import re

from app.application.preview_app.catalogue_contract.imports import normalize_catalogue_page_imports
from app.application.preview_app.catalogue_contract.item_source import (
    catalogue_detail_base,
    unify_catalogue_item_source,
)
from app.application.preview_app.catalogue_contract.scaffold import (
    _SLOT_COMPONENT,
    _is_directory_listing_route,
    catalog_base_from_path,
    schedule_face_required,
    _paint_first_detail_slots,
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


_MOCK_IMPORT_RE = re.compile(
    r"import\s*\{(?P<names>[^}]*)\}\s*from\s*(?P<q>['\"])@/data/mock(?P=q)\s*;?"
)


def _ensure_mock_import_names(content: str, names: list[str]) -> str:
    """Guarantee `import { …names } from '@/data/mock'`, extending any existing one.

    A second `import … from '@/data/mock'` line would shadow nothing but reads as a
    duplicate; extending the named list is what the rest of the pipeline does. This
    exists because slot injection ensured `images` and not `seed`: request 47's cart
    and checkout pages got a `cta` slot reading `seed.cta?.heading` on a page that
    never imported `seed` — twelve TS2304s, six per page, all on one line.
    """
    wanted = [n for n in names if n]
    if not wanted:
        return content
    match = _MOCK_IMPORT_RE.search(content)
    if not match:
        return f"import {{ {', '.join(sorted(set(wanted)))} }} from '@/data/mock';\n" + content
    present = {n.strip() for n in match.group("names").split(",") if n.strip()}
    missing = [n for n in wanted if n not in present]
    if not missing:
        return content
    merged = ", ".join(sorted(present | set(missing)))
    return (
        content[: match.start()]
        + f"import {{ {merged} }} from '@/data/mock';"
        + content[match.end() :]
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
    # Detail faces must stay painting → specs → inquire even when architect
    # section_slots still list showcase/features first (catalogue.json / product_kind).
    if skeleton_id == "public-detail":
        slots = _paint_first_detail_slots(slots)

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


_CONSTANT_BINDING_FIXABLE = frozenset(
    {
        "detail inquire CTA (#inquire)",
        "catalogue item photo pool (images.item*)",
        "catalogue lifestyle imageSrc (card/hero)",
    }
)

#: Codes the SAME near-miss href fires alongside the primary defect — a CTA
#: broken to `#contact` also trips the dead-hash check, and the detail face's
#: InquiryPanel allowance is keyed on the inquire anchor. They ride the gate
#: (never trigger it alone); the re-validate-clean requirement below is what
#: keeps a genuinely broken import on the strict path.
_CONSTANT_BINDING_DERIVED = frozenset(
    {
        "dead hash CTA (#details/#contact)",
        "forbidden @/ui component:InquiryPanel",
    }
)

_INQUIRE_NEAR_MISS_HREF_RE = re.compile(
    r"""href:\s*(['"])(?:/contact#inquire|#contact|#details|/contact(?:-us)?)\1"""
)

_IMAGE_POOL_REGION_RE = re.compile(
    r"(?:imageSrc:\s*\[[^\]]*\]|PAINTING_IMAGES\s*=\s*\[[^\]]*\])",
    re.DOTALL,
)

#: card/hero → item rebinding for lifestyle photo pools. card* maps onto the
#: front of the item pool, hero* onto the middle — deterministic, bounded by
#: the item1…item8 members mock.ts declares for exactly this purpose.
_LIFESTYLE_TO_ITEM = {
    "card": "item1",
    "card2": "item2",
    "card3": "item3",
    "hero": "item4",
    "hero2": "item5",
    "hero3": "item6",
}


def _rebind_lifestyle_image_pools(content: str) -> str:
    """Rewrite `images.card/hero` to the item pool INSIDE image-array regions only.

    A hero section legitimately reading `images.hero` elsewhere on the page must
    keep it — the defect is lifestyle photography in the per-item pool
    (request 62 shipped people-in-museums on every gallery card), so only
    `imageSrc: […]` arrays and `PAINTING_IMAGES = […]` declarations rebind.
    """

    def _rebind_region(match: re.Match[str]) -> str:
        return re.sub(
            r"images\.(card|hero)(\d*)\b",
            lambda m: "images."
            + _LIFESTYLE_TO_ITEM.get(m.group(1) + m.group(2), "item1"),
            match.group(0),
        )

    return _IMAGE_POOL_REGION_RE.sub(_rebind_region, content)


def repair_constant_binding_defects(content: str, route: dict) -> tuple[str, bool]:
    """Coerce compile-time-constant contract defects instead of rebuilding.

    R3 (owner-ruled, session 24): `detail inquire CTA (#inquire)` ALONE
    discarded two whole authored pages to the generic scaffold (session 18's
    ArtworkDetailPage and RoomDetailPage, both at attempt 2/2, two retry asks
    burned) and the image-pool pair discarded a HomePage with no retry — for
    fields whose correct values are known constants. The aced8e7 split applied
    here: coerce the constant, keep faces/skeleton/imports/slots exactly as
    strict as before. Applies ONLY when every blocking error is in the fixable
    set, rewrites only recognizable near-miss shapes, and re-validates — a page
    it cannot prove clean takes the existing path unchanged.
    """

    errors = blocking_contract_errors(validate_catalogue_page_content(content, route))
    fixable = _CONSTANT_BINDING_FIXABLE | _CONSTANT_BINDING_DERIVED
    if not errors or any(error not in fixable for error in errors):
        return content, False
    # No explicit primary-defect clause: each codemod branch below keys on its
    # own primary code, so derived codes alone leave the page byte-identical
    # and the `repaired == content` check refuses the heal (pinned by test).
    repaired = content
    if "detail inquire CTA (#inquire)" in errors:
        repaired = _INQUIRE_NEAR_MISS_HREF_RE.sub(
            "href: '#inquire'", repaired, count=1
        )
    if {
        "catalogue item photo pool (images.item*)",
        "catalogue lifestyle imageSrc (card/hero)",
    } & set(errors):
        repaired = _rebind_lifestyle_image_pools(repaired)
    if repaired == content:
        return content, False
    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):
        return content, False
    logger.info(
        "Catalogue page healed by constant-binding repair route=%s",
        route.get("path"),
    )
    return repaired, True


def repair_missing_catalogue_slots(
    content: str,
    route: dict,
    *,
    brand_name: str | None = None,
    architect: dict | None = None,
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
    # The same base `minimal_catalogue_page_scaffold` derives. Left unpassed, an
    # injected catalogue slot fell back to the `/gallery` default, so a page the
    # repair loop touched came out with card links the generator would never have
    # written — and only on the repair path, which is the hardest place to see it.
    detail_base = catalog_base_from_path(str(route.get("path") or ""), architect)
    ordered_missing = [
        slot for slot in assigned_non_shell_slots(route) if slot in missing
    ]
    if set(ordered_missing) != missing:
        return content, False

    def _slot_jsx(slot: str) -> str:
        return _safe_slot_jsx(
            slot,
            brand,
            title,
            skeleton_id=skeleton_id,
            detail_base=detail_base,
            architect=architect,
        )

    try:
        injected = "".join(
            f"\n    {slot}: (\n      {_slot_jsx(slot)}\n    ),"
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

    injected_jsx = "".join(_slot_jsx(slot) for slot in ordered_missing)
    # Every identifier an injected slot reads out of the mock must be imported,
    # not just `images`.
    repaired = _ensure_mock_import_names(
        repaired,
        [name for name in ("images", "seed") if f"{name}." in injected_jsx],
    )

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


def _is_ops_surface_file(file_path: str, route: dict | None) -> bool:
    """Owner pages keep their own tables; the storefront catalogue is not theirs."""
    path = str((route or {}).get("path") or "").lower()
    rel = (file_path or "").replace("\\", "/").lower()
    return (
        str((route or {}).get("surface") or "").lower() == "ops"
        or path.startswith(("/admin", "/owner", "/ops", "/staff", "/member", "/desk"))
        or "/admin/" in rel
        or "/owner/" in rel
        or "/ops/" in rel
    )


def enforce_catalogue_page_contract(
    file_path: str,
    content: str,
    architect: dict | None,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    route = catalogue_route_for_file(file_path, architect)
    # Before anything else: a listing that inlined its own catalogue links every
    # card at an id the detail route cannot resolve. Rewrite the item source, keep
    # the authored layout and copy. Runs on scaffolds too and is a no-op there.
    if content and not _is_ops_surface_file(file_path, route):
        try:
            unified, touched = unify_catalogue_item_source(
                content, detail_base=catalogue_detail_base(architect)
            )
            if touched:
                logger.info(
                    "catalogue item source unified in %s (%s)",
                    file_path,
                    ", ".join(touched),
                )
                content = unified
        except Exception as e:  # noqa: BLE001 — never fail a build over a codemod
            logger.warning("catalogue item source rewrite skipped for %s: %s", file_path, e)
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
    # Contact/auth must stay utility forms even when architect assigned public-home
    # or left skeleton_id empty (request 50 ContactPage was a marketing clone).
    route_path = str(route.get("path") or "")
    from app.application.preview_app.utility_compositor import (
        compose_utility_page_tsx,
        infer_utility_workspace_type,
        should_compose_utility_page,
    )

    if should_compose_utility_page(route, str(route.get("skeleton_id") or "")):
        wtype = infer_utility_workspace_type(
            route_path,
            str(route.get("title") or ""),
            str(route.get("page_type") or ""),
        )
        if wtype in {"contact", "auth"}:
            needs_form = (
                (wtype == "contact" and "InquiryPanel" not in (content or ""))
                or (wtype == "auth" and "<Input" not in (content or ""))
                or "composed public-utility page" not in (content or "")
            )
            if needs_form:
                return (
                    compose_utility_page_tsx(
                        file_path=file_path,
                        route={**route, "skeleton_id": "public-utility"},
                        content={},
                        brand_name=brand_name or "Brand",
                        workspace_type=wtype,
                    ),
                    True,
                )
            # Already a composed utility form — do not fall through to catalogue
            # validation against a wrong architect skeleton (public-home /
            # public-service). That path replaced request 62's InquiryPanel with a
            # marketing scaffold ("catalogue scaffold replaced ContactPage").
            return content, False
    if not route.get("skeleton_id"):
        # Face pages without a skeleton still need protect-on-sight validation.
        if _is_dedicated_face_page(content or ""):
            if not blocking_contract_errors(
                validate_catalogue_page_content(content or "", route or {"path": "/ai-features"})
            ):
                return content, False
        return content, False
    # Listing routes must keep their dedicated face — AI catalog clones get replaced.
    # Param routes are never directory listings (request 50: /gallery/:collectionId).
    has_route_param = bool(
        re.search(r"/:\w+", route_path) or re.search(r"/\{[^}]+\}", route_path)
    )
    if (
        schedule_face_required(file_path, route)
        and "ScheduleRail" not in (content or "")
        and not has_route_param
    ):
        return (
            minimal_catalogue_page_scaffold(
                file_path, route, brand_name=brand_name, architect=architect
            ),
            True,
        )
    is_listing_face = (
        not has_route_param
        and str(route.get("skeleton_id") or "") != "public-detail"
        and (
            str(route.get("page_intent") or "").strip().lower() == "listing"
            or _is_directory_listing_route(file_path, route)
            or str(route.get("skeleton_id") or "") == "public-catalog"
        )
    )
    lifestyle_catalogue = bool(
        re.search(r"imageSrc:\s*\[images\.(?:card|hero)", content or "")
        or re.search(
            r"PAINTING_IMAGES\s*=\s*\[[\s\S]*?images\.(?:card|hero)", content or ""
        )
        or (
            ("CatalogGrid" in (content or "") or "ProductShowcase" in (content or ""))
            and "images.item1" not in (content or "")
            and "images.item2" not in (content or "")
        )
        # Browse pages capped at 3 cards — journey_browse_caps_items on request 64.
        or (
            "ProductShowcase" in (content or "")
            and "CatalogGrid" not in (content or "")
            and (
                str(route.get("skeleton_id") or "") == "public-catalog"
                or re.search(
                    r"(^|/)(gallery|collection|collections|shop|works|paintings)(/|$)",
                    route_path,
                    re.I,
                )
            )
        )
    )
    # A refine pass strips comments, and the face marker is one. When the face
    # itself is intact — it still renders a listing component, it has not
    # regressed to a home clone — only the label was lost, so put the label back
    # rather than discarding a refinement over a comment.
    if (
        is_listing_face
        and _DIRECTORY_FACE_MARKER not in (content or "")
        and has_listing_face_component(content or "")
        and "seed.hero" not in (content or "")
        and not lifestyle_catalogue
    ):
        content = (
            f"{_DIRECTORY_FACE_MARKER} — distinct from home marketing clone\n"
            f"{content or ''}"
        )
    if is_listing_face and (
        not has_listing_face_component(content or "")
        or "seed.hero" in (content or "")
        or _DIRECTORY_FACE_MARKER not in (content or "")
        or lifestyle_catalogue
    ):
        # Schedule listings still use ScheduleRail — skip those, or the rewrite
        # below replaces a legitimate rail with a CatalogGrid. This site used to
        # inline `page_intent != "listing"`, a third variant of the rule the gate
        # and the generator each spelled differently; it now asks the one
        # function, so the repair restores exactly the face the generator builds.
        if schedule_face_required(file_path, route) and not lifestyle_catalogue:
            pass
        else:
            return (
                minimal_catalogue_page_scaffold(
                    file_path, route, brand_name=brand_name, architect=architect
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
                    file_path, route, brand_name=brand_name, architect=architect
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
    repaired, healed = repair_constant_binding_defects(content, route)
    if healed:
        content = lock_recipe_section_order(repaired, route)
        if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
            return content, False
    repaired, healed = repair_missing_catalogue_slots(
        content,
        route,
        brand_name=brand_name,
        architect=architect,
    )
    if healed:
        return lock_recipe_section_order(repaired, route), False
    return (
        minimal_catalogue_page_scaffold(
            file_path,
            route,
            brand_name=brand_name,
            architect=architect,
        ),
        True,
    )

