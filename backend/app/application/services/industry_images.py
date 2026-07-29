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

_SLOT_QUERY_SUFFIX: dict[str, str] = {
    "hero": "hero lifestyle wide",
    "hero2": "workspace interior",
    "card1": "product detail",
    "card2": "customer experience",
    "card3": "team service",
    "ambient": "atmosphere background",
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

# Pexels truncates at 120 chars; keep composed role queries inside that budget.
_MAX_QUERY_WORDS = 14


def _resolve_category(industry: str) -> str:
    industry_lower = (industry or "").lower()
    for category, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in industry_lower for kw in keywords):
            return category
    return "generic"


def resolve_industry_category(industry: str) -> str:
    """Coarse imagery category for an industry phrase (``generic`` when unknown)."""
    return _resolve_category(industry)


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
    for slot in _SLOTS:
        role = roles.get(slot)
        if role:
            # A role is framing only — subject stays the brand + resolved industry.
            queries[slot] = _compose_query(brand, category_hint, role)
        else:
            queries[slot] = f"{base} {category_hint} {_SLOT_QUERY_SUFFIX[slot]}".strip()
    return queries


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

    for index, slot in enumerate(_SLOTS):
        page = (seed_n + index) % 5 + 1
        photos = _search_pexels(api_key, queries[slot], page=page)
        if not photos:
            # Retry without brand name for better hit rate
            category = _resolve_category(industry)
            fallback_q = f"{category} {_SLOT_QUERY_SUFFIX[slot]}"
            photos = _search_pexels(api_key, fallback_q, page=page)

        chosen = None
        for photo in photos:
            pid = photo.get("id")
            if isinstance(pid, int) and pid in used_ids:
                continue
            url = _pexels_photo_url(photo, large=(slot.startswith("hero")))
            if url:
                chosen = (pid, url)
                break
        if not chosen:
            return None
        pid, url = chosen
        if isinstance(pid, int):
            used_ids.add(pid)
        result[slot] = url

    return result


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
