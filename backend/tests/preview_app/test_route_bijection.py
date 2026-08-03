"""Phase 2 DoD 7 — the route/page mapping, and the two places it is not a bijection.

The DoD row is two claims:

  1. ``len(_smoke_routes(architect))`` equals the count of non-wildcard routes with
     a page file;
  2. ``catalogue_route_for_file`` is injective.

Measured over the 42 archived runs in ``docs/evidence/architect-routes.json``
(``backend/scripts/measure/route_bijection.py``): claim 1 fails on **31 of 42**
runs, leaving **79 of 553** declared routes never smoke-loaded, and claim 2 fails
on **11 of 42**. Neither is asserted as a passing row here — the row is open. What
is asserted is the part of it that was a *silent* defect and is now fixed:

  - a URL the router serves is no longer dropped from the smoke pass because some
    other route reached its component file first, and
  - what the 12-route cap does skip is counted and published, instead of
    ``render_pages_checked`` reading as though every page was loaded.

Every case here is the shape of a real run. Requests 22, 70 and 85 are the
duplicate-component runs; request 33 is the orphaned-page run.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.preview_app.assemble import unrouted_page_files
from app.application.preview_app.catalogue_contract.slots import catalogue_route_for_file
from app.application.preview_app.pipeline.finalize import (
    _SMOKE_MAX_ROUTES,
    _render_smoke_check,
    _smoke_routes,
    smoke_eligible_routes,
)


def _route(path: str, component: str, surface: str = "public", **extra: object) -> dict:
    return {"path": path, "component_file": component, "surface": surface, **extra}


# --------------------------------------------------------------------------- #
# DoD 7a — the count identity, and the two things that break it
# --------------------------------------------------------------------------- #

def test_under_the_cap_every_declared_route_is_smoke_loaded() -> None:
    """The DoD row's own identity, on the 11 of 42 archived runs where it holds."""
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx"),
            _route("/gallery", "src/pages/GalleryPage.tsx"),
            _route("/gallery/:id", "src/pages/ArtworkDetailPage.tsx"),
            _route("/about", "src/pages/AboutPage.tsx"),
            _route("/admin/dashboard", "src/pages/admin/DashboardPage.tsx", "ops"),
            {"path": "*", "component_file": "src/pages/HomePage.tsx"},
            {"path": "/orphan", "component_file": ""},
        ]
    }

    eligible = smoke_eligible_routes(architect)
    smoke = _smoke_routes(architect)

    assert len(eligible) == 5, "the wildcard and the file-less route are not pages"
    assert len(smoke) == len(eligible)


def test_a_second_url_on_one_page_file_is_still_smoke_loaded() -> None:
    """Request 22's shape: `/artwork` and `/gallery/:id` on one detail component.

    Deduping by component loaded whichever came first and left the other unloaded —
    and the un-parameterized `/artwork` is exactly the render condition that fails,
    because there is no `:id` for the page to resolve. 12 URLs across 11 of the 42
    archived runs were dropped this way, all of them served by the shipped router.
    """
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx"),
            _route("/artwork", "src/pages/ArtworkDetailPage.tsx"),
            _route("/gallery/:id", "src/pages/ArtworkDetailPage.tsx"),
        ]
    }

    urls = [url for url, _c, _s in _smoke_routes(architect)]

    assert urls == ["/", "/artwork", "/gallery/1"]


def test_an_alias_url_never_displaces_an_unchecked_page_at_the_cap() -> None:
    """Request 85's shape, scaled to the cap: 17 files under 18 routes.

    Loading a second URL for a page already covered must not cost a page that has
    not been covered at all, so aliases sort behind every first sighting — public
    aliases behind *ops* first sightings too, because an uninspected ops page can
    crash and a second look at a checked component cannot.
    """
    routes = [_route("/home", "src/pages/HomePage.tsx")]
    routes += [
        _route(f"/p{i}", f"src/pages/Page{i}.tsx") for i in range(_SMOKE_MAX_ROUTES - 2)
    ]
    routes.append(_route("/admin/ops", "src/pages/admin/OpsPage.tsx", "ops"))
    routes.append(_route("/", "src/pages/HomePage.tsx"))

    smoke = _smoke_routes(architect := {"routes": routes})

    assert len(smoke) == _SMOKE_MAX_ROUTES
    assert len(smoke_eligible_routes(architect)) == _SMOKE_MAX_ROUTES + 1
    components = [component for _u, component, _s in smoke]
    assert len(set(components)) == _SMOKE_MAX_ROUTES, "every slot is a distinct page"
    assert "src/pages/admin/OpsPage.tsx" in components, "an ops page outranks an alias"
    assert "/" not in [url for url, _c, _s in smoke]


