"""Headless-browser screenshot capture for the post-build visual critique pass.

The preview apps are client-side React SPAs (no SSR) — `index.html` returns a
near-empty shell almost instantly, then React mounts and renders into
`#root`. A plain "page loaded" wait (`networkidle` alone) will happily
screenshot that blank shell before React has painted anything. This module
waits for both conditions before capturing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.logging import get_logger

log = get_logger("Screenshot")

_ROOT_HAS_CHILDREN_JS = (
    "() => { const el = document.getElementById('root'); "
    "return !!el && el.children.length > 0; }"
)

# The preview server SPA-fallbacks unknown paths to dist/index.html with HTTP
# 200 + text/html, so a missing asset is invisible to any status-code probe.
# The browser is the only place it is observable: an <img> that resolved to
# HTML decodes to naturalWidth 0.
_BROKEN_IMAGES_JS = (
    "() => Array.from(document.images)"
    ".filter(img => !img.complete || img.naturalWidth === 0)"
    ".map(img => img.getAttribute('src') || img.currentSrc || '(no src)')"
)


@dataclass
class RouteCapture:
    """Screenshot outcome plus the render defects the browser can see for free."""

    ok: bool
    path: Path | None = None
    broken_images: list[str] = field(default_factory=list)


def launch_chromium(p):
    """Prefer channel=chromium; fall back to bundled Chromium if channel missing."""
    try:
        # channel="chromium" opts into Chromium's "new" headless mode,
        # which runs the same regular Chromium build used for headed
        # mode (closer to real rendering) instead of the separate
        # chromium-headless-shell binary — one less browser download to
        # ship, and one fewer place headless-only rendering quirks can
        # diverge from what a real user's browser would show.
        # Dockerfile.app installs with --no-shell; plain headless=True
        # requires chromium-headless-shell and fails Phase 4 in that image.
        return p.chromium.launch(headless=True, channel="chromium")
    except Exception as e:
        log.warning(
            "screenshot channel=chromium launch failed (%s); using bundled chromium",
            e,
        )
        return p.chromium.launch(headless=True)


# Backward-compatible private alias for existing call sites/tests.
_launch_chromium = launch_chromium

# Steps of one viewport height, so a section whose reveal fires on intersection
# has been intersected at least once before the shot. `reduced_motion` already
# makes both of the template's reveal paths no-ops; this covers a component that
# forgets to check it, and costs one JS round-trip per screen.
_SCROLL_PRIME_JS = """
async () => {
  const step = window.innerHeight;
  const height = () => document.documentElement.scrollHeight;
  for (let y = 0; y < height() + step; y += step) {
    window.scrollTo(0, y);
    await new Promise((r) => requestAnimationFrame(() => r(null)));
  }
  window.scrollTo(0, 0);
  await new Promise((r) => requestAnimationFrame(() => r(null)));
  return height();
}
"""

_MAX_PRIME_SCROLL_PX = 60000


def prime_scroll_reveals(page, *, settle_ms: int = 250) -> int:
    """Scroll the whole page once and return to the top. Returns page height.

    A full-page screenshot of an unscrolled SPA shows the hero and then blank
    space: every section below the fold is wrapped in `observeSectionReveal`,
    which sets `opacity: 0` until an IntersectionObserver fires. Nothing below the
    first viewport had ever been intersected, so "screenshot the page" quietly
    meant "screenshot the hero" — for the vision critic as well as for
    `scripts/preview-qa.sh`.

    Returns 0 and logs on any failure: a page that will not scroll must still be
    screenshotted, just without the guarantee.
    """
    try:
        height = int(page.evaluate(_SCROLL_PRIME_JS) or 0)
        if height > _MAX_PRIME_SCROLL_PX:
            log.warning("page is %spx tall — capture may be truncated", height)
        page.wait_for_timeout(settle_ms)
        return height
    except Exception as e:  # noqa: BLE001 - never lose the screenshot over this
        log.warning("scroll prime failed (%s); capturing unprimed", e)
        return 0


def capture_route_visual(
    base_url: str,
    route_path: str,
    out_path: Path,
    *,
    timeout_ms: int = 20000,
    viewport: dict | None = None,
) -> RouteCapture:
    """Screenshot one route of an already-built, already-served preview app.

    Returns `RouteCapture(ok=False)` on any navigation/timeout/rendering error
    instead of raising — a screenshot failure must never be able to crash the
    main codegen pipeline, it should just mean that route doesn't get visually
    critiqued this run.
    """
    out_path = Path(out_path)
    base = base_url.rstrip("/")
    suffix = route_path.lstrip("/")
    full_url = f"{base}/{suffix}" if suffix else f"{base}/"
    broken: list[str] = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("screenshot skipped: playwright is not installed")
        return RouteCapture(ok=False)

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            try:
                # `reduced_motion` is load-bearing, not an accessibility nicety.
                # Every section below the fold is wrapped in `observeSectionReveal`,
                # which sets `opacity: 0` and only animates to 1 on intersection —
                # so a `full_page=True` screenshot captured the hero and then a
                # column of blank space, and the critic scored *that*. Both reveal
                # paths (`observeSectionReveal`, `AnimeStagger`) short-circuit to
                # visible when `prefers-reduced-motion: reduce` matches.
                page = browser.new_page(
                    viewport=viewport or {"width": 1280, "height": 900},
                    reduced_motion="reduce",
                )
                page.goto(full_url, wait_until="networkidle", timeout=timeout_ms)
                # SPA-specific: wait for React to actually mount content into
                # #root, not just for the network to go quiet — index.html +
                # the JS bundle can finish "loading" well before anything is
                # painted.
                page.wait_for_function(_ROOT_HAS_CHILDREN_JS, timeout=timeout_ms)
                # One extra tick for any post-mount effects (data seeding,
                # image decode) to settle before the shot.
                page.wait_for_timeout(300)
                prime_scroll_reveals(page)
                page.screenshot(path=str(out_path), full_page=True)
                try:
                    broken = [str(src) for src in page.evaluate(_BROKEN_IMAGES_JS) or []]
                except Exception as e:
                    log.warning("broken-image probe failed for %s: %s", route_path, e)
            finally:
                browser.close()
    except Exception as e:
        log.warning("screenshot capture failed for %s (%s): %s", route_path, full_url, e)
        return RouteCapture(ok=False)

    if not (out_path.is_file() and out_path.stat().st_size > 0):
        return RouteCapture(ok=False)
    if broken:
        log.error("broken images on %s: %s", route_path, broken[:6])
    return RouteCapture(ok=True, path=out_path, broken_images=broken)


def capture_route_screenshot(
    base_url: str,
    route_path: str,
    out_path: Path,
    *,
    timeout_ms: int = 20000,
    viewport: dict | None = None,
) -> bool:
    """Boolean-only view of `capture_route_visual`, for callers that only need
    to know whether a shot was taken and not what the browser saw."""
    return capture_route_visual(
        base_url, route_path, out_path, timeout_ms=timeout_ms, viewport=viewport
    ).ok
