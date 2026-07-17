from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.assemble import write_index_css
from app.application.preview_app.catalogue_contract import (
    _safe_slot_jsx,
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.codegen.fix_agent import fix_build_errors
from app.application.preview_app.codegen.generate import generate_file
from app.application.preview_app.fallback import scan_and_repair_double_brace_literals
from app.application.preview_app.pipeline.architect_normalize import _normalize_architect
from app.application.preview_app.safety.imports import (
    ensure_ui_headless_file,
    normalize_ui_kit_imports,
    rewrite_invented_component_imports,
    restore_curated_ui_kit,
    sanitize_ui_component_apis,
    strip_forbidden_npm_imports,
)
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.safety.pages import unwrap_route_layout_wrappers
from app.application.preview_app.safety.runtime import _ensure_tailwind_css
from app.application.preview_app.workspace import (
    snapshot_source,
    write_file,
    write_trusted_contained_file,
    write_trusted_workspace_file,
)
from app.core.config import settings
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


def _route() -> dict:
    return {
        "path": "/",
        "component_file": "src/pages/HomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "features", "showcase", "process", "testimonials", "cta", "footer"],
    }


def _assert_rejected(callable_) -> None:
    try:
        callable_()
    except (ValueError, OSError):
        return
    raise AssertionError("Unsafe write was not rejected")


def test_workspace_writes_fail_closed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        outside = root.parent / f"{root.name}-outside.ts"
        write_file(root, "src/pages/Safe.tsx", "export default null;\n")
        assert (root / "src/pages/Safe.tsx").is_file()

        for unsafe in (
            "../outside.ts",
            "src/../../outside.ts",
            "package.json",
            str(outside.absolute()),
            r"C:\Windows\temp\outside.ts",
        ):
            _assert_rejected(lambda unsafe=unsafe: write_file(root, unsafe, "owned"))
        assert not outside.exists()

        write_trusted_workspace_file(root, "package.json", "{}\n")
        assert (root / "package.json").read_text(encoding="utf-8") == "{}\n"
        _assert_rejected(
            lambda: write_trusted_workspace_file(root, "../trusted-escape.json", "{}")
        )

        linked_target = root.parent / f"{root.name}-linked"
        linked_target.mkdir()
        try:
            os.symlink(linked_target, root / "src" / "linked", target_is_directory=True)
        except OSError:
            pass
        else:
            _assert_rejected(
                lambda: write_file(root, "src/linked/Escape.ts", "export default 1")
            )
            assert not (linked_target / "Escape.ts").exists()
        finally:
            shutil.rmtree(linked_target, ignore_errors=True)

        outside_file = root.parent / f"{root.name}-file-target.ts"
        outside_file.write_text("outside-safe", encoding="utf-8")
        linked_file = root / "src/pages/Linked.tsx"
        try:
            os.symlink(outside_file, linked_file)
        except OSError:
            pass
        else:
            write_file(root, "src/pages/Linked.tsx", "inside-regular")
            assert outside_file.read_text(encoding="utf-8") == "outside-safe"
            assert not linked_file.is_symlink()
            assert linked_file.read_text(encoding="utf-8") == "inside-regular"
        finally:
            outside_file.unlink(missing_ok=True)

        write_trusted_contained_file(
            root,
            "src/components/Trusted.tsx",
            b"export const trusted = true;\n",
        )
        assert (root / "src/components/Trusted.tsx").read_bytes().startswith(b"export")


def test_safety_and_fallback_replace_file_symlinks_without_following() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "src/components").mkdir(parents=True)
        outside_headless = workspace.parent / f"{workspace.name}-headless.tsx"
        outside_headless.write_text("do not overwrite", encoding="utf-8")
        destination = workspace / "src/components/UiHeadless.tsx"
        try:
            os.symlink(outside_headless, destination)
        except OSError:
            return
        ensure_ui_headless_file(workspace)
        assert outside_headless.read_text(encoding="utf-8") == "do not overwrite"
        assert not destination.is_symlink()
        assert "export" in destination.read_text(encoding="utf-8")

        outside_fallback = workspace.parent / f"{workspace.name}-fallback.tsx"
        outside_fallback.write_text(
            "export const rows = [{{ label: 'A', detail: 'B', status: 'C' }}];\n",
            encoding="utf-8",
        )
        linked_page = workspace / "src/pages/LinkedPage.tsx"
        linked_page.parent.mkdir(parents=True)
        os.symlink(outside_fallback, linked_page)
        repaired = scan_and_repair_double_brace_literals(workspace)
        assert repaired == ["src/pages/LinkedPage.tsx"]
        assert "{{ label:" in outside_fallback.read_text(encoding="utf-8")
        assert not linked_page.is_symlink()
        assert "replaced unsafe source symlink" in linked_page.read_text(encoding="utf-8")
        outside_headless.unlink(missing_ok=True)
        outside_fallback.unlink(missing_ok=True)


