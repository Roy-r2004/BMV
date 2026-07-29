"""The scaffold must not reintroduce assets or reference pages generated apps never use."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.workspace import prepare_workspace
from app.core.config import settings

TEMPLATE_DIR = REPO_ROOT / "backend" / "preview-template"
PRUNED_PATHS = (
    "docs",
    "public",
    "scripts",
    "src/ui/examples",
)
LOAD_BEARING_PATHS = (
    "index.html",
    "package.json",
    "vite.config.ts",
    "src/App.tsx",
    "src/ui/index.ts",
    "src/ui/registry.ts",
    "src/ui/catalogue.json",
    "src/ui/compose/SkeletonComposer.tsx",
    "src/ui/lib/AppLink.tsx",
    "src/ui/public/BookingPanel.tsx",
    "src/ui/public/ScheduleRail.tsx",
    "src/ui/public/ConfirmStage.tsx",
    "src/components/UiIcons.tsx",
)
# Every laser-clinic asset the old public/ shipped straight through vite into dist/.
FORBIDDEN_SUBSTRINGS = (
    "catalogue-hero",
    "catalogue-laser",
    "catalogue-ritual",
    "catalogue-result-",
    "catalogue-product",
    "_catalogue/public",
    "ReferencePage",
    "ui/examples",
    "sync-ui-catalogue",
    "verify-ui-catalogue",
)


def _template_sources() -> list[Path]:
    return [
        path
        for path in TEMPLATE_DIR.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx", ".json", ".html", ".css"}
        and "node_modules" not in path.parts
        and "dist" not in path.parts
        and path.name != "package-lock.json"
    ]


def test_template_no_longer_ships_pruned_paths() -> None:
    template = TEMPLATE_DIR
    assert template.is_dir()
    present = [rel for rel in PRUNED_PATHS if (template / rel).exists()]
    assert present == [], f"dead scaffold reintroduced: {present}"
    for rel in LOAD_BEARING_PATHS:
        assert (template / rel).is_file(), f"load-bearing scaffold path missing: {rel}"


def test_template_sources_never_reference_pruned_paths() -> None:
    offenders: list[str] = []
    for path in _template_sources():
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN_SUBSTRINGS:
            if needle in text:
                offenders.append(f"{path.name}: {needle}")
    assert offenders == [], offenders


def test_template_ships_no_raster_or_binary_payload() -> None:
    template = TEMPLATE_DIR
    heavy = sorted(
        str(path.relative_to(template))
        for path in template.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4"}
        and "node_modules" not in path.parts
        and "dist" not in path.parts
    )
    assert heavy == [], f"scaffold ships unrelated imagery: {heavy}"


def test_prepared_workspace_stays_small_and_asset_free() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        original_apps = settings.PREVIEW_APPS_DIR
        original_template = settings.PREVIEW_TEMPLATE_DIR
        settings.PREVIEW_APPS_DIR = Path(tmp)
        settings.PREVIEW_TEMPLATE_DIR = TEMPLATE_DIR
        try:
            workspace = prepare_workspace(9_999_001)
        finally:
            settings.PREVIEW_APPS_DIR = original_apps
            settings.PREVIEW_TEMPLATE_DIR = original_template
        for rel in PRUNED_PATHS:
            assert not (workspace / rel).exists(), f"workspace received dead path {rel}"
        for rel in LOAD_BEARING_PATHS:
            assert (workspace / rel).is_file(), f"workspace missing {rel}"
        copied = sum(path.stat().st_size for path in workspace.rglob("*") if path.is_file())
        assert copied < 1_000_000, f"workspace copy grew back to {copied} bytes"


def main() -> None:
    test_template_no_longer_ships_pruned_paths()
    test_template_sources_never_reference_pruned_paths()
    test_template_ships_no_raster_or_binary_payload()
    test_prepared_workspace_stays_small_and_asset_free()


if __name__ == "__main__":
    main()
