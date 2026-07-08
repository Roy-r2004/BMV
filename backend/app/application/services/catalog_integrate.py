"""One-click integrate / remove pre-built AI features from the catalog."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.application.services.solution_edit import _merge_overlay
from app.application.services.user_auth import add_message, get_or_create_workspace, parse_overlay, save_overlay
from app.data.ai_feature_catalog import get_catalog_feature


def _contribution_from_patch(patch: dict[str, Any]) -> dict[str, Any]:
    sections = patch.get("sections") or []
    section_ids = [
        str(s["id"])
        for s in sections
        if isinstance(s, dict) and s.get("id")
    ]
    contrib: dict[str, Any] = {"sectionIds": section_ids}
    if patch.get("aiChips"):
        contrib["aiChips"] = list(patch["aiChips"])
    for key in ("ctaPrimary", "ctaSecondary"):
        if patch.get(key):
            contrib[key] = patch[key]
    if patch.get("heroStats"):
        contrib["heroStats"] = deepcopy(patch["heroStats"])
    return contrib


def _save_contribution(overlay: dict[str, Any], feature_id: str, contrib: dict[str, Any]) -> None:
    contributions = dict(overlay.get("catalogContributions") or {})
    contributions[feature_id] = contrib
    overlay["catalogContributions"] = contributions


def integrate_catalog_feature(
    db: Session,
    *,
    user_id: int,
    solution_id: str,
    feature_id: str,
) -> tuple[dict[str, Any], str, list[str]]:
    feature = get_catalog_feature(solution_id, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found for this solution.")

    ws = get_or_create_workspace(db, user_id, solution_id)
    overlay = parse_overlay(ws)
    integrated = list(overlay.get("integratedFeatures") or [])

    if feature_id in integrated:
        return overlay, f"“{feature['title']}” is already on your site.", []

    patch = dict(feature.get("patch") or {})
    contrib = _contribution_from_patch(patch)

    existing_chips = list(overlay.get("aiChips") or [])
    new_chips = list(patch.get("aiChips") or [])
    if new_chips:
        seen = set(existing_chips)
        merged = existing_chips + [c for c in new_chips if c not in seen]
        patch["aiChips"] = merged

    integrated.append(feature_id)
    patch["integratedFeatures"] = integrated

    overlay = _merge_overlay(overlay, patch, solution_id=solution_id)
    _save_contribution(overlay, feature_id, contrib)
    save_overlay(db, ws, overlay)

    title = feature.get("title") or feature_id
    changes = [f"Integrated {title}"]
    reply = f"Added {title} to your personal copy. Check the live preview — chips, sections, and CTAs update instantly."

    add_message(db, ws.id, role="assistant", content=reply)
    return overlay, reply, changes


def _cta_used_by_other(
    contributions: dict[str, Any],
    integrated: list[str],
    feature_id: str,
    key: str,
    value: str,
) -> bool:
    for fid in integrated:
        if fid == feature_id:
            continue
        if contributions.get(fid, {}).get(key) == value:
            return True
    return False


def remove_catalog_feature(
    db: Session,
    *,
    user_id: int,
    solution_id: str,
    feature_id: str,
) -> tuple[dict[str, Any], str, list[str]]:
    feature = get_catalog_feature(solution_id, feature_id)
    if not feature:
        raise HTTPException(status_code=404, detail="Feature not found for this solution.")

    ws = get_or_create_workspace(db, user_id, solution_id)
    overlay = parse_overlay(ws)
    integrated = list(overlay.get("integratedFeatures") or [])

    if feature_id not in integrated:
        title = feature.get("title") or feature_id
        return overlay, f"“{title}” is not on your site.", []

    contributions = dict(overlay.get("catalogContributions") or {})
    contrib = contributions.get(feature_id) or _contribution_from_patch(feature.get("patch") or {})
    remaining = [fid for fid in integrated if fid != feature_id]

    section_ids = set(contrib.get("sectionIds") or [])
    if section_ids:
        overlay["sections"] = [
            s for s in (overlay.get("sections") or [])
            if not (isinstance(s, dict) and str(s.get("id")) in section_ids)
        ]

    chip_remove = set(contrib.get("aiChips") or [])
    if chip_remove:
        overlay["aiChips"] = [
            c for c in (overlay.get("aiChips") or [])
            if c not in chip_remove
        ]
        if not overlay["aiChips"]:
            overlay.pop("aiChips", None)

    for cta_key in ("ctaPrimary", "ctaSecondary"):
        val = contrib.get(cta_key)
        if val and overlay.get(cta_key) == val:
            if not _cta_used_by_other(contributions, remaining, feature_id, cta_key, val):
                overlay.pop(cta_key, None)

    if contrib.get("heroStats") and overlay.get("heroStats") == contrib.get("heroStats"):
        if not any(contributions.get(fid, {}).get("heroStats") for fid in remaining):
            overlay.pop("heroStats", None)

    contributions.pop(feature_id, None)
    overlay["catalogContributions"] = contributions
    overlay["integratedFeatures"] = remaining

    save_overlay(db, ws, overlay)

    title = feature.get("title") or feature_id
    changes = [f"Removed {title}"]
    reply = f"Removed {title} from your personal copy. The live preview has been updated."

    add_message(db, ws.id, role="assistant", content=reply)
    return overlay, reply, changes
