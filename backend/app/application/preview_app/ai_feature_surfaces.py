"""Project planned AI features onto deterministic preview surfaces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from app.application.services.ai_features import (
    PAGE_AI_HUB_ID,
    PAGE_AI_HUB_ROUTE,
    ai_feature_hub_page_source,
    ai_features_from_request,
    missing_ai_feature_ids_in_workspace,
)
from app.application.preview_app.workspace import read_file, write_file
from app.infrastructure.logging import get_logger

log = get_logger("AiFeatureSurfaces")

AI_HUB_COMPONENT = "src/pages/AiFeaturesPage.tsx"


def _features_for(req: Any, architect: Mapping[str, Any]) -> list[dict[str, Any]]:
    from_req = ai_features_from_request(req)
    if from_req:
        return from_req
    raw = architect.get("ai_features")
    if isinstance(raw, list):
        from app.application.services.ai_features import parse_ai_features

        return parse_ai_features(raw)
    return []


def ensure_ai_feature_route(architect: dict[str, Any], features: list[dict[str, Any]]) -> dict:
    """Ensure architect has a public route for the AI feature hub."""
    if not features:
        return architect
    routes = list(architect.get("routes") or [])
    existing = next(
        (
            rt
            for rt in routes
            if isinstance(rt, dict)
            and (
                str(rt.get("path") or "") == PAGE_AI_HUB_ROUTE
                or str(rt.get("app_spec_page_id") or rt.get("page_id") or "").casefold()
                == PAGE_AI_HUB_ID.casefold()
                or str(rt.get("component_file") or "").replace("\\", "/") == AI_HUB_COMPONENT
            )
        ),
        None,
    )
    role_id = "ROLE-CUSTOMER"
    for rt in routes:
        if isinstance(rt, dict) and rt.get("role_id") and (
            rt.get("layout") == "public" or rt.get("surface") == "public"
        ):
            role_id = str(rt["role_id"])
            break
    for role in architect.get("roles") or []:
        if isinstance(role, dict) and role.get("id"):
            role_id = str(role["id"])
            break

    evidence_ids = list((existing or {}).get("evidence_ids") or [])
    route = {
        "path": PAGE_AI_HUB_ROUTE,
        "page_id": PAGE_AI_HUB_ID,
        "app_spec_page_id": PAGE_AI_HUB_ID,
        "role_id": role_id,
        "title": "AI features",
        "component_file": AI_HUB_COMPONENT,
        "layout": "public",
        "surface": "public",
        "skeleton_id": "public-utility",
        "purpose": "Interactive hub for every AI feature proposed in the plan",
        "features": [str(f.get("name") or f.get("id")) for f in features],
        "ai_feature_ids": [str(f.get("id")) for f in features if f.get("id")],
        "evidence_ids": evidence_ids,
        "action_ids": list((existing or {}).get("action_ids") or []),
    }
    if existing is None:
        routes.append(route)
    else:
        existing.update({k: v for k, v in route.items() if v is not None})
        # Force the deterministic hub path even if AppSpec suggested another stem.
        existing["component_file"] = AI_HUB_COMPONENT
        existing["path"] = PAGE_AI_HUB_ROUTE
    architect["routes"] = routes
    architect["ai_features"] = features

    files = list(architect.get("files_to_generate") or [])
    # Hub is deterministic — keep it out of the AI codegen queue.
    files = [
        f
        for f in files
        if str((f or {}).get("path") or "").replace("\\", "/") != AI_HUB_COMPONENT
    ]
    architect["files_to_generate"] = files
    return architect


def write_ai_features_mock(workspace: Path, features: list[dict[str, Any]]) -> None:
    mock_path = "src/data/mock.ts"
    current = read_file(workspace, mock_path) or ""
    payload = json.dumps(features, indent=2, ensure_ascii=False)
    export = f"\nexport const aiFeatures = {payload} as const;\n"
    if "export const aiFeatures" in current:
        import re

        current = re.sub(
            r"export const aiFeatures\s*=\s*[\s\S]*?;\s*",
            export.lstrip(),
            current,
            count=1,
        )
        write_file(workspace, mock_path, current)
    else:
        write_file(workspace, mock_path, current.rstrip() + export)


def write_ai_feature_hub_page(
    workspace: Path,
    *,
    brand_name: str,
    features: list[dict[str, Any]],
    evidence_ids: list[str] | None = None,
) -> str:
    source = ai_feature_hub_page_source(
        brand_name=brand_name,
        features=features,
        evidence_ids=evidence_ids,
    )
    write_file(workspace, AI_HUB_COMPONENT, source)
    return AI_HUB_COMPONENT


def ensure_ai_feature_surfaces(
    workspace: Path,
    architect: dict[str, Any],
    req: Any,
    *,
    brand_name: str,
) -> list[str]:
    """Inject route + mock + hub page for planned AI features. Returns written paths."""
    features = _features_for(req, architect)
    if not features:
        return []
    ensure_ai_feature_route(architect, features)
    write_ai_features_mock(workspace, features)
    route = next(
        (
            rt
            for rt in architect.get("routes") or []
            if isinstance(rt, dict)
            and str(rt.get("component_file") or "").replace("\\", "/") == AI_HUB_COMPONENT
        ),
        {},
    )
    written = write_ai_feature_hub_page(
        workspace,
        brand_name=brand_name,
        features=features,
        evidence_ids=list(route.get("evidence_ids") or []),
    )
    log.info(
        "AI feature hub ready (%s features) → %s",
        len(features),
        written,
    )
    return [written, "src/data/mock.ts"]


def assert_ai_features_present(
    workspace: Path,
    features: list[Mapping[str, Any]],
) -> list[str]:
    """Return missing feature ids (empty list means coverage passed)."""
    if not features:
        return []
    blob_parts: list[str] = []
    for rel in (AI_HUB_COMPONENT, "src/data/mock.ts"):
        blob_parts.append(read_file(workspace, rel) or "")
    # Also scan pages folder for widgets embedded elsewhere.
    pages = workspace / "src" / "pages"
    if pages.is_dir():
        for path in pages.rglob("*.tsx"):
            try:
                blob_parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    return missing_ai_feature_ids_in_workspace("\n".join(blob_parts), list(features))
