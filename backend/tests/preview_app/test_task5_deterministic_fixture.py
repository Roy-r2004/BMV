from __future__ import annotations

import hashlib
from contextlib import contextmanager
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
TEMPLATE_ROOT = BACKEND_ROOT / "preview-template"
sys.path.insert(0, str(BACKEND_ROOT))

from app.application.preview_app.assemble import (
    write_app_tsx,
    write_index_css,
    write_plumbing_mock,
)
from app.application.preview_app.catalogue_contract import (
    assigned_non_shell_slots,
    catalogue_route_for_file,
    validate_catalogue_page_content,
)
from app.application.preview_app.build import run_build
from app.application.preview_app.codegen.architect import _route_for_file
from app.application.preview_app.fallback import stabilize_all_route_pages
from app.application.preview_app.npm_shared import shared_npm_root
from app.application.preview_app.pipeline.architect_normalize import _normalize_architect
from app.application.preview_app.safety import apply_workspace_guards
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


def _representative_plan() -> dict:
    return {
        "roles": [
            {
                "id": "public",
                "label": "Guest",
                "defaultPath": "/",
                "pages": [
                    {
                        "id": "home",
                        "title": "Welcome",
                        "path": "/",
                        "surface": "public",
                        "skeleton_id": "public-home",
                        "section_slots": [
                            "hero",
                            "features",
                            "showcase",
                            "process",
                            "testimonials",
                            "cta",
                            "footer",
                        ],
                    }
                ],
            },
            {
                "id": "owner",
                "label": "Owner",
                "defaultPath": "/owner",
                "pages": [
                    {
                        "id": "dashboard",
                        "title": "Operations Dashboard",
                        "path": "/owner",
                        "surface": "ops",
                        "skeleton_id": "ops-dashboard",
                        "section_slots": [
                            "header",
                            "kpis",
                            "chart",
                            "filters",
                            "table",
                            "activity",
                        ],
                    }
                ],
            },
        ]
    }


def _representative_architect() -> dict:
    return {
        "routes": [
            {
                "path": "/",
                "role_id": "public",
                "page_id": "home",
                "title": "Welcome",
                "component_file": "src/pages/HomePage.tsx",
            },
            {
                "path": "/owner",
                "role_id": "owner",
                "page_id": "dashboard",
                "title": "Operations Dashboard",
                "component_file": "src/pages/owner/OwnerDashboardPage.tsx",
            },
        ],
        "files_to_generate": [
            {"path": "src/pages/HomePage.tsx", "kind": "page"},
            {"path": "src/pages/owner/OwnerDashboardPage.tsx", "kind": "page"},
            {"path": "src/components/Nav.tsx", "kind": "component"},
            {"path": "src/layouts/PublicLayout.tsx", "kind": "layout"},
            {"path": "src/layouts/AdminLayout.tsx", "kind": "layout"},
        ],
    }


