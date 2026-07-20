"""Project planned AI features onto deterministic preview surfaces.

Hub at /ai-features is the index. Each feature is also injected into a concrete
workflow page with an interactive demo script ("try this → see that").
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from app.application.services.ai_features import (
    PAGE_AI_HUB_ID,
    PAGE_AI_HUB_ROUTE,
    ai_feature_hub_page_source,
    ai_features_from_request,
    assign_feature_placements,
    business_context_from_request,
    missing_ai_feature_ids_in_workspace,
)
from app.application.preview_app.workspace import read_file, write_file
from app.infrastructure.logging import get_logger

log = get_logger("AiFeatureSurfaces")

AI_HUB_COMPONENT = "src/pages/AiFeaturesPage.tsx"
_PANEL_MARKER = "data-ai-feature-panel"


def _features_for(req: Any, architect: Mapping[str, Any]) -> list[dict[str, Any]]:
    from_req = ai_features_from_request(req)
    if from_req:
        return from_req
    raw = architect.get("ai_features")
    if isinstance(raw, list):
        from app.application.services.ai_features import parse_ai_features

        return parse_ai_features(raw)
    return []


def ensure_ai_feature_route(
    architect: dict[str, Any],
    features: list[dict[str, Any]],
    *,
    context: Mapping[str, str] | None = None,
) -> dict:
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

    placed = assign_feature_placements(features, routes, context=context)
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
        "features": [str(f.get("name") or f.get("id")) for f in placed],
        "ai_feature_ids": [str(f.get("id")) for f in placed if f.get("id")],
        "evidence_ids": evidence_ids,
        "action_ids": list((existing or {}).get("action_ids") or []),
    }
    if existing is None:
        routes.append(route)
    else:
        existing.update({k: v for k, v in route.items() if v is not None})
        existing["component_file"] = AI_HUB_COMPONENT
        existing["path"] = PAGE_AI_HUB_ROUTE
    architect["routes"] = routes
    architect["ai_features"] = placed

    files = list(architect.get("files_to_generate") or [])
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
        # Match through `] as const;` — values may contain bare `;` so do not
        # stop at the first semicolon in the JSON payload.
        current = re.sub(
            r"export const aiFeatures\s*=\s*\[[\s\S]*?\]\s*as\s*const\s*;\s*",
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


def _ensure_import(source: str, symbol: str, module: str = "@/ui") -> str:
    if re.search(rf"\b{re.escape(symbol)}\b", source) and module in source:
        # Symbol already referenced; make sure import includes it.
        pass
    import_re = re.compile(
        rf"import\s*\{{([^}}]*)\}}\s*from\s*['\"]{re.escape(module)}['\"];?"
    )
    match = import_re.search(source)
    if match:
        names = [part.strip() for part in match.group(1).split(",") if part.strip()]
        if symbol not in names:
            names.append(symbol)
            replacement = f"import {{ {', '.join(names)} }} from '{module}';"
            return source[: match.start()] + replacement + source[match.end() :]
        return source
    # Prefer inserting after the last import line.
    lines = source.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, f"import {{ {symbol} }} from '{module}';")
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def _ensure_mock_import(source: str) -> str:
    if "aiFeatures" in source and "@/data/mock" in source:
        # May already import brand/images/seed — extend named import.
        mock_re = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]@/data/mock['\"];?")
        match = mock_re.search(source)
        if match:
            names = [part.strip() for part in match.group(1).split(",") if part.strip()]
            if "aiFeatures" not in names:
                names.append("aiFeatures")
                replacement = f"import {{ {', '.join(names)} }} from '@/data/mock';"
                return source[: match.start()] + replacement + source[match.end() :]
            return source
    if "from '@/data/mock'" in source or 'from "@/data/mock"' in source:
        return source
    lines = source.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("import "):
            insert_at = i + 1
    lines.insert(insert_at, "import { aiFeatures } from '@/data/mock';")
    return "\n".join(lines) + ("\n" if source.endswith("\n") else "")


def _panel_jsx(feature_id: str, brand_name: str) -> str:
    return (
        f'      <div {_PANEL_MARKER}={json.dumps(feature_id)}>\n'
        f'        <AiFeaturePanel\n'
        f'          feature={{(aiFeatures as any).find((f: any) => f.id === {json.dumps(feature_id)}) '
        f'|| {{ id: {json.dumps(feature_id)}, name: {json.dumps(feature_id)} }}}}\n'
        f'          brandName={{{json.dumps(brand_name)}}}\n'
        f'        />\n'
        f'      </div>'
    )


def inject_ai_panel_into_page(
    source: str,
    *,
    feature_id: str,
    brand_name: str,
) -> str:
    """Idempotently inject an in-context AiFeaturePanel into a page source."""
    if not source or not feature_id:
        return source
    if f'{_PANEL_MARKER}="{feature_id}"' in source or f"{_PANEL_MARKER}='{feature_id}'" in source:
        return source
    if f'data-ai-feature="{feature_id}"' in source and "AiFeaturePanel" in source:
        return source

    text = _ensure_import(source, "AiFeaturePanel")
    text = _ensure_mock_import(text)
    panel = _panel_jsx(feature_id, brand_name)

    # Prefer inside PublicShell / OpsShell just before closing tag.
    for closer in ("</PublicShell>", "</OpsShell>"):
        idx = text.rfind(closer)
        if idx >= 0:
            return text[:idx] + panel + "\n    " + text[idx:]

    # Fallback: before the final return closer `);`
    marker = "\n  );\n"
    idx = text.rfind(marker)
    if idx >= 0:
        return text[:idx] + "\n" + panel + text[idx:]
    return text.rstrip() + "\n" + panel + "\n"


def inject_contextual_ai_panels(
    workspace: Path,
    features: list[dict[str, Any]],
    *,
    brand_name: str,
) -> list[str]:
    """Inject each feature panel into its assigned workflow page."""
    written: list[str] = []
    for feature in features:
        fid = str(feature.get("id") or "").strip()
        component = str(feature.get("placement_component") or "").replace("\\", "/")
        if not fid or not component or component == AI_HUB_COMPONENT:
            continue
        source = read_file(workspace, component)
        if source is None:
            continue
        updated = inject_ai_panel_into_page(
            source,
            feature_id=fid,
            brand_name=brand_name,
        )
        if updated != source:
            write_file(workspace, component, updated)
            written.append(component)
            log.info("AI panel injected %s → %s", fid, component)
    return written


def ensure_ai_feature_surfaces(
    workspace: Path,
    architect: dict[str, Any],
    req: Any,
    *,
    brand_name: str,
) -> list[str]:
    """Inject route + mock + hub + contextual panels. Returns written paths."""
    features = _features_for(req, architect)
    if not features:
        return []
    ensure_ai_feature_route(
        architect,
        features,
        context=business_context_from_request(req),
    )
    features = list(architect.get("ai_features") or features)
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
    written = [
        write_ai_feature_hub_page(
            workspace,
            brand_name=brand_name,
            features=features,
            evidence_ids=list(route.get("evidence_ids") or []),
        ),
        "src/data/mock.ts",
    ]
    written.extend(
        inject_contextual_ai_panels(workspace, features, brand_name=brand_name)
    )
    log.info(
        "AI feature surfaces ready (%s features, %s contextual pages)",
        len(features),
        len(written) - 2,
    )
    return list(dict.fromkeys(written))


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
    pages = workspace / "src" / "pages"
    if pages.is_dir():
        for path in pages.rglob("*.tsx"):
            try:
                blob_parts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
    missing = missing_ai_feature_ids_in_workspace("\n".join(blob_parts), list(features))
    if missing:
        return missing
    # Stronger contract: each feature must also appear outside the hub page.
    return missing_contextual_ai_feature_ids(workspace, features)


def missing_contextual_ai_feature_ids(
    workspace: Path,
    features: list[Mapping[str, Any]],
) -> list[str]:
    """Features that only exist on the hub (not on a real workflow page)."""
    missing: list[str] = []
    pages = workspace / "src" / "pages"
    if not pages.is_dir():
        return [str(f.get("id")) for f in features if f.get("id")]
    context_blob_parts: list[str] = []
    for path in pages.rglob("*.tsx"):
        if path.name == "AiFeaturesPage.tsx":
            continue
        try:
            context_blob_parts.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    blob = "\n".join(context_blob_parts)
    for feature in features:
        fid = str(feature.get("id") or "").strip()
        if not fid:
            continue
        markers = (
            f'{_PANEL_MARKER}="{fid}"',
            f'data-ai-feature="{fid}"',
            f"data-ai-feature={json.dumps(fid)}",
            f'"id": "{fid}"',
        )
        if not any(marker in blob for marker in markers):
            missing.append(fid)
    return missing
