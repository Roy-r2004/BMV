"""Recipes must produce distinct public-home section stacks."""
from __future__ import annotations

from app.application.preview_app.catalogue_contract.scaffold import (
    minimal_catalogue_page_scaffold,
)
from app.application.preview_app.catalogue_contract.slots import assigned_non_shell_slots
from app.application.preview_app.design_recipes import (
    apply_recipe_to_architect,
    get_recipe,
    recipe_section_slots,
)
from app.application.preview_app.industry_templates.loader import pick_template_id


def test_public_home_recipe_stacks_differ() -> None:
    stacks = {
        rid: tuple(
            recipe_section_slots(
                "public-home",
                get_recipe(rid),
                [
                    "hero",
                    "features",
                    "showcase",
                    "process",
                    "testimonials",
                    "cta",
                    "footer",
                ],
            )
        )
        for rid in (
            "editorial",
            "bold-retail",
            "warm-service",
            "craft",
            "nocturne",
            "dense-ops",
        )
    }
    # At least four unique faces — not one shared mid-stack.
    assert len(set(stacks.values())) >= 4
    assert "process" not in stacks["bold-retail"]
    assert stacks["bold-retail"][1] == "showcase"
    assert stacks["craft"][1] == "process"
    assert "credentials" in stacks["editorial"]
    assert "booking" in stacks["warm-service"]


def test_skeleton_composer_does_not_append_extra_slots_when_order_set() -> None:
    """Mirrors SkeletonComposer.resolveOrder — recipe order must drop orphan AI slots."""
    recommended = [
        "shell",
        "hero",
        "features",
        "showcase",
        "process",
        "testimonials",
        "cta",
        "footer",
    ]
    required = ["shell", "hero", "cta", "footer"]
    slots = {
        "hero": True,
        "process": True,
        "showcase": True,
        "credentials": True,
        "cta": True,
        "footer": True,
        "features": True,
        "spotlight": True,
        "testimonials": True,
    }
    order = ["hero", "process", "showcase", "credentials", "cta", "footer"]
    sequence = [s for s in order if s != "shell" and slots.get(s) is not None]
    required_missing = [
        s for s in required if s != "shell" and slots.get(s) is not None and s not in sequence
    ]
    final = [*sequence, *required_missing]
    assert final == order
    assert "features" not in final
    assert "spotlight" not in final
    # Without a recipe order, orphans would append (old behavior).
    fallback = [s for s in recommended if s != "shell" and slots.get(s) is not None]
    for key in slots:
        if key != "shell" and key not in fallback:
            fallback.append(key)
    assert "features" in fallback


def test_lock_recipe_section_order_restores_craft_face() -> None:
    from app.application.preview_app.catalogue_contract.repair import (
        lock_recipe_section_order,
    )

    mangled = """
const SKELETON_ID = "public-home" as const;
const RECIPE_ORDER = ["hero", "features", "spotlight", "showcase", "process", "testimonials", "cta", "footer"] as const;
export default function HomePage() {
  return (
    <PublicShell brandName="Clay">
      <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />
    </PublicShell>
  );
}
"""
    route = {
        "path": "/",
        "skeleton_id": "public-home",
        "section_slots": [
            "hero",
            "process",
            "showcase",
            "credentials",
            "cta",
            "footer",
        ],
    }
    locked = lock_recipe_section_order(mangled, route)
    assert '"process"' in locked
    assert locked.index('"process"') < locked.index('"showcase"')
    assert "features" not in locked.split("RECIPE_ORDER")[1].split("as const")[0]
    assert "order={RECIPE_ORDER}" in locked


def test_recipes_define_distinct_chrome() -> None:
    from app.application.preview_app.design_recipes import RECIPES, apply_recipe_to_plan

    faces = {}
    heroes = {}
    for rid in ("editorial", "bold-retail", "warm-service", "craft", "nocturne", "dense-ops"):
        plan = apply_recipe_to_plan({}, recipe_id=rid)
        ds = plan["design_system"]
        faces[rid] = (
            ds.get("shell_chrome"),
            ds.get("nav_variant"),
            ds.get("footer_variant"),
            ds.get("brand_placement"),
        )
        heroes[rid] = ds.get("hero_variant")
    # craft must not share bold-retail's product hero / chrome silhouette
    assert faces["craft"] == ("immersive", "default", "columns", "start")
    assert faces["bold-retail"] == ("immersive", "minimal", "statement", "start")
    assert heroes["craft"] == "atelier"
    assert heroes["bold-retail"] == "product"
    assert len(set(heroes.values())) == 6
    assert faces["editorial"][3] == "center"
    assert faces["dense-ops"][2] == "compact"
    assert len(set(faces.values())) >= 4
    # Keep Python recipe table in lockstep with the assertions above.
    assert RECIPES["craft"]["hero_variant"] == "atelier"
    assert RECIPES["craft"]["chrome"]["footer"] == "columns"


