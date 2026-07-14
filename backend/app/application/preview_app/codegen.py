"""AI codegen for preview React apps."""
from __future__ import annotations

import json
import hashlib
import logging
import re
import shutil
import subprocess
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.parallel import parallel_map
from app.application.preview_app.catalogue_contract import (
    _source_tokens,
    blocking_contract_errors,
    enforce_catalogue_page_contract,
    validate_catalogue_page_content,
)
from app.application.preview_app.utility_compositor import (
    compose_utility_page_tsx,
    default_utility_content,
    infer_utility_workspace_type,
    is_utility_catalogue_route,
    normalize_utility_content,
)
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    is_stubbed_path,
    record_stubbed_path,
)
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    restore_template_owned_files,
    safe_source_path,
    snapshot_template_owned_files,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.shared.json_utils import extract_json_from_text
from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    summarize_files,
    write_file,
)
from app.application.preview_app.safety import (
    _collect_mock_imports,
    fix_unescaped_apostrophes,
    looks_truncated_source,
)
from app.application.services.page_experience import page_required_sections
from app.application.ui_catalogue import (
    compact_catalogue_plan_contract,
    compact_skeleton_contract,
    infer_section_slots,
)

logger = logging.getLogger(__name__)


def page_plan_for_file(file_path: str, plan: dict, architect: dict) -> dict:
    """Find the experience-plan page spec for a generated file path."""
    norm = file_path.replace("\\", "/").lower()
    pages_by_key: dict[tuple[str, str], dict] = {}
    pages_by_id: dict[str, list[dict]] = {}
    for role in plan.get("roles") or []:
        role_id = str(role.get("id") or "")
        for page in role.get("pages") or []:
            page_id = str(page.get("id") or "")
            if not page_id:
                continue
            enriched = {
                **page,
                "role_id": role_id,
                "role_label": role.get("label"),
            }
            pages_by_key[(role_id, page_id)] = enriched
            pages_by_id.setdefault(page_id, []).append(enriched)

    for rt in architect.get("routes") or []:
        cf = (rt.get("component_file") or "").replace("\\", "/").lower()
        if cf and cf == norm:
            page_id = str(rt.get("page_id") or "")
            role_id = str(rt.get("role_id") or "")
            page = pages_by_key.get((role_id, page_id))
            if not page and len(pages_by_id.get(page_id, [])) == 1:
                page = pages_by_id[page_id][0]
            if page:
                return {**page, "route_path": rt.get("path")}
            return {
                "title": rt.get("title"),
                "purpose": rt.get("purpose"),
                "features_to_showcase": rt.get("features") or [],
                "role_id": rt.get("role_id"),
                "route_path": rt.get("path"),
            }
    normalized_path = norm.replace("-", "").replace("_", "")
    candidates: list[dict] = []
    for page_id, matches in pages_by_id.items():
        normalized_id = page_id.replace("-", "").replace("_", "")
        if len(matches) == 1 and normalized_id and normalized_id in normalized_path:
            candidates.append(matches[0])
    if len(candidates) == 1:
        return candidates[0]
    return {}

_FENCE_RE = re.compile(r"^```(?:tsx?|typescript|javascript|css)?\s*\n?", re.MULTILINE)
_EMOJI_ICON_RE = re.compile(r"icon:\s*['\"]([^'\"]+)['\"]")
_EMOJI_TO_KEY = {
    "📋": "clipboard",
    "📊": "chart",
    "🎯": "target",
    "⏱": "clock",
    "⏱️": "clock",
    "👥": "users",
    "✨": "zap",
    "🔔": "bell",
    "📅": "calendar",
    "✅": "check",
    "🔍": "search",
    "🛡": "shield",
    "🛡️": "shield",
}


def _sanitize_emoji_icons(content: str) -> str:
    """Replace emoji icon literals with UiIcon string keys."""
    def _repl(match: re.Match[str]) -> str:
        val = match.group(1)
        for emoji, key in _EMOJI_TO_KEY.items():
            if emoji in val:
                return f"icon: '{key}'"
        return match.group(0)

    return _EMOJI_ICON_RE.sub(_repl, content)


def _strip_fences(text: str) -> str:
    raw = text.strip()
    # Model sometimes prefixes markdown with prose — extract the first fenced block
    fence_match = re.search(
        r"```(?:tsx?|typescript|javascript|css)?\s*\n([\s\S]*?)\n```",
        raw,
    )
    if fence_match:
        return fence_match.group(1).strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[^\n]*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


def _parse_json(raw: str) -> dict:
    if not raw or not raw.strip():
        raise ValueError("Empty response from model")
    try:
        return extract_json_from_text(raw)
    except Exception as first:
        # Second chance: single fence strip + loads (clearer than bare Expecting value).
        from app.shared.json_utils import _strip_markdown_fence_once

        try:
            return json.loads(_strip_markdown_fence_once(raw))
        except Exception:
            raise ValueError(f"Could not parse model JSON: {first}") from first


