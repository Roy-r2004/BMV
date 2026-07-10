"""AI codegen for preview React apps."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.application.prompts import PromptTemplate
from app.application.preview_app.parallel import parallel_map
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


def page_plan_for_file(file_path: str, plan: dict, architect: dict) -> dict:
    """Find the experience-plan page spec for a generated file path."""
    norm = file_path.replace("\\", "/").lower()
    for rt in architect.get("routes") or []:
        cf = (rt.get("component_file") or "").replace("\\", "/").lower()
        if cf and cf == norm:
            pid = rt.get("page_id") or ""
            for role in plan.get("roles") or []:
                for page in role.get("pages") or []:
                    if page.get("id") == pid:
                        return {
                            **page,
                            "role_id": role.get("id"),
                            "role_label": role.get("label"),
                            "route_path": rt.get("path"),
                        }
            return {
                "title": rt.get("title"),
                "purpose": rt.get("purpose"),
                "features_to_showcase": rt.get("features") or [],
                "role_id": rt.get("role_id"),
                "route_path": rt.get("path"),
            }
    for role in plan.get("roles") or []:
        for page in role.get("pages") or []:
            pid = (page.get("id") or "").replace("-", "").replace("_", "")
            if pid and pid in norm.replace("-", "").replace("_", ""):
                return {**page, "role_id": role.get("id"), "role_label": role.get("label")}
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
    except Exception:
        return json.loads(raw)


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
    file_path = file_spec.get("path", "")
    file_kind = file_spec.get("kind", "page")
    instructions = file_spec.get("instructions", "")
    page_plan = page_plan_for_file(file_path, plan, architect)
    page_plan_json = json.dumps(page_plan, ensure_ascii=False, indent=2) if page_plan else "{}"
    if page_plan and file_kind == "page":
        required = page_required_sections(page_plan)
        if required:
            instructions += "\n\nRequired sections:\n" + "\n".join(f"- {s}" for s in required)

    chrome_contract = _CHROME_CONTRACTS.get(file_path.replace("\\", "/").lower())
    if chrome_contract:
        instructions = f"{instructions}\n\n{chrome_contract}".strip()

    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    # Avoid re-reading the whole tree on every parallel worker (was slow + racy).
    existing = ""
    try:
        existing = summarize_files(workspace, list_source_files(workspace))
    except Exception as exc:
        print(f"    summarize_files skip for {file_path}: {exc}", flush=True)

    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_FILE,
        full_context=full_context[:10000],
        architect_json=json.dumps(architect, ensure_ascii=False, indent=2)[:8000],
        design_system_json=json.dumps(design_system, ensure_ascii=False, indent=2),
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_path=file_path,
        file_kind=file_kind,
        file_instructions=instructions,
        page_plan_json=page_plan_json[:6000],
        existing_files_summary=existing[:8000],
    )

    print(f"    ask_chat {file_path} model={settings.PREVIEW_APP_MODEL}", flush=True)
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    content = _sanitize_emoji_icons(_strip_fences(raw))
    if looks_truncated_source(content):
        retry_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Your previous answer was CUT OFF mid-line. "
            "Return the COMPLETE file from first import to the final closing brace — no truncation."
        )
        raw2 = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL, [{"role": "user", "content": retry_prompt}], max_tokens=16000,
        )
        retry_content = _sanitize_emoji_icons(_strip_fences(raw2))
        if not looks_truncated_source(retry_content):
            content = retry_content
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
    paths = list_source_files(workspace)
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
        architect_json=json.dumps(architect, ensure_ascii=False, indent=2)[:3000],
        files_content=files_content[:40000],
    )

    raw = ai_provider.ask_chat(settings.FIX_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    if not raw or not raw.strip():
        raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    if not raw or not raw.strip():
        raw = ai_provider.ask_chat(settings.TEXT_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    data = _parse_json(raw)
    fixed_paths: list[str] = []
    protected = {"package.json", "package-lock.json", "App.tsx", "index.css"}
    for item in data.get("files", []):
        path = item.get("path", "")
        content = item.get("content", "")
        if not path or not content:
            continue
        if path.replace("\\", "/").split("/")[-1] in protected:
            continue
        write_file(workspace, path, _strip_fences(content))
        fixed_paths.append(path)
    return fixed_paths


def critique_file(
    workspace: Path,
    file_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Design-critic agent: score one page and return revision notes."""
    current = read_file(workspace, file_path)
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or "Modern, premium, conversion-focused",
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
        current_content=current[:14000],
    )
    raw = ai_provider.ask_chat(settings.CRITIC_MODEL, [{"role": "user", "content": prompt}], max_tokens=2000)
    try:
        return _parse_json(raw)
    except Exception:
        return {"score": 100, "verdict": "pass", "issues": [], "revision_instructions": ""}


def critique_file_visual(
    workspace: Path,
    file_path: str,
    screenshot_path: str,
    file_instructions: str,
    full_context: str,
    design_direction: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Visual-critic agent: score one page from its rendered screenshot.

    Same return shape as `critique_file` so callers can feed the result into
    the same `refine_file` used by the text critic — but this one judges what
    is actually visible on screen (a screenshot), not raw source, so it can
    catch rendering defects (blank icon slots, broken images, empty-looking
    lists, overlap) that a text-only read of the source can never see.
    """
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_VISUAL_CRITIC,
        full_context=full_context[:8000],
        design_direction=design_direction or "Modern, premium, conversion-focused",
        file_instructions=file_instructions or "Client-facing product page",
        file_path=file_path,
    )
    raw = ai_provider.ask_vision(settings.CRITIC_MODEL, prompt, screenshot_path)
    try:
        return _parse_json(raw)
    except Exception:
        return {"score": 100, "verdict": "pass", "issues": [], "revision_instructions": ""}


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
) -> str:
    """Rewrite a page to satisfy the critic's notes."""
    current = read_file(workspace, file_path)
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_REFINE,
        full_context=full_context[:9000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        file_instructions=file_instructions or "Client-facing product page",
        critic_notes=critic_notes,
        file_path=file_path,
        current_content=current[:14000],
    )
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=14000)
    content = _strip_fences(raw)
    if looks_truncated_source(content):
        retry_prompt = (
            f"{prompt}\n\n"
            "IMPORTANT: Your previous rewrite was CUT OFF. Return the COMPLETE page file."
        )
        raw2 = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL, [{"role": "user", "content": retry_prompt}], max_tokens=14000,
        )
        retry_content = _strip_fences(raw2)
        if not looks_truncated_source(retry_content):
            content = retry_content
        else:
            content = current
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
            ai_provider, template_renderer,
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
                            ai_provider, template_renderer,
                        )
                        if review2.get("verdict") == "revise":
                            notes2 = review2.get("revision_instructions") or "; ".join(review2.get("issues", []))
                            if notes2:
                                print(f"    second pass {path} ({review2.get('score')})", flush=True)
                                refine_file(
                                    workspace, path, spec.get("instructions", ""),
                                    notes2, full_context, manifest, images,
                                    ai_provider, template_renderer,
                                )
                except Exception as e:
                    print(f"    refine FAIL {path}: {e}", flush=True)
        else:
            for spec, result, exc in parallel_map(to_refine, _refine_item, max_workers=workers):
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
                        ai_provider, template_renderer,
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
                        ai_provider, template_renderer,
                    )
                    return path

                parallel_map(poor, _second_pass, max_workers=workers)

    return refined
