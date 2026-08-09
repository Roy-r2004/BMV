"""
Per-business preview imagery.

Primary: Pexels Search API (PEXELS_API_KEY) with queries from business + industry + slot.
Fallback: curated Unsplash CDN URLs rotated by seed (no API key required).

Never redistribute Unsplash Dataset dumps — product use is API / CDN URLs only.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

_LIBRARY: dict[str, dict[str, str]] = {
    "beauty": {
        "hero": "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1616394584738-fc6e612e71b9?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=900&q=80&fit=crop&auto=format",
    },
    "fitness": {
        "hero": "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1549060279-7e168fcee0c2?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1540497077202-7c8a3999166f?w=900&q=80&fit=crop&auto=format",
    },
    "food": {
        "hero": "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1476224203421-9ac39bcb3327?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=900&q=80&fit=crop&auto=format",
    },
    "health": {
        "hero": "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1551190822-a9333d879b1f?w=900&q=80&fit=crop&auto=format",
    },
    "tech": {
        # photo-1551434678… formerly 404'd on images.unsplash.com — keep CDN-only known-good IDs.
        "hero": "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1537432376769-00f5c2f4c8d2?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=900&q=80&fit=crop&auto=format",
    },
    "art": {
        "hero": "https://images.unsplash.com/photo-1541961017774-22349e4a1262?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1579783902614-a3fb3927b6a5?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1460661419201-fd4cecdf8a8b?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1482160549825-59d1b23cb208?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1549490349-8643362247b5?w=900&q=80&fit=crop&auto=format",
    },
    "realestate": {
        "hero": "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1582268611958-ebfd161ef9cf?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=900&q=80&fit=crop&auto=format",
    },
    "education": {
        "hero": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1513258496099-48168024aec0?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1427504494785-3a9ca7044f45?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=900&q=80&fit=crop&auto=format",
    },
    "retail": {
        "hero": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1555529669-e69e7aa0ba9a?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1523381210434-271e8be1f52b?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1489987707025-afc232f7ea0f?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=900&q=80&fit=crop&auto=format",
    },
    "generic": {
        "hero": "https://images.unsplash.com/photo-1553877522-43269d4ea984?w=1400&q=80&fit=crop&auto=format",
        "hero2": "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=1400&q=80&fit=crop&auto=format",
        "card1": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=700&q=80&fit=crop&auto=format",
        "card2": "https://images.unsplash.com/photo-1497366811353-6870744d04b2?w=700&q=80&fit=crop&auto=format",
        "card3": "https://images.unsplash.com/photo-1552664730-d307ca884978?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1542744173-8e7e53415bb0?w=900&q=80&fit=crop&auto=format",
    },
}

_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "art": [
        "fine art",
        "art gallery",
        "artwork",
        "artworks",
        "artist",
        "atelier",
        "oil painting",
        "paintings",
        "painting studio",
        "sculpture",
        "exhibition",
        "curated gallery",
        "gallery",
        "canvas",
    ],
    "beauty": ["beauty", "skin", "spa", "facial", "salon", "cosmetic", "aesthetic", "skincare", "hair", "nail", "wellness", "massage"],
    "fitness": ["fitness", "gym", "sport", "yoga", "pilates", "crossfit", "personal trainer", "coach", "workout", "health coach", "nutrition", "dietitian"],
    "food": ["food", "restaurant", "cafe", "bakery", "catering", "meal", "kitchen", "chef", "coffee", "bar", "bistro", "dining"],
    "health": ["health", "medical", "clinic", "doctor", "dentist", "therapy", "physiotherapy", "mental health", "hospital", "pharmacy", "chiropractic"],
    "tech": ["software", "saas", "tech", "app", "digital", "ai", "automation", "platform", "startup", "development", "agency"],
    "realestate": ["real estate", "property", "realty", "mortgage", "housing", "agent", "realtor", "home", "apartment", "commercial"],
    "education": ["education", "school", "tutor", "course", "academy", "training", "learning", "coaching", "workshop", "certification"],
    "retail": ["retail", "fashion", "apparel", "clothing", "boutique", "outfitter", "outdoor", "gear", "ecommerce", "shop", "store", "merchandise"],
}

_SLOTS = ("hero", "hero2", "card1", "card2", "card3", "ambient")

#: Layout slots whose subject is a *thing*, not a scene. The rest are
#: scene-setting, where a person in frame is usually the better photograph.
_OBJECT_SLOTS = frozenset({"card1"})

# Per-catalogue-item photographs. The six layout slots are shared page furniture;
# a storefront's items each need their own picture or the grid captions two
# different products with one photo. Harvested from search results the slot loop
# already paid for, so this costs at most one extra request.
#
# **24, sized from the corpus rather than from a search page (2026-08-09).** This
# was 8, and 8 was never a considered number — it was `_search_pexels`'s
# `per_page=8` showing through. Census over the 18 stored workspaces with a
# slugged catalogue: **13 declare more items than that**, and the cycle at
# `item_source.py` is `i % len(item_slot_names())`, so item 9 showed item 1's
# photograph. Request 65 is 16 items over 8 photos — **every picture twice**.
# For a gallery selling originals two works sharing one photograph contradicts
# the product outright.
#
# 24 covers the largest catalogue in the corpus (16) with headroom and still
# costs **one request**: Pexels takes `per_page` up to 80, so a bigger pool is a
# bigger page, not a second call. The cost is ~2 KB more in the seed prompt.
_ITEM_SLOT_COUNT = 24
#: What to ask Pexels for in that single request. Larger than the pool on
#: purpose: duplicates, the person/empty-prop ranking and `used_ids` all thin the
#: result, so asking for exactly 24 would deliver fewer.
_ITEM_POOL_PER_PAGE = 40
_ITEM_SLOTS = tuple(f"item{i}" for i in range(1, _ITEM_SLOT_COUNT + 1))
# No "plain background": that phrase is what matched the product *mockups* —
# request 45 captioned "Deep Sea Currents" with two blank canvases on easels.
_ITEM_POOL_FRAMING = "close up detail"

#: Words in a Pexels `alt` that mean the photograph is of a *person*, or of an
#: empty prop, rather than of the thing being sold. Query wording alone cannot
#: keep these out: request 45's gallery captioned four pieces with photos of
#: someone painting, and "Deep Sea Currents" with two blank canvases on easels —
#: a product mockup that "product detail on plain background" asked for. The
#: search index knows what its photographs contain; this reads that.
_ITEM_SUBJECT_REJECT_RE = re.compile(
    r"\b(?:person|people|woman|women|man|men|girl|boy|lady|guy|human|child|"
    r"children|kid|couple|family|crowd|group|portrait|face|smil\w*|posing|model|"
    r"artist|painter|hand|hands|arm|holding|wearing|sitting|standing|working|"
    r"admiring|visitor|museum|tourist|palette|brush|studio\s+shot|"
    r"blank|empty|plain|mockup|mock[-\s]?up|template|easel|frame\s+mockup|"
    r"canvas(?:es)?\s+on\s+easel)\b",
    re.I,
)


def item_slot_names() -> tuple[str, ...]:
    """The catalogue photo pool, in order — ``item1…itemN``.

    Public because the pool is a *contract* between three modules: the fetcher
    fills it, `normalize_image_slot_map` guarantees it, and the catalogue codemods
    bind cards to it. Request 70 shipped two cards showing a person at an easel
    because the page-side pool was restated as a literal instead of read from here.
    """
    return _ITEM_SLOTS


def _photo_is_on_subject(photo: dict[str, Any]) -> bool:
    """True when the photo's own description does not name a person or an empty prop.

    An absent `alt` is treated as on-subject: unknown must not outrank rejected.
    """
    alt = str(photo.get("alt") or "").strip()
    if not alt:
        return True
    return _ITEM_SUBJECT_REJECT_RE.search(alt) is None

_SLOT_QUERY_SUFFIX: dict[str, str] = {
    "hero": "hero lifestyle wide",
    "hero2": "workspace interior",
    "card1": "product detail",
    "card2": "customer experience",
    "card3": "team service",
    "ambient": "atmosphere background",
}

# Art/portfolio heroes must be the work itself — "lifestyle wide" returns painters.
_SLOT_QUERY_SUFFIX_BY_CATEGORY: dict[str, dict[str, str]] = {
    "art": {
        "hero": "abstract oil painting canvas close up",
        "hero2": "oil painting texture detail",
        "card1": "abstract oil painting artwork",
        "card2": "layered oil painting canvas",
        "card3": "contemporary painting detail",
        "ambient": "gallery wall oil paintings",
    },
}

# Concrete subject nouns per category — search quality beats raw brief prose.
_CATEGORY_QUERY_HINT: dict[str, str] = {
    "art": "art gallery painting studio",
    "beauty": "spa salon beauty",
    "fitness": "gym fitness training",
    "food": "restaurant food dining",
    "health": "clinic healthcare",
    "tech": "software office technology",
    "realestate": "modern home real estate",
    "education": "classroom learning education",
    "retail": "fashion retail apparel outdoor gear",
    "generic": "professional small business",
}

_GENERIC_QUERY_HINT = _CATEGORY_QUERY_HINT["generic"]

# The *thing being sold*, per category. `_CATEGORY_QUERY_HINT` names the
# environment — "art gallery painting studio" is what put an artist at an easel on
# four of request 45's ten pieces — so the item grid needs its own vocabulary,
# naming the artifact and nothing around it.
_CATEGORY_ITEM_HINT: dict[str, str] = {
    "art": "abstract oil painting canvas artwork",
    "beauty": "skincare product bottle jar",
    "fitness": "gym equipment weights kit",
    "food": "plated dish food",
    "health": "medical supplies equipment",
    "tech": "app screen dashboard device",
    "realestate": "house exterior interior room",
    "education": "book course material",
    "retail": "apparel garment product",
    "generic": "product",
}

# Pexels truncates at 120 chars; keep composed role queries inside that budget.
_MAX_QUERY_WORDS = 14

# The brief's own industry prose leads a role query; cap it so brand + industry +
# role always fit inside _MAX_QUERY_WORDS and the role can never be clipped away.
_MAX_INDUSTRY_QUERY_WORDS = 6


# Keywords that only mean their bucket in company. Each is an ordinary word in
# some *other* industry's own description of itself, so on its own it is not
# evidence of anything. The value is the counter-example that earns it a place —
# "these feel vague" is not a reason, and this table is what stops the resolver
# guessing.
_WEAK_KEYWORDS: dict[str, str] = {
    "boutique": "a boutique law firm or consultancy is not a shop",
    "commercial": "commercial cleaning, commercial law, commercial insurance",
    "home": "home services, care at home, home cooking",
    "agent": "insurance, travel and booking agents",
    "agency": "any agency, not only a digital one",
    "shop": "a body shop, a bike shop, a print shop",
    "store": "any business at all with a storefront",
    "outdoor": "outdoor dining, an outdoor venue, outdoor events",
    "gear": "gear as machinery, gear as any trade's equipment",
    "platform": "every business calls something a platform",
    "digital": "digital anything",
    "app": "shortened from an application of any kind",
    "coach": "coach a team, a subject, or a career",
    "coaching": "and education claims it too",
    "training": "staff training, dog training, strength training",
    "workshop": "an auto workshop and a teaching workshop",
    "course": "a golf course and a training course",
    "kitchen": "a kitchen fitter and a restaurant kitchen",
    "bar": "a bar of soap, the bar association, a crossbar",
    "sport": "a sports bar, sportswear",
    "wellness": "beauty, fitness and health all claim it",
    "hair": "a salon and a pet groomer",
    "nail": "a manicure and a nail gun",
    "health": "a health coach, health food, health insurance",
    "canvas": "canvas awnings, and a learning platform",
}

_SPECIFIC_KEYWORD_WEIGHT = 2
_WEAK_KEYWORD_WEIGHT = 1
# One specific keyword is enough; one weak keyword never is. Two weak keywords
# corroborate each other, which is what "in company" means here.
_MIN_CATEGORY_SCORE = 2


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Word-anchored keyword matcher that still tolerates a plural (``salon`` → ``salons``).

    Unanchored substring matching mis-buckets ordinary phrasings: ``ai`` inside
    ``repair`` sent every auto-repair brief to ``tech``, and ``app`` inside
    ``apparel`` sent fashion briefs there too.
    """
    return re.compile(rf"\b{re.escape(keyword)}(?:e?s)?\b")