def _normalize_critic_result(value, *, threshold: int) -> dict:
    """Validate critic JSON without turning parser failure into rewrite instructions."""
    failure = {
        "score": None,
        "verdict": "unavailable",
        "issues": ["Critic response unavailable or malformed; preserve current page."],
        "revision_instructions": "",
        "preserve": True,
    }
    if not isinstance(value, dict):
        return failure

    required = {"score", "verdict", "issues", "revision_instructions"}
    if not required.issubset(value):
        return failure
    score = value.get("score")
    verdict = value.get("verdict")
    issues = value.get("issues")
    instructions = value.get("revision_instructions")
    if (
        isinstance(score, bool)
        or not isinstance(score, (int, float))
        or not 0 <= score <= 100
        or verdict not in {"pass", "revise"}
        or not isinstance(issues, list)
        or not all(isinstance(issue, str) for issue in issues)
        or not isinstance(instructions, str)
    ):
        return failure

    normalized_issues = [issue.strip() for issue in issues if issue.strip()]
    normalized_score = int(score)
    normalized_verdict = verdict
    normalized_instructions = instructions.strip()

    inconsistent_pass = (
        normalized_verdict == "pass"
        and (
            normalized_score < threshold
            or bool(normalized_issues)
            or bool(normalized_instructions)
        )
    )
    if inconsistent_pass:
        normalized_verdict = "revise"
        if not normalized_issues:
            normalized_issues.append(
                f"Critic score is below the required {threshold} pass threshold."
            )

    if normalized_verdict == "revise" and normalized_score >= threshold:
        normalized_score = threshold - 1
    if normalized_verdict == "revise":
        if not normalized_issues:
            normalized_issues.append("Critic requested revision without identifying an issue.")
        if not normalized_instructions:
            normalized_instructions = "; ".join(normalized_issues)

    return {
        "score": normalized_score,
        "verdict": normalized_verdict,
        "issues": normalized_issues,
        "revision_instructions": normalized_instructions,
    }


def call_architect(
    full_context: str,
    plan: dict,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_ARCHITECT,
        full_context=full_context[:12000],
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:14000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        catalogue_contract_json=_bounded_json(compact_catalogue_plan_contract(), 8000),
    )
    for model in (settings.ARCHITECT_MODEL, settings.PREVIEW_APP_MODEL, settings.TEXT_MODEL):
        try:
            raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
            return _parse_json(raw)
        except Exception:
            continue
    raise ValueError("Architect agent failed to produce valid JSON")


# index.css only ever defines --color-brand and --color-brand-dark (see
# write_index_css / _ensure_tailwind_css) — no "primary", "navy", "cream", or
# any other invented color family exists anywhere in the build. The regular
# page-file prompt already constrains pages to real tokens; this was missing
# from the chrome contracts, which let a model invent classes like
# `bg-navy-800` that silently compile to nothing (Tailwind drops unknown
# utility classes instead of erroring) — the build passes, the color is gone.
_COLOR_CONSTRAINT = (
    " COLORS: the only theme color tokens that exist are `brand` and `brand-dark` "
    "(text-brand, bg-brand, bg-brand-dark, border-brand, bg-brand/10, etc.) plus "
    "Tailwind's built-in defaults (slate, gray, white, black, and so on). NEVER invent "
    "a new color family name (no bg-navy-800, text-primary-600, bg-cream-50, etc.) — "
    "those classes do not exist in this build's CSS and will silently render as no "
    "color at all. Vary the LOOK using shade/opacity of brand + slate/gray, spacing, "
    "typography, and shape — not by inventing color tokens that were never defined."
)

_CHROME_CONTRACTS: dict[str, str] = {
    "src/components/nav.tsx": (
        "This is the shared top navigation bar, rendered once by PublicLayout on every "
        "public page. Keep the exact signature: "
        "`export default function Nav({ brandName = 'Brand', items = [], cta }: Props)` "
        "with Props = { brandName?: string; items?: {path,label}[]; cta?: {path,label} }. "
        "Redesign the visual style (spacing, typography, button shape) to fit THIS "
        "brand specifically — do not default to a generic indigo/slate look. "
        "It must feel like a real storefront nav the customer trusts: sticky/clean, "
        "brand name as text logo, clear active-ready links, strong CTA — never 'Demo' "
        "or pitch wording in labels."
        + _COLOR_CONSTRAINT
    ),
    "src/layouts/publiclayout.tsx": (
        "This wraps EVERY public page — it must keep rendering <Outlet /> for page content, "
        "keep importing `brand, navigation` from '../data/mock', and keep rendering "
        "<Nav /> from '../components/Nav'. You control the footer content/structure and "
        "overall shell styling — make it specific to this business, not a generic template. "
        "CRITICAL: do NOT wrap <Outlet /> in heavy vertical padding that kills full-bleed "
        "heroes — let pages own their spacing. Footer must feel real (hours, address, "
        "phone-style contact lines from brand context) — not a one-line copyright stub."
        + _COLOR_CONSTRAINT
    ),
    "src/layouts/adminlayout.tsx": (
        "This wraps EVERY admin page — it must keep rendering <Outlet /> for page content and "
        "keep importing `brand, navigation` from '../data/mock'. NEVER hardcode a business "
        "type in any label (do not assume 'Studio', 'Restaurant', 'Clinic', etc.) — use "
        "`brand.name` and neutral wording like 'Admin' or 'Dashboard'. You control the "
        "sidebar/header styling — make it specific to this business. Feel like a real ops "
        "console: sidebar with clear sections, subtle active state, compact header with "
        "today's date or 'Live' status — not a marketing shell."
        + _COLOR_CONSTRAINT
    ),
    "src/components/uiicons.tsx": (
        "This is the shared icon set used everywhere via `<UiIcon name=\"...\" />`. Keep "
        "exporting a default `UiIcon` component that accepts a `name` prop and supports at "
        "least these keys: clipboard, chart, target, clock, users, zap, shield, bell, "
        "calendar, check, search, cart, brain, coffee, arrowRight. Design a bespoke stroke "
        "style (weight, corner rounding) that fits this brand rather than a generic outline "
        "set — but every icon must share the same stroke weight/rounding as each other. "
        "Unknown names must fall back to a simple circle/dot SVG — never crash."
        + _COLOR_CONSTRAINT
    ),
}


