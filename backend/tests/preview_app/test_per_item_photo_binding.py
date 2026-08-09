"""Request 165: the cake gallery was full of bread.

The binding fired (`8 catalogue photo(s) bound`) and bound the wrong pictures,
because it ranks a pool searched for the *business* — a bakery's pool is bread,
so every cake title matched bread. The owner-approved fix: ask the photo index
with each item's own words, so a celebration cake's candidates are photographs
of celebration cakes.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.catalogue_contract.photo_binding import (
    bind_per_title_photos,
)
from app.application.services.industry_images import _title_query, item_photos_by_title

_SLOTS = tuple(f"item{i}" for i in range(1, 25))


def test_request165_each_item_gets_a_photo_from_its_own_search():
    titles = ["Celebration Cake", "Baguette Tradition", "Almond Croissant"]
    per_title = [
        [("https://p/cake1", "a tiered celebration cake"), ("https://p/cake2", "cake")],
        [("https://p/bread1", "baguette on a rack"), ("https://p/bread2", "bread loaf")],
        [("https://p/croissant1", "almond croissant"), ("https://p/bread1", "baguette on a rack")],
    ]
    bound = bind_per_title_photos(titles, per_title, _SLOTS)
    assert bound["item1"] == "https://p/cake1"
    assert bound["item2"] == "https://p/bread1"
    assert bound["item3"] == "https://p/croissant1"


def test_an_own_query_photo_beats_any_cross_match():
    # The cross-match scores tokens; the own-query photo's alt shares none.
    titles = ["Celebration Cake", "Rye Levain"]
    per_title = [
        [("https://p/own", "beautifully iced dessert")],  # no shared token
        [("https://p/rye", "rye levain crumb"), ("https://p/cake-word", "a cake shape loaf")],
    ]
    bound = bind_per_title_photos(titles, per_title, _SLOTS)
    # "cake" appears in the *other* item's candidate alt; own-query still wins.
    assert bound["item1"] == "https://p/own"
    assert bound["item2"] == "https://p/rye"


def test_shared_queries_never_share_a_photograph():
    titles = ["Almond Croissant", "Butter Croissant"]
    shared = [("https://p/c1", "croissant"), ("https://p/c2", "croissant on a plate")]
    bound = bind_per_title_photos(titles, [list(shared), list(shared)], _SLOTS)
    assert len(bound) == 2
    assert len(set(bound.values())) == 2


def test_an_item_whose_search_returned_nothing_falls_back_to_cross_match():
    titles = ["Celebration Cake", "Mystery Special"]
    per_title = [
        [("https://p/cake", "celebration cake"), ("https://p/extra", "pastry tray")],
        [],
    ]
    bound = bind_per_title_photos(titles, per_title, _SLOTS)
    assert bound["item1"] == "https://p/cake"
    # Nothing matched "Mystery Special" by tokens; the spare pool fills it.
    assert bound["item2"] == "https://p/extra"


def test_no_candidates_changes_nothing():
    assert bind_per_title_photos(["A Thing"], [[]], _SLOTS) == {}
    assert bind_per_title_photos([], [], _SLOTS) == {}


def test_the_query_is_the_items_own_words():
    assert _title_query("100% Rye Levain") == "rye levain"
    assert _title_query("Almond Croissant") == "almond croissant"
    assert _title_query("!!") == ""


def test_the_dispatcher_prefers_per_item_results_over_the_pool(monkeypatch, tmp_path):
    from app.application.preview_app.catalogue_contract import photo_binding as pb

    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "src" / "data" / "mock.ts").write_text(
        'export const seed = { items: [{"title": "Celebration Cake"}] };',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_by_title",
        lambda *_a, **_k: [[("https://p/cake", "celebration cake")]],
    )
    # The pooled search must not even be asked when per-item results exist.
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_for_titles",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("pool was queried")),
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_slot_names",
        lambda: ("item1",),
    )
    assert pb.bind_catalogue_photos(tmp_path, "bakery") == {
        "item1": "https://p/cake"
    }


def test_no_api_key_yields_empty_lists_per_title(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.PEXELS_API_KEY", "", raising=False
    )
    result = item_photos_by_title(["Celebration Cake", "Baguette"], "bakery")
    assert result == [[], []]


def test_one_search_per_distinct_subject(monkeypatch):
    calls: list[str] = []

    def fake_search(api_key, query, *, page, per_page, timeout=8.0):
        calls.append(query)
        return [
            {
                "src": {"large": f"https://p/{len(calls)}", "medium": f"https://p/{len(calls)}"},
                "alt": query,
            }
        ]

    monkeypatch.setattr(
        "app.core.config.settings.PEXELS_API_KEY", "k", raising=False
    )
    monkeypatch.setattr(
        "app.application.services.industry_images._search_pexels", fake_search
    )
    result = item_photos_by_title(
        ["Almond Croissant", "Almond Croissant", "Celebration Cake"], "bakery"
    )
    assert len(calls) == 2, f"expected deduped queries, got {calls}"
    assert result[0] == result[1]
    assert result[2] != result[0]
    # The search text carries the item's OWN words — that is the whole fix.
    # Request 165: a query composed from the business alone returns bread for
    # every cake.
    assert any("croissant" in q for q in calls), calls
    assert any("celebration cake" in q for q in calls), calls
    # The industry word rides along to disambiguate the subject.
    assert all("bakery" in q for q in calls)
