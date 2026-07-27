"""Phase 4 must launch Chromium without chromium-headless-shell.

Dockerfile.app installs Playwright with ``--no-shell``. Plain
``chromium.launch(headless=True)`` looks for chromium-headless-shell and
fails with browser_launch_failed even when the full Chromium build exists.
"""
from __future__ import annotations

import inspect

from app.application.preview_app.screenshot import launch_chromium
from app.application.runtime_validation import browser as browser_module


class _FakeChromium:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def launch(self, **kwargs):
        self.calls.append(dict(kwargs))
        if kwargs.get("channel") == "chromium":
            return object()
        raise RuntimeError(
            "BrowserType.launch: Executable doesn't exist at "
            "/ms-playwright/chromium_headless_shell-1228/"
            "chrome-headless-shell-linux64/chrome-headless-shell"
        )


class _FakePlaywright:
    def __init__(self) -> None:
        self.chromium = _FakeChromium()


def test_launch_chromium_prefers_channel_over_headless_shell() -> None:
    playwright = _FakePlaywright()
    browser = launch_chromium(playwright)
    assert browser is not None
    assert playwright.chromium.calls == [
        {"headless": True, "channel": "chromium"}
    ]


def test_phase4_browser_module_uses_shared_channel_launcher() -> None:
    assert browser_module.launch_chromium is launch_chromium
    source = inspect.getsource(browser_module.run_browser_validation)
    assert "launch_chromium(playwright)" in source
    assert "chromium.launch(headless=True)" not in source