def _route_for_file(file_path: str, architect: dict) -> dict:
    norm = (file_path or "").replace("\\", "/").lower()
    for route in architect.get("routes") or []:
        component_file = (route.get("component_file") or "").replace("\\", "/").lower()
        if component_file == norm:
            return route
    return {}


def _catalogue_routes_context(architect: dict) -> str:
    routes = []
    for route in architect.get("routes") or []:
        skeleton_id = route.get("skeleton_id")
        if not skeleton_id:
            continue
        slots = infer_section_slots(route, skeleton_id)
        routes.append({
            "path": route.get("path"),
            "component_file": route.get("component_file"),
            "surface": route.get("surface"),
            "skeleton_id": skeleton_id,
            "contract": compact_skeleton_contract(skeleton_id, slots),
        })
    return _bounded_json(routes, 10000)


def _bounded_json(value, max_chars: int) -> str:
    """Serialize as valid JSON within a hard character budget."""
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(raw) <= max_chars:
        return raw

    def _compact(item, depth: int = 0):
        if isinstance(item, str):
            return item[:500]
        if isinstance(item, list):
            return [_compact(child, depth + 1) for child in item[:12]]
        if isinstance(item, dict):
            return {
                str(key): _compact(child, depth + 1)
                for key, child in item.items()
            }
        return item

    compact = json.dumps(_compact(value), ensure_ascii=False, separators=(",", ":"))
    if len(compact) <= max_chars:
        return compact

    low, high = 0, len(compact)
    best = json.dumps({"truncated": True, "preview": ""}, separators=(",", ":"))
    while low <= high:
        middle = (low + high) // 2
        candidate = json.dumps(
            {"truncated": True, "preview": compact[:middle]},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(candidate) <= max_chars:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _architect_prompt_context(architect: dict) -> str:
    """Serialize bounded architecture context without repeated file instructions."""
    context = {
        key: architect.get(key)
        for key in ("app_name", "design_direction")
        if architect.get(key) is not None
    }
    context["roles"] = [
        {
            key: role.get(key)
            for key in ("id", "label", "defaultPath", "route_prefix", "icon")
            if role.get(key) is not None
        }
        for role in architect.get("roles") or []
    ]
    context["routes"] = [
        {
            key: route.get(key)
            for key in (
                "path",
                "page_id",
                "role_id",
                "title",
                "component_file",
                "layout",
                "surface",
                "skeleton_id",
            )
            if route.get(key) is not None
        }
        for route in architect.get("routes") or []
    ]
    context["shared_components"] = [
        {
            key: component.get(key)
            for key in ("path", "kind")
            if component.get(key) is not None
        }
        for component in architect.get("shared_components") or []
    ]
    return _bounded_json(context, 8000)


def _catalogue_contract_errors(
    file_path: str,
    content: str,
    route: dict,
) -> list[str]:
    if not route.get("skeleton_id"):
        return []
    errors = validate_catalogue_page_content(content, route)
    if errors:
        logger.warning(
            "Catalogue page contract rejected path=%s errors=%s",
            file_path,
            errors,
        )
    return errors


def _catalogue_retry_context(
    *,
    errors: list[str],
    contract_json: str,
    rejected_source: str,
    build_context: str = "",
) -> str:
    source = (rejected_source or "").strip()
    if len(source) <= 3600:
        excerpt = source
    else:
        regions = [f"[HEAD]\n{source[:1000]}"]
        relevant_index = -1
        for error in errors:
            candidates = [error]
            if error.startswith("slot:"):
                candidates.insert(0, error.split(":", 1)[1])
            candidates.extend(["const slots", "SkeletonComposer", "SKELETON_ID"])
            for candidate in candidates:
                relevant_index = source.lower().find(candidate.lower())
                if relevant_index >= 0:
                    break
            if relevant_index >= 0:
                break
        if relevant_index >= 0:
            start = max(0, relevant_index - 700)
            regions.append(f"[RELEVANT]\n{source[start:start + 1600]}")
        regions.append(f"[TAIL]\n{source[-1000:]}")
        excerpt = "\n".join(regions)
    build_section = (
        f"Available build context:\n{build_context[:1200]}\n"
        if build_context
        else ""
    )
    return (
        "CATALOGUE CONTRACT RETRY. The previous complete source was rejected.\n"
        f"Exact validator errors: {json.dumps(errors, ensure_ascii=False)}\n"
        f"Assigned compact contract: {contract_json}\n"
        f"{build_section}"
        "Rejected source excerpt (repair these issues; do not copy invalid structure):\n"
        f"{excerpt}\n"
        "Return the complete corrected file only, with no markdown fences."
    )


def _brand_name_from_manifest(manifest: dict) -> str:
    brand = manifest.get("brand")
    if isinstance(brand, dict) and brand.get("name"):
        return str(brand["name"])
    if manifest.get("brand_name"):
        return str(manifest["brand_name"])
    return "Brand"


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
    print(
        f"    compose_utility {file_path} type={workspace_type} model={settings.PREVIEW_APP_MODEL}",
        flush=True,
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
            print(f"    utility JSON not an object for {file_path}; using defaults", flush=True)
    except Exception as exc:
        print(f"    utility content ask failed for {file_path}: {exc}; using defaults", flush=True)

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
        print(f"    utility compose re-emit defaults for {file_path}", flush=True)
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
    route = _route_for_file(file_path, architect)
    skeleton_id = str(route.get("skeleton_id") or page_plan.get("skeleton_id") or "")
    catalogue_page = file_kind == "page" and bool(skeleton_id)

    # Contract compositor: utility pages never go through freeform React codegen.
    if catalogue_page and is_utility_catalogue_route(route, skeleton_id):
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
    # Avoid re-reading the whole tree on every parallel worker (was slow + racy).
    existing = ""
    try:
        existing = summarize_files(workspace, list_source_files(workspace))
    except Exception as exc:
        print(f"    summarize_files skip for {file_path}: {exc}", flush=True)

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FILE,
        full_context=full_context[:10000],
        architect_json=_architect_prompt_context(architect),
        design_system_json=json.dumps(design_system, ensure_ascii=False, indent=2),
        recipe_id=recipe_id,
        recipe_prompt=recipe_prompt,
        hub_variant=hub_variant,
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_path=file_path,
        file_kind=file_kind,
        file_instructions=instructions,
        page_plan_json=page_plan_json,
        catalogue_page=catalogue_page,
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
        shell_component=shell_component,
        existing_files_summary=existing[:8000],
    )

    print(f"    ask_chat {file_path} model={settings.PREVIEW_APP_MODEL}", flush=True)
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
            _catalogue_contract_errors(file_path, content, route)
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
        print(f"    regen {file_path} attempt {attempt}/2 ({reason})", flush=True)
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
            _catalogue_contract_errors(file_path, retry_content, route)
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
        _catalogue_contract_errors(file_path, content, route)
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
        print(f"    catalogue contract scaffolded {file_path}", flush=True)
        record_stubbed_path(workspace, file_path)
    elif catalogue_page:
        if "deterministic catalogue contract scaffold" in content:
            record_stubbed_path(workspace, file_path)
        else:
            clear_stubbed_path(workspace, file_path)
    write_file(workspace, file_path, content)
    return content


def mock_needs_enrichment(content: str) -> bool:
    if not content or len(content) < 1800:
        return True
    if re.search(r"//\s*(Additional|more items|etc)", content, re.I):
        return True
    if "export const brand" not in content or "export const roles" not in content:
        return True
    return False


_MAX_SYNTHESIZED_MOCK_BYTES = 256_000
_TYPESCRIPT_MOCK_VALIDATOR = r"""
const ts = require(process.argv[1]);
const needed = new Set(JSON.parse(process.argv[2]));
let source = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { source += chunk; });
process.stdin.on("end", () => {
  const file = ts.createSourceFile(
    "mock.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TS,
  );
  if (file.parseDiagnostics.length) process.exit(2);

  const locals = new Set();
  const exported = new Set();
  const bindingNames = (name, target) => {
    if (ts.isIdentifier(name)) {
      target.add(name.text);
      return;
    }
    for (const element of name.elements || []) {
      if (element && element.name) bindingNames(element.name, target);
    }
  };
  const declarationNames = (statement, target) => {
    if (ts.isVariableStatement(statement)) {
      for (const declaration of statement.declarationList.declarations) {
        bindingNames(declaration.name, target);
      }
    } else if (
      (ts.isFunctionDeclaration(statement)
        || ts.isClassDeclaration(statement)
        || ts.isInterfaceDeclaration(statement)
        || ts.isTypeAliasDeclaration(statement)
        || ts.isEnumDeclaration(statement)
        || ts.isModuleDeclaration(statement))
      && statement.name
      && ts.isIdentifier(statement.name)
    ) {
      target.add(statement.name.text);
    }
  };
  const hasExport = statement =>
    (ts.getCombinedModifierFlags(statement) & ts.ModifierFlags.Export) !== 0;

  for (const statement of file.statements) declarationNames(statement, locals);
  for (const statement of file.statements) {
    if (hasExport(statement)) declarationNames(statement, exported);
    if (
      ts.isExportDeclaration(statement)
      && !statement.moduleSpecifier
      && statement.exportClause
      && ts.isNamedExports(statement.exportClause)
    ) {
      for (const element of statement.exportClause.elements) {
        const localName = (element.propertyName || element.name).text;
        if (locals.has(localName)) exported.add(element.name.text);
      }
    }
  }
  for (const name of needed) {
    if (!exported.has(name)) process.exit(3);
  }
  process.stdout.write("ok");
});
"""


def _typescript_candidate_defines(
    content: str,
    needed: list[str],
) -> bool:
    """Parse candidate TypeScript and verify its locally-defined named exports."""
    encoded = content.encode("utf-8", errors="strict")
    if len(encoded) > _MAX_SYNTHESIZED_MOCK_BYTES:
        return False
    node = shutil.which("node")
    compiler = (
        Path(settings.PREVIEW_TEMPLATE_DIR)
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    if not node or not compiler.is_file():
        return False
    try:
        result = subprocess.run(
            [
                node,
                "-e",
                _TYPESCRIPT_MOCK_VALIDATOR,
                str(compiler.resolve()),
                json.dumps(needed),
            ],
            input=content,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=Path(settings.PREVIEW_TEMPLATE_DIR),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return False
    return result.returncode == 0 and result.stdout == "ok"


def _valid_synthesized_mock_source(content: str, needed: list[str]) -> bool:
    """Fail closed unless a safe candidate parses and defines every needed export."""
    if not content.strip() or looks_truncated_source(content):
        return False
    tokens = _source_tokens(content)
    if not tokens:
        return False
    for index, token in enumerate(tokens):
        if token == "require":
            return False
        if token == "import" and index + 1 < len(tokens):
            if tokens[index + 1] == "(":
                return False
            if (
                index + 2 < len(tokens)
                and re.match(r"^[A-Za-z_$][\w$]*$", tokens[index + 1])
                and tokens[index + 2] == "="
            ):
                return False
            if (
                tokens[index + 1].startswith("\0http://")
                or tokens[index + 1].startswith("\0https://")
            ):
                return False
        if (
            token == "from"
            and index + 1 < len(tokens)
            and tokens[index + 1].startswith(("\0http://", "\0https://"))
        ):
            return False
    return _typescript_candidate_defines(content, needed)


def synthesize_mock_data(
    workspace: Path,
    full_context: str,
    plan: dict,
    manifest: dict,
    images: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> bool:
    """After pages exist: AI writes mock.ts exporting ONLY what pages import."""
    mock_path = "src/data/mock.ts"
    needed = sorted(_collect_mock_imports(workspace))
    if not needed:
        return False

    snippets: list[str] = []
    for rel in list_source_files(workspace):
        if rel.endswith((".tsx", ".ts")) and "data/mock" not in rel:
            body = read_file(workspace, rel)
            if "data/mock" in body or "from '../data/mock" in body or 'from "../data/mock' in body:
                snippets.append(f"=== {rel} ===\n{body[:4000]}")
    import_context = "\n\n".join(snippets[:12])[:24000]

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_MOCK_SYNTHESIZE,
        full_context=full_context[:10000],
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:12000],
        routes_json=json.dumps(architect.get("routes", []), ensure_ascii=False, indent=2)[:4000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        required_exports=", ".join(needed),
        import_context=import_context,
        current_content=read_file(workspace, mock_path)[:4000],
    )
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=14000)
    content, _ = fix_unescaped_apostrophes(_strip_fences(raw))
    if not _valid_synthesized_mock_source(content, needed):
        return False
    write_file(workspace, mock_path, content)
    return True


def enrich_mock_if_sparse(
    workspace: Path,
    full_context: str,
    manifest: dict,
    images: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    plan: dict | None = None,
) -> bool:
    """Backward-compatible alias — always synthesize from page imports after codegen."""
    return synthesize_mock_data(
        workspace, full_context, plan or {}, manifest, images, architect, ai_provider, template_renderer,
    )


def fix_build_errors(
    workspace: Path,
    build_log: str,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    max_files: int = 16,
) -> list[str]:
    from app.application.preview_app.fallback import scan_and_repair_double_brace_literals

    paths = [
        path
        for path in list_source_files(workspace)
        if not is_template_owned_path(path, architect)
    ]
    # Prioritise files explicitly named in the build errors, then App/pages/mock.
    errored = [p for p in paths if p.split("/")[-1] in build_log or p in build_log]

    def _rank(p: str) -> tuple:
        return (
            0 if p in errored else 1,
            0 if "App.tsx" in p else 1 if "/pages/" in p else 2 if "mock.ts" in p else 3,
            p,
        )

    priority = sorted(paths, key=_rank)[:max_files]

    files_content = "\n\n".join(
        f"=== {p} ===\n{read_file(workspace, p)[:6000]}" for p in priority
    )
    file_tree = "\n".join(sorted(paths))

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FIX,
        build_errors=build_log[:7000],
        file_tree=file_tree[:4000],
        architect_json=_architect_prompt_context(architect),
        files_content=files_content[:40000],
        catalogue_mode=has_catalogue_routes(architect),
        catalogue_routes_json=_catalogue_routes_context(architect),
    )

    def _ask(prompt_text: str) -> str:
        for model in (settings.FIX_MODEL, settings.PREVIEW_APP_MODEL, settings.TEXT_MODEL):
            try:
                raw = ai_provider.ask_chat(
                    model, [{"role": "user", "content": prompt_text}], max_tokens=16000,
                )
            except Exception as e:
                print(f"    fix agent model {model} failed: {e}", flush=True)
                continue
            if raw and str(raw).strip():
                return str(raw)
        return ""

    def _try_parse(raw: str, label: str) -> dict | None:
        if not raw or not raw.strip():
            print(f"    fix agent {label}: empty response", flush=True)
            return None
        try:
            parsed = _parse_json(raw)
            if isinstance(parsed, dict):
                return parsed
            print(f"    fix agent {label}: JSON was {type(parsed).__name__}, expected object", flush=True)
            return None
        except Exception as e:
            print(f"    fix agent {label} JSON parse failed: {e}", flush=True)
            digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
            print(
                f"    fix agent {label} response metadata: "
                f"length={len(raw)} sha256={digest}",
                flush=True,
            )
            return None

    raw = _ask(prompt)
    data = _try_parse(raw, "primary")

    if data is None:
        strict_prompt = (
            prompt
            + "\n\nSTRICT SCHEMA RETRY: Respond with ONLY a JSON object of shape "
            '{"files":[{"path":"src/pages/Example.tsx","content":"...full file..."}]}. '
            "No markdown fences, no prose, no empty body."
        )
        raw2 = _ask(strict_prompt)
        data = _try_parse(raw2, "strict-retry")

    def _deterministic_local_repair() -> list[str]:
        from app.application.preview_app.safety import (
            ensure_named_ui_icon_exports,
            ensure_ui_icon_coverage,
            ensure_ui_icons,
            normalize_ui_icon_imports,
            strip_forbidden_npm_imports,
        )

        repaired: list[str] = []
        protected_snapshot = snapshot_template_owned_files(workspace, architect)
        try:
            try:
                repaired.extend(
                    scan_and_repair_double_brace_literals(
                        workspace,
                        architect=architect,
                    )
                )
            except ValueError as e:
                print(f"    double-brace deterministic repair failed: {e}", flush=True)
            try:
                repaired.extend(strip_forbidden_npm_imports(workspace))
            except Exception as e:
                print(f"    npm-import deterministic repair failed: {e}", flush=True)
            if not has_catalogue_routes(architect):
                try:
                    if ensure_ui_icons(workspace):
                        repaired.append("src/components/UiIcons.tsx")
                    repaired.extend(normalize_ui_icon_imports(workspace))
                    repaired.extend(ensure_named_ui_icon_exports(workspace))
                    repaired.extend(ensure_ui_icon_coverage(workspace))
                except Exception as e:
                    print(f"    icon deterministic repair failed: {e}", flush=True)
        finally:
            restore_template_owned_files(workspace, architect, protected_snapshot)
        repaired = [
            path for path in repaired
            if not is_template_owned_path(path, architect)
        ]
        return list(dict.fromkeys(repaired))

    def _enforce_all_catalogue_pages(paths: list[str]) -> list[str]:
        enforced = list(paths)
        for route in architect.get("routes") or []:
            path = safe_source_path(route.get("component_file") or "", workspace)
            if not path or not route.get("skeleton_id"):
                continue
            current = read_file(workspace, path)
            guarded, replaced = enforce_catalogue_page_contract(path, current, architect)
            if replaced:
                write_file(workspace, path, guarded)
                record_stubbed_path(workspace, path)
                if path not in enforced:
                    enforced.append(path)
            elif "deterministic catalogue contract scaffold" in guarded:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)
        return enforced

    if data is None:
        repaired = _enforce_all_catalogue_pages(_deterministic_local_repair())
        print(
            f"    fix agent fell back to deterministic local repair: "
            f"{', '.join(repaired) or 'none'}",
            flush=True,
        )
        return repaired

    fixed_paths: list[str] = []
    protected = {"package.json", "package-lock.json", "App.tsx", "index.css"}
    for item in data.get("files", []):
        path = safe_source_path(item.get("path", ""), workspace)
        content = item.get("content", "")
        if not path or not content:
            continue
        if (
            path.replace("\\", "/").split("/")[-1] in protected
            or is_template_owned_path(path, architect, workspace)
        ):
            continue
        route = _route_for_file(path, architect)
        candidate = _strip_fences(content)
        errors = blocking_contract_errors(
            _catalogue_contract_errors(path, candidate, route)
        )
        if errors:
            contract_json = _bounded_json(
                compact_skeleton_contract(
                    str(route.get("skeleton_id") or ""),
                    infer_section_slots(route, str(route.get("skeleton_id") or "")),
                ),
                5000,
            )
            for retry_number in range(1, 3):
                contract_retry_prompt = (
                    _catalogue_retry_context(
                        errors=errors,
                        contract_json=contract_json,
                        rejected_source=candidate,
                        build_context=build_log,
                    )
                    + "\nRespond as JSON only with shape "
                    '{"files":[{"path":'
                    + json.dumps(path)
                    + ',"content":"...complete corrected file..."}]}.'
                )
                retry_data = _try_parse(
                    _ask(contract_retry_prompt),
                    f"catalogue-contract-retry-{retry_number}",
                )
                if not retry_data:
                    continue
                replacement = next(
                    (
                        value.get("content", "")
                        for value in retry_data.get("files", [])
                        if safe_source_path(value.get("path", ""), workspace) == path
                    ),
                    "",
                )
                if not replacement:
                    continue
                candidate = _strip_fences(replacement)
                errors = blocking_contract_errors(
                    _catalogue_contract_errors(path, candidate, route)
                )
                if not errors:
                    break
        fixed_content, replaced = enforce_catalogue_page_contract(
            path,
            candidate,
            architect,
        )
        write_file(workspace, path, fixed_content)
        if replaced:
            record_stubbed_path(workspace, path)
        elif route.get("skeleton_id"):
            if "deterministic catalogue contract scaffold" in fixed_content:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)
        fixed_paths.append(path)

    # Always scrub known corruption / missing icon exports after AI patches.
    for path in _deterministic_local_repair():
        if path not in fixed_paths:
            fixed_paths.append(path)

    return _enforce_all_catalogue_pages(fixed_paths)


