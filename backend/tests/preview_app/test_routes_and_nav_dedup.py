"""Route table + navigation normalization: no duplicate, malformed, or dead entries."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.preview_app.pipeline.architect_normalize import (
    _canonical_route_path,
    _normalize_route_table,
    _remap_role_default_paths,
)
from app.application.preview_app.safety.mock_data import normalize_mock_navigation


def _route(path: str, component: str, skeleton: str, intent: str) -> dict:
    return {
        "path": path,
        "component_file": component,
        "skeleton_id": skeleton,
        "page_intent": intent,
        "surface": "ops" if skeleton.startswith("ops") else "public",
        "section_slots": [],
    }


def _jeanne_architect() -> dict:
    """Verbatim route table extracted from generated preview app 36."""
    manage = "src/pages/admin/ManageArtworksPage.tsx"
    return {
        "routes": [
            _route("/", "src/pages/HomePage.tsx", "public-home", "landing"),
            _route("/works", "src/pages/WorksPage.tsx", "public-catalog", "listing"),
            _route(
                "/works/:slug",
                "src/pages/ArtworkDetailPage.tsx",
                "public-detail",
                "detail",
            ),
            _route("/about", "src/pages/AboutPage.tsx", "public-utility", "about"),
            _route("/contact", "src/pages/ContactPage.tsx", "public-utility", "contact"),
            _route(
                "/admin/dashboard",
                "src/pages/admin/DashboardPage.tsx",
                "ops-dashboard",
                "ops",
            ),
            _route("/admin/artworks", manage, "ops-list", "ops"),
            _route("/admin/:id", manage, "ops-list", "ops"),
            _route("/admin/:slug", manage, "ops-list", "ops"),
            _route(
                "/admin/artworks/edit/:id",
                "src/pages/admin/EditArtworkPage.tsx",
                "ops-detail",
                "ops",
            ),
            _route(
                "/admin/about",
                "src/pages/admin/EditAboutPage.tsx",
                "ops-settings",
                "ops",
            ),
            _route("/gallery", "src/pages/GalleryPage.tsx", "public-catalog", "listing"),
            _route("/works/:id", manage, "public-detail", "detail"),
            _route("/works/:slug/:id", manage, "public-detail", "detail"),
            _route("/works/:slug/:slug", manage, "public-detail", "detail"),
            _route("/gallery/:id", manage, "public-detail", "detail"),
            _route("/gallery/:slug", manage, "public-detail", "detail"),
        ],
        "roles": [
            {"id": "visitor", "defaultPath": "/"},
            {"id": "owner", "defaultPath": "/works"},
        ],
    }


def test_canonical_route_path_drops_unbindable_dynamic_segments():
    assert _canonical_route_path("/works/{slug}") == "/works/:slug"
    assert _canonical_route_path("/works/:slug/:slug") == "/works/:slug"
    assert _canonical_route_path("/works/:slug/:id") == "/works/:slug"
    assert _canonical_route_path("/admin/artworks/edit/:id") == "/admin/artworks/edit/:id"


def test_duplicate_concept_routes_collapse_to_one_canonical_path():
    architect = _jeanne_architect()
    _normalize_route_table(architect)
    paths = [route["path"] for route in architect["routes"]]
    assert paths.count("/gallery") == 1
    assert "/works" not in paths
    assert sorted(paths) == [
        "/",
        "/about",
        "/admin/about",
        "/admin/artworks",
        "/admin/artworks/edit/:id",
        "/admin/dashboard",
        "/contact",
        "/gallery",
        "/gallery/:slug",
    ]


def test_no_duplicate_param_names_ambiguous_siblings_or_shadowed_literals():
    architect = _jeanne_architect()
    _normalize_route_table(architect)
    paths = [route["path"] for route in architect["routes"]]
    shapes = [
        "/".join("*" if s.startswith(":") else s for s in path.split("/"))
        for path in paths
    ]
    assert len(shapes) == len(set(shapes))
    for path in paths:
        params = [s for s in path.split("/") if s.startswith(":")]
        assert len(params) == len(set(params))
    assert "/admin/:id" not in paths and "/admin/:slug" not in paths


def test_literal_routes_are_declared_before_dynamic_siblings():
    architect = _jeanne_architect()
    _normalize_route_table(architect)
    paths = [route["path"] for route in architect["routes"]]
    first_dynamic = next(i for i, p in enumerate(paths) if ":" in p)
    assert all(":" not in p for p in paths[:first_dynamic])
    assert all(":" in p for p in paths[first_dynamic:])


def test_distinct_concepts_with_matching_skeletons_are_not_collapsed():
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx", "public-home", "landing"),
            _route(
                "/services", "src/pages/ServicesPage.tsx", "public-catalog", "listing"
            ),
            _route("/team", "src/pages/TeamPage.tsx", "public-catalog", "listing"),
            _route("/journal", "src/pages/JournalPage.tsx", "public-catalog", "listing"),
        ],
        "roles": [],
    }
    _normalize_route_table(architect)
    assert [route["path"] for route in architect["routes"]] == [
        "/",
        "/services",
        "/team",
        "/journal",
    ]


def test_synonym_routes_with_different_faces_are_not_collapsed():
    architect = {
        "routes": [
            _route("/", "src/pages/HomePage.tsx", "public-home", "landing"),
            _route("/works", "src/pages/WorksPage.tsx", "public-catalog", "listing"),
            _route(
                "/gallery", "src/pages/GalleryPage.tsx", "public-detail", "detail"
            ),
        ],
        "roles": [],
    }
    _normalize_route_table(architect)
    assert {route["path"] for route in architect["routes"]} == {
        "/",
        "/works",
        "/gallery",
    }


def test_role_default_path_follows_a_collapsed_route():
    architect = _jeanne_architect()
    remap = _normalize_route_table(architect)
    _remap_role_default_paths(architect, remap)
    paths = {route["path"] for route in architect["routes"]}
    for role in architect["roles"]:
        assert role["defaultPath"] in paths
    assert next(r for r in architect["roles"] if r["id"] == "owner")["defaultPath"] == (
        "/gallery"
    )


def test_every_route_still_has_a_generated_file_entry():
    from app.application.preview_app.pipeline.architect_normalize import (
        _normalize_architect,
    )

    architect = _jeanne_architect()
    architect["files_to_generate"] = []
    _normalize_architect(architect, {"roles": []})
    file_paths = {
        (f.get("path") or "").lower()
        for f in architect["files_to_generate"]
    }
    for route in architect["routes"]:
        assert route["component_file"].lower() in file_paths


def _write_mock(tmp_path: Path, navigation: dict) -> Path:
    data = tmp_path / "src/data"
    data.mkdir(parents=True)
    mock = data / "mock.ts"
    mock.write_text(
        "export const brand = { name: 'Jeanne Kassab Art' };\n"
        f"export const navigation = {json.dumps(navigation, indent=2)};\n"
        "export const navItemsAdmin = navigation.admin;\n",
        encoding="utf-8",
    )
    return mock


def _nav_public(mock: Path) -> list[dict]:
    raw = mock.read_text(encoding="utf-8")
    body = raw.split("export const navigation = ", 1)[1]
    body = body[: body.index(";\nexport const navItemsAdmin")]
    return json.loads(body)["public"]


def test_navigation_is_deduped_by_destination_and_ordered_journey_first(tmp_path: Path):
    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "home", "path": "/", "href": "/", "label": "Home"},
                {"id": "contact", "path": "/contact", "href": "/contact",
                 "label": "Contact"},
                {"id": "about", "path": "/about", "href": "/about",
                 "label": "About Jeanne Kassab"},
                {"id": "about-2", "path": "/about", "href": "/about", "label": "About"},
                {"id": "gallery", "path": "/gallery", "href": "/gallery",
                 "label": "Gallery"},
            ],
            "admin": [],
        },
    )
    architect = {
        "routes": [
            {"path": "/"},
            {"path": "/about"},
            {"path": "/contact"},
            {"path": "/gallery"},
        ]
    }
    assert normalize_mock_navigation(tmp_path, architect, "Jeanne Kassab Art") == [
        "nav:public"
    ]
    public = _nav_public(mock)
    assert [item["href"] for item in public] == ["/", "/gallery", "/about", "/contact"]
    assert [item["label"] for item in public] == [
        "Home",
        "Gallery",
        "About",
        "Contact",
    ]


def test_navigation_drops_entries_pointing_at_removed_routes(tmp_path: Path):
    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "home", "path": "/", "href": "/", "label": "Home"},
                {"id": "works", "path": "/works", "href": "/works", "label": "Works"},
                {"id": "gallery", "path": "/gallery", "href": "/gallery",
                 "label": "Gallery"},
            ],
            "admin": [],
        },
    )
    architect = {"routes": [{"path": "/"}, {"path": "/gallery"}]}
    assert normalize_mock_navigation(tmp_path, architect, "Jeanne Kassab Art")
    assert [item["href"] for item in _nav_public(mock)] == ["/", "/gallery"]


def test_navigation_keeps_the_all_deep_admin_sidebar(tmp_path: Path):
    admin = [
        {"id": "d", "path": "/admin/dashboard", "href": "/admin/dashboard",
         "label": "Dashboard"},
        {"id": "a", "path": "/admin/artworks", "href": "/admin/artworks",
         "label": "Artworks"},
        {"id": "b", "path": "/admin/about", "href": "/admin/about", "label": "About"},
    ]
    mock = _write_mock(tmp_path, {"public": [], "admin": admin})
    architect = {
        "routes": [{"path": item["path"]} for item in admin] + [{"path": "/"}]
    }
    normalize_mock_navigation(tmp_path, architect, "Jeanne Kassab Art")
    raw = mock.read_text(encoding="utf-8")
    body = raw.split("export const navigation = ", 1)[1]
    body = body[: body.index(";\nexport const navItemsAdmin")]
    assert [item["href"] for item in json.loads(body)["admin"]] == [
        "/admin/dashboard",
        "/admin/artworks",
        "/admin/about",
    ]


def test_a_label_collision_does_not_delete_a_declared_public_route(tmp_path: Path):
    """Request 95's menu named the member page and never linked the public one.

    ``_NAV_LABEL_NOISE_RE`` strips a leading ``My ``, so ``/my-reservations``
    reduces to "Reservations" — the label ``/reservations`` also carries. The
    section then deduped on the label key and dropped whichever came second, so
    a **declared, served, public** route was absent from the menu entirely.

    The fixture puts the member route first on purpose: that is the order the
    real run had, and the order in which the naive fix (dedupe as you go) still
    loses the public page.
    """

    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "home", "path": "/", "href": "/", "label": "Home"},
                {"id": "my-reservations", "path": "/my-reservations",
                 "href": "/my-reservations", "label": "My Reservations"},
                {"id": "reservations", "path": "/reservations",
                 "href": "/reservations", "label": "Reservations"},
            ],
            "admin": [],
        },
    )
    architect = {
        "routes": [{"path": "/"}, {"path": "/my-reservations"}, {"path": "/reservations"}]
    }
    normalize_mock_navigation(tmp_path, architect, "Osteria Vinci")
    public = _nav_public(mock)
    hrefs = [item["href"] for item in public]
    assert "/reservations" in hrefs, hrefs
    assert "/my-reservations" in hrefs, hrefs
    # And the two entries must be tellable apart, which is the point of keeping
    # both. Written as a set-size check so it fails on any duplicate pair.
    labels = [item["label"] for item in public]
    assert len(set(labels)) == 3, labels


def test_two_prefixes_reducing_to_one_word_both_keep_their_full_label(tmp_path: Path):
    """Both shortened forms collide while neither full label does.

    The first sweep's fixture could not reach this — there, the two *full*
    labels collided too, so one guard explained every failure and the other
    could be deleted with the suite still green.
    """

    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "mine", "path": "/my-orders", "href": "/my-orders",
                 "label": "My Orders"},
                {"id": "manage", "path": "/orders", "href": "/orders",
                 "label": "Manage Orders"},
            ],
            "admin": [],
        },
    )
    normalize_mock_navigation(
        tmp_path, {"routes": [{"path": "/my-orders"}, {"path": "/orders"}]}, "Brand"
    )
    public = _nav_public(mock)
    assert [item["href"] for item in public] == ["/my-orders", "/orders"]
    assert [item["label"] for item in public] == ["My Orders", "Manage Orders"]


def test_a_shortened_label_never_takes_a_siblings_full_label(tmp_path: Path):
    """One entry's shortened form equals another's *full* label.

    The shortened-label counter cannot see this — the two shortened forms
    differ — so without its own fixture the second guard could be deleted with
    the suite still green. It was, on the first sweep.
    """

    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "manage-mine", "path": "/manage-my-orders",
                 "href": "/manage-my-orders", "label": "Manage My Orders"},
                {"id": "mine", "path": "/my-orders", "href": "/my-orders",
                 "label": "My Orders"},
            ],
            "admin": [],
        },
    )
    normalize_mock_navigation(
        tmp_path,
        {"routes": [{"path": "/manage-my-orders"}, {"path": "/my-orders"}]},
        "Brand",
    )
    public = _nav_public(mock)
    assert len({item["label"] for item in public}) == 2, public
    by_href = {item["href"]: item["label"] for item in public}
    assert by_href["/my-orders"] == "Orders"
    assert by_href["/manage-my-orders"] == "Manage My Orders"


def test_three_routes_sharing_a_label_all_survive_with_distinct_names(tmp_path: Path):
    """Two routes carrying the *same literal label* exhaust both candidates.

    That is the only way to reach the path-derived fallback, and without this
    fixture deleting the fallback leaves the suite green.
    """

    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "o", "path": "/orders", "href": "/orders", "label": "Orders"},
                {"id": "m", "path": "/my-orders", "href": "/my-orders",
                 "label": "My Orders"},
                {"id": "g", "path": "/manage-orders", "href": "/manage-orders",
                 "label": "My Orders"},
            ],
            "admin": [],
        },
    )
    normalize_mock_navigation(
        tmp_path,
        {"routes": [{"path": "/orders"}, {"path": "/my-orders"}, {"path": "/manage-orders"}]},
        "Brand",
    )
    public = _nav_public(mock)
    assert len(public) == 3, public
    assert len({item["label"] for item in public}) == 3, public


def test_labels_are_compared_case_and_punctuation_insensitively(tmp_path: Path):
    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "mine", "path": "/my-reservations", "href": "/my-reservations",
                 "label": "My Reservations"},
                {"id": "public", "path": "/reservations", "href": "/reservations",
                 "label": "reservations"},
            ],
            "admin": [],
        },
    )
    normalize_mock_navigation(
        tmp_path,
        {"routes": [{"path": "/my-reservations"}, {"path": "/reservations"}]},
        "Brand",
    )
    public = _nav_public(mock)
    assert len({item["label"].lower() for item in public}) == 2
    assert len(public) == 2


def test_a_genuinely_duplicate_destination_is_still_collapsed(tmp_path: Path):
    """The boundary: keeping label collisions must not stop path deduping."""

    mock = _write_mock(
        tmp_path,
        {
            "public": [
                {"id": "a", "path": "/about", "href": "/about", "label": "About Us"},
                {"id": "b", "path": "/about", "href": "/about", "label": "About"},
            ],
            "admin": [],
        },
    )
    normalize_mock_navigation(tmp_path, {"routes": [{"path": "/about"}]}, "Brand")
    assert [item["href"] for item in _nav_public(mock)] == ["/about"]


def test_navigation_normalization_never_empties_chrome(tmp_path: Path):
    mock = _write_mock(
        tmp_path,
        {"public": [{"id": "x", "path": "/gone", "href": "/gone", "label": "Gone"}]},
    )
    normalize_mock_navigation(tmp_path, {"routes": [{"path": "/"}]}, "Brand")
    assert _nav_public(mock) == [
        {"id": "x", "path": "/gone", "href": "/gone", "label": "Gone"}
    ]
