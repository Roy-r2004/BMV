"""AI codegen for preview React apps."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.application.prompts import PromptTemplate
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
    for model in (settings.PREVIEW_APP_MODEL, settings.TEXT_MODEL):
        try:
            raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
            return _parse_json(raw)
        except Exception:
            continue
    raise ValueError("Architect agent failed to produce valid JSON")


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

    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    existing = summarize_files(workspace, list_source_files(workspace))

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
        existing_files_summary=existing[:8000],
    )

    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=16000)
    content = _sanitize_emoji_icons(_strip_fences(raw))
    write_file(workspace, file_path, content)
    return content


def mock_needs_enrichment(content: str) -> bool:
    if not content or len(content) < 2200:
        return True
    if re.search(r"//\s*(Additional|more items|etc)", content, re.I):
        return True
    for name, minimum in (("services", 6), ("testimonials", 6), ("appointments", 8), ("clients", 6)):
        block = re.search(rf"export const {name}\s*=\s*\[([\s\S]*?)\];", content)
        if not block or block.group(1).count("{") < minimum:
            return True
    return False


def enrich_mock_if_sparse(
    workspace: Path,
    full_context: str,
    manifest: dict,
    images: dict,
    architect: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> bool:
    mock_path = "src/data/mock.ts"
    current = read_file(workspace, mock_path)
    if not mock_needs_enrichment(current):
        return False
    prompt = template_renderer.render(
        PromptTemplate.PREVIEW_APP_MOCK_ENRICH,
        full_context=full_context[:10000],
        manifest_json=json.dumps(manifest, ensure_ascii=False, indent=2),
        images_json=json.dumps(images, ensure_ascii=False, indent=2),
        routes_json=json.dumps(architect.get("routes", []), ensure_ascii=False, indent=2)[:4000],
        current_content=current[:8000],
    )
    raw = ai_provider.ask_chat(settings.PREVIEW_APP_MODEL, [{"role": "user", "content": prompt}], max_tokens=12000)
    write_file(workspace, mock_path, _strip_fences(raw))
    return True


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
    protected = {"package.json", "package-lock.json", "mock.ts", "App.tsx", "index.css"}
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
) -> list[str]:
    """Run the design-critic on each page; refine any that score below the bar."""
    refined: list[str] = []
    specs_by_path = {f.get("path", ""): f for f in files_to_gen}
    for spec in files_to_gen:
        if spec.get("kind") != "page":
            continue
        path = spec.get("path", "")
        if not path:
            continue
        try:
            review = critique_file(
                workspace, path, spec.get("instructions", ""), full_context, design_direction,
                ai_provider, template_renderer,
            )
        except Exception as e:
            print(f"    critic skip {path}: {e}", flush=True)
            continue
        score = review.get("score", 100)
        verdict = review.get("verdict", "pass")
        print(f"    critic {path}: {score} ({verdict})", flush=True)
        if verdict != "revise":
            continue
        notes = review.get("revision_instructions") or "; ".join(review.get("issues", []))
        if not notes:
            continue
        try:
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
            refined.append(path)
            print(f"    refined {path}", flush=True)
            # 2nd pass only for critically poor pages (score < 55) to save cost
            if score < 55:
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
    return refined
