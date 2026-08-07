"""A planner-assigned `public-detail` needs item evidence to survive.

`0e678fa` made the detail INFERENCE route-anchored, but the explicit-skeleton
escape hatch returned a planner-assigned `public-detail` unchanged — and plan
pages carry no path, so the fixed rule could never fire on them. Session-18's
AboutPage.tsx and run 124's PrivateDiningPage were both rejected wholesale
against the painting-first detail contract their plan label demanded. Measured
over the 60 stored plans (session 20): the guard flips 52 mislabeled pages
(about x9, contact x8, our-story, private-dining …) to permissive contracts and
keeps all 41 genuine detail pages (painting-detail x11, room-detail variants,
prose-agreement pages like run 88's sauna).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.ui_catalogue import infer_page_contract

# Run 88's sauna plan page, verbatim from the stored experience_plan: no
# explicit anchor, but its own prose ("Amenity Detail Page") re-infers detail —
# the agreement case the guard must not disturb.
_RUN88_SAUNA = {
    "id": "sauna",
    "title": "Relaxing Sauna Retreat",
    "page_type": "Amenity Detail Page",
    "surface": "public",
    "skeleton_id": "public-detail",
    "purpose": "To detail the sauna facilities and promote its use for guest relaxation.",
}


def test_about_page_loses_planner_assigned_detail() -> None:
    page = {
        "id": "about",
        "title": "About the Artist",
        "surface": "public",
        "skeleton_id": "public-detail",
        "purpose": "The story of the studio and the artist behind it.",
    }
    assert infer_page_contract(page)["skeleton_id"] == "public-service"


def test_detail_id_segment_keeps_the_label() -> None:
    page = {
        "id": "painting-detail",
        "title": "Painting",
        "surface": "public",
        "skeleton_id": "public-detail",
        "purpose": "One painting, up close.",
    }
    assert infer_page_contract(page)["skeleton_id"] == "public-detail"


def test_item_anchored_route_keeps_the_label() -> None:
    merged_route = {
        "id": "gallery-item",
        "path": "/gallery/:id",
        "surface": "public",
        "skeleton_id": "public-detail",
        "title": "Artwork",
    }
    assert infer_page_contract(merged_route)["skeleton_id"] == "public-detail"


def test_param_mid_path_is_not_an_item_anchor() -> None:
    # /artwork/:id/inquire is a form ABOUT an item — 0e678fa end-anchored the
    # route rule for exactly this page; the explicit label gets the same rule.
    page = {
        "id": "inquire",
        "path": "/artwork/:id/inquire",
        "surface": "public",
        "skeleton_id": "public-detail",
        "title": "Inquire",
    }
    assert infer_page_contract(page)["skeleton_id"] != "public-detail"


def test_prose_agreement_keeps_detail_without_anchor() -> None:
    assert infer_page_contract(dict(_RUN88_SAUNA))["skeleton_id"] == "public-detail"


def test_title_words_never_anchor_the_label() -> None:
    # "lodge contact details." in a TITLE is the exact bare substring 0e678fa
    # removed; only the page ID's slug may vouch for a detail page.
    page = {
        "id": "contact",
        "title": "Lodge contact details.",
        "surface": "public",
        "skeleton_id": "public-detail",
        "purpose": "How to reach the lodge.",
    }
    assert infer_page_contract(page)["skeleton_id"] == "public-service"


def test_standalone_detail_in_a_title_never_anchors() -> None:
    # The plural fixture above cannot catch a titles-widened rule (the
    # word-boundary regex refuses "details" either way — the first sweep
    # proved it). This one carries a STANDALONE "detail" in the title, with
    # prose that does not independently infer a detail page: only a rule that
    # wrongly reads titles can keep the label here.
    page = {
        "id": "our-story",
        "title": "Our detail-obsessed story",
        "surface": "public",
        "skeleton_id": "public-detail",
        "purpose": "Why the studio sweats every finish.",
    }
    assert infer_page_contract(page)["skeleton_id"] == "public-service"


def test_ops_detail_escape_hatch_is_untouched() -> None:
    page = {
        "id": "shipment-record",
        "title": "Shipment Record",
        "surface": "ops",
        "skeleton_id": "ops-detail",
        "purpose": "One shipment record for the dispatch desk staff tool.",
    }
    assert infer_page_contract(page)["skeleton_id"] == "ops-detail"