def test_architect_rejects_unsafe_generated_files() -> None:
    plan = {
        "roles": [
            {
                "id": "public",
                "pages": [
                    {
                        "id": "home",
                        "title": "Home",
                        "path": "/",
                        "layout": "public",
                    }
                ],
            }
        ]
    }
    architect = _normalize_architect(
        {
            "routes": [
                {
                    "path": "/",
                    "page_id": "home",
                    "role_id": "public",
                    "component_file": "../outside.tsx",
                }
            ],
            "files_to_generate": [
                {"path": "../outside.ts", "kind": "page"},
                {"path": "package.json", "kind": "config"},
                {"path": "src/pages/SafePage.tsx", "kind": "page"},
            ],
            "shared_components": [
                {"path": "src/../../escape.tsx", "kind": "component"},
            ],
        },
        plan,
    )
    assert all(
        str(item.get("path", "")).startswith("src/")
        for item in architect["files_to_generate"]
    )
    assert all(".." not in item["path"] for item in architect["files_to_generate"])
    assert all(
        str(route.get("component_file", "")).startswith("src/pages/")
        for route in architect["routes"]
    )

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        _assert_rejected(
            lambda: generate_file(
                workspace,
                {"path": "../outside.tsx", "kind": "page"},
                "",
                {"routes": []},
                {},
                {},
                {},
                None,
                None,
            )
        )

        safe_page = workspace / "src/pages/SafePage.tsx"
        safe_page.parent.mkdir(parents=True)
        safe_page.write_text("export default function SafePage() { return null; }\n", encoding="utf-8")
        outside = workspace.parent / f"{workspace.name}-fix-escape.ts"

        class _MaliciousFixAI:
            def ask_chat(self, *_args, **_kwargs):
                return (
                    '{"files":['
                    '{"path":"../'
                    + outside.name
                    + '","content":"export default 1;"},'
                    '{"path":"src/../../escape.ts","content":"export default 2;"}'
                    "]}"
                )

        fixed = fix_build_errors(
            workspace,
            "SafePage.tsx error",
            {"routes": []},
            _MaliciousFixAI(),
            JinjaTemplateRenderer(),
        )
        assert not outside.exists()
        assert all(".." not in path for path in fixed)


def test_theme_inputs_cannot_inject_css() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        write_index_css(
            workspace,
            "#123456;} body{background:red}/*",
            "url(javascript:alert(1))",
            'Inter";} @import "https://evil.invalid/x.css";/*',
            JinjaTemplateRenderer(),
        )
        css = (workspace / "src/index.css").read_text(encoding="utf-8")
        assert "background:red" not in css
        assert "javascript:" not in css
        assert "evil.invalid" not in css
        assert "#6366f1" in css
        # Malicious font string must be stripped; recipe fonts (not attacker CSS) remain.
        assert 'Inter";}' not in css
        assert "@import \"https://evil" not in css
        assert "Nunito Sans" in css or "Libre Baskerville" in css or "Inter" in css
        assert "@import url(\"https://fonts.googleapis.com/css2?family=" in css


def test_catalogue_validator_rejects_import_bypasses() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    attacks = (
        "const x = require('evil-package');\n",
        "const x = require('@/ui');\n",
        "const x = module.require('evil-package');\n",
        "const x = import('evil-package');\n",
        "const x = import(sourceName);\n",
        "import Kit = require('@/ui');\n",
    )
    for attack in attacks:
        errors = validate_catalogue_page_content(attack + valid, route)
        assert "forbidden import syntax" in errors, (attack, errors)
    assert validate_catalogue_page_content(
        "// require('evil')\nconst example = \"import(sourceName)\";\n" + valid,
        route,
    ) == []


