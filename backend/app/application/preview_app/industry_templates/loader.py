"""Load + pick industry templates (rich content packs in packs/*.json)."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.application.preview_app.industry_templates import TEMPLATE_IDS

_PACKS_DIR = Path(__file__).resolve().parent / "packs"

# Soft-fallback for public surface must stay on marketing homes — never utilities.
_PUBLIC_HOME_SKELETONS = frozenset({"public-home", "public-service", "public-detail", "public-booking"})
_UTILITY_SKELETON_PREFIXES = ("utility-", "member-", "checkout")

# Shared business vocabulary that must never count as a unique industry hit.
_WEAK_INDUSTRY_TOKENS = frozenset(
    {
        "studio",
        "home",
        "shop",
        "store",
        "service",
        "services",
        "business",
        "online",
        "local",
        "class",
        "classes",
        "booking",
        "bookings",
        "craft",
        "crafts",
        "art",
        "arts",
        "design",
        "creative",
        "maker",
        "makers",
    }
)


@lru_cache(maxsize=1)
def load_templates() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not _PACKS_DIR.is_dir():
        return out
    for path in sorted(_PACKS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        tid = str(data.get("id") or path.stem).strip()
        if not tid:
            continue
        out[tid] = data
    return out


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _is_ops_skeleton(skeleton_id: str) -> bool:
    return skeleton_id.startswith("ops")


def _is_public_marketing_skeleton(skeleton_id: str) -> bool:
    if skeleton_id in _PUBLIC_HOME_SKELETONS:
        return True
    if _is_ops_skeleton(skeleton_id):
        return False
    return not any(skeleton_id.startswith(p) or skeleton_id == p.rstrip("-") for p in _UTILITY_SKELETON_PREFIXES)


def pick_template_id(
    *,
    industry: str = "",
    surface: str = "public",
    seed: int = 0,
    context: str = "",
) -> str | None:
    """Best-effort industry match; None = recipe-only (better than a wrong utility pack)."""
    templates = load_templates()
    if not templates:
        return None
    tokens = _tokenize(f"{industry} {context}")
    scored: list[tuple[int, str]] = []
    for tid, pack in templates.items():
        tag_tokens = _tokenize(" ".join(pack.get("industry_tags") or []))
        sk = str(pack.get("skeleton_id") or "")
        if surface == "ops" and not _is_ops_skeleton(sk):
            continue
        if surface == "public" and not _is_public_marketing_skeleton(sk):
            continue
        overlap = tokens & tag_tokens
        strong = {t for t in overlap if t not in _WEAK_INDUSTRY_TOKENS}
        # Require a real match — shared words like "studio"/"home"/"arts" are too weak
        # and were forcing pottery → fitness/agency packs.
        if len(strong) >= 2:
            scored.append((len(strong) * 10 + (seed % 3), tid))
        elif len(strong) == 1:
            # Allow only distinctive tags (length > 5) as a single-token hit.
            distinctive = {t for t in strong if len(t) > 5}
            if distinctive:
                scored.append((8 + (seed % 3), tid))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]

    # Never rotate a random ops CRM/KPI pack on a miss — wrong industry voice
    # (e.g. trading desks becoming "client follow-up" dashboards) is worse than
    # recipe-only generation.
    return None


def get_template(template_id: str | None) -> dict[str, Any] | None:
    if not template_id:
        return None
    return load_templates().get(template_id)
