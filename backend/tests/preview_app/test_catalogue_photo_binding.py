"""A catalogue photograph depicts the item it is captioned with.

Request 73 shipped twelve works — *Whispers of the Forest*, *Coastal Serenity*,
*City Nocturne*, *River's Edge*, *Autumn Hues*, *Mountain Ascension* —
representational landscapes to a one, captioning **eight non-representational
abstracts**, several of them macro crops of paint texture. Right artifact type,
wrong artifact, and no gate in the pipeline can see it.

It was impossible by construction: `item_pool_query` composes its search from the
industry string, and it runs during planning, before any item exists. The fix is
to ask again once the seed has named them, and to use the photo index's own
`alt` text to decide which picture goes with which title.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.catalogue_contract.photo_binding import (
    bind_photos_to_titles,
    catalogue_item_titles,
    score_photo_for_title,
)

_SLOTS = ("item1", "item2", "item3", "item4")


def test_the_titles_come_out_in_the_order_the_cards_render_them():
    mock = """
export const seed = {
  items: [
    {"title": "Coastal Serenity", "price": 400},
    {"title": "City Nocturne", "price": 650},
    {"title": "Autumn Hues", "price": 300}
  ],
};
"""
    assert catalogue_item_titles(mock) == [
        "Coastal Serenity",
        "City Nocturne",
        "Autumn Hues",
    ]


def test_an_item_carrying_both_title_and_name_is_one_item():
    """The seed writes both fields for the same object; two hits is not two items."""

    mock = (
        'export const seed = { services: [\n'
        '  {"name": "Wheel true", "title": "Wheel true", "price": 30},\n'
        '  {"name": "Brake bleed", "title": "Brake bleed", "price": 45}\n'
        "] };\n"
    )
    assert catalogue_item_titles(mock) == ["Wheel true", "Brake bleed"]


def test_a_description_containing_a_bracket_does_not_truncate_the_catalogue():
    """Bracket counting, not a lazy regex — this read half a catalogue before."""

    mock = (
        'export const seed = { items: [\n'
        '  {"title": "Sourdough [large]", "note": "pain de campagne"},\n'
        '  {"title": "Rye tin", "note": "seeded"}\n'
        "] };\n"
    )
    assert catalogue_item_titles(mock) == ["Sourdough [large]", "Rye tin"]


def test_testimonials_are_not_captioned_as_catalogue_items():
    """A customer's name must never end up naming a photograph."""

    mock = (
        'export const seed = {\n'
        '  testimonials: [{"name": "Maya R.", "quote": "lovely"}],\n'
        '  items: [{"title": "Celebration cake"}, {"title": "Fruit tart"}]\n'
        "};\n"
    )
    assert catalogue_item_titles(mock) == ["Celebration cake", "Fruit tart"]


def test_the_longest_catalogue_wins_and_ties_go_to_the_first():
    """Two catalogue-shaped arrays: the cards are bound to one of them, not both.

    The longer array wins, because that is the one with a card per item. On a
    tie the earlier key in `_CATALOGUE_KEYS` keeps it — `items` before
    `services` — so the outcome does not depend on which key the seed happened
    to write first.
    """
    tie = (
        'export const seed = {\n'
        '  items: [{"title": "Loaf"}, {"title": "Bun"}],\n'
        '  services: [{"title": "Delivery"}, {"title": "Catering"}]\n'
        "};\n"
    )
    assert catalogue_item_titles(tie) == ["Loaf", "Bun"]

    services_longer = (
        'export const seed = {\n'
        '  items: [{"title": "Loaf"}],\n'
        '  services: [{"title": "Delivery"}, {"title": "Catering"}]\n'
        "};\n"
    )
    assert catalogue_item_titles(services_longer) == ["Delivery", "Catering"]


def test_a_nested_array_does_not_end_the_catalogue_early():
    """Depth counting, not "stop at the first `]`" — items carry tag arrays."""

    mock = (
        'export const seed = { items: [\n'
        '  {"title": "Sourdough", "tags": ["daily", "levain"]},\n'
        '  {"title": "Rye tin", "tags": ["seeded"]},\n'
        '  {"title": "Focaccia"}\n'
        "] };\n"
    )
    assert catalogue_item_titles(mock) == ["Sourdough", "Rye tin", "Focaccia"]


def test_a_photo_of_the_thing_beats_a_photo_of_something_else():
    assert score_photo_for_title(
        "Coastal Serenity", "a calm coastal seascape at dawn"
    ) > score_photo_for_title("Coastal Serenity", "a bowl of fruit on a table")