def test_the_cap_reports_what_it_skipped() -> None:
    """`render_pages_checked` alone reads as "every page rendered".

    On request 91 it meant 12 of 19 and nothing recorded the other 7. The
    denominator is the fix, not a larger cap: the smoke pass runs post-deadline
    inside the reserve 1.11 is already fighting.
    """
    architect = {
        "routes": [
            _route(f"/p{i}", f"src/pages/Page{i}.tsx") for i in range(19)
        ]
    }

    eligible = smoke_eligible_routes(architect)
    smoke = _smoke_routes(architect)

    assert len(eligible) == 19
    assert len(smoke) == _SMOKE_MAX_ROUTES
    assert len(eligible) - len(smoke) == 7


def test_the_smoke_report_publishes_the_denominator_it_measured_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive the stage, not just the route list.

    Session 7 shipped six tests that could not fail, and half of them asked "given
    a reason, does the field say so" while nothing asked whether anything set a
    reason. `_smoke_routes` returning a short list is only a defect because
    `_render_smoke_check` publishes its length as coverage, so the assertion has to
    come from the stage.
    """
    import app.application.preview_app.screenshot as screenshot

    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>")
    captured: list[str] = []

    def _fake_capture(base_url: str, targets):
        captured.extend(url for url, _png in targets)
        return [SimpleNamespace(ok=True, render_error="") for _t in targets]

    monkeypatch.setattr(screenshot, "capture_routes_visual", _fake_capture)
    ctx = SimpleNamespace(
        workspace=str(tmp_path),
        base_path="/preview/1",
        db=None,
        request_id=1,
        industry="hospitality",
        template_renderer=None,
    )
    architect = {
        "routes": [_route(f"/p{i}", f"src/pages/Page{i}.tsx") for i in range(19)]
    }

    report = _render_smoke_check(ctx, architect, "Brand")

    assert len(captured) == _SMOKE_MAX_ROUTES
    assert report["checked"] == _SMOKE_MAX_ROUTES
    assert report["eligible"] == 19
    assert report["skipped"] == 7


def test_one_page_crashing_under_two_urls_is_stubbed_once_and_names_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cost of loading a component twice: it can now report twice.

    The crash map is keyed by component because the repair writes a *file*. Two
    failing URLs on one file are one stub and one message, and the message names
    the URL that failed first rather than whichever happened to be probed last.
    """
    import app.application.preview_app.build as build
    import app.application.preview_app.fallback as fallback
    import app.application.preview_app.pipeline.finalize as finalize
    import app.application.preview_app.screenshot as screenshot

    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>")
    stubbed: list[str] = []
    details: list[str] = []

    def _fake_capture(base_url: str, targets):
        return [
            SimpleNamespace(ok=False, render_error=f"boom at {url}")
            for url, _png in targets
        ]

    monkeypatch.setattr(screenshot, "capture_routes_visual", _fake_capture)
    monkeypatch.setattr(
        fallback,
        "write_safe_stub",
        lambda ws, component, **kw: stubbed.append(component),
    )
    monkeypatch.setattr(build, "run_build", lambda *a, **kw: (True, ""))
    monkeypatch.setattr(
        finalize,
        "_emit",
        lambda *a, **kw: details.append(str(kw.get("detail", ""))),
    )
    ctx = SimpleNamespace(
        workspace=str(tmp_path),
        base_path="/preview/1",
        db=None,
        request_id=1,
        industry="art",
        template_renderer=None,
    )
    architect = {
        "routes": [
            _route("/artwork", "src/pages/ArtworkDetailPage.tsx"),
            _route("/gallery/:id", "src/pages/ArtworkDetailPage.tsx"),
        ]
    }

    report = _render_smoke_check(ctx, architect, "Brand")

    assert report["checked"] == 2, "both URLs were loaded"
    assert report["crashed"] == ["src/pages/ArtworkDetailPage.tsx"]
    assert stubbed == ["src/pages/ArtworkDetailPage.tsx"], "one file, one stub"
    assert report["stubbed"] == ["src/pages/ArtworkDetailPage.tsx"]
    assert details == ["/artwork: boom at /artwork"], "the first crash is the reported one"


def test_a_smoke_pass_that_never_ran_reports_every_route_skipped(tmp_path: Path) -> None:
    """No `dist/` means no page was loaded, and `skipped` has to say 19, not 0.

    `checked: 0` beside `skipped: 0` reads as "there was nothing to check".
    """
    architect = {
        "routes": [_route(f"/p{i}", f"src/pages/Page{i}.tsx") for i in range(19)]
    }
    ctx = SimpleNamespace(
        workspace=str(tmp_path),
        base_path="/preview/1",
        db=None,
        request_id=1,
        industry="hospitality",
        template_renderer=None,
    )

    report = _render_smoke_check(ctx, architect, "Brand")

    assert report == {
        "checked": 0,
        "eligible": 19,
        "skipped": 19,
        "crashed": [],
        "stubbed": [],
        "unresolved": [],
    }


