"""Headless-browser screenshot capture for the post-build visual critique pass.

The preview apps are client-side React SPAs (no SSR) — `index.html` returns a
near-empty shell almost instantly, then React mounts and renders into
`#root`. A plain "page loaded" wait (`networkidle` alone) will happily
screenshot that blank shell before React has painted anything. This module
waits for both conditions before capturing.
"""
from __future__ import annotations

import threading
import time
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.infrastructure.logging import get_logger

log = get_logger("Screenshot")

# Playwright's *sync* API drives its own event loop and spawns a driver process
# per session. Two threads entering `sync_playwright()` at the same time race
# for that spawn and one of them dies with
# `RuntimeError: Racing with another loop to spawn a process.`
#
# The visual critic fans its routes out over `PREVIEW_PARALLEL_WORKERS` threads,
# so on request 40 five of six pages were lost that way: the run shipped
# `visual_review_status="partial"` with one page judged, and the four content
# defects on the unjudged pages reached the artifact unseen. Capture is a browser
# operation and belongs behind one lock; the vision call is what deserves the
# workers.
_SESSION_LOCK = threading.Lock()

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


#: The template's error boundary stamps its message here. A page that rendered it
#: is a white screen with a stack trace on it, whatever else the shot contains.
_RENDER_ERROR_JS = (
    "() => { const el = document.querySelector('[data-preview-render-error]'); "
    "return el ? (el.getAttribute('data-preview-render-error') || 'render failed') : ''; }"
)


@dataclass
class RouteCapture:
    """Screenshot outcome plus the render defects the browser can see for free."""

    ok: bool
    path: Path | None = None
    broken_images: list[str] = field(default_factory=list)
    #: Error-boundary message when the page crashed instead of rendering.
    render_error: str = ""


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


def _capture_one(browser, base_url: str, route_path: str, out_path: Path,
                 *, timeout_ms: int, viewport: dict | None) -> RouteCapture:
    """One route, inside an already-open browser. Never raises."""
    base = base_url.rstrip("/")
    suffix = route_path.lstrip("/")
    full_url = f"{base}/{suffix}" if suffix else f"{base}/"
    broken: list[str] = []
    render_error = ""
    page = None
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
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
        # `domcontentloaded`, not `networkidle`. Every public page carries
        # remote Pexels `<img>` tags, so `networkidle` made an image CDN a
        # latency dependency of our own screenshot pass — and it waits for
        # something we do not actually need. The condition that matters for an
        # SPA is the next line: React has mounted content into #root. The
        # network going quiet was never evidence of that (index.html and the
        # bundle finish "loading" well before anything is painted), which is
        # why both waits were already here.
        page.goto(full_url, wait_until="domcontentloaded", timeout=timeout_ms)
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
        try:
            render_error = str(page.evaluate(_RENDER_ERROR_JS) or "")
        except Exception as e:
            log.warning("render-error probe failed for %s: %s", route_path, e)
    except Exception as e:
        log.warning("screenshot capture failed for %s (%s): %s", route_path, full_url, e)
        return RouteCapture(ok=False)
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:
                pass

    if not (out_path.is_file() and out_path.stat().st_size > 0):
        return RouteCapture(ok=False)
    if broken:
        log.error("broken images on %s: %s", route_path, broken[:6])
    if render_error:
        log.error("%s rendered the error boundary: %s", route_path, render_error[:200])
    return RouteCapture(
        ok=True, path=out_path, broken_images=broken, render_error=render_error
    )


#: A route *pattern* is not an address. `/painting/:id` URL-encodes to
#: `/painting/%3Aid`, the page reads `params.id === ":id"`, matches no item and
#: correctly renders its own "not found" branch — so the visual critic scored
#: request 67's PaintingDetailPage 0 and request 66's CollectionPage 5, both
#: quoting "Not Found", on pages that work perfectly when opened properly.
#: `scripts/preview-qa.sh` has substituted params for a while; the pipeline's
#: own critic never did, so every detail page scored 0 in every run.
_ROUTE_PARAM_RE = re.compile(r"/:([A-Za-z_][\w]*)\??|/\{([^}]+)\}")

#: The first item of a generated catalogue is always id/index `1`.
_ROUTE_PARAM_SPECIMEN = "1"


def _navigable_route(path: str) -> str:
    """Turn a declared route pattern into an address a browser can open."""
    return _ROUTE_PARAM_RE.sub(f"/{_ROUTE_PARAM_SPECIMEN}", str(path or ""))


#: Wall clock for one whole capture session, across every route.
#:
#: Capture is not an "ask", so the per-ask ceiling never saw it. The two waits
#: in `_capture_one` each take `timeout_ms`, so a single route could burn
#: 2 x 20 s, and twelve routes serially behind `_SESSION_LOCK` is 480 s — most
#: of a 540 s request. This bounds the session; a route that does not fit comes
#: back `ok=False`, which the callers already treat as `unmeasured` rather than
#: as a pass.
_SESSION_BUDGET_SECONDS = 90.0


def capture_routes_visual(
    base_url: str,
    routes: list[tuple[str, Path]],
    *,
    timeout_ms: int = 8000,
    viewport: dict | None = None,
    session_budget_seconds: float = _SESSION_BUDGET_SECONDS,
) -> list[RouteCapture]:
    """Screenshot several routes in ONE browser session, serially.

    Returns one `RouteCapture` per input route, in order, with `ok=False` for any
    route that failed — a screenshot failure must never crash the pipeline, it
    just means that route does not get visually critiqued this run.

    Serial by construction: see `_SESSION_LOCK`. Reusing one browser also drops
    five browser launches from a six-route run, which is most of what the
    parallel version was buying.

    `timeout_ms` is 8 s rather than 20 s because the wait is now
    `domcontentloaded` plus "React mounted into #root", neither of which
    depends on a remote image CDN finishing.
    """
    routes = [(_navigable_route(str(rt)), Path(out)) for rt, out in routes]
    if not routes:
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("screenshot skipped: playwright is not installed")
        return [RouteCapture(ok=False) for _ in routes]

    with _SESSION_LOCK:
        try:
            with sync_playwright() as p:
                browser = _launch_chromium(p)
                session_started = time.monotonic()
                try:
                    captures: list[RouteCapture] = []
                    for index, (route_path, out_path) in enumerate(routes):
                        spent = time.monotonic() - session_started
                        if spent >= session_budget_seconds:
                            remaining = routes[index:]
                            log.error(
                                "screenshot session budget of %.0fs spent after %s of %s "
                                "route(s) — %s unmeasured: %s",
                                session_budget_seconds,
                                index,
                                len(routes),
                                len(remaining),
                                ", ".join(str(rt) for rt, _ in remaining[:8]),
                            )
                            from app.application.services.request_deadline import (
                                record_degradation,
                            )

                            record_degradation("screenshot", "session_budget_exhausted")
                            captures.extend(RouteCapture(ok=False) for _ in remaining)
                            break
                        captures.append(
                            _capture_one(
                                browser, base_url, route_path, out_path,
                                timeout_ms=timeout_ms, viewport=viewport,
                            )
                        )
                    return captures
                finally:
                    browser.close()
        except Exception as e:
            # A launch failure loses every route, and must say so rather than
            # look like N independent page errors.
            log.error("screenshot session failed (%s) — %s route(s) unmeasured", e, len(routes))
            return [RouteCapture(ok=False) for _ in routes]


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
    return capture_routes_visual(
        base_url,
        [(route_path, Path(out_path))],
        timeout_ms=timeout_ms,
        viewport=viewport,
    )[0]


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