def test_scaffold_emits_recipe_order_prop() -> None:
    arch = {
        "routes": [
            {
                "path": "/",
                "skeleton_id": "public-home",
                "section_slots": [
                    "hero",
                    "features",
                    "showcase",
                    "process",
                    "testimonials",
                    "cta",
                    "footer",
                ],
                "component_file": "src/pages/HomePage.tsx",
                "title": "Home",
            }
        ]
    }
    route = apply_recipe_to_architect(arch, {"recipe_id": "nocturne"})["routes"][0]
    assert assigned_non_shell_slots(route) == [
        "hero",
        "showcase",
        "testimonials",
        "cta",
        "footer",
    ]
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx",
        route,
        brand_name="Nightbird",
    )
    assert "order={RECIPE_ORDER}" in tsx
    assert '"showcase"' in tsx
    assert "process:" not in tsx
    # Chrome is recipe-runtime — do not hardcode immersive for every home.
    assert 'chrome="immersive"' not in tsx


def test_pottery_picks_craft_studio_pack() -> None:
    from app.application.preview_app.industry_templates.apply import (
        apply_industry_template_to_plan,
    )
    from app.application.preview_app.industry_templates.loader import load_templates

    load_templates.cache_clear()
    tid = pick_template_id(industry="Arts & Crafts / Pottery Studio", seed=3)
    assert tid == "pottery-craft-studio"
    assert pick_template_id(industry="Studio", seed=1) is None
    assert pick_template_id(industry="Digital marketing agency portfolio", seed=2) == (
        "agency-portfolio-home"
    )
    plan = apply_industry_template_to_plan(
        {"recipe_id": "craft"},
        industry="Arts & Crafts / Pottery Studio",
        seed=3,
    )
    assert plan["industry_template_id"] == "pottery-craft-studio"
    assert any(
        "Wheel" in item["title"] or "Glaze" in item["title"]
        for item in plan["mock_seed"]["items"]
    )


def test_scaffold_reads_industry_seed() -> None:
    route = {
        "path": "/",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "process", "showcase", "cta", "footer"],
        "title": "Home",
    }
    tsx = minimal_catalogue_page_scaffold(
        "src/pages/HomePage.tsx",
        route,
        brand_name="Clay & Kiln",
    )
    assert "import { images, seed } from '@/data/mock'" in tsx
    assert "(seed.items ?? []).map" in tsx
    assert "seed.process ?? []" in tsx
    assert "Signature service" not in tsx


def test_enriched_industry_packs_carry_seed_items() -> None:
    from app.application.preview_app.industry_templates.apply import (
        apply_industry_template_to_plan,
    )
    from app.application.preview_app.industry_templates.loader import load_templates

    load_templates.cache_clear()
    cases = (
        ("Fitness gym pilates studio", "fitness-studio-home", "Strength"),
        ("Dental clinic healthcare", "clinic-dental-home", "patient"),
        ("Plumbing HVAC handyman trades", "home-services-trades", "leak"),
    )
    for industry, template_id, needle in cases:
        assert pick_template_id(industry=industry, seed=2) == template_id
        plan = apply_industry_template_to_plan({}, industry=industry, seed=2)
        blob = " ".join(
            f"{item.get('title', '')} {item.get('description', '')}"
            for item in plan["mock_seed"]["items"]
        ).lower()
        assert needle.lower() in blob
        assert plan["mock_seed"]["hero"]["subcopy"]


def test_booking_and_detail_recipe_stacks_differ() -> None:
    booking = {
        rid: tuple(
            recipe_section_slots(
                "public-booking",
                get_recipe(rid),
                ["hero", "process", "credentials", "booking", "footer"],
            )
        )
        for rid in ("editorial", "warm-service", "bold-retail", "craft")
    }
    detail = {
        rid: tuple(
            recipe_section_slots(
                "public-detail",
                get_recipe(rid),
                ["hero", "showcase", "process", "features", "cta", "footer"],
            )
        )
        for rid in ("editorial", "warm-service", "bold-retail", "craft")
    }
    assert len(set(booking.values())) >= 3
    assert booking["editorial"][1] == "credentials"
    assert booking["warm-service"][1] == "process"
    assert booking["bold-retail"][1] == "showcase"
    assert "process" not in booking["bold-retail"]
    assert detail["craft"][1] == "process"
    assert detail["bold-retail"][1] == "showcase"
    assert "booking" in detail["warm-service"]

    tsx = minimal_catalogue_page_scaffold(
        "src/pages/BookPage.tsx",
        {
            "path": "/book",
            "skeleton_id": "public-booking",
            "section_slots": list(booking["craft"]),
            "title": "Book",
        },
        brand_name="Studio",
    )
    assert "order={RECIPE_ORDER}" in tsx
    assert "seed.treatments ?? []" in tsx


def test_mismatched_template_does_not_override_craft_home() -> None:
    arch = {
        "routes": [
            {
                "path": "/",
                "skeleton_id": "public-home",
                "section_slots": [
                    "hero",
                    "features",
                    "showcase",
                    "process",
                    "testimonials",
                    "cta",
                    "footer",
                ],
            }
        ]
    }
    plan = {
        "recipe_id": "craft",
        "template_section_order": [
            "hero",
            "showcase",
            "features",
            "process",
            "testimonials",
            "cta",
            "footer",
        ],
        # Missing hint must not wipe the craft face.
        "design_system": {},
    }
    slots = apply_recipe_to_architect(arch, plan)["routes"][0]["section_slots"]
    assert slots[1] == "process"
    assert slots == [
        "hero",
        "process",
        "showcase",
        "credentials",
        "cta",
        "footer",
    ]
