"""Generate structured Launch/Growth/Custom build plans + add-ons (no prices)."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.application.services.ai_features import ai_features_from_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.shared.json_utils import extract_json_from_text

_PLAN_IDS = ("launch", "growth", "custom")
_MONEY_RE = re.compile(
    r"(\$\s*\d|\bUSD\b|\bEUR\b|\bprice\b|\bcost\b|\bfrom\s+\$|\bquote\s+of\b)",
    re.I,
)


def _role_labels(req) -> list[str]:
    if not req.generated_pages:
        return []
    try:
        bundle = json.loads(req.generated_pages)
    except Exception:
        return []
    roles = (bundle.get("preview_app") or {}).get("roles") or bundle.get("roles") or []
    out: list[str] = []
    for r in roles:
        if isinstance(r, dict):
            label = (r.get("label") or r.get("id") or "").strip()
            if label:
                out.append(label)
        elif isinstance(r, str) and r.strip():
            out.append(r.strip())
    return out


def _preview_features(req) -> list[str]:
    if not req.preview_features:
        return []
    try:
        data = json.loads(req.preview_features)
        if isinstance(data, list):
            return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return [line.strip() for line in str(req.preview_features).splitlines() if line.strip()]


def _scrub_money(text: str) -> str:
    if not text:
        return text
    if not _MONEY_RE.search(text):
        return text
    # Soft scrub — drop obvious price fragments
    cleaned = re.sub(r"\$\s*[\d,]+(?:\.\d+)?", "", text)
    cleaned = re.sub(r"\bfrom\s+\d[\d,]*(?:\.\d+)?\s*(USD|usd)?\b", "", cleaned, flags=re.I)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _normalize_plan(raw: dict[str, Any], plan_id: str) -> dict[str, Any]:
    includes = raw.get("includes") or []
    if not isinstance(includes, list):
        includes = [str(includes)]
    includes = [_scrub_money(str(x)) for x in includes if str(x).strip()][:10]
    if not includes:
        includes = ["Production build of your preview", "Owner / admin basics", "Launch handoff"]
    badge = raw.get("badge")
    if badge is not None:
        badge = _scrub_money(str(badge)) or None
    return {
        "id": plan_id,
        "name": _scrub_money(str(raw.get("name") or plan_id.title()))[:80],
        "tagline": _scrub_money(str(raw.get("tagline") or ""))[:200],
        "timeline": _scrub_money(str(raw.get("timeline") or "Scoped together"))[:80],
        "bestFor": _scrub_money(str(raw.get("bestFor") or ""))[:200],
        "includes": includes,
        "badge": badge,
        "highlight": bool(raw.get("highlight")) if plan_id == "growth" else False,
    }


def _normalize_addon(raw: dict[str, Any], idx: int) -> dict[str, Any] | None:
    name = _scrub_money(str(raw.get("name") or "").strip())
    if not name:
        return None
    aid = str(raw.get("id") or f"addon-{idx}").strip().lower()
    aid = re.sub(r"[^a-z0-9\-]+", "-", aid).strip("-") or f"addon-{idx}"
    included = raw.get("includedIn") or []
    if not isinstance(included, list):
        included = []
    included_in = [x for x in included if x in ("launch", "growth")]
    return {
        "id": aid,
        "name": name[:100],
        "description": _scrub_money(str(raw.get("description") or ""))[:280],
        "whyForYou": _scrub_money(str(raw.get("whyForYou") or ""))[:200],
        "includedIn": included_in,
    }


def normalize_build_plans(payload: dict[str, Any]) -> dict[str, Any]:
    plans_raw = {p.get("id"): p for p in (payload.get("plans") or []) if isinstance(p, dict)}
    plans = [_normalize_plan(plans_raw.get(pid) or {"id": pid}, pid) for pid in _PLAN_IDS]
    # Ensure growth is highlighted / badge
    for p in plans:
        if p["id"] == "growth":
            p["highlight"] = True
            if not p.get("badge"):
                p["badge"] = "Most popular"

    addons: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, raw in enumerate(payload.get("addons") or []):
        if not isinstance(raw, dict):
            continue
        addon = _normalize_addon(raw, i)
        if not addon or addon["id"] in seen:
            continue
        seen.add(addon["id"])
        addons.append(addon)
        if len(addons) >= 8:
            break

    rec = payload.get("recommended_plan_id") or "growth"
    if rec not in _PLAN_IDS:
        rec = "growth"

    return {"recommended_plan_id": rec, "plans": plans, "addons": addons}


def fallback_build_plans(req) -> dict[str, Any]:
    brand = req.business_name or "your business"
    ai = ai_features_from_request(req)
    ai_names = [a.get("name") for a in ai if isinstance(a, dict) and a.get("name")]
    roles = _role_labels(req)
    return normalize_build_plans(
        {
            "recommended_plan_id": "growth",
            "plans": [
                {
                    "id": "launch",
                    "name": "Launch MVP",
                    "tagline": f"Ship the {brand} preview you just saw — for real.",
                    "timeline": "4–8 weeks",
                    "bestFor": "Getting live fast with core customer + owner flows",
                    "includes": [
                        "Production build of your preview (public site + core journeys)",
                        "Owner / admin basics",
                        "AI from your preview, wired for production",
                        "Payments on your main customer path",
                        "Customer confirmations (email + WhatsApp/SMS basics)",
                        "Brand, deploy, and launch handoff",
                    ],
                    "highlight": False,
                },
                {
                    "id": "growth",
                    "name": "Growth MVP",
                    "tagline": "Launch + staff ops, polish, and post-launch care.",
                    "timeline": "8–12 weeks",
                    "bestFor": "Teams that need roles, fuller automations, and care",
                    "includes": [
                        "Everything in Launch MVP",
                        "Staff / role dashboards from your preview",
                        "Richer reminder & follow-up automations",
                        "Domain extras for your industry",
                        "Cinematic polish pass",
                        "30-day care after launch",
                    ],
                    "badge": "Most popular",
                    "highlight": True,
                },
                {
                    "id": "custom",
                    "name": "Custom / Scale",
                    "tagline": "Integrations, multi-location, or ongoing product.",
                    "timeline": "Scoped together",
                    "bestFor": "Complex ops or a longer partnership",
                    "includes": [
                        "Everything in Growth MVP",
                        "Third-party integrations",
                        "Advanced roles & permissions",
                        "Custom workflows and reporting",
                        "Dedicated scope call before we quote",
                    ],
                    "highlight": False,
                },
            ],
            "addons": [
                {
                    "id": "ai-pack",
                    "name": (
                        f"AI suite for {brand}"
                        if len(ai_names) >= 2
                        else f"Production-ready {ai_names[0]}"
                        if ai_names
                        else f"AI assistant for {brand}"
                    ),
                    "description": (
                        f"Wire previewed AI: {', '.join(ai_names)}."
                        if ai_names
                        else "Branded AI helper trained on your offerings and FAQs."
                    ),
                    "whyForYou": "Already in your preview — included in Launch.",
                    "includedIn": ["launch", "growth"],
                },
                {
                    "id": "payments",
                    "name": "Payments on your main journey",
                    "description": "Checkout / deposits wired into the primary action in your preview.",
                    "whyForYou": "Core Launch path — not an upgrade.",
                    "includedIn": ["launch", "growth"],
                },
                {
                    "id": "messaging",
                    "name": "Customer confirmations",
                    "description": "WhatsApp/SMS or email confirmations for the main journey.",
                    "whyForYou": "Included in Launch so customers get real updates.",
                    "includedIn": ["launch", "growth"],
                },
                {
                    "id": "roles",
                    "name": (
                        f"Dashboards for {' + '.join(roles[:3])}"
                        if len(roles) >= 2
                        else "Extra staff / partner roles"
                    ),
                    "description": "Separate live workspaces beyond the owner view.",
                    "whyForYou": "Your preview already defines how the team works.",
                    "includedIn": ["growth"],
                },
                {
                    "id": "care",
                    "name": "30-day care after launch",
                    "description": "Priority fixes and small iterations once you’re live.",
                    "whyForYou": "First month is when real customers find edge cases.",
                    "includedIn": ["growth"],
                },
            ],
        }
    )


def generate_build_plans(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict[str, Any]:
    req = get_request(db, request_id)
    if not req.mvp_blueprint and not req.preview_summary:
        raise ValueError("Preview context missing — generate blueprint/preview first.")

    ai_feats = ai_features_from_request(req)
    blueprint_excerpt = (req.mvp_blueprint or "")[:3500]
    prompt = template_renderer.render(
        PromptTemplate.BUILD_PLANS,
        business_name=req.business_name,
        concept_name=req.concept_name or "N/A",
        industry=req.industry or "N/A",
        main_problem=req.main_problem or "N/A",
        desired_outcome=req.desired_outcome or "N/A",
        timeline=req.timeline or "N/A",
        budget_range=req.budget_range or "N/A",
        preview_summary=req.preview_summary or "N/A",
        preview_features=_preview_features(req) or ["(none listed)"],
        ai_features=ai_feats
        or [{"name": "AI helper", "description": "Branded assistant for FAQs and guidance"}],
        role_labels=_role_labels(req) or ["Owner"],
        blueprint_excerpt=blueprint_excerpt or "N/A",
    )

    try:
        raw_text = ai_provider.ask_chat(
            settings.TEXT_MODEL, [{"role": "user", "content": prompt}]
        )
        parsed = extract_json_from_text(raw_text)
        if not isinstance(parsed, dict):
            raise ValueError("Build plans model output was not an object")
        result = normalize_build_plans(parsed)
        if len(result.get("addons") or []) < 3:
            raise ValueError("Too few addons from model")
    except Exception:
        result = fallback_build_plans(req)

    req.build_plans = json.dumps(result)
    req.updated_at = datetime.utcnow()
    db.commit()
    return result


def build_plans_from_request(req) -> dict[str, Any] | None:
    if not getattr(req, "build_plans", None):
        return None
    try:
        data = json.loads(req.build_plans)
        if isinstance(data, dict) and data.get("plans"):
            return normalize_build_plans(data)
    except Exception:
        return None
    return None