def _kit_digest(workspace: Path) -> dict[str, str]:
    paths = sorted((workspace / "src" / "ui").rglob("*"))
    paths.append(workspace / "src" / "components" / "UiIcons.tsx")
    return {
        path.relative_to(workspace).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


def _assert_no_legacy_chrome(content: str) -> None:
    for import_path in (
        "components/Nav",
        "layouts/PublicLayout",
        "layouts/AdminLayout",
    ):
        assert import_path not in content
    for component in ("Nav", "PublicLayout", "AdminLayout"):
        assert not re.search(rf"<{component}(?:\s|/|>)", content)


def _detach_workspace_node_modules(workspace: Path) -> None:
    target = workspace / "node_modules"
    if not target.exists() and not target.is_symlink():
        return
    shared = shared_npm_root() / "node_modules"
    linked_to_shared = False
    try:
        linked_to_shared = target.resolve() == shared.resolve()
    except OSError:
        pass
    if target.is_symlink():
        target.unlink()
    elif os.name == "nt" and linked_to_shared:
        result = subprocess.run(
            ["cmd", "/c", "rmdir", str(target)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    elif linked_to_shared:
        raise AssertionError("Shared node_modules attachment was not a removable link")
    else:
        shutil.rmtree(target)
    assert not target.exists()
    assert (shared / "vite" / "package.json").is_file()


@contextmanager
def _temporary_preview_workspace() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="task5-preview-") as temp_dir:
        workspace = Path(temp_dir)
        assert TEMPLATE_ROOT not in (workspace, *workspace.parents)
        shutil.copytree(
            TEMPLATE_ROOT,
            workspace,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("node_modules", "dist", ".git"),
        )
        try:
            yield workspace
        finally:
            _detach_workspace_node_modules(workspace)


def test_catalogue_route_matching_is_exact_and_separator_safe() -> None:
    home = {
        "component_file": "src/pages/HomePage.tsx",
        "skeleton_id": "public-home",
    }
    owner_home = {
        "component_file": "src/pages/owner/HomePage.tsx",
        "skeleton_id": "ops-dashboard",
    }
    architect = {"routes": [home, owner_home]}

    assert catalogue_route_for_file(r"src\pages\owner\HomePage.tsx", architect) is owner_home
    assert _route_for_file(r"src\pages\owner\HomePage.tsx", architect) is owner_home
    assert catalogue_route_for_file("src/pages/missing/HomePage.tsx", architect) == {}
    assert _route_for_file("src/pages/missing/HomePage.tsx", architect) == {}


def _build_deterministic_catalogue_fixture() -> Path:
    renderer = JinjaTemplateRenderer(BACKEND_ROOT / "app" / "templates")
    plan = _representative_plan()
    architect = _normalize_architect(_representative_architect(), plan)
    routes = architect["routes"]

    assert [route["skeleton_id"] for route in routes] == [
        "public-home",
        "ops-dashboard",
    ]
    assert {
        item["path"].replace("\\", "/").lower()
        for item in architect["files_to_generate"]
    }.isdisjoint(
        {
            "src/components/nav.tsx",
            "src/layouts/publiclayout.tsx",
            "src/layouts/adminlayout.tsx",
        }
    )

    with _temporary_preview_workspace() as workspace:
        kit_before = _kit_digest(workspace)

        write_plumbing_mock(
            workspace,
            architect,
            {},
            "Northstar",
            "#123456",
            "#654321",
        )
        rewritten = stabilize_all_route_pages(
            workspace,
            architect,
            brand_name="Northstar",
            industry="professional services",
        )
        assert {
            "src/pages/HomePage.tsx",
            "src/pages/owner/OwnerDashboardPage.tsx",
        } <= set(rewritten)
        write_app_tsx(workspace, architect, renderer)
        write_index_css(workspace, "#123456", "#654321", "Atkinson", renderer)
        apply_workspace_guards(
            workspace,
            architect,
            plan,
            {},
            "Northstar",
            "#123456",
            "#654321",
            "Atkinson",
            renderer,
        )

        assert _kit_digest(workspace) == kit_before
        for route in routes:
            page = (workspace / route["component_file"]).read_text(encoding="utf-8")
            assert "from '@/ui'" in page
            assert f'const SKELETON_ID = "{route["skeleton_id"]}" as const' in page
            assert validate_catalogue_page_content(page, route) == []
            for slot in assigned_non_shell_slots(route):
                assert f"{slot}:" in page
            _assert_no_legacy_chrome(page)

        app = (workspace / "src" / "App.tsx").read_text(encoding="utf-8")
        assert '<Route path="/" element={<HomePage />} />' in app
        assert '<Route path="/owner" element={<OwnerDashboardPage />} />' in app
        _assert_no_legacy_chrome(app)

        ok, build_log = run_build(
            workspace,
            "/api/preview-apps/task5-fixture",
            renderer,
            timeout=120,
        )
        assert ok, build_log
        assert "=== linked node_modules ->" in build_log
        assert "falling back to local npm install" not in build_log
        shared = shared_npm_root() / "node_modules"
        assert (workspace / "node_modules").resolve() == shared.resolve()

        index = workspace / "dist" / "index.html"
        assert index.is_file()
        index_content = index.read_text(encoding="utf-8")
        assets = workspace / "dist" / "assets"
        js_assets = sorted(assets.glob("*.js"))
        css_assets = sorted(assets.glob("*.css"))
        assert js_assets
        assert css_assets
        assert any(asset.name in index_content for asset in js_assets)
        assert any(asset.name in index_content for asset in css_assets)
        assert "/api/preview-apps/task5-fixture/assets/" in index_content
        return workspace


def test_deterministic_catalogue_fixture_builds_twice_without_llm() -> None:
    first_workspace = _build_deterministic_catalogue_fixture()
    second_workspace = _build_deterministic_catalogue_fixture()
    assert first_workspace != second_workspace
    assert not first_workspace.exists()
    assert not second_workspace.exists()
    assert (shared_npm_root() / "node_modules" / "vite" / "package.json").is_file()
