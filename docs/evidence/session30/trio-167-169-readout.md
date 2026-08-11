# Validation trio 167–169 — readout — session 30 (2026-08-10)

Launched from **`main` @ `0f00146`** (the frozen build) per
`session29/TRIO_LAUNCH_RUNBOOK.md`. Pre-flight GO on all eight checks;
behaviour probe confirmed `_terminal_salvage_pass()` ×3 **in the live
process** (restart happened after the checkout, so uvicorn holds main's
code, not the branch's).

## Cost — attributed from the ledger, not the balance

| source | figure |
|---|---|
| Balance bracket | 62.221 → 59.111 = **−$3.110** |
| `ai_usage_events` for 167/168/169 | **$0.920532** (30 + 34 + 32 = 96 calls) |
| All BMV usage logged in the 90-min window | $0.920532 — i.e. the trio and nothing else |

**Our spend is $0.9205**, in line with every prior trio ($0.900, $0.979,
$0.716). The remaining ≈$2.19 of the balance drop belongs to the other
consumer on the shared key — measured independently *before* launch as a
$3.26 drop across 30 minutes while this session spent nothing. Per the
shared-key policy: attribute the delta from the ledger, raise no leak alarm.
Owner cap for the session was $3; **$0.92 used**.

## Outcomes — the merge gate

| run | business | recipe | wall | outcome |
|---|---|---|---|---|
| 167 | Copperline Hardware | bold-retail | 563 s | **ready** |
| 168 | Ridgeline Bike Works (file mode, refimg) | bold-retail | 553 s | **ready** |
| 169 | Kestrel & Fern Bakehouse | craft | 575 s | **withheld** — `pack_copy_shipped` |

**Upstream AppSpec deaths from the session-29 fixed classes: 0.** No run
crashed, none took the safe-fallback path. That is the merge gate, and it is
satisfied. Best trio outcome to date (session 27's was 1 ready of 3).

Wall times 553–575 s sit inside the 560 floor / 600 cap band; the host was
quiet for the window (no pytest container, no sweep).

Revision ladders: 167 accepted on revision 1; **168 took two
`schema_parse_failed` rejections then accepted on revision 3** — the repair
ladder working, not a death (`terminal_reason` read, per the standing rule
that rejected revisions carry heal rows); 169 accepted on revision 1 with 2
heals.

Classification held the owner's rule — a hardware store and a bike shop both
→ `bold-retail`, a bakehouse → `craft`. Nothing defaulted to storefront.

## Session-29 mechanism markers: none fired

Expected and stated as such, not claimed as proof. All three briefs are
`needs_ai: "no"`, so `bind_ai_features_to_app_spec` never runs, and a clean
run never enters a salvage rung. **Fix B and the salvage rungs remain
live-unproven** — they need a `needs_ai: yes` brief in the next trio.

## Per-item photo binding — the run-165 fix, validated

Pexels logs show one query *per catalogue item*, not a pooled search:
`large angle grinder Independent hardware`, `petrol leaf blower vacuum …`,
`professional jigsaw …`. 108 photo/Pexels log lines in the window. This is
the exact failure 165 died on, working.

## Two defects the trio surfaced (both pre-existing on main, neither ours)

1. **`pack_copy_shipped` withheld 169, correctly.** The bakehouse's
   `mock.ts` carries restaurant-pack copy verbatim — `House pasta`,
   `Chef tasting`, `Bar bites`, `Farm partners within 40 miles` — 29
   sentences of it. The gate did its job.
2. **The same leak shipped `ready` in 167.** Copperline Hardware's mock data
   contains `AI-guided consult`, `Member aftercare`, `Follow-up visit` —
   clinic/service plumbing strings in a hardware store — and the run still
   passed, because `pack_copy_shipped` counts sentences against a threshold
   167 stayed under. So the gate is threshold-shaped while the defect is
   categorical: *any* pack plumbing string in shipped data violates
   demo-matches-the-business. 168 was clean on this.

Catalogue survival itself is healthy — 41 / 34 / 24 distinct titles, real and
business-specific (`Concrete Mixer (Electric)`, `Cascade Endurance Gravel`).

## DoD 10

Runs 1–3 of the streak: **2 ready, 1 withheld, 0 deaths.**

---

# Run 170 — Stage A/B validated in production (post-merge)

The trio ran from the frozen `main`, so it validated the session-29 fixes and
nothing of ours. After the merge, one run on merged `main` closes that gap.

**170 · Lantern & Ash · late-night cocktail bar → recipe `nocturne` · 558 s ·
`ready` · $0.375736 (39 calls).** DoD 10 streak run 4.

Classification is the owner's rule holding again: a dim late-opening bar
resolved to `nocturne`, not to a storefront default.

Verified in the shipped workspace (`/app/data/preview-apps/170`):

| claim | evidence |
|---|---|
| A1's single resolution ships per workspace | `src/lib/site-design.ts` **present** |
| SiteSpec.design is v1.1 | `"version": "1.1"`, `"recipe_id": "nocturne"` |
| 3.10 identity is real, not a default | `"identity": "nocturne-drift"`, ease `[0.16, 1.0, 0.3, 1.0]` — the authored temperament, not the `entrance-only` fallback |
| Both engines consume it in the shipped app | `motionIdentity` × 2 in `presets.tsx`, × 2 in `anime.ts` |
| The arsenal ships | 19 files in `src/ui/effects/` (18 primitives + barrel) |
| **The arsenal is inert** | **0 generated pages reference any foundry primitive** — the reachability gap, confirmed empirically in production exactly as the catalogue read predicted |

So Stage A is a proven no-op on live generation, 3.10 is proven live
end-to-end, and Stage B's mining is proven *shipped but unreachable*. That
last row is the honest state of the foundry and the next thing worth fixing.

## Session cost, final

| item | ledger |
|---|---|
| Trio 167–169 | $0.920532 (96 calls) |
| Run 170 | $0.375736 (39 calls) |
| **Total** | **$1.296268 (135 calls)** |

Owner cap $3 — **$1.30 used, 43%.**
