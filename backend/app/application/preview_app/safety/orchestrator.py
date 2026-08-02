"""Preview safety — orchestrator for all workspace guards."""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.design_recipes import get_recipe
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    restore_template_owned_files,
    snapshot_template_owned_files,
)
from app.application.preview_app.workspace import write_trusted_contained_file
from app.application.preview_app.safety.brand_contract import (
    ensure_brand_shape,
    ensure_brand_usage_paths,
)
from app.application.preview_app.safety.catalogue_guards import enforce_catalogue_workspace_contracts
from app.application.preview_app.safety.dead_links import repair_dead_links
from app.application.preview_app.safety.copy_hygiene import (
    decode_html_entities,
    decode_literal_unicode_escapes,
    strip_template_jargon_copy,
)
from app.application.preview_app.safety.imports import (
    ensure_headless_stub_imports,
    ensure_react_default_import,
    ensure_react_router_imports,
    normalize_ui_kit_imports,
    restore_curated_ui_kit,
    strip_forbidden_npm_imports,
)
from app.application.preview_app.safety.mock_data import (
    assert_brand_content_floor,
    enrich_date_starved_mock_exports,
    enrich_empty_mock_exports,
    ensure_mock_exports,
    normalize_mock_navigation,
    repair_typed_mock_exports,
    sanitize_data_files,
    sync_mock_images,
)
from app.application.preview_app.safety.runtime import ensure_runtime_correctness
from app.application.preview_app.safety.seed_keys import ensure_seed_keys_pages_read
from app.application.preview_app.safety.source_sanitize import (
    fix_nested_import_paths,
    repair_uneven_card_grids,
    sanitize_workspace_sources,
)
from app.application.preview_app.safety.ui_icons import (
    ensure_named_ui_icon_exports,
    ensure_ui_icon_coverage,
    ensure_ui_icons,
)
from app.core.config import settings
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