def test_missing_curated_kit_fails_before_snapshot() -> None:
    route = _route()
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as missing:
        workspace = Path(tmp)
        corrupt = workspace / "src/ui/registry.ts"
        corrupt.parent.mkdir(parents=True)
        corrupt.write_text("export const corrupted = true;\n", encoding="utf-8")
        (workspace / "src/pages").mkdir(parents=True)
        (workspace / "src/pages/HomePage.tsx").write_text(
            "export default null;\n",
            encoding="utf-8",
        )
        old_template = settings.PREVIEW_TEMPLATE_DIR
        settings.PREVIEW_TEMPLATE_DIR = Path(missing)
        try:
            _assert_rejected(lambda: restore_curated_ui_kit(workspace))
            _assert_rejected(
                lambda: apply_workspace_guards(
                    workspace,
                    architect,
                    {"roles": []},
                    {},
                    "Northstar",
                    "#123456",
                    "#654321",
                    "Inter",
                    JinjaTemplateRenderer(),
                )
            )
        finally:
            settings.PREVIEW_TEMPLATE_DIR = old_template
        assert corrupt.read_text(encoding="utf-8") == "export const corrupted = true;\n"

    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as partial:
        workspace = Path(tmp)
        before = {
            "src/ui/registry.ts": "workspace-registry\n",
            "src/ui/Rogue.ts": "workspace-rogue\n",
            "src/components/UiIcons.tsx": "workspace-icons\n",
        }
        for rel, content in before.items():
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

        partial_root = Path(partial)
        for directory in ("core", "public", "ops", "motion", "compose"):
            (partial_root / "src/ui" / directory).mkdir(parents=True, exist_ok=True)
        (partial_root / "src/ui/catalogue.json").write_text("{}", encoding="utf-8")
        (partial_root / "src/ui/registry.ts").write_text("registry", encoding="utf-8")
        (partial_root / "src/ui/index.ts").write_text("index", encoding="utf-8")
        # Deliberately omit compose/SkeletonComposer.tsx.
        (partial_root / "src/components").mkdir(parents=True)
        (partial_root / "src/components/UiIcons.tsx").write_text("icons", encoding="utf-8")

        old_template = settings.PREVIEW_TEMPLATE_DIR
        settings.PREVIEW_TEMPLATE_DIR = partial_root
        try:
            _assert_rejected(lambda: restore_curated_ui_kit(workspace))
        finally:
            settings.PREVIEW_TEMPLATE_DIR = old_template
        assert {
            rel: (workspace / rel).read_text(encoding="utf-8")
            for rel in before
        } == before


def test_unknown_slot_is_controlled_and_guards_are_idempotent() -> None:
    try:
        _safe_slot_jsx("unknown-slot", "Northstar", "Home")
    except ValueError as exc:
        assert "unknown-slot" in str(exc)
    else:
        raise AssertionError("Unknown fallback slot must raise a controlled error")

    route = _route()
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        (workspace / "src/pages").mkdir(parents=True)
        (workspace / "src/pages/HomePage.tsx").write_text(
            minimal_catalogue_page_scaffold(
                route["component_file"],
                route,
                brand_name="Northstar",
            ),
            encoding="utf-8",
        )
        (workspace / "src/data").mkdir(parents=True)
        (workspace / "src/data/mock.ts").write_text(
            "export const brand = { name: 'Northstar' };\n",
            encoding="utf-8",
        )
        args = (
            workspace,
            architect,
            {"roles": []},
            {},
            "Northstar",
            "#123456",
            "#654321",
            "Inter",
            JinjaTemplateRenderer(),
        )
        apply_workspace_guards(*args)
        first = snapshot_source(workspace)
        apply_workspace_guards(*args)
        second = snapshot_source(workspace)
        assert second == first, {
            path: (first.get(path), second.get(path))
            for path in sorted(set(first) | set(second))
            if first.get(path) != second.get(path)
        }


def main() -> None:
    test_workspace_writes_fail_closed()
    test_safety_and_fallback_replace_file_symlinks_without_following()
    test_architect_rejects_unsafe_generated_files()
    test_theme_inputs_cannot_inject_css()
    test_catalogue_validator_rejects_import_bypasses()
    test_missing_curated_kit_fails_before_snapshot()
    test_unknown_slot_is_controlled_and_guards_are_idempotent()


if __name__ == "__main__":
    main()