def critique_file(
    workspace: Path,
    file_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
) -> dict:
    """Design-critic agent: score one page and return revision notes."""
    current = read_file(workspace, file_path)
    if is_stubbed_path(workspace, file_path) or "deterministic catalogue contract scaffold" in current:
        return {
            "score": 0,
            "verdict": "revise",
            "issues": ["Page is a deterministic catalogue contract scaffold."],
            "revision_instructions": (
                "Replace the deterministic scaffold with a valid, business-specific "
                "AI-authored implementation of every assigned skeleton slot."
            ),
        }
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    skeleton_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if skeleton_id
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or "Modern, premium, conversion-focused",
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
        current_content=current[:14000],
        catalogue_page=bool(skeleton_id),
        surface=route.get("surface") or "",
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
    )
    raw = ai_provider.ask_chat(settings.CRITIC_MODEL, [{"role": "user", "content": prompt}], max_tokens=2000)
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = None
    normalized = _normalize_critic_result(parsed, threshold=88)
    if normalized.get("verdict") == "unavailable":
        retry_prompt = (
            prompt
            + "\n\nCRITIC JSON RETRY: The prior response was malformed. Return ONLY "
            "the required JSON object. Do not propose a rewrite unless you can provide "
            "specific, evidence-based issues."
        )
        raw_retry = ai_provider.ask_chat(
            settings.CRITIC_MODEL,
            [{"role": "user", "content": retry_prompt}],
            max_tokens=2000,
        )
        try:
            parsed_retry = _parse_json(raw_retry)
        except Exception:
            parsed_retry = None
        normalized = _normalize_critic_result(parsed_retry, threshold=88)
    return normalized


