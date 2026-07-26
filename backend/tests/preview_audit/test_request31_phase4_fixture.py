from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.application.runtime_validation.build import candidate_dependency_view
from app.application.runtime_validation.prebuild import (
    PrebuildValidationError,
    validate_prebuild,
)
from app.core.config import settings


FIXTURE = Path(__file__).with_name("fixtures") / "request31"


def _copy_fixture(candidate: Path) -> None:
    shutil.copytree(
        FIXTURE,
        candidate,
        ignore=shutil.ignore_patterns(
            "node_modules",
            "dist",
            ".phase4-cache",
            "fixture.json",
        ),
    )


def _run_tsc(candidate: Path) -> subprocess.CompletedProcess[str]:
    modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    return subprocess.run(
        [
            "node",
            str(modules / "typescript" / "bin" / "tsc"),
            "-b",
            "--pretty",
            "false",
        ],
        cwd=candidate,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_request31_fixture_reproduces_production_import_resolution_failure(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    _copy_fixture(candidate)

    result = _run_tsc(candidate)

    assert result.returncode == 1
    output = f"{result.stdout}\n{result.stderr}"
    assert (
        "src/App.tsx(1,41): error TS2307: Cannot find module "
        "'react-router-dom'"
    ) in output
    assert "src/main.tsx(1,28): error TS2307: Cannot find module 'react'" in (
        output
    )


def test_request31_fixture_passes_bounded_prebuild_validation() -> None:
    checked = validate_prebuild(FIXTURE)
    assert "package.json" in checked
    assert "src/generated/route-manifest.ts" in checked


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_location"),
    [
        ("missing_script", "package_manifest_invalid", "package.json"),
        ("missing_route", "route_missing", "src/generated/route-manifest.ts"),
        ("absolute_path", "import_resolution_failed", "src/App.tsx"),
    ],
)
def test_prebuild_validation_emits_precise_evidence(
    tmp_path: Path,
    mutation: str,
    expected_code: str,
    expected_location: str,
) -> None:
    candidate = tmp_path / "candidate"
    _copy_fixture(candidate)
    if mutation == "missing_script":
        path = candidate / "package.json"
        package = json.loads(path.read_text())
        del package["scripts"]["build"]
        path.write_text(json.dumps(package), encoding="utf-8")
    elif mutation == "missing_route":
        (candidate / "src" / "generated" / "route-manifest.ts").unlink()
    else:
        path = candidate / "src" / "App.tsx"
        path.write_text(
            path.read_text(encoding="utf-8") + '\nconst bad = "C:\\\\Users\\\\x";\n',
            encoding="utf-8",
        )

    with pytest.raises(PrebuildValidationError) as caught:
        validate_prebuild(candidate)

    assert caught.value.code == expected_code
    assert caught.value.location == expected_location


def test_request31_fixture_builds_with_verified_candidate_dependency_view(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    _copy_fixture(candidate)
    app_config = (candidate / "tsconfig.app.json").read_bytes()
    node_config = (candidate / "tsconfig.node.json").read_bytes()
    modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    assert json.loads((candidate / "package-lock.json").read_text()) == (
        json.loads(
            (settings.PREVIEW_TEMPLATE_DIR / "package-lock.json").read_text()
        )
    )

    with candidate_dependency_view(candidate, modules):
        assert (candidate / "node_modules" / "react" / "package.json").is_file()
        typescript = _run_tsc(candidate)
        assert typescript.returncode == 0, (
            f"{typescript.stdout}\n{typescript.stderr}"
        )
        vite = subprocess.run(
            [
                "node",
                str(modules / "vite" / "bin" / "vite.js"),
                "build",
                "--mode",
                "production",
                "--outDir",
                "dist",
                "--emptyOutDir",
            ],
            cwd=candidate,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        assert vite.returncode == 0, f"{vite.stdout}\n{vite.stderr}"

    assert not (candidate / "node_modules").exists()
    assert not (candidate / ".phase4-cache").exists()
    assert (candidate / "tsconfig.app.json").read_bytes() == app_config
    assert (candidate / "tsconfig.node.json").read_bytes() == node_config
    assert (candidate / "dist" / "index.html").is_file()


def test_dependency_view_never_deletes_unmanaged_candidate_dependencies(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    marker = candidate / "node_modules" / "owned-by-candidate"
    marker.parent.mkdir()
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unmanaged node_modules"):
        with candidate_dependency_view(
            candidate,
            settings.PREVIEW_TEMPLATE_DIR / "node_modules",
        ):
            pass

    assert marker.read_text(encoding="utf-8") == "keep"
