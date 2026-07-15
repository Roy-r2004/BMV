"""
Plan-driven UI experience generation.
All roles, pages, navigation, and design system come from AI agents reading the full business input.
"""
import json
from typing import Any

from app.application.prompts import PromptTemplate
from app.application.ui_catalogue import (
    compact_catalogue_plan_contract,
    infer_page_contract,
    infer_section_slots,
)
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.domain.models.request import Request
from app.application.services.preview_parser import parse_preview_features
from app.application.preview_app.app_spec_projection import (
    merge_experience_plan_enrichment,
)


def gather_full_context(req: Request, demo: dict | None = None) -> str:
    """Collect every piece of analysis the UI agents should read."""
    features = parse_preview_features(req.preview_features)
    features_block = "\n".join(f"- {f}" for f in features) if features else "- (none listed)"

    demo_summary = ""
    if demo:
        demo_summary = json.dumps(
            {
                "product_name": demo.get("product_name"),
                "visual_theme": demo.get("visual_theme"),
                "hero": demo.get("hero"),
                "feature_cards": demo.get("feature_cards", [])[:8],
                "user_journey": demo.get("user_journey"),
                "admin_dashboard_preview": demo.get("admin_dashboard_preview"),
                "app_config": demo.get("app_config"),
                "preview_content": demo.get("preview_content"),
            },
            ensure_ascii=False,
            indent=2,
        )[:12000]

    parts = [
        f"Business Name: {req.business_name}",
        f"Concept Name: {req.concept_name or req.business_name}",
        f"Industry: {req.industry or 'N/A'}",
        f"Description: {req.business_description}",
        f"Target Customers: {req.target_customers or 'N/A'}",
        f"Main Problem: {req.main_problem or 'N/A'}",
        f"Desired Outcome: {req.desired_outcome or 'N/A'}",
        f"What They Like (reference): {req.what_you_like or 'N/A'}",
        f"Reference URL: {req.reference_url or 'N/A'}",
        f"Needs AI: {req.needs_ai or 'N/A'}",
        # Preview Summary / Features / Visual Demo hero copy are BMV sales language
        # for the result page — NEVER paste them into the live product UI. Use them
        # only to understand which capabilities the product must include.
        "NOTE: Preview Summary, Preview Features, and Visual Demo hero/CTAs are "
        "agency pitch text for the sales page. The live app must speak as the "
        "business product itself (storefront + owner ops), with brand-voice copy "
        "and realistic operational data — never 'We'll build', 'demo', 'showcase', "
        "or 'Start your plan'.",
        f"Preview Summary (capabilities only — do not paste into UI): {req.preview_summary or 'N/A'}",
        f"MVP Blueprint:\n{req.mvp_blueprint or 'N/A'}",
        f"\nPreview Features (capabilities to implement as real screens — do not paste as marketing cards):\n{features_block}",
    ]

    if req.screenshot_analysis:
        parts.append(f"\nScreenshot / Reference Analysis:\n{req.screenshot_analysis[:6000]}")

    if req.reference_metadata:
        try:
            meta = json.loads(req.reference_metadata)
            parts.append(f"\nReference Metadata:\n{json.dumps(meta, ensure_ascii=False)[:3000]}")
        except Exception:
            pass

    if demo_summary:
        parts.append(f"\nVisual Demo Concept:\n{demo_summary}")

    return "\n".join(parts)


def _close_truncated_json(fragment: str) -> str | None:
    """Balance a JSON fragment cut off by a max_tokens limit.

    Scans with string/escape awareness, drops any trailing incomplete string,
    trims dangling commas/colons, then appends the missing closers.
    """
    stack: list[str] = []
    in_str = False
    esc = False
    last_clean = 0
    for index, ch in enumerate(fragment):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                last_clean = index + 1
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
            last_clean = index + 1
        elif ch in "}]":
            if not stack or stack[-1] != ch:
                return None
            stack.pop()
            last_clean = index + 1
        elif not ch.isspace():
            last_clean = index + 1
    candidate = fragment[:last_clean] if in_str else fragment
    candidate = candidate.rstrip()
    while candidate and candidate[-1] in ",:":
        # A dangling colon means the last key lost its value — drop the key too.
        if candidate[-1] == ":":
            quote_start = candidate.rfind('"', 0, candidate.rfind('"'))
            if quote_start < 0:
                return None
            candidate = candidate[:quote_start]
        else:
            candidate = candidate[:-1]
        candidate = candidate.rstrip()
    return candidate + "".join(reversed(stack))


