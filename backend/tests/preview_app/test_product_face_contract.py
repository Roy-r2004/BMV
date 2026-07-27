"""Product Face Contract — packs gap-fill only; intent beats keywords."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.brand_brief import resolve_preview_brand_name
from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.industry_templates.apply import (
    apply_industry_template_to_plan,
    apply_ops_industry_template_to_plan,
)
from app.application.preview_app.industry_templates.loader import load_templates
from app.application.preview_app.industry_templates.seed import normalize_mock_seed
from app.application.preview_app.product_face import (
    _scrub_early_placeholders,
    ensure_product_face_on_plan,
    gap_fill_ops_seed_from_pack,
    materialize_mock_seed,
)


def setup_module() -> None:
    load_templates.cache_clear()


def test_resolve_preview_brand_name_priority() -> None:
    assert (
        resolve_preview_brand_name(
            brand_name="Explicit",
            brand_brief={"brand_name": "Brief"},
            business_name="Biz",
            concept_name="Concept",
            manifest={"brand": {"name": "Manifest"}, "brand_name": "ManifestTop"},
            demo={"product_name": "Demo"},
            plan={"concept_name": "PlanConcept"},
        )
        == "Explicit"
    )
    assert (
        resolve_preview_brand_name(
            brand_brief={"brand_name": "Brief"},
            business_name="Biz",
            concept_name="Concept",
        )
        == "Brief"
    )
    assert (
        resolve_preview_brand_name(
            brand_brief={"brand_name": "Brand"},
            business_name="Biz",
        )
        == "Biz"
    )
    assert (
        resolve_preview_brand_name(
            concept_name="Concept",
            manifest={"brand": {"name": "Manifest"}},
        )
        == "Concept"
    )
    assert (
        resolve_preview_brand_name(
            manifest={"brand": {"name": "Manifest"}},
            demo={"product_name": "Demo"},
        )
        == "Manifest"
    )
    assert resolve_preview_brand_name(demo={"product_name": "Demo"}) == "Demo"
    assert resolve_preview_brand_name(plan={"concept_name": "PlanConcept"}) == "PlanConcept"
    assert resolve_preview_brand_name(fallback=True) == "Brand"
    assert resolve_preview_brand_name(fallback=False) is None
    # Weaker sources never clobber a real early name.
    assert (
        resolve_preview_brand_name(
            brand_name="Early Real",
            manifest={"brand": {"name": "Manifest Mush"}},
            business_name="Biz",
        )
        == "Early Real"
    )


def test_dual_clock_same_resolved_name_no_literal_brand() -> None:
    """Plan-phase order: early resolve → pack apply → plumbing normalize, one name."""
    business_name = "Clay & Kiln"
    early = resolve_preview_brand_name(business_name=business_name, fallback=False)
    assert early == business_name
    out = apply_industry_template_to_plan(
        {},
        industry="Arts & Crafts / Pottery Studio",
        seed=3,
        brand_name=early,
    )
    seed = out["mock_seed"]
    # Late plumbing clock reuses the same resolved name (not a second Brand policy).
    late = resolve_preview_brand_name(
        brand_name=early,
        manifest={"brand": {"name": "Brand"}, "brand_name": "Brand"},
        business_name=business_name,
        fallback=True,
    )
    assert late == business_name
    plumbed = normalize_mock_seed(seed, brand_name=late)
    blob = str(plumbed)
    assert "Brand" not in blob
    assert "Brand" not in str((plumbed.get("hero") or {}).get("eyebrow") or "")
    assert "Brand" not in str(plumbed.get("featuresHeading") or "")


def test_omit_brand_uses_plan_concept_name() -> None:
    out = apply_industry_template_to_plan(
        {"concept_name": "Clay & Kiln"},
        industry="Arts & Crafts / Pottery Studio",
        seed=3,
    )
    seed = out["mock_seed"]
    hero = seed.get("hero") or {}
    assert "Brand" not in str(hero.get("eyebrow") or "")
    assert "Brand" not in str(hero.get("subcopy") or "")
    for key in (
        "showcaseHeading",
        "featuresHeading",
        "processHeading",
        "credentialsHeading",
        "testimonialsHeading",
    ):
        assert "Brand" not in str(seed.get(key) or ""), key
    assert "Brand" not in str((seed.get("cta") or {}).get("heading") or "")
    titles = {
        str(item.get("title") or "")
        for item in (seed.get("items") or [])
        if isinstance(item, dict)
    }
    assert "Brand signature" not in titles
    assert any("Wheel" in t or "Glaze" in t for t in titles)


def test_mixed_list_scrub_keeps_real_items() -> None:
    public = {
        "items": [
            {"title": "Brand signature", "description": "placeholder"},
            {"title": "Wheel Throwing", "description": "real pack class"},
            {"title": "Everyday essential", "description": "placeholder"},
        ]
    }
    scrubbed = _scrub_early_placeholders(public)
    titles = [item["title"] for item in scrubbed["items"]]
    assert titles == ["Wheel Throwing"]
    seed = materialize_mock_seed(
        {"public_seed": public, "ops_seed": {}},
        brand_name="Clay & Kiln",
        fill_defaults=True,
    )
    out_titles = [
        str(item.get("title") or "")
        for item in (seed.get("items") or [])
        if isinstance(item, dict)
    ]
    assert "Brand signature" not in out_titles
    assert "Everyday essential" not in out_titles
    assert "Wheel Throwing" in out_titles


def test_pack_gap_fill_does_not_overwrite_ops_kpis() -> None:
    face = {
        "version": 1,
        "roles": [],
        "routes": [],
        "public_seed": {
            "hero": {
                "headline": "Care that starts on time",
                "subcopy": "Clinic marketing",
            }
        },
        "ops_seed": {
            "hero": {"headline": "Today's patient flow", "subcopy": "Check-ins"},
            "kpis": [
                {"label": "Arrivals today", "value": "28", "delta": "+4", "hint": "vs yesterday"}
            ],
        },
    }
    filled = gap_fill_ops_seed_from_pack(
        face,
        {
            "hero": {"headline": "Floor board", "subcopy": "Restaurant"},
            "items": [{"title": "Waitlist · 6 parties", "description": "Table 12"}],
            "kpis": [{"label": "Running tickets", "value": "11", "delta": "", "hint": "expo"}],
        },
    )
    assert filled["ops_seed"]["hero"]["headline"] == "Today's patient flow"
    assert filled["ops_seed"]["kpis"][0]["label"] == "Arrivals today"
    # Empty items may be filled from pack — OK; non-empty KPIs must stay.
    seed = materialize_mock_seed(filled)
    assert seed["opsHero"]["headline"] == "Today's patient flow"
    assert seed["kpis"][0]["label"] == "Arrivals today"


def test_ops_seed_not_overwritten_by_staff_floor_pack() -> None:
    plan = {
        "roles": [
            {
                "id": "staff",
                "label": "Front Desk",
                "pages": [
                    {
                        "id": "desk",
                        "title": "Staff Dashboard",
                        "path": "/staff/dashboard",
                        "surface": "ops",
                        "skeleton_id": "ops-dashboard",
                        "page_intent": "ops",
                    }
                ],
            }
        ],
        "product_face": {
            "version": 1,
            "roles": [],
            "routes": [
                {
                    "path": "/staff/dashboard",
                    "title": "Staff Dashboard",
                    "role_id": "staff",
                    "page_intent": "ops",
                }
            ],
            "public_seed": {
                "hero": {
                    "headline": "Care that starts on time and explains every step",
                    "subcopy": "Cleanings and orthodontics",
                }
            },
            "ops_seed": {
                "hero": {
                    "headline": "Today's patient flow",
                    "subcopy": "Check-ins and no-show risk",
                },
                "kpis": [
                    {
                        "label": "In chair now",
                        "value": "6",
                        "delta": "2 waiting",
                        "hint": "active visits",
                    }
                ],
            },
        },
    }
    # Even with cafe/hospitality context forcing staff-floor tags, contract KPIs win.
    out = apply_ops_industry_template_to_plan(
        plan,
        industry="Restaurant",
        seed=3,
        context="cafe host stand expo patio dining floor front desk staff",
    )
    assert out["mock_seed"]["opsHero"]["headline"] == "Today's patient flow"
    assert out["mock_seed"]["kpis"][0]["label"] == "In chair now"
    assert "table" not in out["mock_seed"]["kpis"][0]["label"].lower()


def test_page_intent_listing_face_without_doctor_keyword() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/ProvidersPage.tsx",
        {
            "path": "/providers",
            "title": "Our Providers",
            "skeleton_id": "public-service",
            "section_slots": ["hero", "features", "cta", "footer"],
            "page_intent": "listing",
        },
        brand_name="Northside Family Clinic",
    )
    assert "// directory listing scaffold" in tsx
    assert "seed.hero" not in tsx
    assert "ProductShowcase" in tsx


def test_ops_header_uses_ops_seed_not_public_hero() -> None:
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/admin/StaffDashboardPage.tsx",
        {
            "path": "/staff/dashboard",
            "title": "Staff Dashboard",
            "skeleton_id": "ops-dashboard",
            "section_slots": ["header", "kpis", "activity"],
            "page_intent": "ops",
        },
        brand_name="Northside Family Clinic",
    )
    assert "seed.opsHero?.headline" in tsx
    assert "seed.hero?.headline" not in tsx


def test_public_pack_does_not_wipe_existing_hero() -> None:
    plan = {
        "roles": [{"id": "patient", "label": "Patient", "pages": []}],
        "product_face": {
            "version": 1,
            "roles": [],
            "routes": [],
            "public_seed": {
                "hero": {
                    "headline": "Brief-owned headline",
                    "subcopy": "From the LLM contract",
                }
            },
            "ops_seed": {},
        },
    }
    out = apply_industry_template_to_plan(
        plan,
        industry="Healthcare",
        seed=3,
        surface="public",
        context="Northside Family Clinic dental patients",
    )
    assert out["mock_seed"]["hero"]["headline"] == "Brief-owned headline"


def test_ensure_product_face_stamps_intents() -> None:
    plan = ensure_product_face_on_plan(
        {
            "roles": [
                {
                    "id": "patient",
                    "label": "Patient",
                    "pages": [
                        {
                            "id": "home",
                            "title": "Home",
                            "path": "/",
                            "skeleton_id": "public-home",
                            "surface": "public",
                        }
                    ],
                }
            ],
            "routes": [
                {
                    "path": "/",
                    "title": "Home",
                    "skeleton_id": "public-home",
                    "role_id": "patient",
                }
            ],
        }
    )
    assert plan["roles"][0]["pages"][0]["page_intent"] == "home"
    assert plan["routes"][0]["page_intent"] == "home"
    assert plan["product_face"]["version"] == 1


def test_apply_with_brand_name_no_literal_brand() -> None:
    out = apply_industry_template_to_plan(
        {},
        industry="Arts & Crafts / Pottery Studio",
        seed=3,
        brand_name="Clay & Kiln",
    )
    seed = out["mock_seed"]
    hero = seed.get("hero") or {}
    assert "Brand" not in str(hero.get("eyebrow") or "")
    assert "Brand" not in str(hero.get("subcopy") or "")
    for key in (
        "showcaseHeading",
        "featuresHeading",
        "processHeading",
        "credentialsHeading",
        "testimonialsHeading",
    ):
        assert "Brand" not in str(seed.get(key) or ""), key
    assert "Brand" not in str((seed.get("cta") or {}).get("heading") or "")
    # Pack wins where nonempty (pottery classes / subcopy).
    assert "clay" in str(hero.get("subcopy") or "").lower()
    assert any(
        "Wheel" in item.get("title", "") or "Glaze" in item.get("title", "")
        for item in seed.get("items") or []
    )
    assert seed["showcaseHeading"] == "On the boards this season"


def test_early_ensure_fill_defaults_false_skips_brand_items() -> None:
    plan = ensure_product_face_on_plan({}, fill_defaults=False)
    seed = plan.get("mock_seed") or {}
    items = seed.get("items") or []
    titles = {
        str(item.get("title") or "")
        for item in items
        if isinstance(item, dict)
    }
    assert "Brand signature" not in titles
    assert "Everyday essential" not in titles
    assert "Guest favorite" not in titles
    hero = seed.get("hero") or {}
    assert hero.get("eyebrow") != "Brand"
    assert not items


def test_empty_early_brand_bake_then_late_rematerialize() -> None:
    """Empty early → Brand-templated sticky seed → late rematerialize clears Brand."""
    baked = ensure_product_face_on_plan({}, brand_name=None, fill_defaults=True)
    seed = baked.get("mock_seed") or {}
    assert (seed.get("hero") or {}).get("eyebrow") == "Brand"
    assert seed.get("featuresHeading") == "What Brand offers"
    assert seed.get("showcaseHeading") == "From Brand"
    assert "Brand" in str((seed.get("cta") or {}).get("heading") or "")
    assert seed.get("trustLabels") == [
        "Brand quality",
        "On schedule",
        "Repeat guests",
        "Local favorite",
    ]

    # Preserve real pack/LLM copy through scrub + rematerialize.
    baked["product_face"] = dict(baked.get("product_face") or {})
    baked["product_face"]["public_seed"] = dict(
        baked["product_face"].get("public_seed") or {}
    )
    baked["product_face"]["public_seed"]["featuresHeading"] = "Wheel season highlights"
    # Sticky Brand-less orphan residue on face (post-partial scrub lift).
    baked["product_face"]["public_seed"]["trustLabels"] = [
        "On schedule",
        "Repeat guests",
        "Local favorite",
    ]
    baked["mock_seed"] = dict(seed)
    baked["mock_seed"]["featuresHeading"] = "Wheel season highlights"
    baked["mock_seed"]["items"] = [
        {"title": "Brand signature", "description": "placeholder"},
        {"title": "Wheel Throwing", "description": "real pack class"},
    ]

    late = ensure_product_face_on_plan(
        baked, brand_name="Clay & Kiln", fill_defaults=True
    )
    out = late.get("mock_seed") or {}
    blob = str(out)
    assert "What Brand offers" not in blob
    assert "From Brand" not in blob
    assert (out.get("hero") or {}).get("eyebrow") == "Clay & Kiln"
    assert out.get("showcaseHeading") == "From Clay & Kiln"
    assert out.get("featuresHeading") == "Wheel season highlights"
    assert out.get("trustLabels") == [
        "Clay & Kiln quality",
        "On schedule",
        "Repeat guests",
        "Local favorite",
    ]
    public_labels = (late.get("product_face") or {}).get("public_seed", {}).get(
        "trustLabels"
    )
    assert public_labels == out.get("trustLabels")
    assert "Brand signature" not in {
        str(item.get("title") or "")
        for item in (out.get("items") or [])
        if isinstance(item, dict)
    }
    assert any(
        "Wheel Throwing" in str(item.get("title") or "")
        for item in (out.get("items") or [])
        if isinstance(item, dict)
    )
    assert "Brand" not in str((out.get("hero") or {}).get("eyebrow") or "")
    assert "Brand" not in str(out.get("processHeading") or "")


def test_scrub_early_trust_labels_co_resident_and_orphan() -> None:
    """Brand + Brand-less trustDefaults scrub fully; orphan trio also clears."""
    full = {
        "trustLabels": [
            "Brand quality",
            "On schedule",
            "Repeat guests",
            "Local favorite",
        ]
    }
    assert _scrub_early_placeholders(full)["trustLabels"] == []

    orphan = {
        "trustLabels": ["On schedule", "Repeat guests", "Local favorite"],
    }
    assert _scrub_early_placeholders(orphan)["trustLabels"] == []

    mixed_real = {
        "trustLabels": [
            "Brand quality",
            "On schedule",
            "Wheel classes",
            "Local favorite",
        ]
    }
    assert _scrub_early_placeholders(mixed_real)["trustLabels"] == ["Wheel classes"]


def test_real_pack_trust_labels_survive_rematerialize() -> None:
    """Pack/LLM trustLabels outside Brand defaults survive scrub + rematerialize."""
    pack_labels = ["Wheel-thrown", "Kiln-fired", "Studio certified"]
    baked = ensure_product_face_on_plan({}, brand_name=None, fill_defaults=True)
    baked["product_face"] = dict(baked.get("product_face") or {})
    baked["product_face"]["public_seed"] = dict(
        baked["product_face"].get("public_seed") or {}
    )
    baked["product_face"]["public_seed"]["trustLabels"] = list(pack_labels)
    baked["mock_seed"] = dict(baked.get("mock_seed") or {})
    baked["mock_seed"]["trustLabels"] = list(pack_labels)

    late = ensure_product_face_on_plan(
        baked, brand_name="Clay & Kiln", fill_defaults=True
    )
    out = late.get("mock_seed") or {}
    assert out.get("trustLabels") == pack_labels
    public = (late.get("product_face") or {}).get("public_seed") or {}
    assert public.get("trustLabels") == pack_labels


def test_scrub_brand_templated_headings_exact_match_only() -> None:
    public = {
        "featuresHeading": "What Brand offers",
        "showcaseHeading": "From Brand",
        "processHeading": "How our studio works",
        "hero": {
            "eyebrow": "Brand",
            "subcopy": "A clear next step from Brand — warm, specific, and ready when you are.",
            "headline": "Real LLM headline",
        },
    }
    scrubbed = _scrub_early_placeholders(public)
    assert scrubbed["featuresHeading"] == ""
    assert scrubbed["showcaseHeading"] == ""
    assert scrubbed["processHeading"] == "How our studio works"
    assert scrubbed["hero"]["eyebrow"] == ""
    assert scrubbed["hero"]["subcopy"] == ""
    assert scrubbed["hero"]["headline"] == "Real LLM headline"


if __name__ == "__main__":
    setup_module()
    test_resolve_preview_brand_name_priority()
    test_dual_clock_same_resolved_name_no_literal_brand()
    test_omit_brand_uses_plan_concept_name()
    test_mixed_list_scrub_keeps_real_items()
    test_pack_gap_fill_does_not_overwrite_ops_kpis()
    test_ops_seed_not_overwritten_by_staff_floor_pack()
    test_page_intent_listing_face_without_doctor_keyword()
    test_ops_header_uses_ops_seed_not_public_hero()
    test_public_pack_does_not_wipe_existing_hero()
    test_ensure_product_face_stamps_intents()
    test_apply_with_brand_name_no_literal_brand()
    test_early_ensure_fill_defaults_false_skips_brand_items()
    test_empty_early_brand_bake_then_late_rematerialize()
    test_scrub_early_trust_labels_co_resident_and_orphan()
    test_real_pack_trust_labels_survive_rematerialize()
    test_scrub_brand_templated_headings_exact_match_only()
    print("Product face contract tests passed")