_INDUSTRY_KEYWORD_PATTERNS: dict[str, tuple[tuple[re.Pattern[str], int], ...]] = {
    category: tuple(
        (
            _keyword_pattern(kw),
            _WEAK_KEYWORD_WEIGHT if kw in _WEAK_KEYWORDS else _SPECIFIC_KEYWORD_WEIGHT,
        )
        for kw in keywords
    )
    for category, keywords in _INDUSTRY_KEYWORDS.items()
}


def _category_scores(industry: str) -> dict[str, int]:
    industry_lower = (industry or "").lower()
    scores: dict[str, int] = {}
    for category, patterns in _INDUSTRY_KEYWORD_PATTERNS.items():
        score = sum(weight for pattern, weight in patterns if pattern.search(industry_lower))
        if score:
            scores[category] = score
    return scores


def _resolve_category(industry: str) -> str:
    """Best-supported imagery bucket for an industry phrase, or ``generic``.

    Scored, not first-match. This used to return the first category in table order
    with *any* keyword hit, so one ordinary word decided the whole bucket: a
    "Boutique law firm — estate and family law" resolved to ``retail`` on the word
    ``boutique`` and a "Commercial cleaning company" to ``realestate`` on
    ``commercial``.

    That is not a cosmetic misfile. `_curated_fallback` picks an entire photo
    library from this one value, so the law firm's hero *was* a stock photograph of
    a shopfront, and the roleless query carried "fashion retail apparel outdoor
    gear" into a search for a law firm.

    Note that word-boundary anchoring — the other half of the original fix, and
    already in place — cannot help here: "Boutique law firm" genuinely contains the
    word ``boutique``. The defect is that a weak keyword was allowed to win alone.

    ``generic`` is a real answer, not a failure: its hint is "professional small
    business", which is right for every industry this table has no bucket for
    (legal, trades, automotive, logistics...).
    """
    scores = _category_scores(industry)
    if not scores:
        return "generic"
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    top_category, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0
    if top_score < _MIN_CATEGORY_SCORE or top_score <= runner_up:
        return "generic"
    return top_category


