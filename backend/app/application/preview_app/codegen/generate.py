"""Per-file React/TSX generation."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.appspec.hooks import inject_appspec_contract_hooks
from app.application.prompts import PromptTemplate
from app.application.preview_app.brand_brief import brief_prompt_block
from app.application.preview_app.design_brief import (
    design_brief_prompt_block,
    resolve_design_brief,
)
from app.application.preview_app.catalogue_contract import (
    blocking_contract_errors,
    enforce_catalogue_page_contract,
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.repair import lock_recipe_section_order
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
from app.application.preview_app.source_quality import looks_truncated_source, tsx_parse_error
from app.application.preview_app.utility_compositor import (
    compose_utility_page_tsx,
    default_utility_content,
    infer_utility_workspace_type,
    normalize_utility_content,
    should_compose_utility_page,
)
from app.application.preview_app.workspace import list_source_files, read_file, summarize_files, write_file
from app.application.services.page_experience import page_required_sections
from app.application.ui_catalogue import compact_skeleton_contract, infer_section_slots
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.infrastructure.logging import get_logger

cg_log = get_logger("Codegen")

# Signature product faces — keep deterministic scaffolds; AI slot-fill reverts them
# to generic StatCard/DataTable stacks and kills the distinct product look.
_SIGNATURE_SKELETONS = frozenset(
    {
        "ops-ledger-home",
        "ops-invoice-board",
        "ops-recon-split",
        "ops-blotter-desk",
        "ops-expense-queue",
    }
)


# Bounded so a per-page retry cannot starve PREVIEW_MAX_AI_CALLS: at most two
# slot-fill calls per catalogue page, mirroring the freeform path's retry cap.
_MAX_SLOT_FILL_ATTEMPTS = 2

_SLOT_FILL_RETRY_GUIDANCE = {
    "truncated": (
        "The answer stopped mid-file, so braces and tags were left open. Shorten the slot "
        "copy, drop all comments, and make sure the final line closes the default export."
    ),
    "missing-export-default": (
        "The answer had no `export default function` component. Return the whole file, "
        "starting at the first import and ending with the closing brace of the default export."
    ),
    "unparseable-tsx": (
        "The answer did not parse as TSX. Balance every brace, parenthesis, and JSX tag, "
        "and escape apostrophes in visible copy as &apos;."
    ),
}


def _slot_fill_rejection(filled: str) -> tuple[str, str]:
    """`(reason, detail)` for an unusable slot-fill answer; `("", "")` when acceptable."""
    if not (filled or "").strip():
        return "empty", ""
    if looks_truncated_source(filled):
        return "truncated", ""
    if "export default" not in filled:
        return "missing-export-default", ""
    parse_error = tsx_parse_error(filled)
    if parse_error:
        return "unparseable-tsx", parse_error
    return "", ""


def _slot_fill_retry_prompt(prompt: str, *, reason: str, detail: str) -> str:
    guidance = _SLOT_FILL_RETRY_GUIDANCE.get(reason, "")
    failure = f"{reason}: {detail}" if detail else reason
    return (
        f"{prompt}\n\n"
        f"IMPORTANT: Previous answer failed ({failure}). {guidance} "
        "Keep the locked scaffold structure and every data-appspec-* attribute. "
        "Return the COMPLETE TypeScript/React file only. No markdown fences."
    )


def _appspec_ids_from_route_plan(route: dict, page_plan: dict) -> tuple[str, list[str], list[str]]:
    """Resolve page/action/evidence IDs from route + page_plan contract metadata."""
    page_id = (
        route.get("app_spec_page_id")
        or route.get("page_id")
        or page_plan.get("app_spec_page_id")
        or page_plan.get("id")
        or ""
    )
    contract = page_plan.get("app_spec_contract") or {}
    page_meta = contract.get("page") if isinstance(contract, dict) else {}
    if isinstance(page_meta, dict) and page_meta.get("id"):
        page_id = page_meta.get("id") or page_id
    action_ids = list(route.get("action_ids") or [])
    evidence_ids = list(route.get("evidence_ids") or [])
    if not action_ids and isinstance(contract, dict):
        action_ids = [
            str(item.get("id"))
            for item in (contract.get("actions") or [])
            if isinstance(item, dict) and item.get("id")
        ]
    if not evidence_ids and isinstance(contract, dict):
        evidence_ids = [
            str(item.get("id"))
            for item in (contract.get("evidence") or [])
            if isinstance(item, dict) and item.get("id")
        ]
    return str(page_id or ""), action_ids, evidence_ids


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

    # AppSpec hooks are additive — never a reason to skip the compositor.
    page_id, action_ids, evidence_ids = _appspec_ids_from_route_plan(route, page_plan)
    if page_id:
        composed = inject_appspec_contract_hooks(
            composed,
            page_id=page_id,
            action_ids=action_ids,
            evidence_ids=evidence_ids,
        )

    clear_stubbed_path(workspace, file_path)
    write_file(workspace, file_path, composed)
    return composed


def _merged_catalogue_route(
    file_path: str,
    route: dict,
    page_plan: dict,
    skeleton_id: str,
) -> dict:
    slots = infer_section_slots({**page_plan, **route}, skeleton_id)
    page_id, action_ids, evidence_ids = _appspec_ids_from_route_plan(route, page_plan)
    return {
        **route,
        "skeleton_id": skeleton_id,
        "path": route.get("path") or page_plan.get("path") or "",
        "title": route.get("title") or page_plan.get("title") or file_path,
        "section_slots": route.get("section_slots") or page_plan.get("section_slots") or slots,
        "component_file": file_path,
        "app_spec_page_id": page_id,
        "page_id": page_id,
        "action_ids": action_ids,
        "evidence_ids": evidence_ids,
        "surface": route.get("surface") or page_plan.get("surface") or "",
    }


def _generate_catalogue_scaffold_first_file(
    workspace: Path,
    file_path: str,
    *,
    file_spec: dict,
    route: dict,
    page_plan: dict,
    skeleton_id: str,
    full_context: str,
    plan: dict,
    manifest: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    """Emit a compiling catalogue scaffold first; optionally AI-fill slot copy once."""
    brand_name = _brand_name_from_manifest(manifest)
    merged = _merged_catalogue_route(file_path, route, page_plan or {}, skeleton_id)
    scaffold = minimal_catalogue_page_scaffold(
        file_path,
        merged,
        brand_name=brand_name,
    )
    page_id = str(merged.get("app_spec_page_id") or merged.get("page_id") or "")
    if page_id:
        scaffold = inject_appspec_contract_hooks(
            scaffold,
            page_id=page_id,
            action_ids=list(merged.get("action_ids") or []),
            evidence_ids=list(merged.get("evidence_ids") or []),
        )
    write_file(workspace, file_path, scaffold)
    cg_log.info("scaffold-first wrote %s skeleton=%s", file_path, skeleton_id)

    if skeleton_id in _SIGNATURE_SKELETONS:
        # Locked face — do not let slot-fill replace CashPulse/InvoiceBoard/etc.
        record_stubbed_path(workspace, file_path)
        cg_log.info("signature scaffold locked %s skeleton=%s", file_path, skeleton_id)
        return scaffold

    if not settings.PREVIEW_SCAFFOLD_SLOT_FILL:
        record_stubbed_path(workspace, file_path)
        return scaffold

    slots = infer_section_slots(merged, skeleton_id)
    skeleton_contract_json = _bounded_json(
        compact_skeleton_contract(skeleton_id, slots),
        5000,
    )
    shell_component = (
        "OpsShell" if (merged.get("surface") or "") == "ops" else "PublicShell"
    )
    app_spec_contract = page_plan.get("app_spec_contract") or {}
    design_brief_block = design_brief_prompt_block(
        resolve_design_brief(plan=plan, architect=architect)
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_SLOT_FILL,
        full_context=full_context[:8000],
        file_path=file_path,
        file_instructions=file_spec.get("instructions") or "",
        page_plan_json=_bounded_json(page_plan, 4000) if page_plan else "{}",
        app_spec_contract_json=(
            _bounded_json(app_spec_contract, 8000) if app_spec_contract else "{}"
        ),
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
        shell_component=shell_component,
        scaffold_source=scaffold[:16000],
        design_brief_block=design_brief_block,
    )
    content = scaffold
    attempt_prompt = prompt
    for attempt in range(1, _MAX_SLOT_FILL_ATTEMPTS + 1):
        try:
            cg_log.debug(
                "slot_fill %s attempt %s/%s model=%s",
                file_path,
                attempt,
                _MAX_SLOT_FILL_ATTEMPTS,
                settings.PREVIEW_APP_MODEL,
            )
            raw = ai_provider.ask_chat(
                settings.PREVIEW_APP_MODEL,
                [{"role": "user", "content": attempt_prompt}],
                max_tokens=12000,
            )
        except Exception as exc:
            cg_log.warning("slot_fill ask failed for %s: %s — keeping scaffold", file_path, exc)
            break
        filled = _sanitize_emoji_icons(_strip_fences(raw))
        reason, detail = _slot_fill_rejection(filled)
        if not reason:
            content = filled
            break
        retrying = reason != "empty" and attempt < _MAX_SLOT_FILL_ATTEMPTS
        cg_log.warning(
            "slot_fill rejected %s attempt %s/%s (%s%s) — %s",
            file_path,
            attempt,
            _MAX_SLOT_FILL_ATTEMPTS,
            reason,
            f": {detail}" if detail else "",
            "retrying" if retrying else "keeping scaffold",
        )
        if not retrying:
            # An empty answer is how an exhausted AI call budget reports itself;
            # re-asking cannot add information and only burns the retry.
            break
        attempt_prompt = _slot_fill_retry_prompt(prompt, reason=reason, detail=detail)

    content, replaced = enforce_catalogue_page_contract(
        file_path,
        content,
        architect,
        brand_name=brand_name,
    )
    if replaced or "deterministic catalogue contract scaffold" in content:
        # Prefer the known-good scaffold we already wrote over a bad fill.
        if replaced:
            cg_log.warning("slot_fill fell back to scaffold for %s", file_path)
            content = scaffold
            content, _ = enforce_catalogue_page_contract(
                file_path,
                content,
                architect,
                brand_name=brand_name,
            )
        record_stubbed_path(workspace, file_path)
    else:
        clear_stubbed_path(workspace, file_path)

    # Scaffold-like and AI fills both need addressable hooks for AppSpec enforce.
    if page_id:
        content = inject_appspec_contract_hooks(
            content,
            page_id=page_id,
            action_ids=list(merged.get("action_ids") or []),
            evidence_ids=list(merged.get("evidence_ids") or []),
        )

    # Recipe owns public-home section order even after slot-fill rewrites.
    if str(merged.get("skeleton_id") or "") == "public-home":
        content = lock_recipe_section_order(content, merged)

    write_file(workspace, file_path, content)
    return content


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
    # AppSpec contracts must not bypass this — hooks are injected after compose.
    if catalogue_page and should_compose_utility_page(route, skeleton_id, page_plan or {}):
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

    # Scaffold-first: catalogue pages compile from a deterministic template; AI
    # only customizes slot copy (optional). Skips freeform PREVIEW_APP_FILE.
    if catalogue_page and settings.PREVIEW_SCAFFOLD_FIRST:
        return _generate_catalogue_scaffold_first_file(
            workspace,
            file_path,
            file_spec=file_spec,
            route=route or {},
            page_plan=page_plan or {},
            skeleton_id=skeleton_id,
            full_context=full_context,
            plan=plan,
            manifest=manifest,
            architect=architect,
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
    sealed_brief = resolve_design_brief(plan=plan, architect=architect)
    recipe_id = (
        (sealed_brief or {}).get("recipe_id")
        or plan.get("recipe_id")
        or design_system.get("recipe_id")
        or architect.get("recipe_id")
        or ""
    )
    recipe_prompt = (
        (sealed_brief or {}).get("recipe_prompt")
        or design_system.get("recipe_prompt")
        or ""
    )
    hub_variant = (
        (sealed_brief or {}).get("hub_variant")
        or plan.get("hub_variant")
        or design_system.get("hub_variant")
        or architect.get("hub_variant")
        or ""
    )
    design_brief_block = design_brief_prompt_block(sealed_brief)
    brand_brief_block = ""
    if not design_brief_block and design_system.get("brand_locked"):
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
        brand_brief_block=design_brief_block or brand_brief_block,
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
