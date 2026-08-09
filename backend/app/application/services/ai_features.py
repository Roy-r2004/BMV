"""Structured AI features from the plan → AppSpec / preview binding.

The product contract: every AI feature proposed in the blueprint must appear as
an interactive surface in the live preview. Markdown section 11 alone is not
enough — we extract a stable inventory, treat it as customer_input, bind it into
AppSpec, and project it onto a deterministic hub page.
"""
from __future__ import annotations

import json
import re
from typing import Any, Mapping, Optional

AI_FEATURE_SOURCE_REF = "customer_input.ai_features"
# Id chosen so AppSpec projection maps to src/pages/AiFeaturesPage.tsx
PAGE_AI_HUB_ID = "PAGE-AI-FEATURES"
PAGE_AI_HUB_ROUTE = "/ai-features"
MAX_AI_FEATURES = 6

_CATEGORY_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chat", ("chat", "assistant", "qa", "q&a", "convers", "faq", "bot")),
    (
        "scheduling",
        ("schedul", "booking", "appoint", "calendar", "time slot", "reserv", "book a ", "book now"),
    ),
    (
        "digest",
        ("digest", "summary", "report", "brief", "insight", "daily", "cash pulse", "books overview"),
    ),
    (
        "scoring",
        (
            "score",
            "rank",
            "priorit",
            "lead scor",
            "risk",
            "qualify",
            "overdue",
            "collectib",
            "priority",
        ),
    ),
    (
        "ops",
        (
            "ops",
            "admin",
            "dashboard",
            "triage",
            "routing",
            "intake",
            "reconcil",
            "match",
            "bank feed",
            "categor",
            "invoice",
            "expense",
            "ledger",
            "bookkeep",
        ),
    ),
    ("automation", ("automat", "workflow", "trigger", "chase", "follow-up", "remind")),
)

# Route path scoring: higher = better home for that AI category.
_CATEGORY_ROUTE_HINTS: dict[str, tuple[tuple[str, int], ...]] = {
    "chat": (
        ("faq", 12),
        ("assistant", 11),
        ("help", 9),
        ("contact", 7),
        ("home", 3),
        ("/", 2),
    ),
    "scheduling": (
        ("book", 12),
        ("reserv", 11),
        ("appoint", 10),
        ("class", 8),
        ("schedule", 9),
        ("slot", 8),
    ),
    "digest": (("dashboard", 12), ("overview", 9), ("owner", 7), ("admin", 7)),
    "scoring": (("lead", 12), ("inbox", 10), ("dashboard", 8), ("owner", 6)),
    "automation": (
        ("waitlist", 12),
        ("automat", 10),
        ("workflow", 9),
        ("owner", 6),
        ("admin", 6),
    ),
    "ops": (("dashboard", 12), ("owner", 9), ("admin", 9), ("ops", 8)),
}

_DEMO_BY_CATEGORY: dict[str, dict[str, Any]] = {
    "chat": {
        "demo_hint": "Ask a real customer question",
        "demo_prompts": [
            "What are your hours this week?",
            "How does pricing work?",
            "Can I book for tomorrow?",
        ],
        "placement_label": "Customer assistant",
    },
    "scheduling": {
        "demo_hint": "Ask for the next open slot",
        "demo_prompts": [
            "Next available Thursday morning",
            "Any openings this weekend?",
            "Book the soonest 60-minute slot",
        ],
        "placement_label": "Scheduling AI",
    },
    "digest": {
        "demo_hint": "Generate today's owner brief",
        "demo_prompts": [
            "Summarize today",
            "What needs attention?",
            "Top 3 priorities",
        ],
        "placement_label": "Owner digest",
    },
    "scoring": {
        "demo_hint": "Score an incoming lead",
        "demo_prompts": [
            "Score this new inquiry",
            "Who should we call first?",
            "Rank today's leads",
        ],
        "placement_label": "Lead scoring",
    },
    "automation": {
        "demo_hint": "Trigger the next automation step",
        "demo_prompts": [
            "Notify the next waitlisted guest",
            "Chase missing documents",
            "Run tonight's follow-ups",
        ],
        "placement_label": "Automation",
    },
    "ops": {
        "demo_hint": "Route today's ops work",
        "demo_prompts": [
            "Triage new inbox items",
            "Assign an owner for this request",
            "What should the team do next?",
        ],
        "placement_label": "Ops AI",
    },
}


def _slugify(value: str, *, fallback: str = "feature") -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return (text[:48] or fallback).strip("-") or fallback


def infer_category(name: str, description: str = "", *, context: str = "") -> str:
    blob = f"{name} {description}".lower()
    for category, hints in _CATEGORY_HINTS:
        if any(hint in blob for hint in hints):
            return category
    ctx = (context or "").lower()
    # Accounting / ops products should not fall through to chat-like automation.
    if any(
        h in ctx
        for h in (
            "accounting",
            "invoice",
            "ledger",
            "bookkeep",
            "reconcil",
            "expense",
            "trading",
            "blotter",
        )
    ):
        if any(h in blob for h in ("summary", "digest", "brief", "report", "daily")):
            return "digest"
        if any(h in blob for h in ("score", "priorit", "risk", "overdue")):
            return "scoring"
        return "ops"
    return "automation"


def _context_blob(*parts: str) -> str:
    return " ".join(str(p or "") for p in parts).lower()


