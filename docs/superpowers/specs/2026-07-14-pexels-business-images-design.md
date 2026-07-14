# Soft per-business imagery via Pexels API — Design Spec

**Date:** 2026-07-14  
**Status:** Approved via product decision (Pexels API; key in env only)  
**Goal:** Each preview run gets relevant, non-identical stock photos for that business.

## Approach

1. At generation time, call Pexels Search API with queries derived from `business_name` + `industry` + slot (`hero`, `hero2`, `card1`…).
2. Use request `seed` to pick different result pages/offsets so two fitness studios differ.
3. Fall back to existing curated Unsplash URL library if the key is missing or Pexels fails.
4. Never commit `PEXELS_API_KEY`; never use Unsplash Dataset redistribution.

## Non-goals

- Hotlinking arbitrary Google Image results
- Bundling the [Unsplash Dataset](https://github.com/unsplash/datasets) into the product

## Integration

- `get_images_for_industry(..., business_name=)` tries Pexels then curated fallback
- Catalogue scaffolds prefer `images.hero` / `images.card*` from mock
- Prompt: pages must use `images.*` from `@/data/mock`
