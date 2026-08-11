"""Load + pick industry templates (rich content packs in packs/*.json)."""
from __future__ import annotations

import hashlib
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
        # Same word as "shop" and "store", and it cost request 160 its identity.
        # A bike workshop declaring "Bicycle retail, service and workshop"
        # matched `fashion-retail-storefront` on **"retail" alone** — the only
        # pack that matched at all — and shipped "The rack is live" and "Shop
        # the new drop before sizes thin out." At six characters it cleared
        # `_MIN_DISTINCTIVE_TOKEN_LEN`, so one declared category word chose a
        # whole visual identity. With it weak, that brief matches nothing and
        # falls to recipe-only, which this function's own docstring already
        # calls the better answer. Fashion still matches on fashion, apparel,
        # boutique and clothing.
        "retail",
        "retailer",
        "service",
        "services",
        "business",
        "online",
        "local",
        "class",
        "classes",
        "booking",
        "bookings",
        "design",
        "maker",
        "makers",
        "portfolio",
    }
)

# A pack is a whole visual identity — a lone tag hit must be a long, declared word.
_MIN_DISTINCTIVE_TOKEN_LEN = 6

# "…not a booking SaaS or clinic front desk" says what the business is NOT; keyword
# matching cannot see negation, so those clauses are dropped before scoring.
_NEGATED_CLAUSE_RE = re.compile(
    r"\b(?:not|never|no longer|isn'?t|aren'?t|rather than|instead of)\b[^.;:!?\n|–—]*",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def load_templates() -> dict[str, dict[str, Any]]:
    from app.application.preview_app.industry_templates.compatible_recipes import (
        compatible_recipes_for,
    )

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
        # Stage A / 3.2 (session-26 ruling): every loaded pack carries its
        # compatible recipe set. STAMPED from the one keyed map, never
        # authored in the pack JSON — the derivation rule lives beside the
        # data exactly once (compatible_recipes.py), and a pack the map does
        # not know gets an empty tuple, which the map-corpus pin red-exits.
        data["compatible_recipes"] = list(compatible_recipes_for(tid))
        out[tid] = data
    return out


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}


def _claimed_tokens(text: str) -> set[str]:
    """Tokens the brief actually claims — negated clauses do not count."""
    return _tokenize(_NEGATED_CLAUSE_RE.sub(" ", text or ""))


def _rotation(seed: int, template_id: str) -> int:
    """Stable per-seed tiebreak — never ranks packs by id spelling."""
    digest = hashlib.sha256(f"{seed}:{template_id}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


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
    declared_tokens = _claimed_tokens(industry)
    tokens = declared_tokens | _claimed_tokens(context)
    scored: list[tuple[tuple[int, int, int, int], str]] = []
    for tid, pack in templates.items():
        tag_tokens = _tokenize(" ".join(pack.get("industry_tags") or []))
        sk = str(pack.get("skeleton_id") or "")
        if surface == "ops" and not _is_ops_skeleton(sk):
            continue
        if surface == "public" and not _is_public_marketing_skeleton(sk):
            continue
        overlap = tokens & tag_tokens
        # Require a real match — shared words like "studio"/"home" are too weak
        # and were forcing pottery → fitness/agency packs.
        strong = {t for t in overlap if t not in _WEAK_INDUSTRY_TOKENS}
        if not strong:
            continue
        declared = strong & declared_tokens
        if len(strong) == 1 and not any(
            len(t) >= _MIN_DISTINCTIVE_TOKEN_LEN for t in declared
        ):
            # One stray word in generated prose must not pick a visual identity.
            continue
        # The declared industry is stronger evidence than generated prose.
        score = len(strong) + 2 * len(declared)
        coverage = 100 * len(strong) // max(len(tag_tokens), 1)
        scored.append(((score, len(declared), coverage, _rotation(seed, tid)), tid))
    if scored:
        # Merit first (weighted hits, declared hits, tag coverage), then seeded rotation.
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


#: A pack sentence must be at least this long before shipping it verbatim counts
#: as a defect. Short leaves are structure, not voice — "bold", "Popular",
#: "60 min" — and a business may legitimately write them. Sentences are what the
#: owner ruled must be written for the business.
_PACK_SENTENCE_MIN_CHARS = 16


@lru_cache(maxsize=1)
def pack_literal_sentences() -> frozenset[str]:
    """Every sentence the packs would ship if nobody replaced it.

    Owner ruling 2026-08-09: **a pack carries structure and slot choices; every
    sentence is written for the business.** Request 160, a bike workshop, shipped
    `packs/fashion-retail-storefront.json` lines 60-64 unedited — *"The rack is
    live"*, *"Shop the new drop before sizes thin out"*, *"Restock alerts"* —
    and request 158, a bakery doing pre-orders, shipped
    `restaurant-cafe-home.json`'s *"Hold a table — or join the walk-in list with
    a real wait time."* Neither is a dead link or a contract violation, so no
    gate saw them.

    This is the set the gate compares against, by **exact leaf**, never
    substring: a pack sentence is distinctive enough that an identical string in
    a shipped app came from the pack. Anything shorter than
    `_PACK_SENTENCE_MIN_CHARS`, or without a space, is structure rather than
    voice and is excluded — as are hrefs and anchors, which are the route
    literals' problem and are already repaired elsewhere.
    """

    def _walk(node: Any, out: set[str]) -> None:
        if isinstance(node, dict):
            for value in node.values():
                _walk(value, out)
        elif isinstance(node, list):
            for value in node:
                _walk(value, out)
        elif isinstance(node, str):
            text = node.strip()
            if (
                len(text) >= _PACK_SENTENCE_MIN_CHARS
                and " " in text
                and not text.startswith(("/", "#", "http"))
            ):
                out.add(text)

    sentences: set[str] = set()
    for pack in load_templates().values():
        _walk(pack.get("mock_seed"), sentences)
    return frozenset(sentences)
