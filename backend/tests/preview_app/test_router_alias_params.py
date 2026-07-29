"""Detail aliases must never append a param to an already-dynamic path.

`assemble.py` wires `listing/:id` onto the detail component so seed cards linking
`/gallery/<slug>` resolve. But the listing regex also matches `/gallery/:id`, so
the loop appended a second param and minted `/gallery/:id/:id` — the same param
name twice, which React Router cannot bind meaningfully (the second silently
wins). Request 38 shipped `/gallery/:id/:id`, `/gallery/:id/:slug` and
`/collection/:slug/:slug` this way, on top of an architect route table that had
already been normalized.
"""
from __future__ import annotations

import re

from app.application.preview_app.assemble import write_app_tsx
from app.infrastructure.templating.renderer import get_template_renderer

_PATH_RE = re.compile(r'<Route\s+path="([^"]+)"')


def _routes_for(architect: dict, tmp_path) -> list[str]:
    """Render App.tsx for `architect`. Page files must exist — `_resolve_page`
    reads the workspace, and a missing file silently drops the route."""
    workspace = tmp_path / "ws"
    pages = workspace / "src" / "pages"
    pages.mkdir(parents=True)
    for route in architect["routes"]:
        component = route["component"]
        (pages / f"{component}.tsx").write_text(
            f"export default function {component}() {{ return <div />; }}\n",
            encoding="utf-8",
        )
    write_app_tsx(workspace, architect, get_template_renderer())
    found = _PATH_RE.findall((workspace / "src" / "App.tsx").read_text(encoding="utf-8"))
    assert len(found) > 1, (
        f"fixture produced no routes ({found}); every assertion below would pass "
        "vacuously, so the fixture is wrong rather than the code"
    )
    return found


def _architect(paths: list[tuple[str, str]]) -> dict:
    return {
        "routes": [
            {
                "path": path,
                "component_file": f"src/pages/{component}.tsx",
                "component": component,
                "surface": "public",
            }
            for path, component in paths
        ],
        "files_to_generate": [],
        "roles": [],
    }


# The real shape that produced the malformed paths in request 38.
_REQUEST_38 = [
    ("/", "HomePage"),
    ("/gallery", "GalleryHomePage"),
    ("/gallery/:id", "ArtworkDetailPage"),
    ("/collections", "CollectionsListPage"),
    ("/collection/:slug", "CollectionDetailPage"),
    ("/painting/:slug", "PaintingDetailPage"),
    ("/about", "AboutJeannePage"),
]


def test_no_route_repeats_a_param_name(tmp_path) -> None:
    routes = _routes_for(_architect(_REQUEST_38), tmp_path)
    offenders = [
        path
        for path in routes
        if len(re.findall(r":([A-Za-z0-9_]+)", path))
        != len(set(re.findall(r":([A-Za-z0-9_]+)", path)))
    ]
    assert not offenders, f"routes repeat a param name: {offenders} (all: {routes})"


def test_no_alias_is_appended_to_an_already_dynamic_path(tmp_path) -> None:
    routes = _routes_for(_architect(_REQUEST_38), tmp_path)
    for bad in ("/gallery/:id/:id", "/gallery/:id/:slug", "/collection/:slug/:slug"):
        assert bad not in routes, f"{bad} was minted from an already-dynamic listing path"


def test_param_free_listings_still_get_detail_aliases(tmp_path) -> None:
    """The guard must not disable the feature it protects."""
    routes = _routes_for(_architect(_REQUEST_38), tmp_path)
    assert "/gallery/:slug" in routes or "/gallery/:id" in routes, (
        "a param-free listing must still receive a detail alias so seed cards resolve; "
        f"got {routes}"
    )


def test_nesting_depth_stays_sane(tmp_path) -> None:
    routes = _routes_for(_architect(_REQUEST_38), tmp_path)
    deep = [p for p in routes if p.count(":") > 1]
    assert not deep, f"no generated route should need two params: {deep}"