def resolve_industry_category(industry: str) -> str:
    """Coarse imagery category for an industry phrase (``generic`` when unknown)."""
    return _resolve_category(industry)


#: Enough words to name the trade without turning a paragraph into a search query.
_DERIVED_INDUSTRY_MAX_KEYWORDS = 4


def derive_industry_from_description(description: str) -> str:
    """The industry phrase a business description already states, or ``""``.

    Requests 66, 67 and 68 were created without the `industry` form field. Each
    one carried *"An independent fine-art gallery representing a single painter …
    original oil paintings"* in `business_description`, and each resolved to
    `generic` — shipping SIGMA camera-lens packaging, a sales-volume chart and an
    audio-editing timeline to a fine-art gallery. Request 70 is the same
    description with the field filled in, and it shipped paintings. **The pipeline
    had the answer in hand and did not read it.**

    Deterministic, and deliberately so — this runs on the latency budget's
    critical path, before the first model call. It reuses the scoring the imagery
    resolver already applies to the `industry` field: weak keywords need
    corroboration, the winner must clear the runner-up, and anything short of that
    is `generic`. A paragraph offers more words than a form field, not different
    ones, so the same bar is the right bar.

    Returns the category's own specific keywords *as the description states them*,
    in the order they appear, rather than a canned label. Two consumers need that:
    `get_images_for_industry` composes them into a photo search, and
    `pick_template_id` counts them as declared tokens.
    """
    text = (description or "").strip()
    if not text:
        return ""
    category = _resolve_category(text)
    return _keywords_naming(category, text)