def _parse_json_from_response(raw: str) -> dict | None:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start < 0:
        return None
    if end > start:
        try:
            return json.loads(raw[start:end])
        except Exception:
            pass
    # Truncated output (max_tokens hit): trim back object-by-object until the
    # remainder can be balanced and parsed. Losing the tail beats losing the plan.
    fragment = raw[start:]
    for _ in range(60):
        repaired = _close_truncated_json(fragment)
        if repaired:
            try:
                parsed = json.loads(repaired)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        cut = max(fragment.rfind("}"), fragment.rfind("]"))
        if cut <= 0:
            return None
        fragment = fragment[:cut]
    return None


def _call_planner(
    req: Request,
    demo: dict,
    primary: str,
    secondary: str,
    model: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    canonical_seed: dict | None = None,
) -> dict | None:
    full_context = gather_full_context(req, demo)
    features = parse_preview_features(req.preview_features)
    prompt = template_renderer.render(
        PromptTemplate.UI_EXPERIENCE_PLAN,
        full_context=full_context,
        mvp_blueprint=req.mvp_blueprint or "",
        preview_features="\n".join(f"- {f}" for f in features) if features else "- core features",
        visual_demo_summary=json.dumps(demo, ensure_ascii=False)[:8000],
        primary_color=primary,
        secondary_color=secondary,
        concept_name=req.concept_name or req.business_name,
        industry=req.industry or "general business",
        catalogue_contract_json=json.dumps(
            compact_catalogue_plan_contract(), ensure_ascii=False, separators=(",", ":")
        ),
        app_spec_seed_json=(
            json.dumps(canonical_seed, ensure_ascii=False, separators=(",", ":"))
            if canonical_seed
            else ""
        ),
    )
    # Plans for multi-role businesses regularly overflow 14k tokens; the parser
    # also repairs truncation, but headroom avoids losing pages in the first place.
    raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=28000)
    plan = _parse_json_from_response(raw)
    if plan and plan.get("roles"):
        if canonical_seed:
            plan = merge_experience_plan_enrichment(canonical_seed, plan)
        return _normalize_plan(plan, primary, secondary)
    print(
        f"  planner model={model} returned no usable plan: "
        f"parsed={'yes' if plan else 'no'} roles={bool(plan and plan.get('roles'))} "
        f"raw_len={len(raw or '')} raw_tail={(raw or '')[-400:]!r}",
        flush=True,
    )
    return None


