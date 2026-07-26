"""Config-backed deterministic Phase 4 policy."""
from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from app.core.config import settings
from app.domain.schemas.runtime_validation import (
    BASELINE_ACCESSIBILITY_POLICY_REVISION,
    BASELINE_ACCESSIBILITY_SCANNER,
    RUNTIME_VALIDATION_POLICY_REVISION,
    RuntimeLimits,
    RuntimeToolVersions,
    ViewportContract,
)


VIEWPORTS = (
    ViewportContract(name="mobile", width=390, height=844, touch=True),
    ViewportContract(name="tablet", width=768, height=1024, touch=True),
    ViewportContract(name="desktop", width=1440, height=900, touch=False),
)


def runtime_limits() -> RuntimeLimits:
    return RuntimeLimits(
        typescript_timeout_seconds=(
            settings.V2_RUNTIME_TYPESCRIPT_TIMEOUT_SECONDS
        ),
        vite_build_timeout_seconds=(
            settings.V2_RUNTIME_VITE_BUILD_TIMEOUT_SECONDS
        ),
        build_stage_timeout_seconds=settings.V2_RUNTIME_BUILD_TIMEOUT_SECONDS,
        server_startup_timeout_seconds=(
            settings.V2_RUNTIME_SERVER_TIMEOUT_SECONDS
        ),
        route_timeout_seconds=settings.V2_RUNTIME_ROUTE_TIMEOUT_SECONDS,
        journey_timeout_seconds=settings.V2_RUNTIME_JOURNEY_TIMEOUT_SECONDS,
        accessibility_timeout_seconds=(
            settings.V2_RUNTIME_ACCESSIBILITY_TIMEOUT_SECONDS
        ),
        screenshot_timeout_seconds=(
            settings.V2_RUNTIME_SCREENSHOT_TIMEOUT_SECONDS
        ),
        phase_timeout_seconds=settings.V2_RUNTIME_PHASE_TIMEOUT_SECONDS,
        max_browser_contexts=settings.V2_RUNTIME_MAX_BROWSER_CONTEXTS,
        max_browser_pages=settings.V2_RUNTIME_MAX_BROWSER_PAGES,
        max_console_diagnostics=(
            settings.V2_RUNTIME_MAX_CONSOLE_DIAGNOSTICS
        ),
        max_network_diagnostics=(
            settings.V2_RUNTIME_MAX_NETWORK_DIAGNOSTICS
        ),
        max_command_output_bytes=(
            settings.V2_RUNTIME_MAX_COMMAND_OUTPUT_BYTES
        ),
        max_deterministic_repairs=(
            settings.V2_RUNTIME_MAX_DETERMINISTIC_REPAIRS
        ),
        max_dist_bytes=settings.V2_RUNTIME_MAX_DIST_BYTES,
        max_javascript_bytes=(
            settings.V2_RUNTIME_MAX_JAVASCRIPT_BYTES
        ),
        max_css_bytes=settings.V2_RUNTIME_MAX_CSS_BYTES,
        max_dist_files=settings.V2_RUNTIME_MAX_DIST_FILES,
        max_source_maps=settings.V2_RUNTIME_MAX_SOURCE_MAPS,
    )


def _package_version(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return str(payload["version"])


def _browser_bundle_revision() -> str:
    try:
        from playwright.sync_api import sync_playwright

        # Entering the Playwright driver does not launch a browser.
        with sync_playwright() as playwright:
            executable = Path(playwright.chromium.executable_path)
        if not executable.is_file():
            return "chromium-unavailable"
        parent_names = (executable.parent.name, executable.parent.parent.name)
        revision = next(
            (name for name in parent_names if name.startswith("chromium-")),
            executable.parent.parent.name,
        )
        return revision or "chromium-local"
    except Exception:
        return "chromium-unavailable"


def tool_versions() -> RuntimeToolVersions:
    if settings.V2_RUNTIME_POLICY_REVISION != (
        RUNTIME_VALIDATION_POLICY_REVISION
    ):
        raise ValueError("Configured Phase 4 policy revision is unsupported")
    node = subprocess.run(
        ["node", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        shell=False,
    )
    if node.returncode != 0:
        raise RuntimeError("Node runtime is unavailable")
    npm = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        shell=False,
    )
    if npm.returncode != 0:
        raise RuntimeError("npm runtime is unavailable")
    modules = settings.PREVIEW_TEMPLATE_DIR / "node_modules"
    typescript = _package_version(modules / "typescript" / "package.json")
    vite = _package_version(modules / "vite" / "package.json")
    playwright_version = importlib.metadata.version("playwright")
    return RuntimeToolVersions(
        node=node.stdout.strip(),
        npm=npm.stdout.strip(),
        platform=platform.platform(),
        python=sys.version.split()[0],
        typescript=typescript,
        vite=vite,
        playwright=playwright_version,
        browser_name="chromium",
        browser_version=_browser_bundle_revision(),
        accessibility_scanner=BASELINE_ACCESSIBILITY_SCANNER,
        accessibility_policy_revision=(
            BASELINE_ACCESSIBILITY_POLICY_REVISION
        ),
    )


__all__ = ["VIEWPORTS", "runtime_limits", "tool_versions"]