def industry_or_derived(industry: str | None, business_description: str | None) -> str:
    """The declared industry, or the one the description states. Never guesses.

    One rule, so an entry point that is not the main pipeline cannot quietly keep
    the old behaviour. A blank field is blank whether it arrived as ``None``,
    ``""`` or three spaces — `requests.py:202` accepts all three.
    """
    declared = (industry or "").strip()
    if declared:
        return declared
    return derive_industry_from_description(business_description or "")


def _keywords_naming(category: str, text: str) -> str:
    """The category's own specific keywords, as ``text`` states them, in order."""
    if category == "generic":
        return ""
    lowered = text.lower()
    found: list[tuple[int, str]] = []
    for keyword in _INDUSTRY_KEYWORDS.get(category, []):
        # Weak keywords corroborate a category; they do not name one. "home" is
        # not what to send to a stock-photo search for a real-estate brief.
        if keyword in _WEAK_KEYWORDS:
            continue
        match = _keyword_pattern(keyword).search(lowered)
        if match:
            found.append((match.start(), keyword))
    found.sort()
    kept: list[str] = []
    for _, keyword in found:
        # "art gallery" already carries "gallery"; repeating it wastes the
        # 14-word query budget without adding a term.
        if any(keyword in other or other in keyword for other in kept):
            continue
        kept.append(keyword)
        if len(kept) >= _DERIVED_INDUSTRY_MAX_KEYWORDS:
            break
    return " ".join(kept)


def _clip_words(text: str, limit: int) -> str:
    """First ``limit`` word tokens of ``text``."""
    return " ".join(re.findall(r"[A-Za-z0-9&']+", text or "")[:limit])


def _compose_query(*parts: str) -> str:
    """Join query parts left-to-right, dropping repeats and capping length."""
    seen: set[str] = set()
    words: list[str] = []
    for part in parts:
        for word in re.findall(r"[A-Za-z0-9&']+", part or ""):
            key = word.lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(word)
            if len(words) >= _MAX_QUERY_WORDS:
                return " ".join(words)
    return " ".join(words)


def _curated_fallback(
    industry: str,
    seed: str | int | None = None,
    hero_override: str | None = None,
) -> dict[str, str]:
    category = _resolve_category(industry)
    bucket = _LIBRARY[category]
    slots = list(bucket.keys())
    values = list(bucket.values())
    if seed is not None and values:
        offset = int(hashlib.sha256(str(seed).encode("utf-8")).hexdigest(), 16) % len(values)
        values = values[offset:] + values[:offset]
    result = dict(zip(slots, values))
    if hero_override:
        result["hero"] = hero_override
    return result