def test_a_title_no_word_of_which_appears_scores_nothing():
    assert score_photo_for_title("Autumn Hues", "a steel bridge at night") == 0


def test_a_shared_stopword_is_not_a_match():
    """"The" is in almost every caption; counting it makes every photo equal."""

    assert score_photo_for_title("The Ridge", "the harbour at dusk") == 0
    assert score_photo_for_title("The Ridge", "a ridge at dusk") > 0


def test_each_item_gets_the_photograph_of_itself():
    titles = ["Coastal Serenity", "City Nocturne", "Autumn Hues"]
    candidates = [
        ("https://p/city.jpg", "city skyline at night, nocturne"),
        ("https://p/autumn.jpg", "autumn leaves in warm hues"),
        ("https://p/coast.jpg", "coastal cliffs and calm sea"),
    ]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert bound == {
        "item1": "https://p/coast.jpg",
        "item2": "https://p/city.jpg",
        "item3": "https://p/autumn.jpg",
    }


def test_no_two_items_share_a_photograph():
    """The defect this replaces was 16 items over 8 photos, every picture twice."""

    titles = ["Coastal Serenity", "Coastal Light", "Coastal Dawn"]
    candidates = [
        ("https://p/1.jpg", "coastal cliffs"),
        ("https://p/2.jpg", "coastal light on water"),
        ("https://p/3.jpg", "coastal dawn sky"),
    ]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert len(bound) == 3
    assert len(set(bound.values())) == 3


def test_an_item_nothing_matched_still_gets_its_own_picture():
    """A hole is a broken card; a repeat is worse than a merely unmatched photo."""

    titles = ["Coastal Serenity", "Zzyzx"]
    candidates = [
        ("https://p/coast.jpg", "coastal cliffs and calm sea"),
        ("https://p/spare.jpg", "an abstract texture"),
    ]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert bound["item1"] == "https://p/coast.jpg"
    assert bound["item2"] == "https://p/spare.jpg"


def test_the_best_pair_wins_over_reading_the_catalogue_left_to_right():
    """Greedy by title order lets item 1 eat the photograph item 2 needed.

    "Forest" alone matches both photographs equally, so a left-to-right pass
    takes the *misty dawn* picture for it on the tie and leaves "Misty Forest
    Dawn" — which matches that same photograph on three words — with the
    leftover. Taking the strongest pair in the whole grid first gives each its
    own.
    """

    titles = ["Forest", "Misty Forest Dawn"]
    candidates = [
        ("https://p/misty.jpg", "misty forest dawn"),
        ("https://p/plain.jpg", "a forest"),
    ]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert bound["item2"] == "https://p/misty.jpg", "the three-word match wins it"
    assert bound["item1"] == "https://p/plain.jpg"


def test_more_titles_than_slots_binds_the_slots_there_are():
    """A 30-item catalogue against 24 slots must not walk off the end of the ring."""

    titles = [f"Piece {n}" for n in range(1, 8)]
    candidates = [(f"https://p/{n}.jpg", f"piece {n}") for n in range(1, 8)]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert set(bound) <= set(_SLOTS)
    assert len(bound) == len(_SLOTS)


def test_more_items_than_photographs_binds_what_it_can_and_repeats_nothing():
    titles = ["A Ridge", "B Harbour", "C Meadow", "D Orchard"]
    candidates = [("https://p/ridge.jpg", "a mountain ridge")]

    bound = bind_photos_to_titles(titles, candidates, _SLOTS)

    assert bound == {"item1": "https://p/ridge.jpg"}


def test_nothing_to_work_with_changes_nothing():
    assert bind_photos_to_titles([], [("https://p/1.jpg", "x")], _SLOTS) == {}
    assert bind_photos_to_titles(["A Thing"], [], _SLOTS) == {}
    assert catalogue_item_titles("") == []
    assert catalogue_item_titles("export const seed = {};") == []


def test_the_item_pool_covers_the_biggest_catalogue_the_corpus_has_produced():
    """8 was `per_page=8` showing through, not a decision.

    Census over the 18 stored workspaces with a slugged catalogue: 13 declare
    more items than 8, and request 65 declares **16** — every photograph twice.
    The pool must clear that with room, and the search must ask for more than the
    pool, because duplicates and the person-ranking thin the result.
    """
    from app.application.services import industry_images as imgs

    largest_catalogue_in_the_corpus = 16
    assert len(imgs.item_slot_names()) > largest_catalogue_in_the_corpus
    assert imgs._ITEM_POOL_PER_PAGE > len(imgs.item_slot_names())
    assert imgs._ITEM_POOL_PER_PAGE <= 80, "Pexels caps per_page at 80"


