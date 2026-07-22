# Signature Product Faces — Design Spec

**Date:** 2026-07-22  
**Status:** Approved  
**Goal:** Previews look like distinct killer products, not one scaffold with new labels.

## Problem

Ops previews share `OpsShell` + `ops-dashboard` slots and one AI chat deck. Accounting and trading only differ by copy/seed.

## Outcome (what users see)

- **Accounting (LedgerFlow):** light ledger chrome, cash pulse strip, invoice status board, bank recon split.
- **Trading desk:** dark floor chrome, live ticker, dense blotter tape, risk rail.
- **AI hub:** digest / scoring / ops / scheduling render as native tools — not the same chat UI.

## Approach

1. Subtype skeletons + signature components (fallback scaffolds already look distinct).
2. Recipes `dense-ops-ledger` vs `dense-ops-floor` under ops kinds.
3. Category-native AI stages in `AiFeatureStage`.
4. Heal only fixes chrome violations; do not flatten subtype skeletons to generic `ops-dashboard`.

## Non-goals

- Full LLM freeform page layouts (reliability stays scaffold-backed).
- Real backend / live market data.
- Storefront/booking redesign in this ship (ops + AI first).

## Success

At a glance: LedgerFlow ≠ trading desk before reading the brand name. AI features feel like product tools.
