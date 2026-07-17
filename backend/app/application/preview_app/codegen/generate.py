"""Per-file React/TSX generation."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.brand_brief import brief_prompt_block
from app.application.preview_app.catalogue_contract import (
    blocking_contract_errors,
    enforce_catalogue_page_contract,
)
from app.application.preview_app.codegen.architect import (
    _CHROME_CONTRACTS,
    _architect_prompt_context,
    _route_for_file,
)
from app.application.preview_app.codegen.shared import (
    _brand_name_from_manifest,
    _catalogue_contract_errors,
    _catalogue_retry_context,
    _sanitize_emoji_icons,
    page_plan_for_file,
)
from app.application.preview_app.text_utils import _bounded_json, _parse_json, _strip_fences
from app.application.preview_app.fallback import clear_stubbed_path, record_stubbed_path
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    safe_source_path,
)
from app.application.preview_app.source_quality import looks_truncated_source
from app.application.preview_app.utility_compositor import (
    compose_utility_page_tsx,
    default_utility_content,
    infer_utility_workspace_type,
    is_utility_catalogue_route,
    normalize_utility_content,
)
from app.application.preview_app.workspace import list_source_files, read_file, summarize_files, write_file
from app.application.services.page_experience import page_required_sections
from app.application.ui_catalogue import compact_skeleton_contract, infer_section_slots
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

cg_log = get_logger("Codegen")

def _generate_utility_composed_file(
    workspace: Path,
    file_path: str,
    *,
    route: dict,
    page_plan: dict,
    full_context: str,
    manifest: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    """Content-JSON → deterministic TSX for public-utility pages."""
    brand_name = _brand_name_from_manifest(manifest)
    path = str(route.get("path") or page_plan.get("path") or "")
    title = str(route.get("title") or page_plan.get("title") or file_path)
    page_type = str(route.get("page_type") or page_plan.get("page_type") or "")
    workspace_type = infer_utility_workspace_type(path, title, page_type)

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_UTILITY_CONTENT,
        full_context=full_context[:8000],
        route_path=path or "/",
        page_title=title,
        workspace_type=workspace_type,
        brand_name=brand_name,
        page_plan_json=_bounded_json(page_plan, 4000) if page_plan else "{}",
    )

    content_payload: dict = {}
    cg_log.debug(
        "compose_utility %s type=%s model=%s", file_path, workspace_type, settings.PREVIEW_APP_MODEL
    )
    try:
        raw = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL,
            [{"role": "user", "content": prompt}],
            max_tokens=6000,
        )
        parsed = _parse_json(_strip_fences(raw))
        if isinstance(parsed, dict):
            content_payload = parsed
        else:
            cg_log.warning("utility JSON not an object for %s; using defaults", file_path)
    except Exception as exc:
        cg_log.warning("utility content ask failed for %s: %s; using defaults", file_path, exc)

    if not content_payload:
        content_payload = default_utility_content(
            workspace_type, brand_name=brand_name, title=title, path=path
        )
    else:
        content_payload = normalize_utility_content(
            content_payload,
            workspace_type,
            brand_name=brand_name,
            title=title,
            path=path,
        )

    composed = compose_utility_page_tsx(
        file_path=file_path,
        route={**route, "path": path, "title": title, "skeleton_id": "public-utility"},
        content=content_payload,
        brand_name=brand_name,
        workspace_type=workspace_type,
    )

    composed, replaced = enforce_catalogue_page_contract(
        file_path,
        composed,
        {"routes": [{**route, "path": path, "title": title, "skeleton_id": "public-utility", "component_file": file_path}]},
        brand_name=brand_name,
    )
    if replaced:
        # Last resort: compose again from defaults (never leave a blank scaffold).
        cg_log.warning("utility compose re-emit defaults for %s", file_path)
        composed = compose_utility_page_tsx(
            file_path=file_path,
            route={**route, "path": path, "title": title, "skeleton_id": "public-utility"},
            content=default_utility_content(
                workspace_type, brand_name=brand_name, title=title, path=path
            ),
            brand_name=brand_name,
            workspace_type=workspace_type,
        )
        clear_stubbed_path(workspace, file_path)
    else:
        clear_stubbed_path(workspace, file_path)

    write_file(workspace, file_path, composed)
    return composed

def generate_file(
    workspace: Path,
    file_spec: dict,
    full_context: str,
    architect: dict,
    plan: dict,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    raw_file_path = file_spec.get("path", "")
    file_path = safe_source_path(raw_file_path, workspace)
    if not file_path:
        raise ValueError(f"Unsafe generated source path: {raw_file_path}")
    if is_template_owned_path(file_path, architect, workspace):
        return read_file(workspace, file_path)
    file_kind = file_spec.get("kind", "page")
    instructions = file_spec.get("instructions", "")
    page_plan = page_plan_for_file(file_path, plan, architect)
    page_plan_json = _bounded_json(page_plan, 6000) if page_plan else "{}"
    app_spec_contract = page_plan.get("app_spec_contract") or {}
    app_spec_contract_json = (
        _bounded_json(app_spec_contract, 12000) if app_spec_contract else "{}"
    )
    route = _route_for_file(file_path, architect)
    skeleton_id = str(route.get("skeleton_id") or page_plan.get("skeleton_id") or "")
    catalogue_page = file_kind == "page" and bool(skeleton_id)

    # Contract compositor: utility pages never go through freeform React codegen.
    if (
        catalogue_page
        and is_utility_catalogue_route(route, skeleton_id)
        and not app_spec_contract
    ):
        merged_route = {
            **route,
            "skeleton_id": "public-utility",
            "path": route.get("path") or page_plan.get("path") or "",
            "title": route.get("title") or page_plan.get("title") or file_path,
            "page_type": route.get("page_type") or page_plan.get("page_type") or "",
            "section_slots": route.get("section_slots")
            or page_plan.get("section_slots")
            or ["header", "workspace", "summary", "footer"],
            "component_file": file_path,
        }
        return _generate_utility_composed_file(
            workspace,
            file_path,
            route=merged_route,
            page_plan=page_plan or {},
            full_context=full_context,
            manifest=manifest,
            ai_provider=ai_provider,
            template_renderer=template_renderer,
        )

    skeleton_contract_json = "{}"
    shell_component = ""
    if catalogue_page:
        slots = infer_section_slots({**page_plan, **route}, skeleton_id)
        skeleton_contract_json = _bounded_json(
            compact_skeleton_contract(skeleton_id, slots),
            5000,
        )
        shell_component = "OpsShell" if (route.get("surface") or page_plan.get("surface")) == "ops" else "PublicShell"
    if page_plan and file_kind == "page":
        required = page_required_sections(page_plan)
        if required:
            instructions += "\n\nRequired sections:\n" + "\n".join(f"- {s}" for s in required)

    chrome_contract = None
    if not any(item.get("skeleton_id") for item in architect.get("routes") or []):
        chrome_contract = _CHROME_CONTRACTS.get(file_path.replace("\\", "/").lower())
    if chrome_contract:
        instructions = f"{instructions}\n\n{chrome_contract}".strip()

    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    recipe_id = (
        plan.get("recipe_id")
        or design_system.get("recipe_id")
        or architect.get("recipe_id")
        or ""
    )
    recipe_prompt = design_system.get("recipe_prompt") or ""
    hub_variant = (
        plan.get("hub_variant")
        or design_system.get("hub_variant")
        or architect.get("hub_variant")
        or ""
    )
    from app.application.preview_app.brand_brief import brief_prompt_block

    brand_brief_block = ""
    if design_system.get("brand_locked"):
        brand_brief_block = brief_prompt_block(
            {
                "brand_name": manifest.get("brand_name") or manifest.get("name"),
                "mood": design_system.get("mood"),
                "voice": design_system.get("voice"),
                "signature": design_system.get("signature"),
                "palette": {
                    "primary": design_system.get("primary_color"),
                    "secondary": design_system.get("secondary_color"),
                    "background": design_system.get("background_color"),
                    "text": design_system.get("text_color"),
                    "muted": design_system.get("muted_text_color"),
                },
                "typography": {
                    "font_family": design_system.get("font_family"),
                    "display_font_family": design_system.get("display_font_family"),
                },
                "avoid": design_system.get("avoid") or [],
                "rules": design_system.get("rules") or [],
            }
        )
    # Avoid re-reading the whole tree on every parallel worker (was slow + racy).
    existing = ""
    try:
        existing = summarize_files(workspace, list_source_files(workspace))
    except Exception as exc:
        cg_log.debug("summarize_files skip for %s: %s", file_path, exc)

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FILE,
        full_context=full_context[:10000],
        architect_json=_architect_prompt_context(architect),
        design_system_json=json.dumps(design_system, ensure_ascii=False, indent=2),
        brand_brief_block=brand_brief_block,
        recipe_id=recipe_id,
        recipe_prompt=recipe_prompt,
        hub_variant=hub_variant,
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_path=file_path,
        file_kind=file_kind,
        file_instructions=instructions,
        page_plan_json=page_plan_json,
        app_spec_contract_json=app_spec_contract_json,
        catalogue_page=catalogue_page,
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
        shell_component=shell_component,
        existing_files_summary=existing[:8000],
    )

    cg_log.debug("ask_chat %s model=%s", file_path, settings.PREVIEW_APP_MODEL)
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    content = _sanitize_emoji_icons(_strip_fences(raw))

    def _needs_retry(src: str) -> bool:
        if not (src or "").strip():
            return True
        if looks_truncated_source(src):
            return True
        if file_kind in ("page", "layout", "component", "router") and "export default" not in src:
            return True
        return False

    # Up to 2 retries on the primary path — completeness and the catalogue
    # contract are both required before deterministic scaffolding is considered.
    for attempt in range(1, 3):
        contract_errors = (
            _catalogue_contract_errors(
                file_path, content, route, workspace=workspace, attempt=attempt,
            )
            if catalogue_page and not _needs_retry(content)
            else []
        )
        # Prop/variant mismatches alone don't block — enforce tolerates them.
        if not _needs_retry(content) and not blocking_contract_errors(contract_errors):
            break
        reason = (
            "catalogue contract: " + ", ".join(contract_errors)
            if contract_errors
            else "empty" if not (content or "").strip() else (
                "truncated" if looks_truncated_source(content) else "missing export default"
            )
        )
        cg_log.warning("regen %s attempt %s/2 (%s)", file_path, attempt, reason)
        import_rule = (
            "MUST import all page UI from `@/ui`; only React, router, and `@/data/mock` "
            "may be imported elsewhere."
            if catalogue_page
            else
            "ONLY import from react, react-router-dom, ../data/mock (or @/data/mock), "
            "../components/UiIcons, and existing local files. No npm icon/UI libraries."
        )
        if contract_errors:
            retry_prompt = (
                f"{prompt}\n\n"
                + _catalogue_retry_context(
                    errors=contract_errors,
                    contract_json=skeleton_contract_json,
                    rejected_source=content,
                )
            )
        else:
            retry_prompt = (
                f"{prompt}\n\n"
                f"IMPORTANT: Previous answer failed ({reason}). "
                "Return the COMPLETE TypeScript/React file only — start with imports, "
                f"end with export default. MUST compile. {import_rule} No markdown fences."
            )
        raw2 = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL, [{"role": "user", "content": retry_prompt}], max_tokens=16000,
        )
        retry_content = _sanitize_emoji_icons(_strip_fences(raw2))
        retry_contract_errors = (
            _catalogue_contract_errors(file_path, retry_content, route, workspace=workspace)
            if catalogue_page and not _needs_retry(retry_content)
            else []
        )
        if (
            retry_content
            and not _needs_retry(retry_content)
            and not blocking_contract_errors(retry_contract_errors)
        ):
            content = retry_content
            break
        if retry_content:
            content = retry_content

    if catalogue_page:
        _catalogue_contract_errors(file_path, content, route, workspace=workspace)
    content, replaced = enforce_catalogue_page_contract(
        file_path,
        content,
        architect,
        brand_name=(
            (manifest.get("brand") or {}).get("name")
            if isinstance(manifest.get("brand"), dict)
            else manifest.get("brand_name")
        ),
    )
    if replaced:
        cg_log.warning("catalogue contract scaffolded %s", file_path)
        record_stubbed_path(workspace, file_path)
    elif catalogue_page:
        if "deterministic catalogue contract scaffold" in content:
            record_stubbed_path(workspace, file_path)
        else:
            clear_stubbed_path(workspace, file_path)
    write_file(workspace, file_path, content)
    return content
