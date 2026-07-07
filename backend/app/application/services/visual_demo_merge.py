"""Deep-merge visual demo JSON so chat refinements do not drop app_config or preview_content."""
from __future__ import annotations

import copy

LIST_KEYS = frozenset({"feature_cards", "user_journey", "screen_mockups", "ai_workflow"})
DICT_KEYS = frozenset(
    {
        "visual_theme",
        "hero",
        "admin_dashboard_preview",
        "final_cta",
        "app_config",
        "preview_content",
    }
)


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, val in override.items():
        if val is None:
            continue
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = copy.deepcopy(val)
    return out


def merge_visual_demo(existing: dict, updated: dict) -> dict:
    """Preserve existing nested config when the model returns a partial visual_demo."""
    if not existing:
        return copy.deepcopy(updated)
    if not updated:
        return copy.deepcopy(existing)

    result = copy.deepcopy(existing)
    for key, val in updated.items():
        if val is None:
            continue
        if key in DICT_KEYS and isinstance(val, dict):
            result[key] = _deep_merge(result.get(key) or {}, val)
        elif key in LIST_KEYS and isinstance(val, list) and len(val) > 0:
            result[key] = copy.deepcopy(val)
        else:
            result[key] = copy.deepcopy(val)
    return result
