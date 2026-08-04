"""A scaffold CTA may only point where the app actually goes.

`ensure_seed_scaffold_fields` fills `seed.hero` whenever the AI's mock synthesis
drops it, and it filled it with two literals:

    primaryCta:   { label: 'Explore the collection', href: '/gallery' }
    secondaryCta: { label: 'Talk to us',             href: '/contact#inquire' }

A **twelve-table Neapolitan trattoria** shipped "Explore the collection" that
way (request 95), and the string is verbatim in **7 of 64 archived workspaces**
— 20, 66, 78, 81, 85, 93, 95 — across unrelated industries. Request 95's
secondary CTA had already been rewritten to `/` by the dead-link guard, so the
shipped button read "Talk to us" and reloaded the home page.

Two defects wearing one literal, and only one of them is vocabulary:

* *"the collection"* is one industry's word for its artifact applied to every
  business. A restaurant has a menu; a lodge has rooms.
* `/gallery` and `/contact#inquire` are **routes the app may not serve.**

The fix reads no industry and cannot: the destination is whichever public route
the app itself declares first by `_nav_rank`, and the label is that page's own
title. A business with a collection gets one; a business without gets whatever
it does have. That is the same rule `AiFeaturePanel` was fixed with in
`430453a` after its hardcoded `/ai-features` turned out to be dead in 5 of 41
workspaces.
"""
from __future__ import annotations

from app.application.preview_app.safety.mock_data import (
    ensure_seed_scaffold_fields,
    scaffold_hero_ctas,
)

#: Request 95's real route table, which is what produced the trattoria's
#: "Explore the collection". It *does* declare `/gallery` — the point is that
#: the CTA must be the app's own first public destination whatever that is,
#: not a literal that happens to be right for one industry in seven.
_RESTAURANT = {
    "routes": [
        {"path": "/", "title": "Home"},
        {"path": "/menu", "title": "Our Menu"},
        {"path": "/reservations", "title": "Reservations"},
        {"path": "/private-events", "title": "Private Events"},
        {"path": "/my-reservations", "title": "My Reservations"},
        {"path": "/owner/dashboard", "title": "Dashboard"},
        {"path": "/gallery", "title": "Gallery"},
        {"path": "/gallery/:id", "title": "Artwork Detail"},
    ]
}

_LODGE = {
    "routes": [
        {"path": "/", "title": "Home"},
        {"path": "/rooms", "title": "Rooms"},
        {"path": "/activities", "title": "Activities"},
        {"path": "/rooms/:roomId", "title": "Room Detail"},
    ]
}


#: Request 95 minus the two pages the architect should not have invented. The
#: fix here does NOT stop a restaurant being given a gallery — that is the plan
#: and architect layer, and the roadmap assigns it to 2.1-2.3. It stops the
#: *scaffold* naming an artifact type the app never claimed.
_RESTAURANT_WITHOUT_GALLERY = {
    "routes": [r for r in _RESTAURANT["routes"] if not str(r["path"]).startswith("/gallery")]
}


def test_no_industry_string_decides_the_cta() -> None:
    """The rule that makes this general, asserted directly.

    Two businesses, no industry named anywhere, and each gets its own first
    public destination. Anything keyed on the word "restaurant" would be the
    `generic`-industry defect wearing a new hat.
    """

    restaurant_primary, _ = scaffold_hero_ctas(_RESTAURANT_WITHOUT_GALLERY, "Osteria Vinci")
    lodge_primary, _ = scaffold_hero_ctas(_LODGE, "Cedar Point Lodge")

    assert restaurant_primary["href"] == "/menu"
    assert lodge_primary["href"] == "/rooms"
    assert "collection" not in restaurant_primary["label"].lower()
    assert "collection" not in lodge_primary["label"].lower()


def test_a_declared_gallery_is_linked_in_the_apps_own_words() -> None:
    """The limit of this fix, stated as an assertion rather than a hope.

    Request 95 really does declare `/gallery` and `/gallery/:id`, so the CTA
    points there — correctly, because the page exists and a CTA that avoided
    it would be inventing a second opinion about the app's own route table.
    What changes is the wording: "Gallery", which is what the architect called
    the page, instead of "Explore the collection", which is what a literal in
    this module called it for every business in the corpus.
    """

    primary, _ = scaffold_hero_ctas(_RESTAURANT, "Osteria Vinci")

    assert primary == {"label": "Gallery", "href": "/gallery"}


def test_the_cta_only_points_where_the_app_declares_a_route() -> None:
    for architect in (_RESTAURANT, _LODGE):
        declared = {str(r["path"]) for r in architect["routes"]}
        primary, secondary = scaffold_hero_ctas(architect, "Brand")
        assert primary["href"] in declared
        assert secondary["href"] in declared or secondary["href"] == "/"