# --------------------------------------------------------------------------- #
# DoD 7b — injectivity, and what the loser costs
# --------------------------------------------------------------------------- #

def test_two_routes_on_one_page_file_leave_the_second_contract_unreachable() -> None:
    """Request 70's shape: `/owner/artworks/new` and `/owner/artworks/:id/edit`.

    Both ship in `App.tsx`, both are `ArtworkEditPage.tsx`, and they carry
    *different* `app_spec_page_id`s. `catalogue_route_for_file` is a file→route
    lookup over a relation that is not one-to-one, so it hands back the first
    declaration and the second route's contract cannot be looked up by any of the
    six callers that resolve a file to its route.

    This is the open half of DoD 7 and the assertion says so: it pins the current
    behaviour and names the cost, so that closing it in Phase 2 turns this test red
    rather than leaving it quietly true.
    """
    first = _route(
        "/owner/artworks/new",
        "src/pages/owner/ArtworkEditPage.tsx",
        "ops",
        app_spec_page_id="admin-artwork-new",
    )
    second = _route(
        "/owner/artworks/:id/edit",
        "src/pages/owner/ArtworkEditPage.tsx",
        "ops",
        app_spec_page_id="admin-artwork-edit",
    )
    architect = {"routes": [first, second]}

    resolved = catalogue_route_for_file("src/pages/owner/ArtworkEditPage.tsx", architect)

    assert resolved is first
    assert resolved is not second
    shadowed = [
        r
        for r in smoke_eligible_routes(architect)
        if catalogue_route_for_file(r["component_file"], architect) is not r
    ]
    assert shadowed == [second], "one route in this pair has no reachable contract"


def test_the_lookup_is_injective_when_every_route_has_its_own_page() -> None:
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx"),
            _route("/gallery", "src/pages/GalleryPage.tsx"),
            _route("/gallery/:id", "src/pages/ArtworkDetailPage.tsx"),
        ]
    }

    shadowed = [
        r
        for r in smoke_eligible_routes(architect)
        if catalogue_route_for_file(r["component_file"], architect) is not r
    ]

    assert shadowed == []


# --------------------------------------------------------------------------- #
# the other direction — a page file no route declares
# --------------------------------------------------------------------------- #

def test_a_generated_page_no_route_declares_is_reported(tmp_path: Path) -> None:
    """Request 33: `AiFeaturesPage.tsx` shipped, `/ai-features` in the nav, no route.

    The panel's link fell through `path="*"` to home, so a dead link behaved like a
    working one, and the page it named was bundled, typechecked and never served.
    """
    pages = tmp_path / "src" / "pages"
    (pages / "admin").mkdir(parents=True)
    for rel in (
        "HomePage.tsx",
        "GalleryPage.tsx",
        "AiFeaturesPage.tsx",
        "admin/AdminDashboardPage.tsx",
    ):
        (pages / rel).write_text("export default function P() { return null; }\n")
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx"),
            _route("/gallery", "src/pages/GalleryPage.tsx"),
            _route("/admin", "src/pages/admin/AdminDashboardPage.tsx", "ops"),
        ]
    }

    assert unrouted_page_files(tmp_path, architect) == ["src/pages/AiFeaturesPage.tsx"]


def test_a_template_seed_page_left_unrouted_counts_too(tmp_path: Path) -> None:
    """Request 71 renamed the home page and left the template's own behind.

    35 of the 42 archived runs ship an unrouted `admin/AdminDashboardPage.tsx` or
    `HomePage.tsx`. Counting them is deliberate — this is a census, and excluding
    the common case is how DoD 8 nearly shipped an allowlist that raised in
    production.
    """
    pages = tmp_path / "src" / "pages"
    pages.mkdir(parents=True)
    for rel in ("HomePage.tsx", "GalleryHomePage.tsx"):
        (pages / rel).write_text("export default function P() { return null; }\n")
    architect = {
        "routes": [
            _route("/", "src/pages/GalleryHomePage.tsx"),
            _route("/gallery", "src/pages/GalleryHomePage.tsx"),
        ]
    }

    assert unrouted_page_files(tmp_path, architect) == ["src/pages/HomePage.tsx"]


def test_windows_and_dot_slash_route_paths_still_match_their_page(tmp_path: Path) -> None:
    """The lookup canonicalizes; the census has to canonicalize the same way."""
    pages = tmp_path / "src" / "pages"
    pages.mkdir(parents=True)
    (pages / "HomePage.tsx").write_text("export default function P() { return null; }\n")
    architect = {"routes": [_route("/", r".\src\pages\HomePage.tsx")]}

    assert unrouted_page_files(tmp_path, architect) == []
