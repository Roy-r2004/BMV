"""Chromium, for pixels and pages: HTML → PNG (the screen thumbnails) and
HTML → PDF (the proposal). The HTML is the product; the browser only prints it.

Fails open. Without a browser the site still shows the live HTML system,
which needs none; only the PNGs and the PDF are lost, and the callers say so.
"""

import logging
import os
import threading

logger = logging.getLogger("consultant.screens.browser")

_lock = threading.Lock()
_available: bool | None = None


def available() -> bool:
    """Whether Chromium can be launched here. Checked once."""
    global _available
    with _lock:
        if _available is not None:
            return _available
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                b = p.chromium.launch()
                b.close()
            _available = True
        except Exception as exc:
            logger.warning("no browser for screens (PNG and PDF off): %s", str(exc)[:200])
            _available = False
        return _available


def render_pngs(html: str, screen_ids: list[str], out_dir: str, scale: int = 2) -> dict[str, str]:
    """One PNG per screen from the live system page: each screen is shown in
    turn and the frame element is captured. Returns {screen_id: path}."""
    if not available():
        return {}
    from playwright.sync_api import sync_playwright

    os.makedirs(out_dir, exist_ok=True)
    out: dict[str, str] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=scale)
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(150)
        for sid in screen_ids:
            try:
                page.evaluate("id => window.postMessage({type: 'bmv:show', id: id}, '*')", sid)
                page.wait_for_timeout(60)
                path = os.path.join(out_dir, f"{sid}.png")
                page.locator(".frame").screenshot(path=path)
                out[sid] = path
            except Exception as exc:
                logger.warning("screen %s could not be captured: %s", sid, str(exc)[:160])
        browser.close()
    return out


def render_pdf(html: str, out_path: str) -> str:
    """The proposal, printed. Raises when no browser is available."""
    if not available():
        raise RuntimeError("no browser available to print the proposal")
    from playwright.sync_api import sync_playwright

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1123, "height": 794})
        page.set_content(html, wait_until="load")
        page.emulate_media(media="print")
        page.wait_for_timeout(200)
        page.pdf(path=out_path, prefer_css_page_size=True, print_background=True)
        browser.close()
    return out_path
