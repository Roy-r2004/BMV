"""pick_template_id evidence rules: declared industry, negation, merit tie-breaks."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.industry_templates import TEMPLATE_IDS  # noqa: E402
from app.application.preview_app.industry_templates import loader  # noqa: E402
from app.application.preview_app.industry_templates.loader import (  # noqa: E402
    load_templates,
    pick_template_id,
)


def setup_function() -> None:
    load_templates.cache_clear()


def _synthetic(monkeypatch: Any, packs: dict[str, dict[str, Any]]) -> None:
    monkeypatch.setattr(loader, "load_templates", lambda: packs)


def _pack(tid: str, tags: list[str]) -> dict[str, Any]:
    return {"id": tid, "label": tid, "industry_tags": tags, "skeleton_id": "public-home"}


def test_declared_single_token_still_picks_a_pack() -> None:
    assert pick_template_id(industry="Orthodontics practice") == "clinic-dental-home"
    assert pick_template_id(industry="Arts & Crafts / Pottery Studio", seed=3) == (
        "pottery-craft-studio"
    )


def test_stray_prose_token_cannot_pick_a_pack() -> None:
    # "orthodontics" is distinctive but appears once, in generated prose only.
    #
    # This asserted `is None`, which only held while "bookshop" matched no pack at
    # all. Once retail-store-home existed the proxy broke, so pin the real intent:
    # the pack must come from the *declared* industry, never the leaked prose.
    picked = pick_template_id(
        industry="Neighbourhood bookshop",
        context=(
            "The owner previously ran the front office of an orthodontics practice "
            "and wants the same calm feeling."
        ),
    )
    assert picked != "clinic-dental-home", picked
    assert picked in (None, "retail-store-home"), picked


def test_negated_clause_cannot_pick_a_pack() -> None:
    # Same correction as above: assert the negated words lost, not that nothing won.
    picked = pick_template_id(
        industry="Neighbourhood bookshop",
        context="A reading room for the street - not a dental clinic dentist waiting room.",
    )
    assert picked != "clinic-dental-home", picked
    assert picked in (None, "retail-store-home"), picked


def test_tie_break_is_not_descending_template_id(monkeypatch: Any) -> None:
    _synthetic(
        monkeypatch,
        {
            "aaa-pack": _pack("aaa-pack", ["gizmo", "widget"]),
            "zzz-pack": _pack("zzz-pack", ["gizmo", "widget"]),
        },
    )
    picks = {
        seed: pick_template_id(industry="gizmo widget", seed=seed) for seed in range(12)
    }
    assert set(picks.values()) == {"aaa-pack", "zzz-pack"}
    # Deterministic for a given seed.
    for seed, tid in picks.items():
        assert pick_template_id(industry="gizmo widget", seed=seed) == tid


def test_tie_break_prefers_the_more_specific_pack(monkeypatch: Any) -> None:
    broad = [f"tag{i}" for i in range(18)] + ["gizmo", "widget"]
    _synthetic(
        monkeypatch,
        {
            "aaa-narrow": _pack("aaa-narrow", ["gizmo", "widget"]),
            "zzz-broad": _pack("zzz-broad", broad),
        },
    )
    for seed in range(12):
        assert pick_template_id(industry="gizmo widget", seed=seed) == "aaa-narrow"


def test_declared_industry_outweighs_prose(monkeypatch: Any) -> None:
    _synthetic(
        monkeypatch,
        {
            "declared-pack": _pack("declared-pack", ["gizmo", "widget"]),
            "prose-pack": _pack("prose-pack", ["sprocket", "flange", "gasket"]),
        },
    )
    assert (
        pick_template_id(
            industry="gizmo widget",
            context="sprocket flange gasket",
            seed=1,
        )
        == "declared-pack"
    )


def test_registry_ids_match_pack_files() -> None:
    assert set(TEMPLATE_IDS) == set(load_templates())


if __name__ == "__main__":
    setup_function()
    test_declared_single_token_still_picks_a_pack()
    test_stray_prose_token_cannot_pick_a_pack()
    test_negated_clause_cannot_pick_a_pack()
    test_registry_ids_match_pack_files()
    print("Industry template pick evidence tests passed")