def critique_file_visual(
    workspace: Path,
    file_path: str,
    screenshot_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
) -> dict:
    """Visual-critic agent: score one page from its rendered screenshot.

    Same return shape as `critique_file` so callers can feed the result into
    the same `refine_file` used by the text critic — but this one judges what
    is actually visible on screen (a screenshot), not raw source, so it can
    catch rendering defects (blank icon slots, broken images, empty-looking
    lists, overlap) that a text-only read of the source can never see.
    """
    if is_stubbed_path(workspace, file_path) or (
        "deterministic catalogue contract scaffold" in read_file(workspace, file_path)
    ):
        return {
            "score": 0,
            "verdict": "revise",
            "issues": ["Page is a deterministic catalogue contract scaffold."],
            "revision_instructions": (
                "Replace the deterministic scaffold with a valid, business-specific "
                "AI-authored implementation of every assigned skeleton slot."
            ),
        }
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    skeleton_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if skeleton_id
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_VISUAL_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or "Modern, premium, conversion-focused",
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
        catalogue_page=bool(skeleton_id),
        surface=route.get("surface") or "",
        skeleton_id=skeleton_id,
        skeleton_contract_json=skeleton_contract_json,
    )
    raw = ai_provider.ask_vision(settings.CRITIC_MODEL, prompt, screenshot_path)
    try:
        parsed = _parse_json(raw)
    except Exception:
        parsed = None
    normalized = _normalize_critic_result(parsed, threshold=80)
    if normalized.get("verdict") == "unavailable":
        retry_prompt = (
            prompt
            + "\n\nCRITIC JSON RETRY: The prior response was malformed. Return ONLY "
            "the required JSON object. Preserve the page unless specific visual issues "
            "can be stated in the required schema."
        )
        raw_retry = ai_provider.ask_vision(
            settings.CRITIC_MODEL,
            retry_prompt,
            screenshot_path,
        )
        try:
            parsed_retry = _parse_json(raw_retry)
        except Exception:
            parsed_retry = None
        normalized = _normalize_critic_result(parsed_retry, threshold=80)
    return normalized


