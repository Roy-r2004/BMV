# Stage B / batch 4 — the last Lenis-free primitives — session 30

Branch `phase3-stage-a`, on top of the 3.10 wiring (`b335a1c`). Owner
directive: "finish them." With this batch, **every Stage B item that can
land without a new dependency has landed.** Trio preconditions intact: no
dependency entered, silhouette **17/17**, main frozen.

## Batch 4 — foundry ledger reaches 18 rows

| primitive | the rewrite | personalities |
|---|---|---|
| `ShimmerButton` | **NOT grafted into core/Button** — ops surfaces keep a chrome-free Button by the restraint rule; the standalone composes only where a marketing CTA wants it. Upstream's two config keyframes + container queries became one motion-driven sweep; black/white → brand/card tokens; radius rides `--radius-ui`; reduced motion = the resting button, same size/color/label | bold-retail, warm-service, nocturne |
| `AnimatedGridPattern` | square scatter from an **id+cycle hash** (upstream re-rolled Math random per cycle); grid lines ride `--color-border-subtle`, breathing cells ride the brand token; reduced motion = the bare grid | editorial, dense-ops, craft |
| `ScrollProgress` | violet/pink/peach hex gradient → **brand→accent tokens**; native scroll (the roadmap wanted this "with Lenis" — it needs nothing); reduced motion renders nothing, the scrollbar already tells the truth | editorial, nocturne |
| `ProgressiveBlur` | static backdrop-filter stack; dead `children` prop + leftover class dropped; layer construction deduplicated; rgba(0,0,0,x) stops are mask alpha geometry, not palette | nocturne, editorial, bold-retail |

The HANDOFF's earlier sketch said "Shimmer → fold into core/Button"; the
graft was **rejected during implementation** — Button is consumed by every
surface including ops, and motion chrome in a core component breaks the
demo-matches-the-business restraint rule. The standalone gives marketing
pages the same capability at zero ops cost. (That sketch was a working note,
not an owner ruling.)

## Gates

| gate | result |
|---|---|
| tsc | exit 0 |
| vite build smoke | clean |
| Silhouette | **17/17 byte-identical** |
| Full suite | **2,392 / 1 / 0** — +0: file-scanning pins auto-cover the four new files |
| Sweep | **6 killed / 0 survived** (`mutate_session30_b4_mining.py`) — lost row, re-randomized scatter, hex gradient, dropped motion guard, unregistered, un-exported |
| Session sweep total | **66 killed / 0 survived** across eight scripts |

## Stage B remainder (all blocked, none by code)

- **Lenis (3.8)** — adds a dependency; illegal until the trio's clocks are
  banked. First post-merge move.
- **Reveal-shape switching** (the visual half of temperament: blur/slide
  variants per `reveal` value) — needs the screenshot/critic loop; post-trio.
- **3.11 perf gate** — CDP tracing on the headless scroll driver, budgets
  per recipe wired into `quality_gate.py` + DoD9. A ~1-week project by the
  roadmap's own estimate; not tonight's work, and honestly better built
  AFTER Lenis lands so the traces measure the real scroll engine.
