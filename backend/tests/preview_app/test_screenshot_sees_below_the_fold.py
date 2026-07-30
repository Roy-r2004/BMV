"""A screenshot of a page must show the page, not just its hero.

Two independent reasons it did not, and both had to be fixed:

1. **Height.** `scripts/preview-qa.sh` drove host Chrome with `--screenshot
   --window-size=1440,2000`, which captures the *viewport only*. Public heroes are
   viewport-height, so every route's screenshot was that route's hero — the
   harness structurally could not see a broken catalogue grid, the exact defect it
   was added to catch.

2. **Visibility.** `observeSectionReveal` sets `opacity: 0` and only animates to 1
   when an IntersectionObserver fires. Nothing below the first viewport had ever
   been intersected, so even `full_page=True` — which the *production* critic
   already used — produced a hero over blank space. Proven by rendering app 37's
   `/gallery` three ways: viewport-only showed the hero alone; full-page unprimed
   showed the cards but a completely blank CTA band; full-page with reduced motion
   and a scroll prime showed the whole page.

So the vision critic had been scoring pages whose below-fold sections were
invisible, and could have flagged a section that renders fine for a real visitor.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app import screenshot as shot  # noqa: E402


class _FakePage:
    def __init__(self, *, height: int = 4113, evaluate_raises: bool = False) -> None:
        self.height = height
        self.evaluate_raises = evaluate_raises
        self.evaluated: list[str] = []
        self.waits: list[int] = []
        self.screenshots: list[dict] = []
        self.closed = False
        # Ordered log. `capture_route_visual` also evaluates the broken-image
        # probe, so "evaluate was called" does not mean "the reveals were primed",
        # and priming after the shot would be useless.
        self.events: list[str] = []

    def evaluate(self, js):
        if self.evaluate_raises:
            raise RuntimeError("execution context was destroyed")
        self.evaluated.append(js)
        if "scrollHeight" in js and "innerHeight" in js:
            self.events.append("prime")
            return self.height
        self.events.append("evaluate")
        return []

    def wait_for_timeout(self, ms):
        self.waits.append(ms)

    def wait_for_function(self, _js, **_kw):
        return True

    def goto(self, _url, **_kw):
        return None

    def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)
        self.events.append("screenshot")
        path = kwargs.get("path")
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"\x89PNG fake")
        return b"\x89PNG fake"

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, page: _FakePage) -> None:
        self.page = page
        self.new_page_kwargs: list[dict] = []
        self.closed = False

    def new_page(self, **kwargs):
        self.new_page_kwargs.append(kwargs)
        return self.page

    def close(self):
        self.closed = True


# ---------------------------------------------------------------------------
# prime_scroll_reveals
# ---------------------------------------------------------------------------

def test_prime_scroll_reveals_scrolls_the_page_and_returns_its_height() -> None:
    page = _FakePage(height=4113)
    assert shot.prime_scroll_reveals(page) == 4113
    assert len(page.evaluated) == 1
    js = page.evaluated[0]
    # It must walk the page by viewport steps and come back to the top, or a
    # sticky header lands mid-page in the capture.
    assert "window.innerHeight" in js
    assert "scrollHeight" in js
    assert "window.scrollTo(0, 0)" in js
    assert page.waits == [250], "no settle after scrolling — reveals mid-animation"


def test_prime_scroll_reveals_degrades_instead_of_losing_the_screenshot() -> None:
    """A page that will not scroll must still be captured, just unguaranteed."""
    page = _FakePage(evaluate_raises=True)
    assert shot.prime_scroll_reveals(page) == 0
    assert page.waits == []


def test_prime_scroll_reveals_warns_on_an_absurdly_tall_page(caplog) -> None:
    page = _FakePage(height=shot._MAX_PRIME_SCROLL_PX + 1)
    with caplog.at_level("WARNING"):
        assert shot.prime_scroll_reveals(page) == shot._MAX_PRIME_SCROLL_PX + 1
    assert any("tall" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# capture_route_visual
# ---------------------------------------------------------------------------

def _install_fake_playwright(monkeypatch: pytest.MonkeyPatch, page: _FakePage) -> _FakeBrowser:
    browser = _FakeBrowser(page)

    class _Ctx:
        def __enter__(self):
            return object()

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(shot, "_launch_chromium", lambda _p: browser)
    monkeypatch.setitem(
        sys.modules,
        "playwright.sync_api",
        type(
            "_M",
            (),
            {"sync_playwright": staticmethod(lambda: _Ctx())},
        ),
    )
    return browser


def test_the_production_capture_asks_for_reduced_motion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Load-bearing, not an accessibility nicety.

    Both of the template's reveal paths (`observeSectionReveal`, `AnimeStagger`)
    check `prefersReducedMotion()` and leave content visible when it matches. It
    is the only thing that makes a below-fold section appear in a static shot.
    """
    page = _FakePage()
    browser = _install_fake_playwright(monkeypatch, page)

    capture = shot.capture_route_visual(
        "http://api/api/preview-apps/36", "/gallery", tmp_path / "shot.png"
    )

    assert capture.ok is True
    assert browser.new_page_kwargs[0]["reduced_motion"] == "reduce"


def test_the_production_capture_is_full_page_and_primed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _FakePage()
    _install_fake_playwright(monkeypatch, page)

    shot.capture_route_visual(
        "http://api/api/preview-apps/36", "/gallery", tmp_path / "shot.png"
    )

    assert page.screenshots[0]["full_page"] is True
    # The prime must have happened, and happened *before* the shot.
    assert "prime" in page.events, "the page was captured without priming its reveals"
    assert page.events.index("prime") < page.events.index("screenshot")


def test_a_viewport_override_still_gets_reduced_motion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = _FakePage()
    browser = _install_fake_playwright(monkeypatch, page)

    shot.capture_route_visual(
        "http://api/api/preview-apps/36",
        "/gallery",
        tmp_path / "shot.png",
        viewport={"width": 390, "height": 844},
    )

    kwargs = browser.new_page_kwargs[0]
    assert kwargs["viewport"] == {"width": 390, "height": 844}
    assert kwargs["reduced_motion"] == "reduce"


# ---------------------------------------------------------------------------
# the QA harness's capture CLI
# ---------------------------------------------------------------------------

def test_route_specs_parse_into_names_and_paths() -> None:
    from scripts.cli.capture_full_page import _parse_route

    assert _parse_route("gallery:/gallery") == ("gallery", "/gallery")
    assert _parse_route("gallery-1:/gallery/1") == ("gallery-1", "/gallery/1")
    # A bare path names itself, and the site root is "home" rather than "".
    assert _parse_route("/about") == ("about", "/about")
    assert _parse_route("/") == ("home", "/")


def test_the_qa_harness_captures_full_page_not_the_viewport() -> None:
    """Guards the shell rewiring, which no python test would otherwise reach.

    The old section 7 hardcoded five route names — three of which did not exist on
    the app it was pointed at — and captured 1440x2000 of a 4113px page.
    """
    harness = (BACKEND_DIR.parent / "scripts" / "preview-qa.sh").read_text(encoding="utf-8")
    section = harness.split("7. SCREENSHOTS", 1)[1]
    assert "capture_full_page" in section, "harness no longer uses the full-page capturer"
    # Routes come from the app's own route table, not a guess.
    assert "src/App.tsx" in section
    assert "QA_DETAIL_ID" in section, "detail routes are not visited"
    # The viewport-only path must survive only as an explicit opt-out, and say so.
    legacy = section.split("QA_LEGACY_CHROME", 1)[1]
    assert "VIEWPORT ONLY" in legacy
