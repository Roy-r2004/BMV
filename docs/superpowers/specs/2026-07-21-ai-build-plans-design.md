# AI Build Plans (no client prices) — Design

**Date:** 2026-07-21  
**Status:** Approved

## Goals

1. Remove the client-facing Proposal section (nav + Overview / Project title / WhatsApp cards). Customers never see `proposal_draft`.
2. Generate structured Launch / Growth / Custom plans + business-specific add-ons via the pipeline (JSON), from preview content.
3. Show **no prices** on the client — plans and add-ons only; quoting stays human.
4. Support **Regenerate for this preview** after refine.

## Non-goals

- Stripe / checkout
- Changing admin proposal editor (keep `proposal_draft` for admin)
- Hard dollar amounts in customer UI or build-request payload

## Data shape (`build_plans` JSON on Request)

```json
{
  "recommended_plan_id": "growth",
  "plans": [
    {
      "id": "launch",
      "name": "Launch MVP",
      "tagline": "...",
      "timeline": "4–8 weeks",
      "bestFor": "...",
      "includes": ["..."],
      "badge": null,
      "highlight": false
    }
  ],
  "addons": [
    {
      "id": "payments",
      "name": "...",
      "description": "...",
      "whyForYou": "...",
      "includedIn": ["launch", "growth"]
    }
  ]
}
```

Rules for the LLM:

- Exactly three plans: `launch`, `growth`, `custom`.
- Launch must feel complete (AI + main commerce path + basic messaging as Included where relevant).
- Growth steps up (roles, specialty, polish, care).
- Add-ons are specific to this preview (features, AI, roles, industry).
- **No dollar amounts** in any field.
- Clamp / validate; on failure fall back to static frontend defaults (also price-free).

## Pipeline

- New step `generate_build_plans` after preview ready (alongside or just after proposal).
- Persist on `Request.build_plans` (JSON/Text column).
- Expose on `PreviewResponse.build_plans`.
- Endpoint: `POST /api/requests/{id}/generate-build-plans` (and admin equivalent if pattern exists) for regenerate.

## Client UX

- Remove Proposal from `deliveryNavItems` + `FullDeliveryPackage`.
- `BuildRequestCTA` consumes `preview.build_plans` when present.
- No `fromUsd` / estimate UI; optional add-ons toggle as Add / Added only.
- Build request body: `package_id`, `addon_ids`, notes — drop `estimate_from_usd` from customer flow (ignore if sent).
- Regenerate button on Build plans section when preview is ready.

## Landing

- `Packages.tsx`: remove price display; keep generic static plan copy or share price-free defaults.
