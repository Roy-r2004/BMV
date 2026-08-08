"""An industry pack supplies structure; the sentences are written for the business.

Owner ruling, 2026-08-09. Two shipped apps from the session-27b trio carried pack
copy word for word:

    160  Ridgeline Bike Works (a bike workshop)
         "The rack is live" · "Shop the new drop before sizes thin out."
         · "Restock alerts"          -> packs/fashion-retail-storefront.json

    158  Kestrel & Fern Bakehouse (pre-orders, no table service)
         "Hold a table — or join the walk-in list with a real wait time."
                                     -> packs/restaurant-cafe-home.json

Neither is a dead link and neither breaks a contract, so every gate passed them.
The bakery's pack is roughly right and its copy is not; the bike shop's is
neither.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.industry_templates.loader import (
    _PACK_SENTENCE_MIN_CHARS,
    load_templates,
    pack_literal_sentences,
)

_PACKS = REPO_ROOT / "backend/app/application/preview_app/industry_templates/packs"


def test_the_two_sentences_that_shipped_are_in_the_set():
    """The regression, named. Both are still in the packs, unedited."""

    sentences = pack_literal_sentences()
    assert "Shop the new drop before sizes thin out." in sentences
    assert (
        "Hold a table — or join the walk-in list with a real wait time."
        in sentences
    )


def test_structure_is_not_copy():
    """Short leaves are shape, and a business may legitimately write them.

    "bold", "Popular", "60 min", a slot name — failing a run over those would
    make the row measure our own vocabulary rather than whether the writers
    said anything.

    The floor is asserted as a literal, not as `_PACK_SENTENCE_MIN_CHARS`.
    Comparing the set against the constant that built it is a tautology: drop
    the constant to 1 and the assertion follows it down, which is exactly what
    the mutation sweep caught.
    """
    assert _PACK_SENTENCE_MIN_CHARS == 16, "the floor moved; re-judge the cases below"
    for sentence in pack_literal_sentences():
        assert len(sentence) >= 16
        assert " " in sentence

    # Real short leaves from the packs, which must never fail a run.
    for structural in ("bold", "Popular", "60 min", "warm"):
        assert structural not in pack_literal_sentences()


def test_no_route_literal_is_treated_as_a_sentence():
    """`/shop` and `#inquire` are the route-literal rule's problem, not this one.

    The `startswith` guard in the walker is **not currently reachable** and is
    recorded as such rather than chased: no leaf in any of the 27 packs is both
    16+ characters and contains a space and starts with a path or a URL, so
    removing the guard changes nothing today. It is kept because a pack could
    add a long link tomorrow, and this assertion is what would then fail.
    """
    assert not [s for s in pack_literal_sentences() if s.startswith(("/", "#", "http"))]


def test_every_pack_contributes_and_the_set_is_not_empty():
    """A silent zero here would make the gate look green forever."""

    assert len(pack_literal_sentences()) > 100, "27 packs of seed copy is not a handful"


def test_the_set_is_read_from_the_packs_and_not_restated():
    """Add a sentence to a pack and the gate must see it, with no code change.

    Restating literals in the checker is how two earlier censuses in this repo
    drifted from the thing they claimed to measure.
    """
    pack = json.loads(
        (_PACKS / "fashion-retail-storefront.json").read_text(encoding="utf-8")
    )
    for line in (pack["mock_seed"]["hero"]["headline"],
                 pack["mock_seed"]["hero"]["subcopy"]):
        if len(line) >= _PACK_SENTENCE_MIN_CHARS and " " in line:
            assert line in pack_literal_sentences()


def test_the_gate_fails_a_workspace_that_ships_pack_copy(tmp_path):
    from app.application.preview_app import quality_gate

    leaked = "Shop the new drop before sizes thin out."
    mock = (
        "export const brand = { name: 'Ridgeline Bike Works' };\n"
        "export const seed = { hero: { subcopy: "
        f'"{leaked}" '
        "} };\n"
    )
    report = _run_mock_checks(quality_gate, tmp_path, mock)

    codes = [issue.code for issue in report.issues]
    assert "pack_copy_shipped" in codes
    assert any(leaked in issue.message for issue in report.issues)


def test_the_gate_passes_copy_written_for_the_business(tmp_path):
    from app.application.preview_app import quality_gate

    mock = (
        "export const brand = { name: 'Ridgeline Bike Works' };\n"
        "export const seed = { hero: { subcopy: "
        '"Frame-up rebuilds and same-week servicing for riders in the valley." '
        "} };\n"
    )
    report = _run_mock_checks(quality_gate, tmp_path, mock)

    assert "pack_copy_shipped" not in [issue.code for issue in report.issues]


def test_a_sentence_that_merely_contains_a_pack_phrase_is_not_a_hit(tmp_path):
    """Exact leaf, never substring — the census learned this the hard way."""

    from app.application.preview_app import quality_gate

    # The pack's exact sentence, embedded in a longer one the business wrote.
    # Case and punctuation match on purpose: an earlier version of this test
    # lower-cased the phrase, so a substring check would have passed it too and
    # the mutation survived.
    leaked = "Shop the new drop before sizes thin out."
    mock = (
        "export const brand = { name: 'X' };\n"
        "export const seed = { note: "
        f'"Our rivals will tell you: {leaked} We will not." '
        "} };\n"
    )
    assert leaked in pack_literal_sentences()
    report = _run_mock_checks(quality_gate, tmp_path, mock)

    assert "pack_copy_shipped" not in [issue.code for issue in report.issues]


def _run_mock_checks(quality_gate, tmp_path: Path, mock: str):
    """Evaluate a workspace that exists only to carry one `mock.ts`.

    The gate returns early without pages, so there is one, and the report will
    also carry unrelated failures (`no_dist` and friends). Only the code under
    test is asserted on — this is a check about `mock.ts`, not a whole app.
    """
    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "src" / "data" / "mock.ts").write_text(mock, encoding="utf-8")
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "pages" / "HomePage.tsx").write_text(
        "export default function HomePage() { return <div />; }\n", encoding="utf-8"
    )
    return quality_gate.evaluate_quality_gate(tmp_path, {}, require_ai_hub=False)


def test_a_bike_workshop_does_not_get_a_fashion_boutique():
    """Request 160's exact brief, and the selector defect underneath the copy one.

    "Bicycle retail, service and workshop" matched
    `fashion-retail-storefront` on **"retail" alone** — the only pack that
    matched at all — because at six characters that one declared word cleared
    `_MIN_DISTINCTIVE_TOKEN_LEN` and a lone tag hit was enough to choose a whole
    visual identity. The app shipped "The rack is live" and "Shop the new drop
    before sizes thin out."

    Recipe-only is the right answer here, and `pick_template_id`'s own docstring
    says so: *"None = recipe-only (better than a wrong utility pack)"*. There is
    no bicycle pack, and inventing one to fix this would be inventing more copy.
    """
    from app.application.preview_app.industry_templates.loader import pick_template_id

    picked = pick_template_id(
        industry="Bicycle retail, service and workshop",
        surface="public",
        seed=160,
        context=(
            "A bike shop selling around twenty models across gravel, commuter and "
            "kids ranges, alongside a workshop that takes in repairs and annual "
            "services. Customers browse the range and book a mechanic slot."
        ),
    )
    assert picked != "fashion-retail-storefront"
    assert picked is None


def test_a_real_fashion_boutique_still_gets_the_fashion_pack():
    """Weakening "retail" must not cost the businesses the pack is for."""

    from app.application.preview_app.industry_templates.loader import pick_template_id

    assert (
        pick_template_id(
            industry="Womenswear boutique and apparel",
            surface="public",
            seed=1,
            context="An independent clothing boutique with seasonal drops.",
        )
        == "fashion-retail-storefront"
    )