_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "with", "from", "that", "this", "these",
    "those", "into", "your", "their", "about", "using", "using", "when", "what",
    "how", "can", "will", "are", "is", "to", "of", "in", "on", "at", "by", "as",
    "it", "its", "be", "been", "was", "were", "have", "has", "had", "do", "does",
    "did", "not", "no", "yes", "each", "every", "also", "than", "then", "them",
    "they", "you", "we", "our", "real", "value", "feature", "features", "ai",
    "assistant", "automation", "customer", "customers", "business", "owner",
    "hand", "time", "help", "next", "person", "people", "common", "questions",
    "details", "policies", "studio", "provided", "using", "knowledge", "base",
    "should", "know", "get", "open", "spot", "opens", "tonight", "week", "today",
}

# Fragment phrases that score as "domain" but read broken in demo chips.
_JUNK_PHRASES = {
    "by hand",
    "the time",
    "spot opens",
    "get help",
    "next person",
    "common questions",
    "studio policies",
    "class details",
    "knowledge base",
    "should know",
    "this week",
    "the next",
    "kiln studio",  # truncated brand fragment
}

_DOMAIN_SEEDS: dict[str, tuple[str, ...]] = {
    "pottery": ("glazes", "kiln firing", "wheel throwing", "class seats", "open studio"),
    "ceramic": ("glazes", "kiln firing", "wheel throwing", "class seats", "bisque"),
    "clay": ("glazes", "kiln firing", "wheel classes", "studio seats"),
    "salon": ("color", "cut", "chair time", "stylist"),
    "spa": ("treatment", "booking", "aftercare"),
    "clinic": ("appointment", "intake", "follow-up"),
    "restaurant": ("reservation", "menu", "table"),
    "fitness": ("class", "membership", "trainer"),
}


def _demo_payload(category: str) -> dict[str, Any]:
    base = dict(_DEMO_BY_CATEGORY.get(category) or _DEMO_BY_CATEGORY["automation"])
    base["demo_prompts"] = list(base.get("demo_prompts") or [])
    return base


def business_context_from_request(req: Any) -> dict[str, str]:
    """Collect business-specific text used to personalize demo scripts."""
    return {
        "business_name": str(getattr(req, "business_name", None) or "").strip(),
        "industry": str(getattr(req, "industry", None) or "").strip(),
        "business_description": str(getattr(req, "business_description", None) or "").strip(),
        "main_problem": str(getattr(req, "main_problem", None) or "").strip(),
        "desired_outcome": str(getattr(req, "desired_outcome", None) or "").strip(),
        "concept_name": str(getattr(req, "concept_name", None) or "").strip(),
        "mvp_blueprint": str(getattr(req, "mvp_blueprint", None) or "")[:2500],
    }


def _topic_terms(*parts: str, limit: int = 8) -> list[str]:
    """Pull concrete nouns/phrases from business + feature copy."""
    blob = " ".join(p for p in parts if p)
    if not blob:
        return []
    folded_blob = blob.casefold()
    # Prefer multi-word phrases that look domain-specific.
    phrases = re.findall(
        r"\b(?:[A-Za-z][A-Za-z0-9]+(?:\s+[A-Za-z][A-Za-z0-9]+){1,2})\b",
        blob,
    )
    words = re.findall(r"\b[A-Za-z][A-Za-z0-9-]{3,}\b", blob)
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()

    # Seed high-quality domain terms when industry is known.
    for key, seeds in _DOMAIN_SEEDS.items():
        if key in folded_blob:
            for seed in seeds:
                if seed in seen:
                    continue
                seen.add(seed)
                scored.append((18, seed))

    for raw in phrases + words:
        text = re.sub(r"\s+", " ", raw.strip())
        folded = text.casefold()
        if folded in seen or folded in _STOPWORDS or folded in _JUNK_PHRASES:
            continue
        tokens = folded.split()
        if all(tok in _STOPWORDS for tok in tokens):
            continue
        # Drop "prep + weak noun" fragments ("by hand", "the time").
        if len(tokens) >= 2 and tokens[0] in {
            "by", "the", "a", "an", "for", "with", "from", "to", "of", "in", "on", "at",
        }:
            continue
        if len(tokens) == 1 and len(folded) < 4:
            continue
        seen.add(folded)
        # Prefer feature-description phrases (appear earlier in joined blob).
        score = 10 if " " in text else 4
        if any(ch.isdigit() for ch in text):
            score -= 2
        # Boost clear domain nouns.
        if any(
            tok in folded
            for tok in (
                "glaze",
                "kiln",
                "firing",
                "wheel",
                "class",
                "waitlist",
                "booking",
                "pottery",
                "clay",
            )
        ):
            score += 6
        scored.append((score, text))
    scored.sort(key=lambda item: (-item[0], len(item[1])))
    return [item[1] for item in scored[:limit]]


