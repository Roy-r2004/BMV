"""Load + pick industry templates (content packs land tomorrow)."""
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
) -> str | None:
    """Best-effort industry match; None = recipe-only (better than a wrong utility pack)."""
    templates = load_templates()
    if not templates:
        return None
    tokens = _tokenize(industry)
    scored: list[tuple[int, str]] = []
    for tid, pack in templates.items():
        tag_tokens = _tokenize(" ".join(pack.get("industry_tags") or []))
        sk = str(pack.get("skeleton_id") or "")
        if surface == "ops" and not _is_ops_skeleton(sk):
            continue
        if surface == "public" and not _is_public_marketing_skeleton(sk):
            continue
        hit = len(tokens & tag_tokens)
        if hit:
            scored.append((hit * 10 + (seed % 3), tid))
    if scored:
        scored.sort(reverse=True)
        return scored[0][1]

    # Soft fallback only among marketing homes for public; ops dashboards for ops.
    candidates = [
        tid
        for tid in TEMPLATE_IDS
        if tid in templates
        and (
            (_is_ops_skeleton(str(templates[tid].get("skeleton_id") or "")) if surface == "ops"
             else _is_public_marketing_skeleton(str(templates[tid].get("skeleton_id") or "")))
        )
    ]
    if not candidates:
        return None
    return candidates[seed % len(candidates)]


def get_template(template_id: str | None) -> dict[str, Any] | None:
    if not template_id:
        return None
    return load_templates().get(template_id)
