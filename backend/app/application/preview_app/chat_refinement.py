"""Apply chat feedback to an existing preview React workspace and rebuild."""
from __future__ import annotations

import json
import hashlib
import re
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.application.pipelines._shared import business_info, get_request
from app.application.preview_app.assemble import write_app_tsx, write_index_css
from app.application.preview_app.ai_budget import request_mutation_boundary
from app.application.preview_app.app_spec_projection import (
    PreviewScope,
    browser_projection,
    merge_architecture_enrichment,
    merge_experience_plan_enrichment,
    page_contract,
    runtime_projection,
    select_preview_scope,
    to_architecture_seed,
    to_experience_plan_seed,
)
from app.application.preview_app.app_spec_workspace import validate_app_spec_workspace
from app.application.preview_app.build import extract_build_errors, run_build
from app.application.preview_app.codegen import (
    _bounded_json,
    _catalogue_routes_context,
    _catalogue_retry_context,
    _strip_fences,
    fix_build_errors,
)
from app.application.preview_app.catalogue_contract import (
    catalogue_route_for_file,
    enforce_catalogue_page_contract,
    validate_catalogue_page_content,
)
from app.application.preview_app.fallback import (
    clear_stubbed_path,
    consume_stubbed_paths,
    record_stubbed_path,
)
from app.application.preview_app.protected_paths import (
    has_catalogue_routes,
    is_template_owned_path,
    safe_generated_route_path,
    safe_source_path,
)
from app.application.preview_app.pipeline import MAX_BUILD_FIX_ATTEMPTS, generate_preview_app
from app.application.preview_app.safety import (
    apply_workspace_guards,
    ensure_mock_exports,
    looks_truncated_source,
)
from app.application.preview_app.workspace import (
    backup_dist,
    discard_backup,
    get_dist_dir,
    get_workspace,
    list_source_files,
    read_file,
    restore_dist,
    restore_source,
    snapshot_source,
    write_file,
)
from app.application.prompts import PromptTemplate
from app.application.services.industry_images import get_images_for_industry
from app.application.services.app_spec_generation import app_spec_mode
from app.application.services.app_spec_repository import (
    AppSpecRepository,
    load_json_object,
)
from app.application.services.progress import emit as _emit
from app.application.ui_catalogue import (
    compact_skeleton_contract,
    get_skeleton,
    infer_page_contract,
    infer_section_slots,
)
from app.application.services.visual_demo_enrichment import enrich_visual_demo
from app.application.services.visual_demo_merge import merge_visual_demo
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.app_spec import APP_SPEC_STATUS_ACCEPTED, AppSpecRevision
from app.domain.schemas.app_spec import AppSpec
from app.shared.json_utils import extract_json_from_text


_FULL_REDESIGN_RE = re.compile(
    r"\b("
    r"redesign\s+(everything|all|the\s+whole)|"
    r"change\s+all\s+(the\s+)?design|"
    r"completely\s+(new|different)\s+(look|design|ui)|"
    r"start\s+over|"
    r"rebuild\s+(everything|the\s+(whole\s+)?(app|preview))|"
    r"all\s+the\s+pages\s+exist|"
    r"ensure\s+all\s+(the\s+)?pages"
    r")\b",
    re.IGNORECASE,
)


def _is_full_redesign_request(message: str) -> bool:
    """Broad redesigns need a full pipeline regen, not a single chat JSON patch."""
    return bool(_FULL_REDESIGN_RE.search(message or ""))


def _architect_from_generated(generated_pages: dict, experience_plan: dict) -> dict:
    from app.application.preview_app.assemble import architect_from_stored
    return architect_from_stored(generated_pages, experience_plan)


@dataclass(frozen=True)
class AppSpecRefinementContext:
    """Canonical contract and deterministic projections for one refinement."""

    revision: AppSpecRevision
    spec: AppSpec
    scope: PreviewScope
    plan_seed: dict[str, Any]
    plan: dict[str, Any]
    architecture_seed: dict[str, Any]
    architect: dict[str, Any]
    selected_contracts: dict[str, Any]


