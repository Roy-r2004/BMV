# Tomorrow: curated React starter templates (~20)

## Why yes — this helps

Built-in **industry/layout templates** (not blank canvases) raise the floor the same way Lovable’s best demos do:

- AI fills **slots inside a strong composition** instead of inventing layout from scratch
- Brand/recipe tokens recolor a proven structure → less pale/generic SaaS
- Faster codegen, fewer contract retries, more consistent cinematic chrome
- Easier QA: each template has known hero/ops patterns and required sections

The catalogue skeletons we already have (`public-home`, `ops-dashboard`, …) are the right *mechanism*. What’s missing is a **library of ~20 filled templates** (copy, section order, imagery roles, ops density) keyed by industry + recipe.

## Proposed set (20)

### Public / marketing (12)
1. Boutique spa / wellness home  
2. Local restaurant / cafe  
3. Law / professional services  
4. Fitness / studio  
5. Real estate showcase  
6. Fashion / retail storefront  
7. Clinic / dental  
8. Agency / studio portfolio  
9. Home services / trades  
10. Education / tutoring  
11. Hotel / hospitality  
12. Auto / dealership  

### Member / transactional (3)
13. Member hub (bookings + history)  
14. Checkout / cart utility  
15. Account / tracking utility  

### Ops / admin (5)
16. Owner KPI dashboard  
17. Staff floor ops  
18. Inventory / catalog ops  
19. Leads / CRM list  
20. Booking calendar ops  

Each template = skeleton_id + recipe hint + section_slots + sample content pack + mock shape + optional “signature moves” (marquee, cinematic hero, rail activity).

## Build plan (1 day)

1. **Schema** — `templates/*.json` (id, industry tags, recipe_id, routes[], mock_seed, prompt_hints)  
2. **Loader** — pick template from industry/seed before architect; seed architect routes from template  
3. **Content packs** — rich sample slot JSX / mock data per template (not lorem)  
4. **Wire** — `pick_recipe_id` + template picker in plan/architect phase  
5. **Gallery** — internal preview of all 20 for QA  
6. **Eval** — generate 5 businesses, score “bland vs Lovable” vs baseline  

## Success criteria

- Generated homes never look like flat white Tailwind starters  
- Ops dashboards always brand-tinted (no gray SaaS)  
- At least 2 intentional motions + atmosphere on public home  
- Template hit rate ≥70% for common industries; fallback to recipe-only otherwise  

## Dependency on today’s kit work

Today’s tokenized OpsShell/StatCard/Card/CSS/prompts make templates *actually* look branded. Tomorrow’s templates plug into that system instead of fighting slate hardcodes.

## Scaffold started today

- `backend/app/application/preview_app/industry_templates/` — schema ids + loader/picker + apply
- **All 20 JSON packs** present (metadata + prompt hints + section order)
- Plan phase already stamps `industry_template_id` + template prompt hints and prefers `recipe_hint`
- Tomorrow: richer content/mock JSX packs, section_order → architect routes, gallery QA

## Done today (kit floor raised)

- 6 recipes: editorial, dense-ops, warm-service, bold-retail, **nocturne**, **craft**
- Atmosphere utilities: `ui-mesh`, `ui-noise`, `ui-float`, `ui-gradient-border`, grain/vignette
- Public surfaces enriched: MarketingHero, FeatureBento, CTABand, PublicShell, ProductShowcase, BrandFooter, Spotlight, ResultRail, AccentBeam
- Ops surfaces brand-tokenized (no pale `#f4f7fb` / slate SaaS)
- Prompts ban pale/slate dashboards; require motion + atmosphere
- Scaffold fallbacks use richer cinematic copy
- Plan lives here for tomorrow’s ~20 industry templates