def apply_workspace_guards(
    workspace,
    architect: dict,
    plan: dict,
    images: dict,
    brand_name: str,
    primary: str,
    secondary: str,
    font: str,
    template_renderer: TemplateRenderer,
) -> list[str]:
    """Run every deterministic build guard. Safe to call before every `vite build`."""
    from app.application.preview_app.assemble import write_app_tsx, write_index_css

    actions: list[str] = []
    catalogue_workspace = has_catalogue_routes(architect)
    if catalogue_workspace:
        actions.extend(restore_curated_ui_kit(workspace))
    protected_snapshot = snapshot_template_owned_files(workspace, architect)
    recipe = get_recipe(
        (plan or {}).get("recipe_id")
        or ((plan or {}).get("design_system") or {}).get("recipe_id")
        or (architect or {}).get("recipe_id")
    )
    for fn, label in (
        (lambda: sanitize_workspace_sources(workspace), "fences stripped"),
        (lambda: sanitize_data_files(workspace), "quotes escaped"),
        (lambda: fix_nested_import_paths(workspace), "import paths fixed"),
        (lambda: repair_uneven_card_grids(workspace), "uneven card grids fixed"),
        (lambda: normalize_ui_kit_imports(workspace), "UI imports normalized"),
        (lambda: strip_forbidden_npm_imports(workspace), "forbidden npm imports stripped"),
        (lambda: ensure_headless_stub_imports(workspace), "headless stubs imported"),
        (lambda: ensure_react_default_import(workspace), "React imports fixed"),
        (lambda: ensure_react_router_imports(workspace), "react-router imports fixed"),
    ):
        try:
            result = fn()
            if result:
                actions.extend(result if isinstance(result, list) else [label])
        except Exception as e:
            guard_log.warning("guard %s skipped: %s", label, e)
    if catalogue_workspace:
        try:
            repaired = enforce_catalogue_workspace_contracts(
                workspace,
                architect,
                brand_name,
            )
            actions.extend(repaired)
        except Exception as e:
            restore_template_owned_files(workspace, architect, protected_snapshot)
            raise RuntimeError(
                f"Catalogue contract enforcement failed before build: {e}"
            ) from e
    if not has_catalogue_routes(architect):
        try:
            if ensure_ui_icons(workspace):
                actions.append("src/components/UiIcons.tsx")
        except Exception as e:
            guard_log.warning("ui icons guard skipped: %s", e)
        try:
            actions.extend(ensure_ui_icon_coverage(workspace))
        except Exception as e:
            guard_log.warning("ui icon coverage guard skipped: %s", e)
        try:
            named = ensure_named_ui_icon_exports(workspace)
            if named:
                actions.extend(named)
                guard_log.debug("%s", named[0])
        except Exception as e:
            guard_log.warning("named ui icon exports guard skipped: %s", e)
    try:
        synced = sync_mock_images(workspace, images, brand_name=brand_name)
        if synced:
            actions.extend([f"mock-images:{n}" for n in synced])
    except Exception as e:
        guard_log.warning("mock images sync skipped: %s", e)
    try:
        added = ensure_mock_exports(workspace, architect, plan, images, brand_name)
        actions.extend(added)
    except Exception as e:
        guard_log.warning("mock exports guard skipped: %s", e)
    try:
        filled = enrich_empty_mock_exports(workspace, brand_name)
        if filled:
            actions.extend([f"mock:{n}" for n in filled])
            guard_log.info("filled empty mock exports: %s", ", ".join(filled))
    except Exception as e:
        guard_log.warning("empty mock enrich skipped: %s", e)
    try:
        dated = enrich_date_starved_mock_exports(workspace, brand_name)
        if dated:
            actions.extend([f"mock-dates:{n}" for n in dated])
            guard_log.info("enriched date-starved mock exports: %s", ", ".join(dated))
    except Exception as e:
        guard_log.warning("date-starved mock enrich skipped: %s", e)
    try:
        # A `seed.<key>` a page reads and the seed never defined is `undefined`,
        # and one property access later the error boundary replaces the page.
        added = ensure_seed_keys_pages_read(workspace, brand_name)
        if added:
            actions.extend([f"seed-key:{n}" for n in added])
    except Exception as e:
        guard_log.warning("seed key guard skipped: %s", e)
    try:
        floor = assert_brand_content_floor(workspace, brand_name)
        if floor:
            actions.extend([f"mock-floor:{n}" for n in floor])
            guard_log.info("brand content floor: %s", ", ".join(floor))
    except Exception as e:
        guard_log.warning("brand content floor skipped: %s", e)
    try:
        repaired = repair_typed_mock_exports(workspace, brand_name, primary, secondary, font)
        if repaired:
            actions.extend([f"mock-typed:{n}" for n in repaired])
            guard_log.info("repaired typed mock exports: %s", ", ".join(repaired))
    except Exception as e:
        guard_log.warning("typed mock repair skipped: %s", e)
    try:
        if ensure_brand_shape(workspace, brand_name, primary, secondary, font):
            actions.append("src/data/mock.ts (brand shape fallback)")
            guard_log.debug(
                "contract: hardcoded fallback ensure_brand_shape "
                "(design_system/services/testimonials/client_names as needed)"
            )
    except Exception as e:
        guard_log.warning("brand shape guard skipped: %s", e)
    try:
        usage = ensure_brand_usage_paths(workspace, brand_name, primary, secondary, font)
        if usage:
            actions.extend(usage)
    except Exception as e:
        guard_log.warning("brand usage contract skipped: %s", e)
    try:
        src_main = settings.PREVIEW_TEMPLATE_DIR / "src" / "main.tsx"
        dst_main = Path(workspace) / "src" / "main.tsx"
        if src_main.is_file():
            text = src_main.read_text(encoding="utf-8")
            if "PreviewErrorBoundary" in text and (
                dst_main.is_symlink()
                or not dst_main.is_file()
                or "PreviewErrorBoundary" not in dst_main.read_text(encoding="utf-8")
            ):
                write_trusted_contained_file(workspace, "src/main.tsx", text)
                actions.append("src/main.tsx (error boundary)")
    except Exception as e:
        guard_log.warning("main.tsx sync skipped: %s", e)
    try:
        write_index_css(
            workspace,
            primary,
            secondary,
            font,
            template_renderer,
            recipe=recipe,
            design_system=(plan or {}).get("design_system") or {},
        )
        write_app_tsx(workspace, architect, template_renderer)
        # App.tsx can introduce mock imports after the earlier contract pass.
        # Close that deterministic gap in the same guard invocation.
        actions.extend(
            ensure_mock_exports(workspace, architect, plan, images, brand_name)
        )
    except Exception as e:
        guard_log.warning("assemble skipped: %s", e)
    if catalogue_workspace:
        try:
            from app.application.preview_app.chrome_nav import enforce_shared_chrome_nav

            chrome_fixed = enforce_shared_chrome_nav(workspace, architect)
            if chrome_fixed:
                actions.extend([f"chrome:{path}" for path in chrome_fixed])
                guard_log.info("shared chrome enforced on %s page(s)", len(chrome_fixed))
        except Exception as e:
            guard_log.warning("shared chrome guard skipped: %s", e)
    try:
        actions.extend(normalize_mock_navigation(workspace, architect, brand_name))
    except Exception as e:
        guard_log.warning("navigation normalization skipped: %s", e)
    try:
        # After `write_app_tsx` and after the nav normalizer, because both change
        # the answer: the first writes the route table this is judged against,
        # the second removes the nav entries that would otherwise be repaired
        # into links rather than deleted.
        actions.extend(repair_dead_links(workspace, architect))
    except Exception as e:
        guard_log.warning("dead-link repair skipped: %s", e)
    try:
        actions.extend(ensure_runtime_correctness(
            workspace, architect, plan, primary, secondary, font, template_renderer,
        ))
    except Exception as e:
        guard_log.warning("runtime correctness skipped: %s", e)
    # Copy hygiene runs last — every earlier writer is a possible source.
    for fn, label in (
        (lambda: decode_literal_unicode_escapes(workspace), "unicode escapes decoded"),
        (lambda: decode_html_entities(workspace), "html entities decoded"),
        (lambda: strip_template_jargon_copy(workspace), "template jargon replaced"),
    ):
        try:
            result = fn()
            if result:
                actions.extend(result)
        except Exception as e:
            guard_log.warning("guard %s skipped: %s", label, e)
    restore_template_owned_files(workspace, architect, protected_snapshot)
    return [
        action for action in actions
        if not is_template_owned_path(action.split(" (", 1)[0], architect)
    ]