def _app_spec_ref_is_enforced(generated_pages: Mapping[str, Any]) -> bool:
    """Only required rollout modes turn persisted provenance into a hard gate."""

    return bool(generated_pages.get("app_spec_ref")) and app_spec_mode() in {
        "required_new",
        "required",
    }


def _plan_for_persistence(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Persist enrichment/provenance, never embedded canonical AppSpec slices."""

    persisted = json.loads(json.dumps(dict(plan)))
    for role in persisted.get("roles") or []:
        for page in role.get("pages") or []:
            page.pop("app_spec_contract", None)
    return persisted


def _load_app_spec_refinement_context(
    db: Session,
    request_id: int,
    generated_pages: Mapping[str, Any],
    *,
    experience_plan: Mapping[str, Any] | None = None,
    architect: Mapping[str, Any] | None = None,
) -> AppSpecRefinementContext | None:
    """Resolve an exact accepted same-request AppSpec and rebuild its seeds.

    The provenance reference is treated as a capability: every persisted value
    (row id, revision, schema and digest) must match before refinement can touch
    the workspace. This prevents a stale or cross-request contract from being
    used merely because its JSON happens to parse.
    """

    if not _app_spec_ref_is_enforced(generated_pages):
        return None
    ref = generated_pages.get("app_spec_ref")
    if not isinstance(ref, Mapping):
        raise ValueError("Required AppSpec provenance is malformed.")
    try:
        revision_number = int(ref["revision"])
        revision_id = int(ref["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Required AppSpec provenance is incomplete.") from exc

    row = AppSpecRepository(db).get_revision(request_id, revision_number)
    if (
        row is None
        or row.id != revision_id
        or row.request_id != request_id
        or row.status != APP_SPEC_STATUS_ACCEPTED
        or not row.validation_passed
        or not row.coverage_passed
    ):
        raise ValueError(
            "The preview's AppSpec reference is not an accepted revision for this request."
        )
    if ref.get("schema_version") and ref.get("schema_version") != row.schema_version:
        raise ValueError("The preview's AppSpec schema reference is stale.")
    if ref.get("sha256") and ref.get("sha256") != row.app_spec_sha256:
        raise ValueError("The preview's AppSpec digest does not match its accepted revision.")

    spec = AppSpec.model_validate(load_json_object(row.app_spec_json))
    scope = select_preview_scope(
        spec,
        target_pages=settings.APPSPEC_PREVIEW_TARGET_PAGES,
        max_pages=settings.APPSPEC_PREVIEW_MAX_PAGES,
    )
    plan_seed = to_experience_plan_seed(spec, scope)
    enriched_plan = merge_experience_plan_enrichment(
        plan_seed,
        experience_plan or generated_pages.get("experience_plan") or {},
    )
    architecture_seed = to_architecture_seed(spec, scope)
    stored_architect = architect or _architect_from_generated(
        dict(generated_pages), enriched_plan
    )
    enriched_architect = merge_architecture_enrichment(
        architecture_seed,
        stored_architect,
    )
    selected_contracts = {
        "scope": scope.as_dict(),
        "pages": {
            page_id: page_contract(spec, page_id)
            for page_id in scope.selected_page_ids
        },
        "runtime": runtime_projection(spec, scope),
        "browser": browser_projection(spec, scope),
    }
    return AppSpecRefinementContext(
        revision=row,
        spec=spec,
        scope=scope,
        plan_seed=plan_seed,
        plan=enriched_plan,
        architecture_seed=architecture_seed,
        architect=enriched_architect,
        selected_contracts=selected_contracts,
    )


def _merge_app_spec_refinement_enrichment(
    context: AppSpecRefinementContext,
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Discard semantic AI drift and retain only allow-listed design choices."""

    plan = merge_experience_plan_enrichment(
        context.plan_seed,
        payload.get("experience_plan") or context.plan,
    )
    architect = merge_architecture_enrichment(
        context.architecture_seed,
        payload.get("architect") or context.architect,
    )
    return plan, architect


def _rank_refinement_files(path: str) -> tuple:
    low = path.lower().replace("\\", "/")
    if "app.tsx" in low:
        return (0, path)
    if "/pages/" in low:
        return (1, path)
    if "mock.ts" in low:
        return (2, path)
    if "/layouts/" in low or "/components/" in low:
        return (3, path)
    return (4, path)


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


@request_mutation_boundary
def refine_preview_app_from_chat(
    db: Session,
    request_id: int,
    user_message: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Patch the preview workspace from chat instructions, rebuild, and persist status."""
    req = get_request(db, request_id)
    generated_pages: dict = {}
    if req.generated_pages:
        try:
            generated_pages = json.loads(req.generated_pages)
        except Exception:
            generated_pages = {}
    original_generated_pages = json.loads(json.dumps(generated_pages))
    original_generated_pages_text = req.generated_pages
    metadata_fields = (
        "concept_name",
        "preview_summary",
        "preview_features",
        "business_fit_score",
        "visual_demo_json",
        "visual_demo_generated_at",
        "updated_at",
    )
    original_metadata = {
        field: getattr(req, field, None)
        for field in metadata_fields
    }

    workspace = get_workspace(request_id)
    if not workspace.is_dir():
        raise ValueError("Preview app workspace not found.")

    stored_plan = generated_pages.get("experience_plan") or {}
    stored_architect = _architect_from_generated(generated_pages, stored_plan)
    try:
        app_spec_context = _load_app_spec_refinement_context(
            db,
            request_id,
            generated_pages,
            experience_plan=stored_plan,
            architect=stored_architect,
        )
    except Exception as exc:
        # The public request marked this preview as "rebuilding" before the
        # worker started. Contract resolution happens before any file write, so
        # restore the prior live status immediately and fail closed.
        restored = original_generated_pages
        restored_preview = restored.setdefault("preview_app", {})
        restored_preview["status"] = "ready"
        restored_preview["last_refinement_error"] = str(exc)[:300]
        req.generated_pages = json.dumps(restored)
        db.commit()
        return {
            "reply": (
                "I couldn't safely apply that change because the preview's "
                "product contract could not be verified. The current preview "
                "has been kept unchanged."
            ),
            "changes_made": ["No changes applied — AppSpec verification failed"],
            "preview_rebuild_succeeded": False,
            "reverted": True,
        }

    # Full redesign / "make sure all pages exist" → regenerate the whole app.
    # One-shot chat JSON can't reliably rewrite every file without truncation.
    if _is_full_redesign_request(user_message):
        print(f"[refine] full redesign requested for {request_id} — regenerating preview app", flush=True)
        message_digest = hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:16]
        _emit(
            db,
            request_id,
            "refine",
            "Full redesign — regenerating the live app...",
            10,
            detail=f"message length={len(user_message)} sha256={message_digest}",
        )
        try:
            result = generate_preview_app(
                db,
                request_id,
                ai_provider,
                template_renderer,
                app_spec_revision_id=(
                    app_spec_context.revision.id if app_spec_context else None
                ),
            )
            pa = (result or {}).get("preview_app") or {}
            ok = pa.get("status") == "ready"
            _emit(
                db, request_id,
                "refine_done" if ok else "refine_failed",
                "Live preview redesigned!" if ok else "Redesign finished with build issues",
                100,
            )
            return {
                "reply": (
                    "I've fully redesigned your live preview and regenerated the pages. "
                    "Refresh the Live Product tab to see the new look."
                    if ok else
                    "I tried a full redesign but the build still had issues. "
                    "Try a smaller change, or ask me to redesign again."
                ),
                "changes_made": ["Full preview app regeneration"],
                "preview_rebuild_succeeded": ok,
                "reverted": False,
            }
        except Exception as exc:
            print(f"[refine] full redesign failed: {exc}", flush=True)
            traceback.print_exc()
            _emit(db, request_id, "refine_failed", f"Redesign failed: {exc}", 100)
            return {
                "reply": (
                    f"I couldn't complete a full redesign ({exc}). "
                    "Try again, or ask for one specific change at a time."
                ),
                "changes_made": [],
                "preview_rebuild_succeeded": False,
                "reverted": False,
            }

    # Safety net: snapshot the current working state so a bad AI edit, a
    # failed build, or any unexpected error can never leave the live
    # preview broken — we roll back to exactly what was being served
    # before this chat message.
    source_snapshot = snapshot_source(workspace)
    dist_backup = backup_dist(workspace)
    had_previous_good_build = dist_backup is not None

    plan = app_spec_context.plan if app_spec_context else stored_plan
    architect = app_spec_context.architect if app_spec_context else stored_architect
    if has_catalogue_routes(architect):
        architect["_catalogue_workspace"] = True

    ok = False
    data: dict = {}
    changes_made: list[str] = []
    error_message: str | None = None
    pending_metadata: dict[str, object] = {}

    try:
        message_digest = hashlib.sha256(user_message.encode("utf-8")).hexdigest()[:16]
        _emit(
            db,
            request_id,
            "refine",
            "Applying your feedback to the live app...",
            5,
            detail=f"message length={len(user_message)} sha256={message_digest}",
        )

        paths = [
            path
            for path in sorted(list_source_files(workspace), key=_rank_refinement_files)
            if not is_template_owned_path(path, architect)
        ]
        priority = [p for p in paths if p.endswith((".tsx", ".ts", ".css"))][:18]
        files_content = "\n\n".join(
            f"=== {p} ===\n{read_file(workspace, p)[:8000]}" for p in priority
        )
        file_tree = "\n".join(sorted(paths))

        prompt = template_renderer.render(
            PromptTemplate.PREVIEW_APP_CHAT_REFINEMENT,
            business_context=business_info(req)[:6000],
            user_message=user_message,
            experience_plan_json=json.dumps(plan, ensure_ascii=False, indent=2)[:8000],
            architect_json=json.dumps(architect, ensure_ascii=False, indent=2)[:6000],
            file_tree=file_tree[:4000],
            files_content=files_content[:45000],
            catalogue_mode=has_catalogue_routes(architect),
            catalogue_routes_json=_catalogue_routes_context(architect),
            app_spec_enforced=bool(app_spec_context),
            app_spec_ref_json=_bounded_json(
                generated_pages.get("app_spec_ref") or {}, 1200
            ),
            app_spec_contracts_json=_bounded_json(
                app_spec_context.selected_contracts if app_spec_context else {},
                24000,
            ),
        )

        _emit(db, request_id, "refine", "AI is updating your pages...", 25)
        data = _request_chat_refinement_payload(ai_provider, prompt)

        changes_made = list(data.get("changes_made") or [])
        changes_made.extend(
            _apply_chat_file_updates(
                workspace,
                data,
                architect,
                ai_provider=ai_provider,
                chat_prompt=prompt,
            )
        )

        if app_spec_context:
            plan, architect = _merge_app_spec_refinement_enrichment(
                app_spec_context,
                data,
            )
            pa = generated_pages.setdefault("preview_app", {})
            pa["routes"] = architect.get("routes") or []
            pa["roles"] = architect.get("roles") or []
            pa["design_direction"] = architect.get("design_direction", "")
            generated_pages["experience_plan"] = _plan_for_persistence(plan)
            if data.get("architect") or data.get("experience_plan"):
                changes_made.append(
                    "Applied design enrichment while preserving the AppSpec structure"
                )
        else:
            if data.get("architect"):
                arch = data["architect"]
                pa = generated_pages.setdefault("preview_app", {})
                if arch.get("routes"):
                    updated_routes = _merge_chat_routes(
                        architect.get("routes") or [],
                        arch["routes"],
                        data.get("experience_plan") or plan,
                        workspace,
                    )
                    pa["routes"] = updated_routes
                    architect["routes"] = updated_routes
                if arch.get("roles"):
                    pa["roles"] = arch["roles"]
                    architect["roles"] = arch["roles"]
                if arch.get("design_direction"):
                    pa["design_direction"] = arch["design_direction"]
                changes_made.append("Updated navigation structure")

            if data.get("experience_plan"):
                generated_pages["experience_plan"] = data["experience_plan"]
                plan = data["experience_plan"]
                changes_made.append("Updated experience plan")

        for route in architect.get("routes") or []:
            path = route.get("component_file") or ""
            if not path or not route.get("skeleton_id"):
                continue
            current = read_file(workspace, path)
            guarded, replaced = enforce_catalogue_page_contract(
                path,
                current,
                architect,
            )
            if replaced:
                write_file(workspace, path, guarded)
                record_stubbed_path(workspace, path)
                changes_made.append(f"Repaired catalogue contract for {path}")
            elif "deterministic catalogue contract scaffold" in guarded:
                record_stubbed_path(workspace, path)
            else:
                clear_stubbed_path(workspace, path)

        # These fields summarize product semantics, not visual treatment. An
        # AppSpec-governed refinement must not create a competing contract.
        if not app_spec_context:
            if data.get("concept_name"):
                pending_metadata["concept_name"] = data["concept_name"]
                changes_made.append(f"Renamed concept to {data['concept_name']}")
            if data.get("preview_summary"):
                pending_metadata["preview_summary"] = data["preview_summary"]
                changes_made.append("Updated preview summary")
            if data.get("preview_features"):
                pending_metadata["preview_features"] = json.dumps(data["preview_features"])
                changes_made.append("Updated feature list")
            if data.get("business_fit_score") is not None:
                pending_metadata["business_fit_score"] = int(data["business_fit_score"])

        demo: dict = {}
        if req.visual_demo_json:
            try:
                demo = json.loads(req.visual_demo_json)
            except Exception:
                pass
        if data.get("visual_demo"):
            demo = merge_visual_demo(demo, data["visual_demo"])
            demo = enrich_visual_demo(demo, req)
            pending_metadata["visual_demo_json"] = json.dumps(demo)
            pending_metadata["visual_demo_generated_at"] = datetime.utcnow()
            changes_made.append("Updated visual theme and copy")

        theme = demo.get("visual_theme", {})
        primary = theme.get("primary_color", "#6366f1")
        secondary = theme.get("secondary_color", "#0d9488")
        design_system = plan.get("design_system") or {}
        font = design_system.get("font_family") or design_system.get("font") or ""
        ref_meta: dict = {}
        if req.reference_metadata:
            try:
                ref_meta = json.loads(req.reference_metadata)
            except Exception:
                ref_meta = {}
        images = get_images_for_industry(
            req.industry or "",
            seed=request_id,
            hero_override=ref_meta.get("og_image") or None,
            business_name=req.business_name,
        )
        brand_name = req.business_name or "Brand"

        try:
            apply_workspace_guards(
                workspace, architect, plan, images, brand_name, primary, secondary, font, template_renderer,
            )
        except Exception as guard_exc:
            print(f"    refine guards skipped: {guard_exc}", flush=True)
            ensure_mock_exports(workspace, architect, plan, images, brand_name)
            from app.application.preview_app.design_recipes import get_recipe

            recipe = get_recipe(
                plan.get("recipe_id")
                or (plan.get("design_system") or {}).get("recipe_id")
            )
            write_index_css(workspace, primary, secondary, font, template_renderer, recipe=recipe)
            write_app_tsx(workspace, architect, template_renderer)

        base_path = f"/api/preview-apps/{request_id}"
        _emit(db, request_id, "refine", "Rebuilding live preview...", 60)
        ok, build_log = run_build(workspace, base_path, template_renderer)
        attempt = 0
        while not ok and attempt < MAX_BUILD_FIX_ATTEMPTS:
            attempt += 1
            _emit(
                db, request_id, "refine",
                f"Fixing build errors (attempt {attempt}/{MAX_BUILD_FIX_ATTEMPTS})...",
                65 + attempt,
            )
            errors = extract_build_errors(build_log)
            try:
                fix_build_errors(workspace, errors, architect, ai_provider, template_renderer)
                apply_workspace_guards(
                    workspace, architect, plan, images, brand_name, primary, secondary, font, template_renderer,
                )
            except Exception:
                pass
            ok, build_log = run_build(workspace, base_path, template_renderer)
        if ok and app_spec_context:
            workspace_issues = validate_app_spec_workspace(
                workspace,
                app_spec_context.spec,
                app_spec_context.scope,
                architect,
            )
            scaffold_pages = _catalogue_fallback_paths(workspace, architect)
            stubbed_pages = consume_stubbed_paths(workspace)
            contract_fallback_pages = list(
                dict.fromkeys([*scaffold_pages, *stubbed_pages])
            )
            if workspace_issues or contract_fallback_pages:
                ok = False
                parts: list[str] = []
                if workspace_issues:
                    parts.append(
                        "missing AppSpec hooks: " + "; ".join(workspace_issues[:6])
                    )
                if contract_fallback_pages:
                    parts.append(
                        "fallback/stub pages: " + ", ".join(contract_fallback_pages[:8])
                    )
                error_message = "AppSpec refinement rejected — " + " | ".join(parts)
        if not ok:
            error_message = (
                error_message
                or extract_build_errors(build_log)[:500]
                or "Build failed"
            )
            error_digest = hashlib.sha256(error_message.encode("utf-8")).hexdigest()[:16]
            print(
                f"[refine] build failed for {request_id}: "
                f"length={len(error_message)} sha256={error_digest}",
                flush=True,
            )
    except Exception as exc:
        ok = False
        error_message = str(exc)
        print(f"[refine] exception for {request_id}: {exc}", flush=True)
        traceback.print_exc()

    reverted = False
    restored_fallback_pages: list[str] = []
    if not ok:
        restore_source(workspace, source_snapshot)
        restored_fallback_pages = _catalogue_fallback_paths(workspace, architect)
        if had_previous_good_build:
            restore_dist(workspace, dist_backup)
            reverted = True
        generated_pages = original_generated_pages
        if reverted:
            restored_preview = generated_pages.setdefault("preview_app", {})
            restored_preview["status"] = "ready"
            restored_preview["fallback_pages"] = restored_fallback_pages
        for field, value in original_metadata.items():
            setattr(req, field, value)
    discard_backup(dist_backup)

    base_path = f"/api/preview-apps/{request_id}"
    if ok:
        for field, value in pending_metadata.items():
            setattr(req, field, value)
        pa = generated_pages.setdefault("preview_app", {})
        pa["url"] = f"{base_path}/"
        pa["status"] = "ready"
        pa["fallback_pages"] = _catalogue_fallback_paths(workspace, architect)
        pa.pop("last_refinement_error", None)
        generated_pages["preview_app"] = pa
        if app_spec_context:
            generated_pages["experience_plan"] = _plan_for_persistence(plan)
            generated_pages["app_spec_ref"] = original_generated_pages.get(
                "app_spec_ref"
            )
        req.generated_pages = json.dumps(generated_pages)
        req.updated_at = datetime.utcnow()
    else:
        req.generated_pages = (
            json.dumps(generated_pages)
            if reverted
            else original_generated_pages_text
        )
    db.commit()

    if ok:
        _emit(db, request_id, "refine_done", "Live preview updated!", 100, detail="; ".join(changes_made[:4]))
    elif reverted:
        _emit(db, request_id, "refine_reverted", "Change couldn't be applied safely — kept your previous version", 100)
    else:
        _emit(db, request_id, "refine_failed", "Rebuild failed — try rephrasing your request", 100)

    if ok:
        reply = data.get("reply") or "I've updated your live preview based on your feedback."
    elif reverted:
        reply = (
            "I couldn't apply that change without breaking the app, so I've kept your previous "
            "working version live. Try describing one smaller, more specific change at a time."
        )
        if error_message:
            reply += f" (Build issue: {error_message[:180]})"
        changes_made = ["No changes applied — reverted to previous working version"]
    else:
        reply = "I couldn't get the live preview building. Try describing one smaller, more specific change."
        if error_message:
            changes_made = changes_made or []

    return {
        "reply": reply,
        "changes_made": changes_made,
        "preview_rebuild_succeeded": ok,
        "reverted": reverted,
    }
