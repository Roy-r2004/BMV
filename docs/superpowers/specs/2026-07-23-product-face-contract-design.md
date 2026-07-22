# Product Face Contract — Packs as Fallback Only

**Date:** 2026-07-23  
**Status:** Approved (approach B)  
**Related:** `2026-07-22-llm-first-inventory-design.md` (inventory); this spec covers **copy, page intent, and ops seed**.

## Problem

The pipeline is strong; product truth is weak. Industry packs + keyword face pickers overwrite or invent vertical voice:

- Clinic staff desk showed restaurant floor KPIs (`staff-floor-ops` tag match on “front desk”).
- Ops headers reused marketing `seed.hero`.
- `/doctors` cloned homepage via `seed.hero` + keyword scaffolds.

Adding more packs (e.g. `clinic-front-desk-ops`) stops bleeds but deepens hardcoding. We chose **B**: LLM/brief contract always wins; packs fill gaps only.

## Goal

One **Product Face Contract** per generate owns:

1. Roles + routes  
2. Per-route `page_intent`  
3. `public_seed` (marketing)  
4. `ops_seed` (staff/owner consoles)  

Scaffolds and codegen bind to that contract. Packs and keyword lists never overwrite non-empty contract fields.

## Non-goals

- Removing catalogue shells / component kit  
- Removing quality gate compile contracts  
- Full deletion of pack JSON files in v1 (keep as thin fallback)  
- Real booking backends  

## Contract shape

Persisted on `experience_plan` (and mirrored into `mock_seed` for existing scaffolds):

```json
{
  "product_face": {
    "version": 1,
    "roles": [
      { "id": "patient", "label": "Patient", "tagline": "…", "defaultPath": "/" }
    ],
    "routes": [
      {
        "path": "/",
        "title": "Home",
        "role_id": "patient",
        "page_intent": "home"
      },
      {
        "path": "/doctors",
        "title": "Doctors",
        "role_id": "patient",
        "page_intent": "listing"
      },
      {
        "path": "/staff/dashboard",
        "title": "Staff Dashboard",
        "role_id": "staff",
        "page_intent": "ops"
      }
    ],
    "public_seed": {
      "hero": { "headline": "…", "subcopy": "…", "primaryCta": {}, "secondaryCta": {} },
      "services": [],
      "features": [],
      "process": [],
      "testimonials": [],
      "credentials": [],
      "trustLabels": []
    },
    "ops_seed": {
      "hero": { "headline": "…", "subcopy": "…" },
      "kpis": [{ "label": "…", "value": "…", "delta": "…", "hint": "…" }],
      "items": [{ "title": "…", "description": "…" }],
      "activity": [],
      "risk": []
    }
  }
}
```

### `page_intent` enum (closed)

`home | listing | detail | booking | confirm | ops | ai | utility`

No industry strings. Faces map by intent only.

## Precedence rules (hard)

1. **Contract wins.** If `product_face.public_seed.hero` is set, packs must not replace it.  
2. **Ops seed wins on ops pages.** Ops headers/KPIs read `ops_seed` only — never `public_seed.hero`.  
3. **Packs fill gaps only.** `merge_pack_fallback(contract, pack)` copies a pack field only when the contract field is missing/empty.  
4. **Keyword face pickers are demoted.** `_is_schedule_listing_route` / `_is_directory_listing_route` / trading-accounting hints become fallbacks when `page_intent` is absent; when intent is present, intent decides the scaffold face.  
5. **Thin contract only.** If LLM returns empty `ops_seed` and empty routes, packs + product_kind may seed — same spirit as LLM-first inventory.

## Pipeline integration

### Emit

After `build_experience_plan` (and AppSpec seed merge if any), call:

- Prefer fields already on the plan / AppSpec projection.  
- LLM enrichment prompt (or extend `ui_experience_plan`) to fill missing `page_intent`, `public_seed`, `ops_seed` from the brief.  
- Normalize via `normalize_product_face(plan) → product_face`.

### Merge packs (changed behavior)

`apply_industry_template_to_plan` / `apply_ops_industry_template_to_plan`:

- Today: pack often **sets** `mock_seed` / merges ops KPIs over the plan.  
- Target: pack runs as **fallback filler** into `product_face` empty slots only; then `materialize_mock_seed(product_face)` writes:

  - `mock_seed` ← public_seed (+ marketing fields)  
  - `mock_seed.opsHero` ← ops_seed.hero  
  - `mock_seed.kpis|activity|risk|opsItems` ← ops_seed  

### Scaffolds

- `minimal_catalogue_page_scaffold`: choose face from `route.page_intent` (listing → directory/schedule-style face; ops → ops dashboard; home → public-home; etc.).  
- Slot JSX for ops `header` / `kpis` binds `seed.opsHero` / `seed.kpis` only.  
- Keyword helpers remain as last-resort when intent missing.

### Architect / host

- Routes carry `page_intent` through finalize → `preview_app.routes` (host page map already uses routes).  
- Host role UX unchanged except it can show better titles from contract.

## What gets demoted (not deleted in v1)

| Hardcoding | Status after this work |
|------------|-------------------------|
| Industry pack **overwrite** of seed | Removed (gap-fill only) |
| `clinic-front-desk-ops` / `staff-floor-ops` as primary brain | Fallback only |
| Doctor/schedule keyword face pickers | Fallback if no `page_intent` |
| Design overlays / recipes | Keep (visual grammar, not industry story) |
| Catalogue shells | Keep |

## Success criteria

1. Clinic brief with front desk → `ops_seed` KPIs about patients/appointments even if a restaurant pack would tag-match.  
2. `/doctors` with `page_intent=listing` → listing face without depending on path keywords.  
3. Ops dashboard title ≠ marketing homepage headline.  
4. Unit tests: pack merge never overwrites non-empty ops KPIs; intent beats keyword face.  
5. No new industry pack JSON required for a new vertical to look “about that business.”

## Test plan

- `test_product_face_pack_gap_fill_only`  
- `test_ops_seed_not_overwritten_by_staff_floor_pack`  
- `test_page_intent_listing_face_without_doctor_keyword` (path `/providers`, intent listing)  
- `test_ops_header_uses_ops_seed_not_public_hero`  
- Regression: existing schedule-listing + directory tests still pass when intent absent (keyword fallback).

## Rollout

1. Spec + `product_face` normalize/merge module  
2. Wire plan_phase + pack apply gap-fill  
3. Scaffold intent routing  
4. Prompt updates for experience plan  
5. Eval on clinic + cafe (cafe still gets floor voice from **its** contract/fallback, not from stealing clinic)

## Out of scope for follow-ups

- Deleting all pack files  
- Page-intent critic / vision evals  
- Removing product_kind chrome entirely  