def _seed_int(seed: str | int | None) -> int:
    if seed is None:
        return 0
    return int(hashlib.sha256(str(seed).encode("utf-8")).hexdigest(), 16)


def _slot_suffix(category: str, slot: str) -> str:
    overrides = _SLOT_QUERY_SUFFIX_BY_CATEGORY.get(category) or {}
    return overrides.get(slot) or _SLOT_QUERY_SUFFIX[slot]


def _slot_queries(
    business_name: str | None,
    industry: str,
    imagery_roles: dict[str, str] | None = None,
) -> dict[str, str]:
    brand = (business_name or "").strip()
    industry_clean = (industry or "business").strip() or "business"
    base = f"{brand} {industry_clean}".strip() if brand else industry_clean
    # Prefer concrete industry words for search quality
    category = _resolve_category(industry)
    category_hint = _CATEGORY_QUERY_HINT.get(category, _GENERIC_QUERY_HINT)
    roles = {
        str(slot): str(query).strip()
        for slot, query in (imagery_roles or {}).items()
        if str(slot) in _SLOTS and str(query).strip()
    }
    queries: dict[str, str] = {}
    industry_head = _clip_words(industry_clean, _MAX_INDUSTRY_QUERY_WORDS)
    for slot in _SLOTS:
        role = roles.get(slot)
        if role:
            # A role is framing only — subject stays the brand + the brief's own
            # industry words. The category hint trails as filler: _resolve_category
            # is a nine-bucket approximation and must never *be* the subject.
            queries[slot] = _compose_query(brand, industry_head, role, category_hint)
        else:
            queries[slot] = f"{base} {category_hint} {_slot_suffix(category, slot)}".strip()
    return queries


def item_pool_query(industry: str) -> str:
    """Search text for the catalogue's per-item photographs.

    Deliberately not one of the slot queries. Item photos are the *thing being
    sold*, so this carries neither the brand (noise in a stock-photo index) nor the
    category hint, whose environment words are what pulled people into the grid:
    `art gallery painting studio` returned an artist at an easel and a hand holding
    a palette for three of request 41's six pieces, and the vision critic blocked
    the page for exactly that — "all of the artwork catalog images show people
    painting rather than the finished artworks".
    """
    industry_clean = (industry or "business").strip() or "business"
    head = _clip_words(industry_clean, _MAX_INDUSTRY_QUERY_WORDS)
    item_hint = _CATEGORY_ITEM_HINT.get(
        _resolve_category(industry_clean), _CATEGORY_ITEM_HINT["generic"]
    )
    return _compose_query(head, item_hint, _ITEM_POOL_FRAMING)


def _pexels_photo_url(photo: dict[str, Any], *, large: bool) -> str | None:
    src = photo.get("src") or {}
    if large:
        return src.get("large2x") or src.get("large") or src.get("original")
    return src.get("large") or src.get("medium") or src.get("original")


