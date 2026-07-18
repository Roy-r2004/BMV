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


def test_pottery_does_not_pick_fitness_template() -> None:
    from app.application.preview_app.industry_templates.loader import load_templates

    load_templates.cache_clear()
    tid = pick_template_id(industry="Arts & Crafts / Pottery Studio", seed=3)
    assert tid is None
    assert pick_template_id(industry="Studio", seed=1) is None
    assert pick_template_id(industry="Digital marketing agency portfolio", seed=2) == (
        "agency-portfolio-home"
    )


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
