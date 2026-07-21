# AI Build Plans Implementation Plan

> **For agentic workers:** Implement task-by-task. Spec: `docs/superpowers/specs/2026-07-21-ai-build-plans-design.md`.

**Goal:** Client sees AI-written Launch/Growth/Custom + add-ons (no prices). Proposal hidden from clients. Regenerate supported.

**Architecture:** Pipeline writes `Request.build_plans` JSON → `PreviewResponse` → `BuildRequestCTA`. Fallback: price-free static defaults.

## File map

| File | Change |
|------|--------|
| `backend/.../models/request.py` | `build_plans` column |
| Alembic migration | add column |
| `backend/.../schemas/request.py` | expose + regenerate body |
| `backend/.../pipelines/build_plans.py` | new LLM JSON generator |
| `templates/prompts/build_plans.j2` | prompt |
| `orchestrator.py` | call after proposal |
| `routers/requests.py` | regenerate endpoint + preview field |
| `BuildRequestCTA.tsx` / `buildPlans.ts` | consume AI JSON, strip prices |
| `FullDeliveryPackage.tsx` / `deliveryNavItems.ts` | remove Proposal |
| `Packages.tsx` | strip prices |
| `types/request.ts` / `buildRequest.ts` | types |

## Tasks

1. DB + schema `build_plans`
2. Prompt + `generate_build_plans` + orchestrator
3. Preview API + regenerate endpoint
4. Remove client Proposal UI
5. Frontend consume AI plans, no prices, regenerate button
6. Smoke on existing preview (regenerate) + commit
