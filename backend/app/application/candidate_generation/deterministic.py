"""Deterministic Phase 3B foundation, data, and route projections."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.application.appspec.source import canonical_json
from app.application.candidate_generation.cache import sha256_bytes, sha256_text
from app.application.candidate_generation.context import CandidateContext
from app.domain.schemas.preview_candidate import (
    CandidateArtifactKind,
    CandidateArtifactManifest,
    CandidateFileDescriptor,
    CandidateFileKind,
)


@dataclass(frozen=True)
class CandidateSourceFile:
    path: str
    file_kind: CandidateFileKind
    owner_contract_ids: tuple[str, ...]
    source: str


_FOUNDATION_FILES = (
    "package.json",
    "package-lock.json",
    "tsconfig.app.json",
    "tsconfig.json",
    "tsconfig.node.json",
    "vite.config.ts",
    "index.html",
)


def dependency_lock_sha256(template_dir: Path) -> str:
    return sha256_bytes((template_dir / "package-lock.json").read_bytes())


def _foundation_runtime_sources() -> tuple[CandidateSourceFile, ...]:
    return (
        CandidateSourceFile(
            path="src/vite-env.d.ts",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source='/// <reference types="vite/client" />\n',
        ),
        CandidateSourceFile(
            path="src/runtime/styles.d.ts",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source='declare module "*.css";\n',
        ),
        CandidateSourceFile(
            path="src/index.css",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source=(
                '@import "tailwindcss";\n\n'
                ":root {\n"
                "  font-synthesis: none;\n"
                "  text-rendering: optimizeLegibility;\n"
                "  color-scheme: light;\n"
                "}\n\n"
                "* { box-sizing: border-box; }\n"
                "html { min-width: 320px; background: #fff; }\n"
                "body { margin: 0; min-width: 320px; min-height: 100vh; }\n"
                "button, input, select, textarea { font: inherit; }\n"
                "@media (prefers-reduced-motion: reduce) {\n"
                "  *, *::before, *::after {\n"
                "    scroll-behavior: auto !important;\n"
                "    animation-duration: 0.01ms !important;\n"
                "    animation-iteration-count: 1 !important;\n"
                "    transition-duration: 0.01ms !important;\n"
                "  }\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/runtime/ErrorBoundary.tsx",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import { Component, type ErrorInfo, type ReactNode } from "react";\n\n'
                "type Props = { children: ReactNode };\n"
                "type State = { failed: boolean };\n\n"
                "export class CandidateErrorBoundary extends Component<Props, State> {\n"
                "  state: State = { failed: false };\n\n"
                "  static getDerivedStateFromError(): State {\n"
                "    return { failed: true };\n"
                "  }\n\n"
                "  componentDidCatch(error: Error, info: ErrorInfo): void {\n"
                '    console.error("candidate-render-error", error, info);\n'
                "  }\n\n"
                "  render(): ReactNode {\n"
                "    if (this.state.failed) {\n"
                "      return <main role=\"alert\">This candidate could not render.</main>;\n"
                "    }\n"
                "    return this.props.children;\n"
                "  }\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/runtime/RoleAccess.tsx",
            file_kind="runtime",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import type { ReactNode } from "react";\n\n'
                "type Props = {\n"
                "  pageId: string;\n"
                "  roleIds: readonly string[];\n"
                "  children: ReactNode;\n"
                "};\n\n"
                "export function RoleAccess({ pageId, roleIds, children }: Props) {\n"
                "  return (\n"
                "    <div\n"
                "      data-bmv-route-page-id={pageId}\n"
                "      data-bmv-role-ids={roleIds.join(\",\")}\n"
                "    >\n"
                "      {children}\n"
                "    </div>\n"
                "  );\n"
                "}\n"
            ),
        ),
        CandidateSourceFile(
            path="src/main.tsx",
            file_kind="infrastructure",
            owner_contract_ids=("FOUNDATION",),
            source=(
                'import { StrictMode } from "react";\n'
                'import { createRoot } from "react-dom/client";\n'
                'import { BrowserRouter } from "react-router-dom";\n'
                'import App from "./App";\n'
                'import { CandidateErrorBoundary } from "./runtime/ErrorBoundary";\n'
                'import "./index.css";\n\n'
                'const root = document.getElementById("root");\n'
                'if (!root) throw new Error("Missing #root mount point");\n\n'
                "createRoot(root).render(\n"
                "  <StrictMode>\n"
                "    <CandidateErrorBoundary>\n"
                "      <BrowserRouter>\n"
                "        <App />\n"
                "      </BrowserRouter>\n"
                "    </CandidateErrorBoundary>\n"
                "  </StrictMode>,\n"
                ");\n"
            ),
        ),
    )


def build_foundation_sources(template_dir: Path) -> tuple[CandidateSourceFile, ...]:
    files: list[CandidateSourceFile] = []
    for relpath in _FOUNDATION_FILES:
        source = (template_dir / relpath).read_text(encoding="utf-8")
        files.append(
            CandidateSourceFile(
                path=relpath,
                file_kind="infrastructure",
                owner_contract_ids=("FOUNDATION",),
                source=source,
            )
        )
    files.extend(_foundation_runtime_sources())
    return tuple(files)


def _typescript_const(name: str, value: object) -> str:
    return (
        f"export const {name} = "
        f"{json.dumps(value, ensure_ascii=False, separators=(',', ':'))} "
        "as const;\n"
    )


def build_data_sources(context: CandidateContext) -> tuple[CandidateSourceFile, ...]:
    content_payload = context.content_data.model_dump(mode="json")
    page_payload = context.page_purpose.model_dump(mode="json")
    interaction_payload = context.interactions.model_dump(mode="json")
    content_ids = tuple(
        item.content_id for item in context.content_data.content_items
    )
    collection_ids = tuple(
        item.collection_id for item in context.content_data.data_collections
    )
    page_ids = tuple(item.page_id for item in context.page_purpose.pages)
    action_ids = tuple(
        item.action_id for item in context.interactions.interactions
    )
    return (
        CandidateSourceFile(
            path="src/generated/content-data.json",
            file_kind="data",
            owner_contract_ids=content_ids + collection_ids,
            source=canonical_json(content_payload) + "\n",
        ),
        CandidateSourceFile(
            path="src/generated/content-data.ts",
            file_kind="data",
            owner_contract_ids=content_ids + collection_ids,
            source=(
                _typescript_const("contentDataPlan", content_payload)
                + _typescript_const(
                    "contentDataSha256",
                    context.refs.content_data_plan_ref.sha256,
                )
            ),
        ),
        CandidateSourceFile(
            path="src/generated/canonical-contracts.ts",
            file_kind="contract",
            owner_contract_ids=page_ids + action_ids,
            source=(
                _typescript_const("pagePurposeContract", page_payload)
                + _typescript_const("interactionContract", interaction_payload)
            ),
        ),
    )


def _symbol(identifier: str, suffix: str = "") -> str:
    parts = re.findall(r"[A-Za-z0-9]+", identifier)
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) + suffix


def page_export_symbol(page_id: str) -> str:
    return _symbol(page_id, "Page")


def _page_file_map(
    context: CandidateContext,
    page_sources: tuple[CandidateSourceFile, ...],
) -> dict[str, CandidateSourceFile]:
    result: dict[str, CandidateSourceFile] = {}
    tier_page_ids = {item.page_id for item in context.page_purpose.pages}
    for source in page_sources:
        owners = tier_page_ids.intersection(source.owner_contract_ids)
        if len(owners) != 1:
            raise ValueError(
                f"Page file {source.path} must own exactly one Tier 1 page."
            )
        page_id = next(iter(owners))
        if page_id in result:
            raise ValueError(f"Tier 1 page {page_id} has multiple page files.")
        result[page_id] = source
    if set(result) != tier_page_ids:
        raise ValueError("Every Tier 1 page requires exactly one page file.")
    return result


def build_route_sources(
    context: CandidateContext,
    page_sources: tuple[CandidateSourceFile, ...],
) -> tuple[CandidateSourceFile, ...]:
    page_file_map = _page_file_map(context, page_sources)
    ia_pages = {
        item.page_id: item for item in context.composition.information_architecture.pages
    }
    page_rows = []
    imports = []
    route_elements = []
    for page in context.page_purpose.pages:
        source = page_file_map[page.page_id]
        symbol = page_export_symbol(page.page_id)
        import_path = "./" + source.path.removeprefix("src/").removesuffix(".tsx")
        imports.append(f'import {{ {symbol} }} from "{import_path}";')
        page_rows.append(
            {
                "pageId": page.page_id,
                "route": page.route,
                "roleIds": list(page.role_ids),
                "surface": page.surface,
                "navigationVisibility": page.navigation_visibility,
                "mobile": page.mobile.model_dump(mode="json"),
            }
        )
        roles = json.dumps(list(page.role_ids), ensure_ascii=False)
        route_elements.append(
            "      <Route\n"
            f'        path="{page.route}"\n'
            "        element={\n"
            f'          <RoleAccess pageId="{page.page_id}" roleIds={{{roles}}}>\n'
            f"            <{symbol} />\n"
            "          </RoleAccess>\n"
            "        }\n"
            "      />"
        )

    tier_ids = {item.page_id for item in context.page_purpose.pages}
    navigation_groups = [
        {
            "id": group.id,
            "label": group.label,
            "surface": group.surface,
            "roleIds": list(group.role_ids),
            "pageIds": [
                page_id for page_id in group.page_ids if page_id in tier_ids
            ],
        }
        for group in context.composition.information_architecture.navigation_groups
        if any(page_id in tier_ids for page_id in group.page_ids)
    ]
    role_access = [
        {
            "roleId": item.role_id,
            "entryPageId": item.entry_page_id,
            "accessiblePageIds": [
                page_id
                for page_id in item.accessible_page_ids
                if page_id in tier_ids
            ],
        }
        for item in context.composition.information_architecture.role_access
        if item.entry_page_id in tier_ids
    ]
    first_route = context.page_purpose.pages[0].route
    app_source = (
        'import { Navigate, Route, Routes } from "react-router-dom";\n'
        + "\n".join(imports)
        + '\nimport { RoleAccess } from "./runtime/RoleAccess";\n\n'
        + "export default function App() {\n"
        + "  return (\n"
        + "    <Routes>\n"
        + "\n".join(route_elements)
        + "\n"
        + f'      <Route path="*" element={{<Navigate to="{first_route}" replace />}} />\n'
        + "    </Routes>\n"
        + "  );\n"
        + "}\n"
    )
    return (
        CandidateSourceFile(
            path="src/generated/route-manifest.ts",
            file_kind="route",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=(
                _typescript_const("routeManifest", page_rows)
                + _typescript_const(
                    "routeManifestSha256",
                    sha256_text(canonical_json(page_rows)),
                )
            ),
        ),
        CandidateSourceFile(
            path="src/generated/navigation.ts",
            file_kind="navigation",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=(
                _typescript_const("navigationGroups", navigation_groups)
                + _typescript_const("roleAccess", role_access)
            ),
        ),
        CandidateSourceFile(
            path="src/App.tsx",
            file_kind="route",
            owner_contract_ids=tuple(item.page_id for item in context.page_purpose.pages),
            source=app_source,
        ),
    )


def source_manifest(
    *,
    artifact_kind: CandidateArtifactKind,
    input_hashes: tuple[str, ...],
    sources: tuple[CandidateSourceFile, ...],
) -> CandidateArtifactManifest:
    return CandidateArtifactManifest(
        artifact_kind=artifact_kind,
        input_hashes=input_hashes,
        files=tuple(
            CandidateFileDescriptor(
                path=item.path,
                file_kind=item.file_kind,
                owner_contract_ids=item.owner_contract_ids,
                sha256=sha256_text(item.source),
                byte_count=len(item.source.encode("utf-8")),
            )
            for item in sources
        ),
    )


__all__ = [
    "CandidateSourceFile",
    "build_data_sources",
    "build_foundation_sources",
    "build_route_sources",
    "dependency_lock_sha256",
    "page_export_symbol",
    "source_manifest",
]
