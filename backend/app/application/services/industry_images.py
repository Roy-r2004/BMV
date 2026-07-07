"""
Curated, verified Unsplash photo URLs mapped by industry category.
All URLs use ?w=NNN&q=80&fit=crop&auto=format for reliable loading.

Two mechanisms keep two businesses in the same industry from ending up with
pixel-identical imagery:
  1. `seed` deterministically rotates which of the bucket's verified photos
     lands in which slot (hero/card1/card2/...), so "fitness business #12"
     doesn't get the exact same hero photo as "fitness business #3".
  2. `hero_override` lets a real image scraped from the client's own
     reference URL (og:image) replace the generic stock hero entirely.
"""
import hashlib

_LIBRARY: dict[str, dict[str, str]] = {
    "beauty": {
        "hero":    "https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1616394584738-fc6e612e71b9?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1519823551278-64ac92734fb1?w=900&q=80&fit=crop&auto=format",
    },
    "fitness": {
        "hero":    "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1549060279-7e168fcee0c2?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1583454110551-21f2fa2afe61?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1540497077202-7c8a3999166f?w=900&q=80&fit=crop&auto=format",
    },
    "food": {
        "hero":    "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1565299624946-b28f40a0ae38?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1567620905732-2d1ec7ab7445?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1476224203421-9ac39bcb3327?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=900&q=80&fit=crop&auto=format",
    },
    "health": {
        "hero":    "https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1631217868264-e5b90bb7e133?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1584820927498-cfe5211fd8bf?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1559757148-5c350d0d3c56?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1530026405186-ed1f139313f8?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1551190822-a9333d879b1f?w=900&q=80&fit=crop&auto=format",
    },
    "tech": {
        "hero":    "https://images.unsplash.com/photo-1551434678-e076c223a692?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1537432376769-00f5c2f4c8d2?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=900&q=80&fit=crop&auto=format",
    },
    "realestate": {
        "hero":    "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1582268611958-ebfd161ef9cf?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=900&q=80&fit=crop&auto=format",
    },
    "education": {
        "hero":    "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1513258496099-48168024aec0?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1427504494785-3a9ca7044f45?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=900&q=80&fit=crop&auto=format",
    },
    "generic": {
        "hero":    "https://images.unsplash.com/photo-1553877522-43269d4ea984?w=1400&q=80&fit=crop&auto=format",
        "hero2":   "https://images.unsplash.com/photo-1521737604893-d14cc237f11d?w=1400&q=80&fit=crop&auto=format",
        "card1":   "https://images.unsplash.com/photo-1497366216548-37526070297c?w=700&q=80&fit=crop&auto=format",
        "card2":   "https://images.unsplash.com/photo-1497366811353-6870744d04b2?w=700&q=80&fit=crop&auto=format",
        "card3":   "https://images.unsplash.com/photo-1552664730-d307ca884978?w=700&q=80&fit=crop&auto=format",
        "ambient": "https://images.unsplash.com/photo-1542744173-8e7e53415bb0?w=900&q=80&fit=crop&auto=format",
    },
}

_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "beauty":      ["beauty", "skin", "spa", "facial", "salon", "cosmetic", "aesthetic", "skincare", "hair", "nail", "wellness", "massage"],
    "fitness":     ["fitness", "gym", "sport", "yoga", "pilates", "crossfit", "personal trainer", "coach", "workout", "health coach", "nutrition", "dietitian"],
    "food":        ["food", "restaurant", "cafe", "bakery", "catering", "meal", "kitchen", "chef", "coffee", "bar", "bistro", "dining"],
    "health":      ["health", "medical", "clinic", "doctor", "dentist", "therapy", "physiotherapy", "mental health", "hospital", "pharmacy", "chiropractic"],
    "tech":        ["software", "saas", "tech", "app", "digital", "ai", "automation", "platform", "startup", "development", "agency"],
    "realestate":  ["real estate", "property", "realty", "mortgage", "housing", "agent", "realtor", "home", "apartment", "commercial"],
    "education":   ["education", "school", "tutor", "course", "academy", "training", "learning", "coaching", "workshop", "certification"],
}


def get_images_for_industry(
    industry: str,
    seed: str | int | None = None,
    hero_override: str | None = None,
) -> dict[str, str]:
    """Return curated Unsplash image URLs matched to the given industry string.

    `seed` (e.g. the request id or business name) rotates the assignment of
    the bucket's photos across slots so repeat businesses in the same
    industry don't render identical imagery. `hero_override` — typically the
    client's own reference-site og:image — replaces the generic stock hero
    when one was found.
    """
    industry_lower = (industry or "").lower()
    bucket = _LIBRARY["generic"]
    for category, keywords in _INDUSTRY_KEYWORDS.items():
        if any(kw in industry_lower for kw in keywords):
            bucket = _LIBRARY[category]
            break

    slots = list(bucket.keys())
    values = list(bucket.values())
    if seed is not None and values:
        offset = int(hashlib.sha256(str(seed).encode("utf-8")).hexdigest(), 16) % len(values)
        values = values[offset:] + values[:offset]
    result = dict(zip(slots, values))

    if hero_override:
        result["hero"] = hero_override

    return result
