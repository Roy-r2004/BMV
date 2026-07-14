"""HTML fallback pipeline: generates one bundled, navigable HTML site per role
when the React preview-app pipeline is unavailable or fails."""
import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.prompts import PromptTemplate
from app.application.pipelines._shared import get_request
from app.core.config import settings
from app.domain.interfaces.ai_provider import AIProvider
from app.domain.interfaces.template_renderer import TemplateRenderer
from app.application.services.industry_images import get_images_for_industry
from app.application.services.page_bundle import build_role_site_bundle
from app.application.services.page_experience import (
    build_design_manifest,
    build_experience_plan,
    gather_full_context,
)
from app.application.services.page_inject import fix_broken_images, inject_page_enhancements
from app.application.services.page_qa import check_page, fix_page


def _generate_one_page_html(
    full_context: str,
    concept_name: str,
    page_spec: dict,
    page_id: str,
    images: dict,
    manifest: dict,
    plan: dict,
    role_spec: dict,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> str:
    """Generate one HTML page from the experience plan, QA up to 2 fix attempts."""
    page_spec_json = json.dumps(page_spec, ensure_ascii=False, indent=2)
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    design_system_json = json.dumps(design_system, ensure_ascii=False, indent=2)
    role_navigation_json = json.dumps(role_spec.get("navigation") or {}, ensure_ascii=False, indent=2)
    consistency = "\n".join(f"- {r}" for r in plan.get("consistency_rules", []))
    features = "\n".join(f"- {f}" for f in page_spec.get("features_to_showcase", [])) or "- (see page spec)"

    prompt = template_renderer.render(
        PromptTemplate.HTML_PAGE,
        full_context=full_context[:14000],
        concept_name=concept_name,
        design_system_json=design_system_json,
        design_manifest=manifest_json,
        design_direction=plan.get("design_direction", ""),
        consistency_rules=consistency or "- Keep brand consistent",
        role_navigation_json=role_navigation_json,
        current_page_id=page_id,
        page_spec_json=page_spec_json,
        page_type=page_spec.get("page_type", page_spec.get("title", "Page")),
        page_purpose=page_spec.get("purpose", ""),
        features_to_showcase=features,
        img_hero=images.get("hero", ""),
        img_hero2=images.get("hero2", ""),
        img_card1=images.get("card1", ""),
        img_card2=images.get("card2", ""),
        img_card3=images.get("card3", ""),
        img_ambient=images.get("ambient", ""),
    )

    raw = ai_provider.ask_chat(settings.HTML_MODEL, [{"role": "user", "content": prompt}], max_tokens=12000)
    html = raw.strip()
    for fence in ("```html", "```"):
        if html.startswith(fence):
            html = html[len(fence):]
        if html.endswith("```"):
            html = html[:-3]
    html = html.strip()

    if "<html" not in html.lower():
        raise ValueError("AI did not return valid HTML on attempt 1")

    accent = design_system.get("primary_color") or manifest.get("accent") or "#6366f1"
    for attempt in range(2):
        try:
            qa = check_page(html, page_spec, ai_provider, template_renderer)
            if qa.passes:
                break
            fixed = fix_page(
                html, page_spec, qa, manifest, plan, role_spec, page_id, accent, images,
                ai_provider, template_renderer,
            )
            if "<html" in fixed.lower() and len(fixed) > len(html) * 0.4:
                html = fixed
        except Exception:
            break

    return html


def generate_role_pages(
    db: Session,
    request_id: int,
    ai_provider: AIProvider,
    template_renderer: TemplateRenderer,
) -> dict:
    req = get_request(db, request_id)
    if not req.mvp_blueprint:
        raise ValueError("MVP blueprint must be generated first.")

    demo: dict = {}
    if req.visual_demo_json:
        try:
            demo = json.loads(req.visual_demo_json)
        except Exception:
            pass

    theme = demo.get("visual_theme", {})
    primary = theme.get("primary_color", "#6366f1")
    secondary = theme.get("secondary_color", "#0d9488")
    concept = req.concept_name or req.business_name
    images = get_images_for_industry(
        req.industry or "",
        seed=req.id,
        business_name=req.business_name,
    )

    # ── Step 1: Planner + validator agents ──
    print("  [1/4] Planning UI experience from full business input...", flush=True)
    full_context = gather_full_context(req, demo)
    plan = build_experience_plan(req, demo, primary, secondary, ai_provider, template_renderer)
    total_pages = sum(len(r.get("pages", [])) for r in plan.get("roles", []))
    coverage = len(plan.get("feature_coverage", []))
    print(f"  OK Plan: {len(plan.get('roles', []))} roles, {total_pages} pages, {coverage} features mapped", flush=True)

    # ── Step 2: Brand manifest (inherits design_system from plan) ──
    print("  [2/4] Building brand manifest...", flush=True)
    manifest = build_design_manifest(full_context, plan, ai_provider, template_renderer)
    design_system = plan.get("design_system") or manifest.get("design_system") or {}
    brand_accent = design_system.get("primary_color") or manifest.get("accent") or primary

    # ── Step 3: Builder + QA agents per page ──
    print(f"  [3/4] Generating {total_pages} pages from plan...", flush=True)
    roles: dict = {}
    page_num = 0
    for role_spec in plan.get("roles", []):
        role_id = role_spec.get("id", "role")

        roles[role_id] = {
            "id": role_id,
            "label": role_spec.get("label", role_id),
            "tagline": role_spec.get("tagline", ""),
            "icon": role_spec.get("icon", "users"),
            "accent": brand_accent,
            "navigation": role_spec.get("navigation"),
            "pages": [],
        }

        for page_spec in role_spec.get("pages", []):
            page_num += 1
            page_id = page_spec.get("id", f"page_{page_num}")
            page_title = page_spec.get("title", page_id)
            try:
                print(f"  -> [{page_num}/{total_pages}] [{role_id}] {page_title} ...", flush=True)
                html = _generate_one_page_html(
                    full_context, concept, page_spec, page_id, images, manifest, plan, role_spec,
                    ai_provider, template_renderer,
                )
                print(f"  OK [{role_id}] {page_title} ({len(html):,} chars)", flush=True)
                roles[role_id]["pages"].append({
                    "id": page_id,
                    "title": page_title,
                    "html": html,
                })
            except Exception as e:
                print(f"  FAIL [{role_id}] {page_title} - {e}", flush=True)

        # ── Step 4: Inject theme + bundle into one navigable website per role ──
        role_pages = roles[role_id]["pages"]
        for pg in role_pages:
            pg["html"] = fix_broken_images(pg["html"], images)
            pg["html"] = inject_page_enhancements(
                pg["html"], role_spec, role_pages, design_system, manifest, template_renderer,
            )
        slug = (concept or "preview").lower().replace(" ", "-")
        roles[role_id]["site_html"] = build_role_site_bundle(
            role_pages, design_system, manifest, slug, template_renderer,
        )

    print("  [4/4] Done.", flush=True)

    result = {
        "roles": [v for v in roles.values() if v["pages"]],
        "experience_plan": plan,
    }

    req.generated_pages = json.dumps(result) if result["roles"] else None
    req.updated_at = datetime.utcnow()
    db.commit()
    return result


def enhance_generated_pages(
    db: Session,
    request_id: int,
    template_renderer: TemplateRenderer,
) -> dict:
    """Re-inject theme + nav bridge into existing pages without full regen."""
    req = get_request(db, request_id)
    if not req.generated_pages:
        raise ValueError("No generated pages to enhance.")

    demo: dict = {}
    if req.visual_demo_json:
        try:
            demo = json.loads(req.visual_demo_json)
        except Exception:
            pass

    theme = demo.get("visual_theme", {})
    primary = theme.get("primary_color", "#6366f1")
    secondary = theme.get("secondary_color", "#0d9488")
    data = json.loads(req.generated_pages)
    plan = data.get("experience_plan") or {}
    design_system = plan.get("design_system") or {}
    manifest = {"accent": design_system.get("primary_color", primary), "brand_name": req.concept_name or req.business_name}

    images = get_images_for_industry(
        req.industry or "",
        seed=req.id,
        business_name=req.business_name,
    )
    for role in data.get("roles", []):
        role_id = role.get("id", "")
        role_spec = next((r for r in plan.get("roles", []) if r.get("id") == role_id), {"id": role_id, "navigation": role.get("navigation")})
        accent = design_system.get("primary_color") or primary
        role["accent"] = accent
        role_pages = role.get("pages", [])
        for pg in role_pages:
            if pg.get("html"):
                pg["html"] = fix_broken_images(pg["html"], images)
                pg["html"] = inject_page_enhancements(
                    pg["html"], role_spec, role_pages, design_system, manifest, template_renderer,
                )
        slug = (req.concept_name or req.business_name or "preview").lower().replace(" ", "-")
        role["site_html"] = build_role_site_bundle(
            role_pages, design_system, manifest, slug, template_renderer,
        )

    req.generated_pages = json.dumps(data)
    req.updated_at = datetime.utcnow()
    db.commit()
    return data