def build_business_demo_scripts(
    feature: Mapping[str, Any],
    context: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build try-this prompts + canned answers grounded in this business."""
    ctx = dict(context or {})
    category = str(feature.get("category") or feature.get("surface") or "automation").lower()
    if category not in _DEMO_BY_CATEGORY:
        category = infer_category(str(feature.get("name") or ""), str(feature.get("description") or ""))
    fallback = _demo_payload(category)
    name = str(feature.get("name") or "AI feature").strip()
    description = str(feature.get("description") or name).strip()
    biz = ctx.get("business_name") or ctx.get("concept_name") or "the studio"
    industry = ctx.get("industry") or "this business"

    terms = _topic_terms(
        description,
        name,
        ctx.get("main_problem", ""),
        ctx.get("desired_outcome", ""),
        ctx.get("business_description", "")[:500],
        industry,
        ctx.get("mvp_blueprint", "")[:800],
    )
    # Waitlist / booking features should talk about seats/classes, not glaze chemistry.
    name_desc = f"{name} {description}".casefold()
    if "waitlist" in name_desc or category == "scheduling":
        preferred = [
            t
            for t in terms
            if any(k in t.casefold() for k in ("class", "seat", "wheel", "studio", "session", "booking"))
        ]
        if preferred:
            terms = preferred + [t for t in terms if t not in preferred]
    t0 = terms[0] if terms else industry
    t1 = terms[1] if len(terms) > 1 else name
    t2 = terms[2] if len(terms) > 2 else (terms[0] if terms else "today")

    if category == "chat":
        prompts = [
            f"What should I know about {t0}?",
            f"How does {t1} work at {biz}?",
            f"Can beginners join a {t2} this week?",
        ]
        hint = f"Ask the way a real guest would ask {biz}"
        results = {
            prompts[0]: (
                f"{biz}: For “{prompts[0]}” — {description.rstrip('.')} "
                f"Here’s the short answer, what to prepare, and when a human should join."
            ),
            prompts[1]: (
                f"{biz}: “{prompts[1]}” — we walk guests through {t1} step by step, "
                f"including timing, cost cues, and the next action to take."
            ),
            prompts[2]: (
                f"{biz}: Yes — for “{prompts[2]}”, the assistant qualifies the request, "
                f"shares what {t2} involves, and offers the best next booking path."
            ),
        }
    elif category == "scheduling":
        prompts = [
            f"Next opening for {t0}",
            f"Any {t1} slots this weekend?",
            f"Book the soonest {t2}",
        ]
        hint = f"Ask for availability in {biz}'s real schedule"
        results = {
            prompts[0]: (
                f"Best fits for “{prompts[0]}”: Thu 10:00 · Fri 14:30 · Mon 09:15 — "
                f"holds a seat for {t0} at {biz}."
            ),
            prompts[1]: (
                f"Weekend openings for “{prompts[1]}”: Sat 11:00 · Sun 15:30. "
                f"Capacity updates as {t1} fills."
            ),
            prompts[2]: (
                f"Held the soonest match for “{prompts[2]}”. Confirmation draft ready; "
                f"customer can confirm in one tap."
            ),
        }
    elif category == "digest":
        prompts = [
            f"Summarize {t0} for today",
            f"What needs attention around {t1}?",
            f"Top priorities for {biz}",
        ]
        hint = f"Generate today's brief for {biz}"
        results = {
            prompts[0]: (
                f"Daily brief — “{prompts[0]}”: 3 priorities · 1 risk · 1 win tied to {t0}. "
                f"Owner can act in under a minute."
            ),
            prompts[1]: (
                f"Attention list for “{prompts[1]}”: overdue follow-ups, capacity risk on {t1}, "
                f"and one customer waiting on a reply."
            ),
            prompts[2]: (
                f"Top priorities for {biz}: protect today's {t0}, clear the {t1} queue, "
                f"and confirm tomorrow's commitments."
            ),
        }
    elif category == "scoring":
        prompts = [
            f"Score this inquiry about {t0}",
            f"Who should we call first about {t1}?",
            f"Rank today's leads for {biz}",
        ]
        hint = f"Score a lead the way {biz} would"
        results = {
            prompts[0]: (
                f"Score 86/100 for “{prompts[0]}” — high intent on {t0}. "
                f"Suggested next step: call within 2 hours."
            ),
            prompts[1]: (
                f"Call first: the lead asking about {t1}. "
                f"Reason: urgency + fit with {biz}'s core offer."
            ),
            prompts[2]: (
                f"Lead ranking for {biz}: 1) {t0} inquiry 2) {t1} follow-up 3) browse-only. "
                f"Focus staff time on the top two."
            ),
        }
    elif category == "ops":
        prompts = [
            f"Triage new requests about {t0}",
            f"Assign an owner for this {t1} issue",
            f"What should the {biz} team do next?",
        ]
        hint = f"Route ops work the way {biz} runs"
        results = {
            prompts[0]: (
                f"Routed “{prompts[0]}” → queue + owner + checklist for {t0}. "
                f"Status: In progress."
            ),
            prompts[1]: (
                f"Assigned “{prompts[1]}” to the best available owner with a {t1} checklist "
                f"and due time today."
            ),
            prompts[2]: (
                f"Next for {biz}: clear the {t0} backlog, confirm {t1}, then review tonight's handoff."
            ),
        }
    else:  # automation
        prompts = [
            f"Notify the next person waiting for {t0}",
            f"Chase what's missing for {t1}",
            f"Run tonight's follow-ups for {biz}",
        ]
        hint = f"Trigger the automation {biz} actually needs"
        results = {
            prompts[0]: (
                f"Automation for “{prompts[0]}”: message drafted, spot held for 30 minutes, "
                f"next guest in line ready if they decline."
            ),
            prompts[1]: (
                f"Chase sequence for “{prompts[1]}”: reminder #1 sent about {t1}, "
                f"escalates tomorrow if still open."
            ),
            prompts[2]: (
                f"Tonight's follow-ups for {biz} are queued — review → approve → run. "
                f"Covers {t0} and {t1}."
            ),
        }

    # Keep prompts short for chips.
    prompts = [p[:90] for p in prompts]
    results = {k[:90]: v for k, v in results.items()}
    return {
        "demo_hint": hint,
        "demo_prompts": prompts or list(fallback["demo_prompts"]),
        "demo_results": results,
        "placement_label": fallback["placement_label"],
    }


def enrich_feature(
    feature: Mapping[str, Any],
    context: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Add demo script + placement metadata used by contextual panels."""
    out = dict(feature)
    ctx_blob = _context_blob(
        *(str((context or {}).get(k) or "") for k in (
            "business_name",
            "industry",
            "business_description",
            "main_problem",
            "desired_outcome",
            "concept_name",
            "mvp_blueprint",
        ))
    )
    category = str(out.get("category") or out.get("surface") or "").lower()
    if category not in _DEMO_BY_CATEGORY or category in {"automation", "chat"}:
        # Re-infer for ops/accounting briefs so we don't ship a chat wall.
        inferred = infer_category(
            str(out.get("name") or ""),
            str(out.get("description") or ""),
            context=ctx_blob,
        )
        if category not in _DEMO_BY_CATEGORY or (
            category in {"automation", "chat"} and inferred != "chat"
        ):
            category = inferred
    out["category"] = category
    out["surface"] = str(out.get("surface") or category)

    if context and any(str(context.get(k) or "").strip() for k in context):
        scripts = build_business_demo_scripts(out, context)
        out["demo_hint"] = scripts["demo_hint"]
        out["demo_prompts"] = list(scripts["demo_prompts"])
        out["demo_results"] = dict(scripts["demo_results"])
        out["placement_label"] = scripts["placement_label"]
    else:
        demo = _demo_payload(category)
        out.setdefault("demo_hint", demo["demo_hint"])
        out.setdefault("demo_prompts", list(demo["demo_prompts"]))
        out.setdefault("placement_label", demo["placement_label"])
        out.setdefault("demo_results", {})
    return out


def score_route_for_category(category: str, path: str, title: str = "", purpose: str = "") -> int:
    blob = f"{path} {title} {purpose}".lower()
    score = 0
    for hint, weight in _CATEGORY_ROUTE_HINTS.get(category, ()):
        if hint == "/" and (path or "") in {"/", "/home"}:
            score += weight
        elif hint in blob:
            score += weight
    # Prefer public for chat/scheduling; ops for digest/ops/scoring/automation.
    if category in {"chat", "scheduling"} and ("owner" in blob or "admin" in blob):
        score -= 3
    if category in {"digest", "ops", "scoring", "automation"} and not (
        "owner" in blob or "admin" in blob or "dashboard" in blob
    ):
        score -= 1
    return score


def _concrete_placement_path(path: str) -> str:
    """Turn /classes/:id into a clickable path (/classes), never a raw param URL."""
    raw = (path or "").strip() or PAGE_AI_HUB_ROUTE
    if ":" not in raw:
        return raw
    parts = [p for p in raw.split("/") if p]
    if parts and parts[-1].startswith(":"):
        parent = "/" + "/".join(parts[:-1])
        return parent if parent != "/" else PAGE_AI_HUB_ROUTE
    return re.sub(r"/:[^/]+", "", raw) or PAGE_AI_HUB_ROUTE


def assign_feature_placements(
    features: list[Mapping[str, Any]],
    routes: list[Mapping[str, Any]],
    context: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Bind each feature to the best concrete route in the architect."""
    usable_routes = [
        rt
        for rt in routes
        if isinstance(rt, Mapping)
        and str(rt.get("path") or "").strip()
        and str(rt.get("path") or "") != PAGE_AI_HUB_ROUTE
        and str(rt.get("component_file") or "").replace("\\", "/")
        # Prefer real URLs over parameterized templates in "See it in context" links.
        and ":" not in str(rt.get("path") or "")
    ]
    if not usable_routes:
        usable_routes = [
            rt
            for rt in routes
            if isinstance(rt, Mapping)
            and str(rt.get("path") or "").strip()
            and str(rt.get("path") or "") != PAGE_AI_HUB_ROUTE
            and str(rt.get("component_file") or "").replace("\\", "/")
        ]
    assigned: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for raw in features:
        feature = enrich_feature(raw, context=context)
        category = str(feature.get("category") or "automation")
        ranked = sorted(
            usable_routes,
            key=lambda rt: (
                -score_route_for_category(
                    category,
                    str(rt.get("path") or ""),
                    str(rt.get("title") or ""),
                    str(rt.get("purpose") or ""),
                ),
                0 if str(rt.get("path") or "") not in used_paths else 1,
                str(rt.get("path") or ""),
            ),
        )
        best = ranked[0] if ranked else None
        if best is not None:
            path = _concrete_placement_path(str(best.get("path") or ""))
            feature["placement_path"] = path
            feature["placement_component"] = str(best.get("component_file") or "").replace(
                "\\", "/"
            )
            feature["placement_title"] = str(best.get("title") or path)
            used_paths.add(str(best.get("path") or path))
        else:
            feature["placement_path"] = PAGE_AI_HUB_ROUTE
            feature["placement_component"] = "src/pages/AiFeaturesPage.tsx"
            feature["placement_title"] = "AI features"
        assigned.append(feature)
    return assigned


def _split_name_description(line: str) -> tuple[str, str]:
    cleaned = re.sub(r"^[-*•\d.)]+\s*", "", (line or "").strip())
    cleaned = re.sub(r"\*+", "", cleaned).strip()
    if not cleaned:
        return "", ""
    for sep in (": ", " — ", " – ", " - "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                return left[:120], right[:400]
    return cleaned[:120], cleaned[:400]


def extract_ai_features_from_blueprint(blueprint: str) -> list[dict[str, Any]]:
    """Parse blueprint §11 into a stable structured inventory."""
    if not (blueprint or "").strip():
        return []

    section = re.search(
        r"(?:^|\n)\s*11\.\s*AI features[^\n]*\n([\s\S]*?)(?=\n\s*12\.|\n\s*#|\Z)",
        blueprint,
        re.IGNORECASE,
    )
    if not section:
        section = re.search(
            r"(?:AI features that add real value|AI features)[:\s]*\n([\s\S]*?)"
            r"(?=\n\s*\d+\.\s|\n#{1,3}\s|\Z)",
            blueprint,
            re.IGNORECASE,
        )
    if not section:
        return []

    body = section.group(1).strip()
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    features: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines:
        if re.match(r"^\d+\.\s+\S", line) and not re.match(r"^\d+\.\s", line[:4]):
            break
        # Stop if a new numbered top-level section leaked in.
        if re.match(r"^(1[2-9]|[2-9]\d)\.\s", line):
            break
        name, description = _split_name_description(line)
        if not name or len(name) < 3:
            continue
        # Skip prose that is not a feature bullet.
        if name.lower().startswith(("note", "none", "n/a", "not applicable")):
            continue
        feature_id = _slugify(name)
        base = feature_id
        n = 2
        while feature_id in seen:
            feature_id = f"{base}-{n}"
            n += 1
        seen.add(feature_id)
        category = infer_category(name, description)
        features.append(
            enrich_feature(
                {
                    "id": feature_id,
                    "name": name,
                    "description": description or name,
                    "category": category,
                    "surface": category,
                }
            )
        )
        if len(features) >= MAX_AI_FEATURES:
            break
    return features


def parse_ai_features(raw: Optional[str | list | dict]) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("ai_features") or raw.get("features") or []
    else:
        try:
            parsed = json.loads(raw)
        except Exception:
            return extract_ai_features_from_blueprint(str(raw))
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict):
            items = parsed.get("ai_features") or parsed.get("features") or []
        else:
            return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if isinstance(item, str):
            name, description = _split_name_description(item)
            if not name:
                continue
            feature = {
                "id": _slugify(name),
                "name": name,
                "description": description or name,
                "category": infer_category(name, description),
                "surface": infer_category(name, description),
            }
        elif isinstance(item, Mapping):
            name = str(item.get("name") or item.get("title") or "").strip()
            if not name:
                continue
            description = str(item.get("description") or item.get("summary") or name).strip()
            category = str(item.get("category") or item.get("surface") or "").strip().lower()
            if category not in {c for c, _ in _CATEGORY_HINTS}:
                category = infer_category(name, description)
            feature = {
                "id": _slugify(str(item.get("id") or name)),
                "name": name[:120],
                "description": description[:400],
                "category": category,
                "surface": str(item.get("surface") or category),
            }
        else:
            continue
        fid = feature["id"]
        if fid in seen:
            continue
        seen.add(fid)
        out.append(enrich_feature(feature))
        if len(out) >= MAX_AI_FEATURES:
            break
    return out


def ai_features_from_request(req: Any) -> list[dict[str, Any]]:
    needs = str(getattr(req, "needs_ai", None) or "").strip().lower()
    if needs == "no":
        return []
    stored = parse_ai_features(getattr(req, "ai_features", None))
    features = stored or extract_ai_features_from_blueprint(
        getattr(req, "mvp_blueprint", None) or ""
    )
    context = business_context_from_request(req)
    return [enrich_feature(item, context=context) for item in features]


def ai_features_from_source(source_snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    customer = source_snapshot.get("customer_input") if isinstance(source_snapshot, Mapping) else None
    if not isinstance(customer, Mapping):
        return []
    needs = str(customer.get("needs_ai") or "").strip().lower()
    if needs == "no":
        return []
    return parse_ai_features(customer.get("ai_features"))


def _unique_id(prefix: str, existing: set[str], stem: str) -> str:
    base = f"{prefix}-{_slugify(stem, fallback='AI').upper().replace('-', '-')}"
    base = re.sub(r"[^A-Za-z0-9_-]+", "", base)[:56] or f"{prefix}-AI"
    candidate = base
    n = 2
    while candidate.casefold() in existing:
        candidate = f"{base}-{n}"[:64]
        n += 1
    existing.add(candidate.casefold())
    return candidate


def _feature_already_bound(payload: Mapping[str, Any], feature: Mapping[str, Any]) -> bool:
    fid = str(feature.get("id") or "").casefold()
    name = str(feature.get("name") or "").casefold()
    for req in payload.get("requirements") or []:
        if not isinstance(req, Mapping):
            continue
        rid = str(req.get("id") or "").casefold()
        title = str(req.get("title") or "").casefold()
        desc = str(req.get("description") or "").casefold()
        refs = [str(r).casefold() for r in (req.get("source_refs") or [])]
        if AI_FEATURE_SOURCE_REF.casefold() in refs and (
            fid and fid in rid or (name and (name in title or name in desc))
        ):
            return True
        if fid and f"req-ai-{fid}" == rid:
            return True
    for page in payload.get("pages") or []:
        if not isinstance(page, Mapping):
            continue
        if str(page.get("id") or "").casefold() == PAGE_AI_HUB_ID.casefold():
            purpose = str(page.get("purpose") or "").casefold()
            if name and name in purpose:
                return True
    return False


def _normalized_route(value: Any) -> str:
    text = str(value or "").strip().casefold()
    return text.rstrip("/") or "/"


def _stranded_ai_requirement_ids(payload: Mapping[str, Any]) -> list[str]:
    """Injector-sourced requirements that no traceability link accounts for.

    The binder used to treat "the requirement exists" as "the feature is
    bound". A model repair re-emits the whole document and may keep the
    requirement while dropping its traceability row — request 130 died with
    `REQ-AI-SMART-PRICING-INSIGHTS` present, must-priority, and untraced,
    because the guard could not see that only part of the binding survived.
    """
    traced = {
        str(link.get("requirement_id") or "").casefold()
        for link in (payload.get("traceability") or [])
        if isinstance(link, Mapping)
    }
    stranded: list[str] = []
    marker = AI_FEATURE_SOURCE_REF.casefold()
    for req in payload.get("requirements") or []:
        if not isinstance(req, Mapping):
            continue
        rid = str(req.get("id") or "")
        refs = [str(r).casefold() for r in (req.get("source_refs") or [])]
        if rid and marker in refs and rid.casefold() not in traced:
            stranded.append(rid)
    return stranded


def bind_ai_features_to_app_spec(
    payload: Mapping[str, Any],
    features: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Ensure every planned AI feature is a must requirement on PAGE-AI-HUB.

    Content-verified requirements share one hub page so preview page caps stay
    intact while every feature remains in scope (never deferred_scope-only).
    """
    import copy

    if not features:
        return dict(payload) if not isinstance(payload, dict) else copy.deepcopy(payload)

    sanitized = copy.deepcopy(dict(payload))
    pending = [f for f in features if not _feature_already_bound(sanitized, f)]
    if (
        not pending
        and not _stranded_ai_requirement_ids(sanitized)
        and any(
            str(p.get("id") or "").casefold() == PAGE_AI_HUB_ID.casefold()
            or _normalized_route(p.get("route")) == _normalized_route(PAGE_AI_HUB_ROUTE)
            for p in (sanitized.get("pages") or [])
            if isinstance(p, Mapping)
        )
    ):
        return sanitized

    roles = [r for r in (sanitized.get("roles") or []) if isinstance(r, dict)]
    if not roles:
        return sanitized
    role = next(
        (r for r in roles if str(r.get("id") or "").upper().startswith("ROLE")),
        roles[0],
    )
    role_id = str(role.get("id") or "ROLE-CUSTOMER")

    id_index: set[str] = set()
    for key in (
        "requirements",
        "capabilities",
        "pages",
        "states",
        "actions",
        "transitions",
        "evidence",
        "journeys",
        "acceptance_tests",
        "entities",
        "assumptions",
        "open_questions",
    ):
        for item in sanitized.get(key) or []:
            if isinstance(item, Mapping) and item.get("id"):
                id_index.add(str(item["id"]).casefold())

    pages = [p for p in (sanitized.get("pages") or []) if isinstance(p, dict)]
    hub = next(
        (p for p in pages if str(p.get("id") or "").casefold() == PAGE_AI_HUB_ID.casefold()),
        None,
    )
    if hub is None:
        # Adopt a model-authored hub that already owns the route. The guard
        # used to be "is *this id* already present", which cannot see the hub
        # the model wrote under its own name — request 136 died on
        # `duplicate_route` because the model had `PAGE-AI-FEATURES-HUB` at
        # `/ai-features` and the binder appended a second page at the same
        # route. Same defect shape as the 62cb26d initial-state fix: guard by
        # what the spec expresses, not by the literal the binder would mint.
        hub = next(
            (
                p
                for p in pages
                if _normalized_route(p.get("route"))
                == _normalized_route(PAGE_AI_HUB_ROUTE)
            ),
            None,
        )
    if hub is None:
        hub = {
            "id": PAGE_AI_HUB_ID,
            "name": "AI features",
            "purpose": (
                "Interactive hub where every AI feature proposed in the plan "
                "is visible and usable in the live product."
            ),
            "route": PAGE_AI_HUB_ROUTE,
            "surface": "public",
            "primary": False,
            "role_ids": [role_id],
            "capability_ids": [],
            "state_ids": [],
            "action_ids": [],
            "evidence_ids": [],
        }
        pages.append(hub)
        id_index.add(PAGE_AI_HUB_ID.casefold())
        sanitized["pages"] = pages
    # An adopted hub keeps the model's page id; every wire below must use it.
    hub_id = str(hub.get("id") or PAGE_AI_HUB_ID)

    requirements = [r for r in (sanitized.get("requirements") or []) if isinstance(r, dict)]
    capabilities = [c for c in (sanitized.get("capabilities") or []) if isinstance(c, dict)]
    evidence = [e for e in (sanitized.get("evidence") or []) if isinstance(e, dict)]
    states = [s for s in (sanitized.get("states") or []) if isinstance(s, dict)]
    acceptance_tests = [
        t for t in (sanitized.get("acceptance_tests") or []) if isinstance(t, dict)
    ]
    traceability = [t for t in (sanitized.get("traceability") or []) if isinstance(t, dict)]
    deferred = [d for d in (sanitized.get("deferred_scope") or []) if isinstance(d, dict)]

    # Drop deferred entries that duplicate these AI feature outcomes.
    pending_names = {str(f.get("name") or "").casefold() for f in pending}
    deferred = [
        d
        for d in deferred
        if str(d.get("name") or "").casefold() not in pending_names
        and not str(d.get("id") or "").upper().startswith("DEFER-REQ-AI")
    ]

    state_id = "STATE-AI-HUB-READY"
    if state_id.casefold() not in id_index:
        # `initial` only when the page does not already have one. The guard used
        # to be "is *this id* already present", which cannot see a state the
        # model wrote under a different name — and the model routinely writes
        # one, because a page with content has an initial state by definition.
        #
        # Requests 137, 138 and 139 died on the identical message:
        # *"Page 'PAGE-AI-FEATURES' must contain exactly one initial state;
        # found 2."* Both were `initial: true` — `STATE-AI-FEATURES-LOADED`
        # from the model and this one from us. **The pipeline injected the
        # second initial state and then failed the run for having two**, on a
        # page the pipeline itself requires. Three runs, one hardcoded literal.
        hub_existing = {
            str(sid).casefold() for sid in (hub.get("state_ids") or [])
        }
        page_already_has_initial = any(
            str(s.get("id") or "").casefold() in hub_existing and s.get("initial")
            for s in states
            if isinstance(s, dict)
        )
        states.append(
            {
                "id": state_id,
                "page_id": hub_id,
                "name": "Ready",
                "description": "AI feature hub is ready for customers and operators.",
                "initial": not page_already_has_initial,
                # Content hub has no interaction graph — treat ready as terminal.
                "terminal": True,
                "evidence_ids": [],
            }
        )
        id_index.add(state_id.casefold())
    hub_state_ids = list(hub.get("state_ids") or [])
    if state_id not in hub_state_ids:
        hub_state_ids.append(state_id)
    hub["state_ids"] = hub_state_ids

    for feature in pending:
        fid = str(feature.get("id") or "feature")
        name = str(feature.get("name") or fid)
        description = str(feature.get("description") or name)
        req_id = _unique_id("REQ-AI", id_index, fid)
        cap_id = _unique_id("CAP-AI", id_index, fid)
        ev_id = _unique_id("EVIDENCE-AI", id_index, fid)
        test_id = _unique_id("TEST-AI", id_index, fid)

        requirements.append(
            {
                "id": req_id,
                "title": name[:240],
                "description": (
                    f"The live product exposes the planned AI feature '{name}': {description}"
                )[:4000],
                "priority": "must",
                "verification_mode": "content",
                "source_refs": [AI_FEATURE_SOURCE_REF],
            }
        )
        capabilities.append(
            {
                "id": cap_id,
                "name": name[:240],
                "description": description[:4000],
                "requirement_ids": [req_id],
                "role_ids": [role_id],
                "entity_ids": [],
            }
        )
        evidence.append(
            {
                "id": ev_id,
                "page_id": hub_id,
                "name": f"{name} surface",
                "description": (
                    f"Interactive AI feature '{name}' is visible with data-ai-feature='{fid}'."
                )[:4000],
                "kind": "status",
                "capability_ids": [cap_id],
            }
        )
        acceptance_tests.append(
            {
                "id": test_id,
                "name": f"{name} is visible",
                "description": (
                    f"Prove the planned AI feature '{name}' is visible on the AI hub page."
                )[:4000],
                "requirement_ids": [req_id],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": f"AI feature '{name}' is visible on the hub.",
                        "page_id": hub_id,
                        "state_id": state_id,
                        "evidence_id": ev_id,
                        "expected": fid,
                    }
                ],
            }
        )
        hub_caps = list(hub.get("capability_ids") or [])
        if cap_id not in hub_caps:
            hub_caps.append(cap_id)
        hub["capability_ids"] = hub_caps
        hub_ev = list(hub.get("evidence_ids") or [])
        if ev_id not in hub_ev:
            hub_ev.append(ev_id)
        hub["evidence_ids"] = hub_ev
        for st in states:
            if str(st.get("id") or "") == state_id:
                st_ev = list(st.get("evidence_ids") or [])
                if ev_id not in st_ev:
                    st_ev.append(ev_id)
                st["evidence_ids"] = st_ev
        traceability.append(
            {
                "requirement_id": req_id,
                "capability_ids": [cap_id],
                "page_ids": [hub_id],
                "evidence_ids": [ev_id],
                "journey_ids": [],
                "acceptance_test_ids": [test_id],
            }
        )

    # Re-trace stranded injector requirements. A model repair re-emits the
    # whole document and may drop any piece of a previous binding while keeping
    # the requirement; "already bound" then skips the feature forever and the
    # run dies on `requirement_unaccounted_for` (request 130). Rebuild only the
    # missing pieces, reusing whatever survived.
    traced_ids = {
        str(t.get("requirement_id") or "").casefold() for t in traceability
    }
    marker = AI_FEATURE_SOURCE_REF.casefold()
    for req in requirements:
        rid = str(req.get("id") or "")
        refs = [str(r).casefold() for r in (req.get("source_refs") or [])]
        if not rid or marker not in refs or rid.casefold() in traced_ids:
            continue
        name = str(req.get("title") or rid)
        cap = next(
            (
                c
                for c in capabilities
                if rid in [str(x) for x in (c.get("requirement_ids") or [])]
            ),
            None,
        )
        if cap is None:
            cap = {
                "id": _unique_id("CAP-AI", id_index, rid),
                "name": name[:240],
                "description": str(req.get("description") or name)[:4000],
                "requirement_ids": [rid],
                "role_ids": [role_id],
                "entity_ids": [],
            }
            capabilities.append(cap)
        cap_id = str(cap.get("id") or "")
        ev = next(
            (
                e
                for e in evidence
                if str(e.get("page_id") or "") == hub_id
                and cap_id in [str(x) for x in (e.get("capability_ids") or [])]
            ),
            None,
        )
        if ev is None:
            ev = {
                "id": _unique_id("EVIDENCE-AI", id_index, rid),
                "page_id": hub_id,
                "name": f"{name} surface"[:240],
                "description": (
                    f"Interactive AI feature '{name}' is visible on the hub."
                )[:4000],
                "kind": "status",
                "capability_ids": [cap_id],
            }
            evidence.append(ev)
        ev_id = str(ev.get("id") or "")
        test = next(
            (
                t
                for t in acceptance_tests
                if rid in [str(x) for x in (t.get("requirement_ids") or [])]
            ),
            None,
        )
        if test is None:
            test = {
                "id": _unique_id("TEST-AI", id_index, rid),
                "name": f"{name} is visible"[:240],
                "description": (
                    f"Prove the planned AI feature '{name}' is visible on the AI hub page."
                )[:4000],
                "requirement_ids": [rid],
                "journey_id": None,
                "assertions": [
                    {
                        "kind": "visible",
                        "description": f"AI feature '{name}' is visible on the hub.",
                        "page_id": hub_id,
                        "state_id": state_id,
                        "evidence_id": ev_id,
                        "expected": name[:240],
                    }
                ],
            }
            acceptance_tests.append(test)
        test_id = str(test.get("id") or "")
        hub_caps = list(hub.get("capability_ids") or [])
        if cap_id not in hub_caps:
            hub_caps.append(cap_id)
        hub["capability_ids"] = hub_caps
        hub_ev = list(hub.get("evidence_ids") or [])
        if ev_id not in hub_ev:
            hub_ev.append(ev_id)
        hub["evidence_ids"] = hub_ev
        for st in states:
            if str(st.get("id") or "") == state_id:
                st_ev = list(st.get("evidence_ids") or [])
                if ev_id not in st_ev:
                    st_ev.append(ev_id)
                st["evidence_ids"] = st_ev
        traceability.append(
            {
                "requirement_id": rid,
                "capability_ids": [cap_id],
                "page_ids": [hub_id],
                "evidence_ids": [ev_id],
                "journey_ids": [],
                "acceptance_test_ids": [test_id],
            }
        )
        traced_ids.add(rid.casefold())

    # Ensure hub purpose mentions all feature names for coverage reviewers.
    names = [str(f.get("name") or "") for f in features if f.get("name")]
    if names:
        hub["purpose"] = (
            "Interactive hub for planned AI features: " + "; ".join(names[:MAX_AI_FEATURES])
        )[:4000]

    if role_id not in list(hub.get("role_ids") or []):
        hub["role_ids"] = list(dict.fromkeys([*(hub.get("role_ids") or []), role_id]))

    sanitized["requirements"] = requirements
    sanitized["capabilities"] = capabilities
    sanitized["evidence"] = evidence
    sanitized["states"] = states
    sanitized["pages"] = pages
    sanitized["acceptance_tests"] = acceptance_tests
    sanitized["traceability"] = traceability
    sanitized["deferred_scope"] = deferred
    return sanitized