def test_the_guard_sweep_never_reaches_the_network():
    """The first cut of this put the fetch in `sync_mock_images`, and that is wrong.

    `apply_workspace_guards` runs before **every** build attempt. A network fetch
    inside it re-picks the photographs on each retry, so the workspace stops
    being idempotent — `test_unknown_slot_is_controlled_and_guards_are_idempotent`
    went red on exactly that. It only went red because this machine happens to
    have a Pexels key; on a machine without one the same defect would have
    shipped green. Hence a test about the *structure*, which holds either way.
    """
    safety = REPO_ROOT / "backend/app/application/preview_app/safety"
    offenders = [
        path.name
        for path in sorted(safety.rglob("*.py"))
        if "item_photos_for_titles" in path.read_text(encoding="utf-8")
        or "bind_catalogue_photos" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"the guard sweep must not fetch photographs; found in {offenders}"
    )


def test_the_binding_runs_once_per_generation_not_once_per_attempt():
    """Its only call site is the codegen phase, right after the seed succeeds."""

    preview_app = REPO_ROOT / "backend/app/application/preview_app"
    callers = sorted(
        path.relative_to(preview_app).as_posix()
        for path in preview_app.rglob("*.py")
        if "bind_catalogue_photos(" in path.read_text(encoding="utf-8")
        and path.name != "photo_binding.py"
    )
    assert callers == ["pipeline/codegen_phase.py"]


def test_a_binding_that_would_repeat_a_photograph_is_refused(monkeypatch, tmp_path):
    """Take it whole or leave it: a repeat is worse than the rotation it replaces."""

    from app.application.preview_app.catalogue_contract import photo_binding as pb

    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "src" / "data" / "mock.ts").write_text(
        'export const seed = { items: [{"title": "A Ridge"}, {"title": "A Ridge"}] };',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_by_title",
        lambda *_a, **_k: [[], []],
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_for_titles",
        lambda *_a, **_k: [("https://p/one.jpg", "a mountain ridge")],
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_slot_names",
        lambda: ("item1", "item2"),
    )
    monkeypatch.setattr(
        pb, "bind_photos_to_titles", lambda *_a: {"item1": "https://p/x", "item2": "https://p/x"}
    )

    assert pb.bind_catalogue_photos(tmp_path, "outdoor gear") == {}


def test_every_failure_path_changes_nothing(monkeypatch, tmp_path):
    from app.application.preview_app.catalogue_contract import photo_binding as pb

    # No workspace at all.
    assert pb.bind_catalogue_photos(tmp_path / "nope", "art") == {}

    (tmp_path / "src" / "data").mkdir(parents=True)
    mock = tmp_path / "src" / "data" / "mock.ts"

    # A mock with no catalogue.
    mock.write_text("export const brand = { name: 'X' };", encoding="utf-8")
    assert pb.bind_catalogue_photos(tmp_path, "art") == {}

    # A search that raises — the per-item search and the pooled fallback both.
    mock.write_text('export const seed = { items: [{"title": "A Ridge"}] };', encoding="utf-8")
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_by_title",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("pexels down")),
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_for_titles",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("pexels down")),
    )
    assert pb.bind_catalogue_photos(tmp_path, "art") == {}

    # A search that returns nothing.
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_by_title",
        lambda *_a, **_k: [[]],
    )
    monkeypatch.setattr(
        "app.application.services.industry_images.item_photos_for_titles",
        lambda *_a, **_k: [],
    )
    assert pb.bind_catalogue_photos(tmp_path, "art") == {}


def test_the_binding_is_deterministic():
    """Same inputs, same assignment — twice, and on any machine.

    Scores are integers and both tie-breaks are indices, so there is no set
    iteration order or float comparison anywhere in the result.
    """

    titles = ["Coastal Serenity", "Coastal Serenity"]
    candidates = [
        ("https://p/a.jpg", "coastal serenity"),
        ("https://p/b.jpg", "coastal serenity"),
    ]

    first = bind_photos_to_titles(titles, candidates, _SLOTS)
    assert first == bind_photos_to_titles(titles, candidates, _SLOTS)
    assert first == {"item1": "https://p/a.jpg", "item2": "https://p/b.jpg"}