def refine_file(
    workspace: Path,
    file_path: str,
    file_instructions: str,
    critic_notes: str,
    full_context: str,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    architect: dict | None = None,
) -> str:
    safe_file_path = safe_source_path(file_path, workspace)
    if not safe_file_path:
        raise ValueError(f"Unsafe generated source path: {file_path}")
    file_path = safe_file_path
    """Rewrite a page to satisfy the critic's notes."""
    current = read_file(workspace, file_path)
    if is_template_owned_path(file_path, architect, workspace):
        return current
    route = _route_for_file(file_path, architect or {})
    skeleton_id = str(route.get("skeleton_id") or "")
    # Composed utility pages are content-JSON driven. Freeform refine would undo
    # the contract and reintroduce invent-React crashes — keep them intact.
    if is_utility_catalogue_route(route, skeleton_id) or "composed public-utility page" in current:
        print(f"    refine skip composed utility page {file_path}", flush=True)
        return current
    catalogue_page = bool(skeleton_id)
    catalogue_contract_json = (
        _bounded_json(
            compact_skeleton_contract(
                skeleton_id,
                infer_section_slots(route, skeleton_id),
            ),
            5000,
        )
        if catalogue_page
        else "{}"
    )
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_REFINE,
        full_context=full_context[:9000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_instructions=file_instructions or "Client-facing product page",
        critic_notes=critic_notes,
        file_path=file_path,
        current_content=current[:14000],
        catalogue_page=catalogue_page,
        skeleton_id=skeleton_id,
        shell_component="OpsShell" if route.get("surface") == "ops" else "PublicShell",
        catalogue_contract_json=catalogue_contract_json,
    )
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=14000)
    content = _strip_fences(raw)
    for attempt in range(1, 3):
        incomplete = looks_truncated_source(content) or not (content or "").strip()
        contract_errors = (
            _catalogue_contract_errors(file_path, content, route)
            if catalogue_page and not incomplete
            else []
        )
        if not incomplete and not blocking_contract_errors(contract_errors):
            break
        retry_prompt = (
            f"{prompt}\n\n"
            + (
                _catalogue_retry_context(
                    errors=contract_errors,
                    contract_json=catalogue_contract_json,
                    rejected_source=content,
                )
                if contract_errors
                else
                "IMPORTANT: Your previous rewrite was CUT OFF or empty. "
                "Return the COMPLETE page file."
            )
        )
        raw2 = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL, [{"role": "user", "content": retry_prompt}], max_tokens=14000,
        )
        retry_content = _strip_fences(raw2)
        if retry_content:
            content = retry_content
    if looks_truncated_source(content) or not (content or "").strip():
        content = current
    if catalogue_page:
        contract_errors = _catalogue_contract_errors(file_path, content, route)
        # A refine that breaks the contract must never cost the user a page
        # that was valid before the critic touched it.
        if (
            blocking_contract_errors(contract_errors)
            and not blocking_contract_errors(
                validate_catalogue_page_content(current, route)
            )
        ):
            print(f"    refine rejected — keeping pre-refine {file_path}", flush=True)
            content = current
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
        print(f"    catalogue contract scaffolded {file_path} after refine", flush=True)
        record_stubbed_path(workspace, file_path)
    elif catalogue_page:
        if "deterministic catalogue contract scaffold" in content:
            record_stubbed_path(workspace, file_path)
        else:
            clear_stubbed_path(workspace, file_path)
    write_file(workspace, file_path, content)
    return content