def _plan_meets_minimums(plan: dict, preview_features: list[str] | None = None) -> tuple[bool, list[str]]:
    """Light gate — only reject empty or feature-incomplete plans, not fixed role/page counts."""
    issues: list[str] = []
    roles = plan.get("roles") or []

    if not roles:
        issues.append("No roles defined — add whatever user types this product needs")

    total_pages = sum(len(r.get("pages") or []) for r in roles)
    if total_pages == 0:
        issues.append("No pages defined — add pages that showcase the blueprint")

    features = preview_features or []
    coverage = plan.get("feature_coverage") or []
    if features and len(coverage) < max(1, len(features) // 2):
        issues.append(
            f"feature_coverage too thin ({len(coverage)} items) — map preview features to pages"
        )

    for role in roles:
        pages = role.get("pages") or []
        page_ids = {p.get("id") for p in pages if p.get("id")}
        nav = role.get("navigation") or {}
        for link in nav.get("links") or []:
            pid = link.get("page_id")
            if pid and pid not in page_ids:
                issues.append(f"Role {role.get('id')}: nav link points to missing page {pid}")

    return len(issues) == 0, issues


def build_experience_plan(
    req: Request,
    demo: dict,
    primary: str,
    secondary: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    *,
    canonical_seed: dict | None = None,
) -> dict:
    """Planner + validator + expansion when plan is empty or missing feature coverage."""
    plan: dict | None = None
    features = parse_preview_features(req.preview_features)

    for model in (settings.TEXT_MODEL, settings.ARCHITECT_MODEL):
        try:
            plan = _call_planner(
                req,
                demo,
                primary,
                secondary,
                model,
                ai_provider,
                template_renderer,
                canonical_seed,
            )
            if plan:
                break
        except Exception as exc:
            print(f"  planner model={model} raised: {type(exc).__name__}: {exc}", flush=True)
            continue

    if not plan and canonical_seed:
        # Product semantics are already complete. A design-model outage may
        # reduce visual specificity, but it must not erase the accepted product
        # contract or send required mode back through the legacy planner.
        plan = _normalize_plan(
            merge_experience_plan_enrichment(canonical_seed, None),
            primary,
            secondary,
        )
    if not plan:
        raise ValueError("Experience planner failed — could not generate a valid plan.")

    if canonical_seed:
        # The generic validator/expander is allowed to add pages. AppSpec mode
        # instead uses the deterministic schema + coverage gates upstream and
        # locks the selected canonical page set here.
        return plan

    plan = validate_and_expand_plan(req, plan, ai_provider, template_renderer, demo)

    ok, issues = _plan_meets_minimums(plan, features)
    if not ok:
        print(f"  Plan expansion needed: {'; '.join(issues)}", flush=True)
        plan = _expand_plan(req, demo, plan, issues, primary, secondary, ai_provider, template_renderer)

    ok, issues = _plan_meets_minimums(plan, features)
    if not ok:
        print(f"  WARN Plan gaps remain: {'; '.join(issues)}", flush=True)

    return plan


def _expand_plan(
    req: Request,
    demo: dict,
    plan: dict,
    issues: list[str],
    primary: str,
    secondary: str,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Force full plan expansion when validator output is too thin."""
    features = parse_preview_features(req.preview_features)
    full_context = gather_full_context(req, demo)
    prompt = template_renderer.render(
        PromptTemplate.PLAN_EXPANSION,
        issues="\n".join(f"- {i}" for i in issues),
        plan_json=json.dumps(plan, ensure_ascii=False)[:10000],
        preview_features="\n".join(f"- {f}" for f in features) if features else "- all blueprint features",
        mvp_blueprint=(req.mvp_blueprint or "")[:8000],
        full_context=full_context[:8000],
        catalogue_contract_json=json.dumps(
            compact_catalogue_plan_contract(), ensure_ascii=False, separators=(",", ":")
        ),
    )
    for model in (settings.ARCHITECT_MODEL, settings.TEXT_MODEL):
        try:
            raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
            result = _parse_json_from_response(raw)
            if result and result.get("roles"):
                expanded = _normalize_plan(result, primary, secondary)
                return validate_and_expand_plan(req, expanded, ai_provider, template_renderer, demo)
        except Exception:
            continue
    return plan


def validate_and_expand_plan(
    req: Request,
    plan: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
    demo: dict | None = None,
) -> dict:
    """Validator agent checks feature coverage and patches the plan if gaps exist."""
    features = parse_preview_features(req.preview_features)
    primary = plan.get("design_system", {}).get("primary_color", "#6366f1")

    prompt = template_renderer.render(
        PromptTemplate.PLAN_VALIDATION,
        plan_json=json.dumps(plan, ensure_ascii=False)[:12000],
        preview_features="\n".join(f"- {f}" for f in features) if features else "- all blueprint features",
        mvp_blueprint=(req.mvp_blueprint or "")[:8000],
        catalogue_contract_json=json.dumps(
            compact_catalogue_plan_contract(), ensure_ascii=False, separators=(",", ":")
        ),
    )
    for model in (settings.ARCHITECT_MODEL, settings.TEXT_MODEL):
        try:
            raw = ai_provider.ask_chat(model, [{"role": "user", "content": prompt}], max_tokens=14000)
            result = _parse_json_from_response(raw)
            if result and result.get("roles"):
                return _normalize_plan(result, primary, "")
        except Exception:
            continue
    return plan


def build_design_manifest(
    full_context: str,
    plan: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    """Brand manifest from full context + plan — inherits design_system from planner."""
    ds = plan.get("design_system") or {}
    accent = ds.get("primary_color") or "#6366f1"

    features_from_plan: list[str] = []
    for role in plan.get("roles", []):
        for page in role.get("pages", []):
            features_from_plan.extend(page.get("features_to_showcase", []))

    prompt = template_renderer.render(
        PromptTemplate.DESIGN_MANIFEST,
        full_context=full_context[:10000],
        experience_plan_summary=_summarize_plan(plan),
        design_system_json=json.dumps(ds, ensure_ascii=False, indent=2),
        accent=accent,
        features=", ".join(dict.fromkeys(features_from_plan))[:800] or "core features",
    )
    try:
        raw = ai_provider.ask_chat(settings.ARCHITECT_MODEL, [{"role": "user", "content": prompt}], max_tokens=1500)
        manifest = _parse_json_from_response(raw)
        if manifest:
            manifest["design_system"] = ds
            return manifest
    except Exception:
        pass

    return {
        "accent": accent,
        "brand_name": plan.get("concept_name", "Business"),
        "design_system": ds,
        "services": [],
    }


def page_required_sections(page_spec: dict) -> list[str]:
    sections = page_spec.get("sections") or []
    result: list[str] = []
    for s in sections:
        if isinstance(s, str):
            result.append(s)
        elif isinstance(s, dict):
            name = s.get("name", "")
            desc = s.get("description", "")
            if name:
                result.append(f"{name}: {desc}" if desc else name)
    features = page_spec.get("features_to_showcase") or []
    for f in features:
        result.append(f"Feature UI visible: {f}")
    return result


def _summarize_plan(plan: dict) -> str:
    lines: list[str] = []
    if plan.get("design_direction"):
        lines.append(f"Design direction: {plan['design_direction']}")
    for role in plan.get("roles", []):
        lines.append(f"Role: {role.get('label')} ({role.get('id')})")
        nav = role.get("navigation") or {}
        links = nav.get("links") or []
        if links:
            lines.append(f"  Nav: {', '.join(l.get('label', '') for l in links)}")
        for page in role.get("pages", []):
            sections = page.get("sections") or []
            lines.append(
                f"  Page [{page.get('id')}]: {page.get('title')} — "
                f"{len(sections)} sections, features: {', '.join(page.get('features_to_showcase', [])[:4])}"
            )
    cov = plan.get("feature_coverage") or []
    if cov:
        lines.append(f"Feature coverage: {len(cov)} items mapped")
    return "\n".join(lines)


def _normalize_plan(plan: dict, primary: str, secondary: str) -> dict:
    ds = plan.setdefault("design_system", {})
    ds.setdefault("primary_color", primary)
    ds.setdefault("secondary_color", secondary or primary)
    ds.setdefault("background_color", "#ffffff")
    ds.setdefault("text_color", "#1e293b")
    ds.setdefault("muted_text_color", "#64748b")
    ds.setdefault("font_family", "Inter")
    plan.setdefault("design_direction", "")
    plan.setdefault("consistency_rules", [])
    plan.setdefault("feature_coverage", [])

    for i, role in enumerate(plan.get("roles", [])):
        role.setdefault("id", f"role_{i}")
        role.setdefault("label", role["id"].replace("_", " ").title())
        role.setdefault("tagline", "")
        role.setdefault("icon", "users" if i == 0 else "chart")

        pages = role.get("pages") or []
        page_ids = {p.get("id") for p in pages if p.get("id")}

        # Auto-build navigation from pages if planner omitted it
        if not role.get("navigation") and pages:
            nav_type = role.get("navigation_type") or "top_nav"
            role["navigation"] = {
                "type": nav_type,
                "links": [
                    {"label": p.get("title", p.get("id", "")), "page_id": p.get("id"), "style": "link"}
                    for p in pages if p.get("id")
                ],
            }

        nav = role.get("navigation") or {}
        valid_links = [
            lnk for lnk in (nav.get("links") or [])
            if lnk.get("page_id") in page_ids
        ]
        if valid_links:
            nav["links"] = valid_links
            role["navigation"] = nav

        for j, page in enumerate(pages):
            page.setdefault("id", f"page_{j}")
            page.setdefault("title", page["id"].replace("-", " ").title())
            page.setdefault("page_type", page.get("title", "Page"))
            page.setdefault("purpose", "")
            page.setdefault("sections", [])
            page.setdefault("features_to_showcase", [])
            page.setdefault("layout_notes", "")
            page.setdefault("sample_data_notes", "")
            inference_source = {
                **page,
                "role_id": role.get("id"),
                "role_label": role.get("label"),
            }
            inferred = infer_page_contract(inference_source)
            page["surface"] = inferred["surface"]
            page["skeleton_id"] = inferred["skeleton_id"]
            page["section_slots"] = infer_section_slots(page, page["skeleton_id"])

    return plan
