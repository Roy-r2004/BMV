# Stage B / batch 2 + motion identity (3.10, data half) — session 30

Branch `phase3-stage-a`, on top of B1 (`35bb7dc`). **Tomorrow's trio is
untouched:** no dependency entered (npm fingerprint stable), `index.css`
byte-identical (silhouette 17/17 — motion identity travels through
`site-design.ts`, which the CSS gate correctly does not hash), main frozen,
tree clean.

## Motion identity — each recipe now has a temperament

Authored per recipe in `design_recipes.RECIPES` (3.10's data), resolved by
`resolve_site_design` (SITE_DESIGN_VERSION 1.0 → 1.1), emitted per workspace,
consumed via the new guarded accessor `src/lib/motion-identity.ts`:

| family | identity | ease | stagger | travel | reveal |
|---|---|---|---|---|---|
| editorial | editorial-calm | 0.22,1,0.36,1 | 110 ms | 18px | fade-up |
| dense-ops | ops-utility | 0.4,0,0.2,1 | 45 ms | 8px | fade |
| · ledger | ops-ledger-paper | same | 55 ms | 10px | fade |
| · floor | ops-floor-instant | same | 35 ms | 6px | fade |
| warm-service | warm-rise | 0.34,1.3,0.64,1 | 90 ms | 16px | rise |
| bold-retail | retail-punch | 0.85,0,0.15,1 | 60 ms | 26px | slide-up |
| nocturne | nocturne-drift | 0.16,1,0.3,1 | 130 ms | 22px | blur-fade |
| craft | craft-settle | 0.25,1,0.5,1 | 100 ms | 14px | fade-up |

Pinned, not aspirational: **no two families share an identity** (the Phase 3
DoD's motion-distinctness seed) and **every ops stagger < every marketing
stagger** (the owner's restraint rule, as an assertion). Bare/unknown recipes
keep the `entrance-only` fallback with null values; the accessor validates
every field (4-finite-number ease, positive stagger) and falls back to the
kit's long-standing entrance constants. Wiring `presets.tsx`/`anime.ts`
onto the identity — which changes every existing page's entrance motion —
is deliberately deferred to the post-trio session with the screenshot/critic
loop available.

## Batch 2 — five more primitives, same pinned commit (`5543371f`)

| primitive | the rewrite | personalities |
|---|---|---|
| `NumberTicker` | color inherits caller tokens (upstream forced black/white); reduced motion shows the final value instantly — a stat is content | dense-ops, bold-retail, editorial |
| `VelocityScroll` | upstream's container/row/context family condensed to one component; scroll-velocity-reactive kinetic marquee on NATIVE scroll (no Lenis); reduced motion = single static row | bold-retail, nocturne |
| `AuroraText` | default stops are brand/accent mixes, never upstream's fixed pink/violet; config keyframes → motion sweep (no new CSS); reduced motion keeps the gradient, static | nocturne, warm-service, bold-retail |
| `DotPattern` | color rides `--color-border-subtle`; glow delays SEEDED by index — the screenshot critic sees the same frame twice; ResizeObserver, static under reduced motion | editorial, craft, dense-ops |
| `AvatarCircles` | borders on `--color-card`, chip on brand tokens; upstream's dead `href=""` anchors removed; images through `KitImage` | warm-service, editorial, craft |

`WordRotate` and `AnimatedShinyText` (batch 1) now take their easing from
`motionIdentity()` — the identity has real consumers from day one.

## Gates

| gate | result |
|---|---|
| tsc | exit 0 |
| Silhouette | **17/17 byte-identical** |
| Full suite | **2,385 / 1 / 0** (+2 vs B1: the motion-identity pin and the accessor pin) |
| Sweep | **7 killed / 0 survived** (`mutate_session30_b2.py`) — shared identity, broken ops restraint, resolution bypass, unvalidated ease, `Math.random` smuggling, lost provenance row, unregistered manifest row |
| New discipline pins | effects may never call `Math.random` (determinism for the visual critic — the pin caught its own first violation: a docstring); motion-safety required exactly where `motion/react` is imported; `motionIdentity()` must keep ≥2 real consumers |

## Foundry ledger after batch 2

8 primitives mined, 8 provenance rows, all at one pinned MIT commit;
`ATTRIBUTIONS.md` regenerated. Tier A remaining for batch 3: Text Reveal,
Scroll Progress treatments (want Lenis), Shimmer Button variants (fold into
`core/Button`), Hero Video Dialog, Lens, Animated List, Flickering Grid,
Animated Grid Pattern, Progressive Blur + Magic Card + Marquee grafts.