def critique_and_refine(
    workspace: Path,
    files_to_gen: list[dict],
    full_context: str,
    design_direction: str,
    manifest: dict,
    images: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    on_progress=None,
    max_workers: int | None = None,
    architect: dict | None = None,
) -> list[str]:
    """Run the design-critic on each page; refine any that score below the bar.

    `on_progress(index, total, path)` is called as pages complete.
    When `max_workers` > 1, critique and refine run in parallel batches.
    """
    workers = max_workers if max_workers is not None else settings.PREVIEW_PARALLEL_WORKERS
    specs_by_path = {f.get("path", ""): f for f in files_to_gen}
    pages = [f for f in files_to_gen if f.get("kind") == "page" and f.get("path")]
    total = len(pages)
    if not pages:
        return []

    def _critique_spec(spec: dict) -> tuple[str, dict]:
        path = spec.get("path", "")
        review = critique_file(
            workspace, path, spec.get("instructions", ""), full_context, design_direction,
            ai_provider, template_renderer, architect,
        )
        return path, review

    reviews: dict[str, dict] = {}
    if workers <= 1:
        for i, spec in enumerate(pages, 1):
            path = spec.get("path", "")
            if on_progress:
                try:
                    on_progress(i, total, path)
                except Exception:
                    pass
            try:
                path, review = _critique_spec(spec)
            except Exception as exc:
                print(f"    critic skip {path}: {exc}", flush=True)
                continue
            reviews[path] = review
            score = review.get("score", 100)
            verdict = review.get("verdict", "pass")
            print(f"    critic {path}: {score} ({verdict})", flush=True)
    else:
        def _on_critique_done(done: int, tot: int, spec: dict, result, exc) -> None:
            path = spec.get("path", "")
            if on_progress:
                try:
                    on_progress(done, tot, path)
                except Exception:
                    pass
            if exc:
                print(f"    critic skip {path}: {exc}", flush=True)
            elif result:
                path, review = result
                print(f"    critic {path}: {review.get('score', 100)} ({review.get('verdict', 'pass')})", flush=True)

        for spec, result, exc in parallel_map(
            pages, _critique_spec, max_workers=workers, on_done=_on_critique_done,
        ):
            if result:
                path, review = result
                reviews[path] = review

    to_refine: list[tuple[dict, dict]] = []
    for spec in pages:
        path = spec.get("path", "")
        review = reviews.get(path)
        if not review or review.get("verdict") != "revise":
            continue
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        if notes:
            to_refine.append((spec, review))

    refined: list[str] = []

    def _refine_item(item: tuple[dict, dict]) -> str:
        spec, review = item
        path = spec.get("path", "")
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        refine_file(
            workspace,
            path,
            specs_by_path.get(path, {}).get("instructions", ""),
            notes,
            full_context,
            manifest,
            images,
            ai_provider,
            template_renderer,
            architect,
        )
        return path

    if to_refine:
        if workers <= 1:
            for spec, review in to_refine:
                path = spec.get("path", "")
                try:
                    _refine_item((spec, review))
                    refined.append(path)
                    print(f"    refined {path}", flush=True)
                    if review.get("score", 100) < 55:
                        review2 = critique_file(
                            workspace, path, spec.get("instructions", ""), full_context, design_direction,
                            ai_provider, template_renderer, architect,
                        )
                        if review2.get("verdict") == "revise":
                            notes2 = review2.get("revision_instructions") or "; ".join(review2.get("issues", []))
                            if notes2:
                                print(f"    second pass {path} ({review2.get('score')})", flush=True)
                                refine_file(
                                    workspace, path, spec.get("instructions", ""),
                                    notes2, full_context, manifest, images,
                                    ai_provider, template_renderer, architect,
                                )
                except Exception as e:
                    print(f"    refine FAIL {path}: {e}", flush=True)
        else:
            for item, result, exc in parallel_map(to_refine, _refine_item, max_workers=workers):
                spec, _review = item
                path = spec.get("path", "")
                if exc:
                    print(f"    refine FAIL {path}: {exc}", flush=True)
                    continue
                refined.append(path)
                print(f"    refined {path}", flush=True)

            poor = [(s, r) for s, r in to_refine if r.get("score", 100) < 55]
            if poor:
                def _second_pass(item: tuple[dict, dict]) -> str | None:
                    spec, _ = item
                    path = spec.get("path", "")
                    review2 = critique_file(
                        workspace, path, spec.get("instructions", ""), full_context, design_direction,
                        ai_provider, template_renderer, architect,
                    )
                    if review2.get("verdict") != "revise":
                        return None
                    notes2 = review2.get("revision_instructions") or "; ".join(review2.get("issues", []))
                    if not notes2:
                        return None
                    print(f"    second pass {path} ({review2.get('score')})", flush=True)
                    refine_file(
                        workspace, path, spec.get("instructions", ""),
                        notes2, full_context, manifest, images,
                        ai_provider, template_renderer, architect,
                    )
                    return path

                parallel_map(poor, _second_pass, max_workers=workers)

    return refined
