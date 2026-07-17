"""Headless-browser screenshot capture for the post-build visual critique pass.

The preview apps are client-side React SPAs (no SSR) — `index.html` returns a
near-empty shell almost instantly, then React mounts and renders into
`#root`. A plain "page loaded" wait (`networkidle` alone) will happily
screenshot that blank shell before React has painted anything. This module
waits for both conditions before capturing.
"""
from __future__ import annotations

from pathlib import Path

from app.infrastructure.logging import get_logger

log = get_logger("Screenshot")

_ROOT_HAS_CHILDREN_JS = (
    "() => { const el = document.getElementById('root'); "
    "return !!el && el.children.length > 0; }"
)


def capture_route_screenshot(
    base_url: str,
    route_path: str,
    out_path: Path,
    *,
    timeout_ms: int = 20000,
    viewport: dict | None = None,
) -> bool:
    """Screenshot one route of an already-built, already-served preview app.

    Returns False on any navigation/timeout/rendering error instead of
    raising — a screenshot failure must never be able to crash the main
    codegen pipeline, it should just mean that route doesn't get visually
    critiqued this run.
    """
    out_path = Path(out_path)
    base = base_url.rstrip("/")
    suffix = route_path.lstrip("/")
    full_url = f"{base}/{suffix}" if suffix else f"{base}/"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("screenshot skipped: playwright is not installed")
        return False

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            # channel="chromium" opts into Chromium's "new" headless mode,
            # which runs the same regular Chromium build used for headed
            # mode (closer to real rendering) instead of the separate
            # chromium-headless-shell binary — one less browser download to
            # ship, and one fewer place headless-only rendering quirks can
            # diverge from what a real user's browser would show.
            browser = p.chromium.launch(headless=True, channel="chromium")
            try:
                page = browser.new_page(viewport=viewport or {"width": 1280, "height": 900})
                page.goto(full_url, wait_until="networkidle", timeout=timeout_ms)
                # SPA-specific: wait for React to actually mount content into
                # #root, not just for the network to go quiet — index.html +
                # the JS bundle can finish "loading" well before anything is
                # painted.
                page.wait_for_function(_ROOT_HAS_CHILDREN_JS, timeout=timeout_ms)
                # One extra tick for any post-mount effects (data seeding,
                # image decode) to settle before the shot.
                page.wait_for_timeout(300)
                page.screenshot(path=str(out_path), full_page=True)
            finally:
                browser.close()
    except Exception as e:
        log.warning("screenshot capture failed for %s (%s): %s", route_path, full_url, e)
        return False

    return out_path.is_file() and out_path.stat().st_size > 0