def test_a_parameterized_route_is_never_a_cta_destination() -> None:
    """`/gallery/:id` and `/rooms/:roomId` render with nothing to resolve.

    They are also the alias-inflation class the roadmap tracks under DoD 7 —
    request 96 serves `/rooms/:roomId`, `/rooms/:id` and `/rooms/:slug` for one
    page — so a CTA that could pick one would pick arbitrarily among three.
    """

    for architect in (_RESTAURANT, _LODGE):
        for cta in scaffold_hero_ctas(architect, "Brand"):
            assert ":" not in cta["href"]


def test_an_ops_only_app_falls_back_to_something_neutral_not_to_a_guess() -> None:
    """No public destination is a real shape — an internal desk has none.

    Inventing `/gallery` for it is precisely the defect; `/` is the one route
    every generated app serves.
    """

    primary, secondary = scaffold_hero_ctas(
        {"routes": [{"path": "/", "title": "Home"}, {"path": "/admin", "title": "Admin"}]},
        "Brand",
    )

    assert primary == {"label": "See what we offer", "href": "/"}
    assert secondary == {"label": "See what we offer", "href": "/"}


def test_no_architect_at_all_still_produces_a_live_link() -> None:
    primary, secondary = scaffold_hero_ctas(None, "Brand")

    assert primary["href"] == "/"
    assert secondary["href"] == "/"


def test_the_two_ctas_do_not_repeat_one_destination() -> None:
    primary, secondary = scaffold_hero_ctas(_RESTAURANT, "Osteria Vinci")

    assert primary["href"] != secondary["href"]


def test_the_scaffold_writes_the_derived_cta_into_the_mock(monkeypatch) -> None:
    """The seam, not the helper.

    `scaffold_hero_ctas` can be perfectly right while `ensure_seed_scaffold_fields`
    goes on emitting the literal — which is how a fix lands in a function
    nothing calls. This drives the producer.
    """

    mock = "export const seed = {\n  items: [],\n};\n"
    out = ensure_seed_scaffold_fields(
        mock, brand_name="Osteria Vinci", architect=_RESTAURANT_WITHOUT_GALLERY
    )

    assert "Explore the collection" not in out
    # The `cta` block carried the same literal twice more, and the first
    # version of this test found them by failing on it.
    assert "/contact#inquire" not in out
    assert "primaryCta: { label: 'Our Menu', href: '/menu' }" in out


def test_the_pipeline_hands_the_scaffold_its_architect(tmp_path) -> None:
    """One seam further up, and it survived a sweep without this test.

    `scaffold_hero_ctas` can be right and `ensure_seed_scaffold_fields` can emit
    it faithfully, and the CTA is still a guess if `ensure_mock_exports` — the
    function the pipeline actually calls — does not pass the architect along.
    Dropping that one keyword argument reverts the whole fix silently, because
    the default is `None` and `None` produces a perfectly valid neutral CTA.
    """

    from app.application.preview_app.safety.mock_data import ensure_mock_exports

    data = tmp_path / "src" / "data"
    data.mkdir(parents=True)
    (data / "mock.ts").write_text("export const seed = {\n  items: [],\n};\n", encoding="utf-8")

    ensure_mock_exports(tmp_path, _RESTAURANT_WITHOUT_GALLERY, {}, {}, "Osteria Vinci")

    written = (data / "mock.ts").read_text(encoding="utf-8")
    assert "href: '/menu'" in written
    assert "See what we offer" not in written, "the architect never reached the scaffold"


def test_a_seed_that_already_has_a_hero_is_untouched() -> None:
    """Request 96 wrote its own hero and must keep it. Only missing keys are
    added — re-declaring one is how request 43 shipped six TS1117 duplicates."""

    mock = (
        "export const seed = {\n"
        "  hero: { headline: 'Your Adirondack Escape Starts Here' },\n"
        "};\n"
    )
    out = ensure_seed_scaffold_fields(mock, brand_name="Cedar Point Lodge", architect=_LODGE)

    assert out.count("hero:") == 1
    assert "Your Adirondack Escape Starts Here" in out


def test_a_quote_in_a_page_title_cannot_break_the_generated_module() -> None:
    """The labels are now data-derived, so they carry whatever the model wrote."""

    architect = {"routes": [{"path": "/menu", "title": "Nonna's Menu"}]}
    mock = "export const seed = {\n  items: [],\n};\n"
    out = ensure_seed_scaffold_fields(mock, brand_name="Brand", architect=architect)

    assert "\\'" in out
    assert "label: 'Nonna\\'s Menu'" in out