def missing_ai_feature_ids_in_workspace(
    workspace_text_blob: str,
    features: list[Mapping[str, Any]],
) -> list[str]:
    missing: list[str] = []
    blob = workspace_text_blob or ""
    for feature in features:
        fid = str(feature.get("id") or "").strip()
        if not fid:
            continue
        markers = (
            f'data-ai-feature="{fid}"',
            f"data-ai-feature='{fid}'",
            f"data-ai-feature={json.dumps(fid)}",
            f'data-ai-feature={{json.dumps("{fid}")}}',
            # Hub page / mock inventory embed the planned id even when the
            # interactive attribute lives inside AiFeatureDeck at runtime.
            f'"id": "{fid}"',
            f'"id":"{fid}"',
        )
        if not any(marker in blob for marker in markers):
            missing.append(fid)
    return missing


def ai_feature_hub_page_source(
    *,
    brand_name: str,
    features: list[Mapping[str, Any]],
    page_id: str = PAGE_AI_HUB_ID,
    evidence_ids: list[str] | None = None,
    ops_shell: bool = False,
    appearance: str | None = None,
) -> str:
    """Deterministic interactive hub page for planned AI features."""
    brand = brand_name or "Brand"
    page = page_id or PAGE_AI_HUB_ID
    ev_ids = [str(e) for e in (evidence_ids or []) if e]
    evidence_spans = "\n".join(
        f'        <span className="sr-only" data-appspec-evidence={json.dumps(eid)}>{eid}</span>'
        for eid in ev_ids
    )
    feature_json = json.dumps([dict(f) for f in features], ensure_ascii=False)
    # Only trading desks get dark floor chrome; accounting stays soft ledger.
    shell_appearance = appearance
    if ops_shell and shell_appearance is None:
        shell_appearance = "soft"
    appearance_attr = (
        f' appearance={json.dumps(shell_appearance)}' if ops_shell and shell_appearance else ""
    )
    if ops_shell:
        return f"""// plan AI feature hub — ops product chrome (preview basename-safe)
import {{ useAdminNavItems }} from '@/lib/app-nav';
import {{ aiFeatures }} from '@/data/mock';
import {{ OpsShell, AiFeatureDeck }} from '@/ui';

export default function AiFeaturesPage() {{
  const adminNavItems = useAdminNavItems();
  const features = Array.isArray(aiFeatures) && aiFeatures.length
    ? aiFeatures
    : {feature_json};
  return (
    <OpsShell brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}}{appearance_attr}>
      <div data-appspec-page={{{json.dumps(page)}}}>
{evidence_spans}
        <AiFeatureDeck features={{features}} brandName={{{json.dumps(brand)}}} variant="ops" />
      </div>
    </OpsShell>
  );
}}
"""
    return f"""// plan AI feature hub — every planned AI feature is interactive here
import {{ usePublicNavItems, publicCta }} from '@/lib/app-nav';
import {{ aiFeatures }} from '@/data/mock';
import {{ PublicShell, PublicNav, AiFeatureDeck }} from '@/ui';

export default function AiFeaturesPage() {{
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  const features = Array.isArray(aiFeatures) && aiFeatures.length
    ? aiFeatures
    : {feature_json};
  return (
    <PublicShell brandName={{{json.dumps(brand)}}} nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>
      <div data-appspec-page={{{json.dumps(page)}}}>
{evidence_spans}
        <AiFeatureDeck features={{features}} brandName={{{json.dumps(brand)}}} />
      </div>
    </PublicShell>
  );
}}
"""
