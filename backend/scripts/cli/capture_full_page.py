#!/usr/bin/env python
"""Full-page screenshots of a served preview, for `scripts/preview-qa.sh`.

Why this exists: the QA harness drove host Chrome with `--headless --screenshot
--window-size=1440,2000`, which captures the **viewport only**. Public heroes are
viewport-height, so every attempt to see below the fold returned the hero again —
`preview-qa.sh` structurally could not see a broken catalogue grid, which is
exactly the class of defect it was added to catch. "Look at the screenshots" had a
blind spot precisely where the journey work landed.

Two things are needed, not one:

1. **Capture beyond the viewport.** Playwright's `full_page=True` is CDP's
   `captureBeyondViewport` and is already installed in the api image, so the
   harness gets a real full-page PNG without a WebSocket client in `sh`.
2. **Make the below-fold content visible.** `observeSectionReveal` sets
   `opacity: 0` and only animates to 1 on intersection, so a full-page shot of an
   unscrolled page is a hero over a column of blank space. `reduced_motion` makes
   both reveal paths no-ops, and a scroll prime covers anything that forgets to
   check it.

Writes PNGs to `--out-dir`, or base64 to stdout with `--stdout` so the host can
decode them without a shared volume. Prints one `name<TAB>path<TAB>bytes<TAB>height`
line per route to stderr.

    python -m scripts.cli.capture_full_page \
        --base-url http://localhost:8000/api/preview-apps/36 \
        --route home:/ --route gallery:/gallery --out-dir /tmp/qa
"""
from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.screenshot import (  # noqa: E402
    _ROOT_HAS_CHILDREN_JS,
    launch_chromium,
    prime_scroll_reveals,
)

DEFAULT_WIDTH = 1440
DEFAULT_HEIGHT = 900


def _parse_route(spec: str) -> tuple[str, str]:
    """`name:path` → `(name, path)`; a bare path names itself."""
    name, sep, path = spec.partition(":")
    if not sep:
        return (name.strip("/") or "home", name)
    return (name or path.strip("/") or "home", path)


def capture(
    base_url: str,
    routes: list[tuple[str, str]],
    *,
    out_dir: Path | None,
    to_stdout: bool,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    timeout_ms: int = 20000,
) -> int:
    from playwright.sync_api import sync_playwright

    base = base_url.rstrip("/")
    failures = 0
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = launch_chromium(p)
        try:
            for name, route in routes:
                suffix = route.lstrip("/")
                url = f"{base}/{suffix}" if suffix else f"{base}/"
                page = browser.new_page(
                    viewport={"width": width, "height": height},
                    reduced_motion="reduce",
                )
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                    page.wait_for_function(_ROOT_HAS_CHILDREN_JS, timeout=timeout_ms)
                    page.wait_for_timeout(300)
                    page_height = prime_scroll_reveals(page)
                    png = page.screenshot(full_page=True)
                except Exception as e:  # noqa: BLE001 - one bad route, not the run
                    print(f"{name}\tFAILED\t0\t0\t{e}", file=sys.stderr)
                    failures += 1
                    continue
                finally:
                    page.close()

                target = ""
                if out_dir:
                    path = out_dir / f"{name}.png"
                    path.write_bytes(png)
                    target = str(path)
                if to_stdout:
                    print(f"===PNG {name}")
                    print(base64.b64encode(png).decode("ascii"))
                print(f"{name}\t{target or '(stdout)'}\t{len(png)}\t{page_height}",
                      file=sys.stderr)
        finally:
            browser.close()
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", required=True, help="served preview origin + base path")
    parser.add_argument(
        "--route",
        action="append",
        default=[],
        metavar="NAME:PATH",
        help="repeatable; `gallery:/gallery`. Defaults to the site root.",
    )
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--stdout", action="store_true", help="emit base64 PNGs on stdout")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args(argv)

    routes = [_parse_route(spec) for spec in args.route] or [("home", "/")]
    if not args.out_dir and not args.stdout:
        parser.error("nothing to do: pass --out-dir and/or --stdout")
    return capture(
        args.base_url,
        routes,
        out_dir=args.out_dir,
        to_stdout=args.stdout,
        width=args.width,
        height=args.height,
    )


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