def _search_pexels(
    api_key: str,
    query: str,
    *,
    page: int,
    per_page: int = 8,
    timeout: float = 8.0,
) -> list[dict[str, Any]]:
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={
            "query": query[:120],
            "per_page": per_page,
            "page": max(1, page),
            "orientation": "landscape",
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        logger.warning("Pexels search HTTP %s for query=%r", resp.status_code, query[:80])
        return []
    data = resp.json()
    photos = data.get("photos") or []
    return photos if isinstance(photos, list) else []


def _fetch_pexels_images(
    api_key: str,
    industry: str,
    *,
    business_name: str | None,
    seed: str | int | None,
    imagery_roles: dict[str, str] | None = None,
) -> dict[str, str] | None:
    queries = _slot_queries(business_name, industry, imagery_roles=imagery_roles)
    seed_n = _seed_int(seed)
    used_ids: set[int] = set()
    result: dict[str, str] = {}
    # Every slot search asks for 8 photos and keeps 1. The other 7 were thrown
    # away, which is why an eight-item catalogue had to reuse three pictures.
    # `on_subject` carries the search index's own verdict on each spare, so the
    # item grid can prefer a photograph of a thing over one of a person.
    spare: list[tuple[int | None, str, bool]] = []

    for index, slot in enumerate(_SLOTS):
        page = (seed_n + index) % 5 + 1
        photos = _search_pexels(api_key, queries[slot], page=page)
        if not photos:
            # Retry without brand name for better hit rate
            category = _resolve_category(industry)
            fallback_q = f"{category} {_slot_suffix(category, slot)}"
            photos = _search_pexels(api_key, fallback_q, page=page)

        # Usable candidates in search order, with the index's own verdict on each.
        candidates: list[tuple[int | None, str, bool]] = []
        for photo in photos:
            pid = photo.get("id")
            if isinstance(pid, int) and pid in used_ids:
                continue
            url = _pexels_photo_url(photo, large=(slot.startswith("hero")))
            if not url:
                continue
            candidates.append((pid, url, _photo_is_on_subject(photo)))
        if not candidates:
            return None
        # `card1` is the product-detail slot by definition, so it takes the first
        # photograph of a *thing*. The other five are scene-setting, where a person
        # in frame is usually right — a hero of an empty room is worse than a hero
        # of someone at work.
        pick = 0
        if slot in _OBJECT_SLOTS:
            pick = next(
                (i for i, (_p, _u, ok) in enumerate(candidates) if ok),
                0,
            )
        pid, url, _ok = candidates.pop(pick)
        # Detail/product framings first: those are the photographs that can
        # plausibly *be* a catalogue item, rather than a room or a team shot.
        spare.extend(candidates)
        if isinstance(pid, int):
            used_ids.add(pid)
        result[slot] = url

    result.update(
        _item_slot_urls(api_key, item_pool_query(industry), seed_n, used_ids, spare)
    )
    return result


def _item_slot_urls(
    api_key: str,
    pool_query: str,
    seed_n: int,
    used_ids: set[int],
    spare: list[tuple[int | None, str, bool]],
) -> dict[str, str]:
    """One distinct photograph per catalogue slot, best-effort.

    Photographs whose own description names a person or an empty prop go to the
    back of the queue rather than being dropped — a filter that can return fewer
    than eight pictures would reintroduce the repeated-photo defect it was written
    to fix. Ranking cannot: the grid gets the same count, better ordered.

    Returns only the slots it could fill; `normalize_image_slot_map` rotates the
    layout photos into whatever is left, so a partial result is never a hole.
    """
    on_subject: list[str] = []
    off_subject: list[str] = []
    seen: set[str] = set()

    def _take(pid, url, subject_ok: bool) -> None:
        if not url or url in seen:
            return
        if isinstance(pid, int) and pid in used_ids:
            return
        seen.add(url)
        if isinstance(pid, int):
            used_ids.add(pid)
        (on_subject if subject_ok else off_subject).append(url)

    # The pool search is worth making even when the spares would cover the count:
    # spares come from hero/workspace/team framings, which is how people ended up
    # in the item grid in the first place.
    try:
        for photo in _search_pexels(
            api_key, pool_query, page=(seed_n % 3) + 1, per_page=_ITEM_POOL_PER_PAGE
        ):
            _take(
                photo.get("id"),
                _pexels_photo_url(photo, large=False),
                _photo_is_on_subject(photo),
            )
    except Exception as exc:  # noqa: BLE001 — item photos are an enhancement
        logger.warning("Pexels item-pool fetch failed (%s); reusing slot photos", exc)
    for pid, url, subject_ok in spare:
        _take(pid, url, subject_ok)

    pool = on_subject + off_subject
    if off_subject and len(on_subject) < _ITEM_SLOT_COUNT:
        logger.info(
            "item photos: %s on-subject, falling back to %s that show a person or "
            "an empty prop",
            len(on_subject),
            min(len(off_subject), _ITEM_SLOT_COUNT - len(on_subject)),
        )
    return {slot: pool[i] for i, slot in enumerate(_ITEM_SLOTS) if i < len(pool)}


def item_photos_for_titles(
    titles: list[str], industry: str, *, count: int | None = None
) -> list[tuple[str, str]]:
    """Photographs of the things this catalogue actually sells, with their `alt`.

    The pool fetched during planning cannot depict the items — it is composed
    from the industry string, before any item exists. This is the same search
    asked *after* the seed has named them, so the query carries the catalogue's
    own nouns; the `alt` text comes back with each photograph so the caller can
    tell which picture goes with which item.

    One request, whatever the catalogue's length. Returns `[]` on any failure —
    no key, no titles, a raising search — because the caller's fallback is the
    pool it already has, which is today's behaviour.
    """
    if not titles:
        return []
    api_key = ""
    try:
        from app.core.config import settings

        api_key = (getattr(settings, "PEXELS_API_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001 — configuration is not this function's job
        api_key = ""
    if not api_key:
        return []

    # The subject words the items themselves state, deduped in first-seen order
    # and clipped: a stock-photo index answers a phrase, not a catalogue.
    seen: set[str] = set()
    words: list[str] = []
    for title in titles:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", title):
            key = word.lower()
            if key not in seen and len(key) > 2:
                seen.add(key)
                words.append(word)
    query = " ".join(words[:8]) or _clip_words(industry or "", _MAX_INDUSTRY_QUERY_WORDS)
    if not query.strip():
        return []

    wanted = count or max(len(titles), _ITEM_SLOT_COUNT)
    photos: list[tuple[str, str]] = []
    try:
        for photo in _search_pexels(
            api_key, query, page=1, per_page=min(80, max(wanted * 2, 20))
        ):
            url = _pexels_photo_url(photo, large=False)
            if url:
                photos.append((url, str(photo.get("alt") or "")))
    except Exception as exc:  # noqa: BLE001 — item photos are an enhancement
        logger.warning("Pexels item-title fetch failed (%s); keeping the pool", exc)
        return []
    # A photograph of a person is still wrong where the artifact belongs, and
    # this search asks for the artifact by name, so the same ranking applies.
    on_subject = [(u, a) for u, a in photos if not _ITEM_SUBJECT_REJECT_RE.search(a)]
    off_subject = [(u, a) for u, a in photos if _ITEM_SUBJECT_REJECT_RE.search(a)]
    return on_subject + off_subject


#: Distinct per-item searches per generation. Catalogues run 18-32 items, but
#: items share subjects ("Almond Croissant" and "Butter Croissant" are one
#: query), so the cap is rarely felt; when it is, the overflow items fall back
#: to whatever the pooled candidates match.
_MAX_ITEM_QUERIES = 16


def _title_query(title: str) -> str:
    """The subject phrase one item's own words state, empty when they state none."""
    words = [
        w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", title or "") if len(w) > 2
    ]
    return " ".join(words[:4]).lower()


#: Wall-clock ceiling for the whole per-item fetch pass. Sixteen sequential
#: searches at the 8 s HTTP timeout is a 128 s worst case inside the
#: generation's own clock — a slow index day must degrade to the pooled
#: fallback, never eat the deadline. 20 s covers ~14 healthy searches
#: (measured p50 well under 1.5 s) and caps a sick index at ~one timeout.
_ITEM_QUERY_BUDGET_SECONDS = 20.0


def item_photos_by_title(
    titles: list[str],
    industry: str,
    *,
    per_query: int = 6,
    budget_seconds: float = _ITEM_QUERY_BUDGET_SECONDS,
) -> list[list[tuple[str, str]]]:
    """Photographs of *each* item, searched with that item's own words.

    Request 165 is why the pooled search is not enough: a bakery's pool is
    bread, so every cake title matched bread and the critic withheld the run on
    a cake gallery full of loaves. One query per *distinct* item subject — a
    croissant photograph cannot answer for a celebration cake, whatever the
    ranking does downstream.

    Returns one candidate list per title, parallel to ``titles``; a search that
    fails or a title with no subject words yields an empty list for that title
    only. All-empty means the caller falls back to the pooled behaviour.
    """
    if not titles:
        return []
    api_key = ""
    try:
        from app.core.config import settings

        api_key = (getattr(settings, "PEXELS_API_KEY", "") or "").strip()
    except Exception:  # noqa: BLE001 — configuration is not this function's job
        api_key = ""
    if not api_key:
        return [[] for _ in titles]

    industry_head = _clip_words(industry or "", 2)
    started = time.monotonic()
    results_by_query: dict[str, list[tuple[str, str]]] = {}
    per_title: list[list[tuple[str, str]]] = []
    for title in titles:
        query = _title_query(title)
        if not query:
            per_title.append([])
            continue
        if query not in results_by_query:
            if len(results_by_query) >= _MAX_ITEM_QUERIES:
                per_title.append([])
                continue
            if time.monotonic() - started > budget_seconds:
                # Out of runway: no NEW searches. Titles whose query already
                # ran keep their results; the rest fall to the pooled binding.
                per_title.append([])
                continue
            # The industry disambiguates the noun ("tart" the pastry, not the
            # adjective) without overpowering the item's own words.
            search_text = f"{query} {industry_head}".strip()
            try:
                photos = _search_pexels(
                    api_key, search_text, page=1, per_page=per_query
                )
            except Exception as exc:  # noqa: BLE001 — an enhancement, not a stage
                logger.warning(
                    "Pexels per-item fetch failed for %r (%s); leaving the slot "
                    "to the pooled candidates",
                    search_text[:60],
                    exc,
                )
                photos = []
            found: list[tuple[str, str]] = []
            for photo in photos:
                url = _pexels_photo_url(photo, large=False)
                if url:
                    found.append((url, str(photo.get("alt") or "")))
            on_subject = [
                (u, a) for u, a in found if not _ITEM_SUBJECT_REJECT_RE.search(a)
            ]
            off_subject = [
                (u, a) for u, a in found if _ITEM_SUBJECT_REJECT_RE.search(a)
            ]
            results_by_query[query] = on_subject + off_subject
        per_title.append(list(results_by_query[query]))
    return per_title


def curated_library_urls() -> frozenset[str]:
    """All known-good curated CDN URLs (for scrubbing AI-invented Unsplash IDs)."""
    urls: set[str] = set()
    for bucket in _LIBRARY.values():
        urls.update(bucket.values())
    return frozenset(urls)


def curated_photo_ids() -> frozenset[str]:
    """Photo ids present in the curated Unsplash CDN allowlist."""
    ids: set[str] = set()
    for url in curated_library_urls():
        m = re.search(r"photo-[A-Za-z0-9_-]+", url)
        if m:
            ids.add(m.group(0))
    return frozenset(ids)


def _is_allowed_image_url(url: str, *, allowed_ids: frozenset[str]) -> bool:
    text = (url or "").strip()
    if not text.startswith(("https://", "http://")):
        return False
    # Pexels / non-Unsplash CDNs are trusted when the pipeline fetched them.
    if "images.unsplash.com" not in text:
        return True
    m = re.search(r"photo-[A-Za-z0-9_-]+", text)
    return bool(m and m.group(0) in allowed_ids)


def normalize_image_slot_map(images: dict[str, str] | None) -> dict[str, str]:
    """Ensure required slots exist; drop unknown Unsplash photo IDs (AI 404s)."""
    base = _curated_fallback("generic")
    allowed_ids = curated_photo_ids()
    out = dict(base)
    if images:
        for key, value in images.items():
            url = str(value or "").strip()
            if _is_allowed_image_url(url, allowed_ids=allowed_ids):
                out[str(key)] = url
    for slot in _SLOTS:
        if slot not in out or not _is_allowed_image_url(
            str(out.get(slot) or ""), allowed_ids=allowed_ids
        ):
            out[slot] = base[slot]
    # Catalogue slots are always present, even when the fetch could not fill them,
    # so a page can write `images.item3` without `tsc` complaining and without the
    # eight-item grid showing the same photograph twice (request 40 mapped `card1`
    # to both "Whispering Winds" and "Desert Bloom").
    # Rotation order is the item-subject ranking, not slot-declaration order.
    # `card2` ("customer experience") and `card3` ("team service") are the two
    # slots whose queries ask for a person *on purpose*, so filling a catalogue
    # position from them reintroduces the exact defect `_ITEM_SUBJECT_REJECT_RE`
    # exists to prevent — request 70 captioned two photographs of someone at an
    # easel "Still Life with Pears · Oil on Panel". They are out of the rotation
    # entirely, not merely last: repeating a photograph the grid already shows is
    # a blemish, whereas a person where the artifact should be is a wrong page.
    # What remains is still six distinct photographs — the item slots the fetch
    # did fill, then `card1` (the object slot) and the three scene slots — so
    # request 40's repeated-photo defect does not come back to pay for this.
    filled_items = [
        out[s]
        for s in _ITEM_SLOTS
        if _is_allowed_image_url(str(out.get(s) or ""), allowed_ids=allowed_ids)
    ]
    rotation = filled_items + [
        out[s] for s in ("card1", "ambient", "hero2", "hero") if s in out
    ]
    # Only if the map somehow carries nothing else: a hole in `images.item3` is a
    # `tsc` error and a broken page, which is worse than a badly chosen photo.
    rotation = rotation or [out[s] for s in ("card2", "card3") if s in out]
    for index, slot in enumerate(_ITEM_SLOTS):
        if slot not in out or not _is_allowed_image_url(
            str(out.get(slot) or ""), allowed_ids=allowed_ids
        ):
            out[slot] = rotation[index % len(rotation)]
    return out


def get_images_for_industry(
    industry: str,
    seed: str | int | None = None,
    hero_override: str | None = None,
    business_name: str | None = None,
    imagery_roles: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return image URLs for preview mock data (Pexels when configured, else curated)."""
    api_key = ""
    try:
        from app.core.config import settings

        api_key = (getattr(settings, "PEXELS_API_KEY", None) or "").strip()
    except Exception:
        api_key = ""

    if api_key:
        try:
            pexels = _fetch_pexels_images(
                api_key,
                industry,
                business_name=business_name,
                seed=seed,
                imagery_roles=imagery_roles,
            )
            if pexels and len(pexels) >= 4:
                if hero_override:
                    pexels["hero"] = hero_override
                logger.info(
                    "Pexels imagery for industry=%r business=%r slots=%s",
                    industry,
                    business_name,
                    list(pexels.keys()),
                )
                return normalize_image_slot_map(pexels)
            logger.warning("Pexels returned incomplete set; using curated fallback")
        except Exception as exc:
            logger.warning("Pexels fetch failed (%s); using curated fallback", exc)

    return normalize_image_slot_map(
        _curated_fallback(industry, seed=seed, hero_override=hero_override)
    )
