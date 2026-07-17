"""Apply one chat-refinement AI payload onto the workspace: files and routes."""
from __future__ import annotations

import json

from app.application.preview_app.catalogue_contract import (
    catalogue_route_for_file,
    enforce_catalogue_page_contract,
    validate_catalogue_page_content,
)
from app.application.preview_app.codegen.shared import _catalogue_retry_context
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    record_stubbed_path,
)
from app.application.preview_app.protected_paths import (
    is_template_owned_path,
    safe_generated_route_path,
    safe_source_path,
)
from app.application.preview_app.source_quality import looks_truncated_source
from app.application.preview_app.text_utils import _strip_fences
from app.application.preview_app.workspace import read_file, write_file
from app.application.ui_catalogue import (
    compact_skeleton_contract,
    get_skeleton,
    infer_page_contract,
    infer_section_slots,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.shared.json_utils import extract_json_from_text


def _architect_from_generated(generated_pages: dict, experience_plan: dict) -> dict:
    from app.application.preview_app.assemble import architect_from_stored
    return architect_from_stored(generated_pages, experience_plan)


def _apply_chat_file_updates(
    workspace,
    data: dict,
    architect: dict,
    *,
    ai_provider: AIProvider | None = None,
    chat_prompt: str = "",
) -> list[str]:
    changes: list[str] = []
    for item in data.get("files", []):
        path = item.get("path", "")
        content = item.get("content", "")
        if not path or not content:
            continue
        safe_path = safe_source_path(path, workspace)
        if not safe_path:
            changes.append(f"Skipped unsafe path {path}")
            continue
        if is_template_owned_path(safe_path, architect, workspace):
            changes.append(f"Skipped template-owned file {safe_path}")
            continue
        cleaned = _strip_fences(content)
        if looks_truncated_source(cleaned):
            changes.append(f"Skipped truncated write to {safe_path} (kept existing file)")
            continue
        route = catalogue_route_for_file(safe_path, architect)
        errors = validate_catalogue_page_content(cleaned, route)
        if errors and ai_provider is not None:
            contract_json = json.dumps(
                compact_skeleton_contract(
                    str(route.get("skeleton_id") or ""),
                    infer_section_slots(route, str(route.get("skeleton_id") or "")),
                ),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for _attempt in range(2):
                retry_prompt = (
                    f"{chat_prompt}\n\n"
                    + _catalogue_retry_context(
                        errors=errors,
                        contract_json=contract_json,
                        rejected_source=cleaned,
                    )
                    + "\nReturn ONLY JSON with shape "
                    '{"files":[{"path":'
                    + json.dumps(safe_path)
                    + ',"content":"...complete corrected file..."}]}.'
                )
                retry_raw = ai_provider.ask_chat(
                    settings.PREVIEW_APP_MODEL,
                    [{"role": "user", "content": retry_prompt}],
                    max_tokens=16000,
                )
                try:
                    retry_data = extract_json_from_text(retry_raw)
                except Exception:
                    continue
                replacement = next(
                    (
                        candidate.get("content", "")
                        for candidate in retry_data.get("files", [])
                        if safe_source_path(candidate.get("path", ""), workspace) == safe_path
                    ),
                    "",
                )
                if not replacement:
                    continue
                cleaned = _strip_fences(replacement)
                errors = validate_catalogue_page_content(cleaned, route)
                if not errors:
                    break
        cleaned, replaced = enforce_catalogue_page_contract(safe_path, cleaned, architect)
        write_file(workspace, safe_path, cleaned)
        if replaced or "deterministic catalogue contract scaffold" in cleaned:
            record_stubbed_path(workspace, safe_path)
        elif route.get("skeleton_id"):
            clear_stubbed_path(workspace, safe_path)
        changes.append(
            f"Updated {safe_path}"
            + (" with catalogue scaffold" if replaced else "")
        )
    return changes


def _catalogue_fallback_paths(workspace, architect: dict) -> list[str]:
    paths: list[str] = []
    for route in architect.get("routes") or []:
        path = (route.get("component_file") or "").replace("\\", "/")
        if not path or not route.get("skeleton_id"):
            continue
        if "deterministic catalogue contract scaffold" in read_file(workspace, path):
            record_stubbed_path(workspace, path)
            paths.append(path)
        else:
            clear_stubbed_path(workspace, path)
    return paths


def _merge_chat_routes(
    existing_routes: list[dict],
    incoming_routes: list[dict],
    plan: dict,
    workspace=None,
) -> list[dict]:
    plan_by_page = {
        (str(role.get("id") or ""), str(page.get("id") or "")): {
            **page,
            "role_id": role.get("id"),
            "role_label": role.get("label"),
        }
        for role in plan.get("roles") or []
        for page in role.get("pages") or []
        if page.get("id")
    }
    merged = [dict(route) for route in existing_routes]
    matched_indexes: set[int] = set()
    route_architect = {
        "routes": existing_routes,
        "_catalogue_workspace": any(
            route.get("skeleton_id") for route in existing_routes
        ),
    }
    for route_data in incoming_routes:
        route_data = dict(route_data)
        if route_data.get("component_file"):
            component_file = safe_generated_route_path(
                route_data["component_file"],
                route_architect,
                workspace,
            )
            if component_file:
                route_data["component_file"] = component_file
            else:
                route_data.pop("component_file", None)
        role_id = str(route_data.get("role_id") or "")
        page_id = str(route_data.get("page_id") or "")
        match_index: int | None = None
        for index, existing in enumerate(existing_routes):
            if index in matched_indexes:
                continue
            if role_id and page_id and (
                str(existing.get("role_id") or ""),
                str(existing.get("page_id") or ""),
            ) == (role_id, page_id):
                match_index = index
                break
            if route_data.get("path") and route_data.get("path") == existing.get("path"):
                match_index = index
                break
            if (
                route_data.get("component_file")
                and route_data.get("component_file") == existing.get("component_file")
            ):
                match_index = index
                break
        previous = existing_routes[match_index] if match_index is not None else {}
        route = {**previous, **route_data}
        key = (
            str(route.get("role_id") or ""),
            str(route.get("page_id") or ""),
        )
        page = plan_by_page.get(key) or {}
        source = {**page, **previous, **route}
        inferred = infer_page_contract(source)
        requested_skeleton = str(route_data.get("skeleton_id") or "")
        try:
            skeleton = get_skeleton(requested_skeleton) if requested_skeleton else get_skeleton(
                str(route.get("skeleton_id") or inferred["skeleton_id"])
            )
        except ValueError:
            route["skeleton_id"] = inferred["skeleton_id"]
            skeleton = get_skeleton(route["skeleton_id"])
        else:
            route["skeleton_id"] = str(skeleton["id"])
        contract_changed = (
            "skeleton_id" in route_data
            or "surface" in route_data
            or not route.get("section_slots")
        )
        route["surface"] = skeleton["surface"]
        if contract_changed:
            slot_source = {**page, **route}
            slot_source.pop("section_slots", None)
            if route_data.get("section_slots"):
                slot_source["section_slots"] = route_data["section_slots"]
            route["section_slots"] = infer_section_slots(
                slot_source,
                route["skeleton_id"],
            )
        route["catalogue_contract"] = compact_skeleton_contract(
            route["skeleton_id"],
            route["section_slots"],
        )
        for field in ("title", "layout", "role_id", "page_id"):
            if not route.get(field) and source.get(field):
                route[field] = source[field]
        if match_index is None:
            merged.append(route)
        else:
            merged[match_index] = route
            matched_indexes.add(match_index)
    return merged


def _request_chat_refinement_payload(
    ai_provider: AIProvider,
    prompt: str,
) -> dict:
    """Request one structured chat patch, retrying malformed transport once."""
    current_prompt = prompt
    last_error: Exception | None = None
    for attempt in range(2):
        raw = ai_provider.ask_chat(
            settings.PREVIEW_APP_MODEL,
            [{"role": "user", "content": current_prompt}],
            max_tokens=16000,
        )
        if not (raw or "").strip():
            last_error = RuntimeError("AI returned an empty response for the chat refinement")
        else:
            try:
                data = extract_json_from_text(raw)
                if isinstance(data, dict):
                    return data
                last_error = RuntimeError(
                    "AI response was not valid JSON for the chat refinement"
                )
            except ValueError as exc:
                last_error = exc
        if attempt == 0:
            current_prompt = (
                f"{prompt}\n\n"
                "The previous response was malformed. Return one valid JSON object only, "
                "matching the requested chat-refinement schema. Do not use markdown fences "
                "or explanatory text."
            )
    raise last_error or RuntimeError("AI chat refinement failed")
