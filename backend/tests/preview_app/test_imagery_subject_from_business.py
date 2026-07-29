"""Imagery subject comes from the business — a layout pack may only frame it.

Regression for preview app 36 (fine-art gallery brief that shipped dental clinic
stock photos because the chosen pack's industry_tags became the Pexels query).
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402

from app.application.preview_app.industry_templates.apply import (  # noqa: E402
    _ROLE_FRAMINGS,
    apply_industry_template_to_plan,
)
from app.application.preview_app.industry_templates.loader import (  # noqa: E402
    load_templates,
    pick_template_id,
)
from app.application.services import industry_images  # noqa: E402
from app.application.services.industry_images import (  # noqa: E402
    _CATEGORY_QUERY_HINT,
    _fetch_pexels_images,
    _resolve_category,
    _slot_queries,
)

JEANNE_BRIEF: dict[str, str] = {
    "business_name": "Jeanne Kassab Art",
    "industry": (
        "Fine art gallery - original oil paintings - artist portfolio (gallery/portfolio)"
    ),
    "business_description": (
        "Personal fine art gallery for original paintings - abstract landscapes and "
        "layered oils. A living gallery of latest works - not a booking SaaS or clinic "
        "front desk."
    ),
    "target_customers": (
        "Collectors, interior designers, and gallery visitors browsing original oil "
        "paintings"
    ),
    "main_problem": "No elegant online home to show and sell original paintings",
    "desired_outcome": "Editorial storefront / portfolio, not an ops ledger",
}

# Same corpus plan_phase.py builds for the picker.
JEANNE_CONTEXT = " ".join(
    (
        JEANNE_BRIEF["industry"],
        JEANNE_BRIEF["business_description"],
        JEANNE_BRIEF["main_problem"],
        JEANNE_BRIEF["desired_outcome"],
        JEANNE_BRIEF["target_customers"],
        JEANNE_BRIEF["business_name"],
    )
)

WRONG_SUBJECT_WORDS = (
    "dental",
    "dentist",
    "clinic",
    "orthodontics",
    "medical",
    "healthcare",
)
ART_SUBJECT_WORDS = ("art", "gallery", "painting", "canvas", "artist")


def setup_function() -> None:
    load_templates.cache_clear()


def _jeanne_plan(seed: int = 36) -> dict[str, Any]:
    return apply_industry_template_to_plan(
        {},
        industry=JEANNE_BRIEF["industry"],
        seed=seed,
        surface="public",
        context=JEANNE_CONTEXT,
        brand_name=JEANNE_BRIEF["business_name"],
    )


def _fake_pexels(monkeypatch: Any) -> None:
    """Stub the HTTP layer: each photo URL echoes the query that found it."""

    def _search(api_key: str, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        slug = "-".join(query.lower().split())
        url = f"https://images.pexels.com/photos/{slug}.jpg"
        return [
            {
                "id": abs(hash(query)) % 10_000,
                "src": {"large2x": url, "large": url, "medium": url, "original": url},
            }
        ]

    monkeypatch.setattr(industry_images, "_search_pexels", _search)


def test_jeanne_brief_picks_an_art_pack_at_every_seed() -> None:
    for seed in range(12):
        tid = pick_template_id(
            industry=JEANNE_BRIEF["industry"],
            surface="public",
            seed=seed,
            context=JEANNE_CONTEXT,
        )
        assert tid == "art-gallery-portfolio-home", seed


def test_jeanne_brief_stamps_no_ops_pack() -> None:
    # "portfolio" alone must not hand a gallery the trading-desk identity.
    assert (
        pick_template_id(
            industry=JEANNE_BRIEF["industry"],
            surface="ops",
            seed=36,
            context=JEANNE_CONTEXT,
        )
        is None
    )


def test_jeanne_recipe_stays_editorial() -> None:
    plan = _jeanne_plan()
    assert plan["design_system"]["template_recipe_hint"] == "editorial"


def test_jeanne_imagery_urls_carry_art_subject_only(monkeypatch: Any) -> None:
    _fake_pexels(monkeypatch)
    plan = _jeanne_plan()
    urls = _fetch_pexels_images(
        "test-key",
        JEANNE_BRIEF["industry"],
        business_name=JEANNE_BRIEF["business_name"],
        seed="jeanne-36",
        imagery_roles=plan["imagery_roles"],
    )
    assert urls and len(urls) == 6
    for slot, url in urls.items():
        lowered = url.lower()
        assert any(word in lowered for word in ART_SUBJECT_WORDS), (slot, url)
        for wrong in WRONG_SUBJECT_WORDS:
            assert wrong not in lowered, (slot, wrong, url)


def test_pack_without_imagery_roles_contributes_no_subject() -> None:
    plan = apply_industry_template_to_plan(
        {}, industry="Dental clinic healthcare", seed=2, surface="public"
    )
    assert plan["industry_template_id"] == "clinic-dental-home"
    roles = plan["imagery_roles"]
    assert set(roles) == {"hero", "hero2", "card1", "card2", "card3", "ambient"}
    blob = " ".join(roles.values()).lower()
    for word in ("dental", "dentist", "clinic", "orthodontics", "healthcare"):
        assert word not in blob, word


def test_off_industry_pack_subject_is_dropped_with_warning(
    caplog: Any,
) -> None:
    with caplog.at_level(logging.WARNING):
        plan = apply_industry_template_to_plan(
            {},
            industry="Gallery",
            seed=4,
            surface="public",
            context="spa wellness massage facial salon beauty treatment rooms",
        )
    assert plan["industry_template_id"] == "spa-wellness-home"
    blob = " ".join(plan["imagery_roles"].values()).lower()
    for word in ("spa", "massage", "facial", "wellness"):
        assert not re.search(rf"\b{word}\b", blob), word
    warning = " ".join(
        record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
    )
    assert "spa-wellness-home" in warning
    assert "beauty" in warning and "art" in warning


def test_role_framing_composes_with_business_subject() -> None:
    queries = _slot_queries(
        JEANNE_BRIEF["business_name"],
        JEANNE_BRIEF["industry"],
        imagery_roles={
            "hero": "lifestyle wide atmosphere",
            "card1": "dental clinic operatory close-up",
        },
    )
    hero = queries["hero"].lower()
    # Brand, then the brief's own industry words, then the role. The nine-bucket
    # category hint trails as filler and never leads.
    assert hero.startswith("jeanne kassab art fine gallery original oil paintings")
    assert "lifestyle wide atmosphere" in hero
    # Even a hostile role cannot displace the business subject.
    card1 = queries["card1"].lower()
    assert card1.startswith("jeanne kassab art fine gallery original oil paintings")


# One row per _CATEGORY_QUERY_HINT bucket. The art row is the only one the
# original test covered, and it is the only one whose bucket resolves correctly —
# which is exactly why dropping industry_clean went unnoticed.
SUBJECT_CASES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Ridge Motors", "Auto repair garage and detailing", ("auto", "repair", "garage")),
    ("Clearflow", "Plumbing and heating repair", ("plumbing", "heating")),
    ("Hale & Marsh", "Boutique law firm - estate and family law", ("law", "firm", "estate")),
    ("Brightwork", "Commercial cleaning company", ("cleaning", "company")),
    ("Northside Threads", "Fashion apparel boutique", ("fashion", "apparel")),
    ("Sunrise Dental", "Dental clinic and orthodontics", ("dental", "clinic")),
    ("Cedar Table", "Neighbourhood bistro and wine bar", ("bistro", "wine")),
    ("Ironworks", "Strength gym and personal training", ("gym", "strength")),
    ("Lumen Labs", "B2B SaaS platform for logistics", ("saas", "logistics")),
    ("Harbour Realty", "Residential real estate brokerage", ("estate", "brokerage")),
    ("Northlight Academy", "Language school and tutoring", ("language", "school")),
    ("Still Waters", "Day spa and massage studio", ("spa", "massage")),
    ("Jeanne Kassab Art", JEANNE_BRIEF["industry"], ("gallery", "paintings")),
)


@pytest.mark.parametrize("brand,industry,expected_words", SUBJECT_CASES)
def test_role_query_carries_the_briefs_own_industry_words(
    brand: str, industry: str, expected_words: tuple[str, ...]
) -> None:
    """The subject of a role query is the business, not a nine-bucket guess.

    Regression: _slot_queries composed (brand, category_hint, role) and never
    passed industry_clean, so the entire subject of every Pexels query was one of
    nine hints — and _resolve_category mis-buckets ordinary phrasings.
    """
    queries = _slot_queries(brand, industry, imagery_roles=dict(_ROLE_FRAMINGS))
    assert set(queries) == set(_ROLE_FRAMINGS)
    for slot, query in queries.items():
        lowered = query.lower()
        assert lowered.startswith(brand.lower()), (slot, query)
        for word in expected_words:
            assert word in lowered, (slot, word, query)
        # The role framing survives the word cap, so slots stay distinguishable.
        first_framing_word = _ROLE_FRAMINGS[slot].split()[0].lower()
        assert first_framing_word in lowered, (slot, query)
    assert len(set(queries.values())) == len(queries), queries


@pytest.mark.parametrize(
    "industry,forbidden_bucket,leaked_word",
    (
        ("Auto repair garage and detailing", "tech", "software"),  # "ai" in "repair"
        ("Plumbing and heating repair", "tech", "software"),
        ("Fashion apparel boutique", "tech", "software"),  # "app" in "apparel"
        ("Handmade chairs and furniture", "beauty", "salon"),  # "hair" in "chairs"
        ("Barbershop and grooming", "food", "restaurant"),  # "bar" in "barbershop"
    ),
)
def test_category_resolution_is_word_anchored(
    industry: str, forbidden_bucket: str, leaked_word: str
) -> None:
    """Unanchored substring matching sent auto-repair briefs to software imagery."""
    resolved = _resolve_category(industry)
    assert resolved != forbidden_bucket, (industry, resolved)
    # And the wrong subject noun must be gone from the hint the query would carry.
    assert leaked_word not in _CATEGORY_QUERY_HINT[resolved], (industry, resolved)


def test_word_anchoring_keeps_matching_plurals_and_phrases() -> None:
    # Anchoring must not cost the matches that were already correct.
    assert _resolve_category("hair salons and nails") == "beauty"
    assert _resolve_category("outdoor gear shops") == "retail"
    assert _resolve_category("real estate agents") == "realestate"
    assert _resolve_category("fine art gallery") == "art"
    assert _resolve_category("AI automation platform") == "tech"
    assert _resolve_category("something entirely unmapped") == "generic"


def test_roleless_callers_keep_legacy_queries() -> None:
    industry = "Dental clinic healthcare"
    queries = _slot_queries("Acme Dental", industry)
    assert queries["hero"] == "Acme Dental Dental clinic healthcare clinic healthcare hero lifestyle wide"
    assert queries == _slot_queries("Acme Dental", industry, imagery_roles={})
    assert queries == _slot_queries("Acme Dental", industry, imagery_roles=None)


if __name__ == "__main__":
    setup_function()
    test_jeanne_brief_picks_an_art_pack_at_every_seed()
    test_jeanne_recipe_stays_editorial()
    test_pack_without_imagery_roles_contributes_no_subject()
    test_role_framing_composes_with_business_subject()
    test_roleless_callers_keep_legacy_queries()
    for _brand, _industry, _words in SUBJECT_CASES:
        test_role_query_carries_the_briefs_own_industry_words(_brand, _industry, _words)
    test_word_anchoring_keeps_matching_plurals_and_phrases()
    print("Imagery subject tests passed")
