"""Catalogue helpers and shared codegen utilities."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.application.preview_app.catalogue_contract import validate_catalogue_page_content
from app.application.preview_app.text_utils import _bounded_json, _parse_json, _strip_fences
from app.application.ui_catalogue import compact_skeleton_contract, infer_section_slots
from app.infrastructure.logging import get_logger
from app.infrastructure.logging.diagnostics import dump_catalogue_rejection

cg_log = get_logger("Codegen")

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

def _catalogue_contract_errors(
    file_path: str,
    content: str,
    route: dict,
    *,
    workspace: Path | None = None,
    attempt: int | None = None,
) -> list[str]:
    if not route.get("skeleton_id"):
        return []
    errors = validate_catalogue_page_content(content, route)
    if errors:
        if workspace is not None:
            dump_catalogue_rejection(
                workspace,
                file_path=file_path,
                errors=errors,
                source=content,
                route=route,
                attempt=attempt,
            )
        else:
            cg_log.warning(
                "catalogue contract rejected path=%s errors=%s",
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
    guidance: str = "",
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
    # Request 107 repeated a face violation with the raw validator errors in
    # hand — the errors need translating into edits, so a caller with a
    # translation for its rejection class threads it here. Optional because
    # the fix/critic/refine callers judge different error vocabularies.
    guidance_section = f"How to repair: {guidance}\n" if guidance else ""
    return (
        "CATALOGUE CONTRACT RETRY. The previous complete source was rejected.\n"
        f"Exact validator errors: {json.dumps(errors, ensure_ascii=False)}\n"
        f"{guidance_section}"
        f"Assigned compact contract: {contract_json}\n"
        f"{build_section}"
        "Rejected source excerpt (repair these issues; do not copy invalid structure):\n"
        f"{excerpt}\n"
        "Return the complete corrected file only, with no markdown fences."
    )

def _brand_name_from_manifest(manifest: dict) -> str:
    """The brand a page is written for, or the placeholder every guard knows.

    Reads the manifest through `resolve_preview_brand_name` rather than by hand,
    so the "this is not a name" list is one list. Reading it by hand is how
    request 156's `ServiceBookingPage.tsx` came out addressed to "Business":
    `design_manifest` had put that word in `manifest["brand_name"]` and this
    returned it, while the placeholder filter one module over rejected only
    `Brand`.
    """
    from app.application.preview_app.brand_brief import resolve_preview_brand_name

    return resolve_preview_brand_name(manifest=manifest) or "Brand"
