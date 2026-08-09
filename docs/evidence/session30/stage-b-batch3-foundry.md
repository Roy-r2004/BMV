# Stage B / batch 3 — six more primitives, same pinned commit — session 30

Branch `phase3-stage-a`, on top of B2 (`25a2479`). **Tomorrow's trio still
untouched:** no dependency entered (npm fingerprint stable), `index.css`
byte-identical (silhouette **17/17**), main frozen, tree clean at commit.
Balance probed before starting: still −$0.063 — the trio stays blocked on the
owner top-up, which is what made batch 3 the right work tonight.

## Batch 3 — the foundry ledger reaches 14 rows

All six from `magicuidesign/magicui` at the same pinned MIT commit
(`5543371f`), fetched verbatim per file via the container (GitHub raw at the
sha), rewritten like house code:

| primitive | the rewrite | personalities |
|---|---|---|
| `TextReveal` | ghost/active words are **currentColor mixes** (inherits any section's palette — no black/white pairs, no `dark:`); native scroll scrubs; reduced motion renders the sentence as a plain full-strength paragraph — the statement is content | editorial, nocturne, craft |
| `AnimatedList` | arrivals take ease + travel from `motionIdentity()` instead of a fixed spring — **an ops feed ticks quietly, a retail feed pops**; reduced motion renders the complete list, every item present | dense-ops, warm-service, bold-retail |
| `Marquee` | upstream's Tailwind-config `animate-marquee` keyframes became a **motion-driven frame loop** sharing VelocityScroll's wrap math; pause-on-hover is a ref the loop reads, not `animation-play-state`; vertical mode dropped (no kit consumer); reduced motion = one static strip | bold-retail, craft, warm-service |
| `MagicCard` | border sweep runs **brand→accent token mixes** resting on `--color-border-subtle` (upstream: hardcoded violet/pink + next-themes dark detection — both gone, tokens know the theme); surface is `--color-card`; orb mode dropped; reduced motion = plain resting card | nocturne, bold-retail, warm-service |
| `FlickeringGrid` | every random call became an **index+tick hash and skipped frames replay their missed ticks** — the texture is identical run-to-run at any frame rate; color defaults to the brand token, resolved from computed style (canvas can't read `var()`); reduced motion draws tick zero once | nocturne, bold-retail |
| `Lens` | demo static/fixed-position modes dropped; radius rides `--radius-ui`; reduced motion renders the wrapped content untouched — zoom is a flourish, never the only way to see the image | craft, bold-retail, editorial |

**Deliberately not mined:** `HeroVideoDialog` — generated sites have no real
video assets; a lightbox over a dead URL is a prop, not a feature. Scroll
Progress treatments wait for Lenis (post-trio, dependency).

## New pin

Effects may never smuggle CSS keyframes: `@keyframes` / `animation-name:` /
`animation-play-state:` / bare `animation:` all fail
`test_every_mined_effect_is_manifested_and_motion_safe`. Marquee is the
precedent this pin exists for — the classic temptation is pasting the
upstream keyframes into a config. Worded so prose mentions of
`animation-play-state` (no colon) survive; only real CSS dies.

## Gates

| gate | result |
|---|---|
| tsc | exit 0 |
| Silhouette | **17/17 byte-identical** (motion/effects travel through `site-design.ts` + components; the CSS gate correctly never moves) |
| Full suite | **2,385 / 1 / 0** — **+0 vs B2**, fully accounted: no new test files, the keyframes pin strengthens an existing test function |
| Sweep | **8 killed / 0 survived** (`mutate_session30_b3.py`) — lost provenance row, Math.random re-roll, hardcoded violet, keyframes smuggling, dropped reduced-motion guard, manifested-but-unregistered, registered-but-not-exported, truncated sha |
| Session sweep total | **53 killed / 0 survived** across six scripts |

One sweep iteration: B3-4 first ran as MISCOUNT (anchor quoted with `'`
against a JSX `"` attribute) — anchor corrected, mutation then killed. A
MISCOUNT is a harness defect to fix, never a skip.

## Mid-batch note

A request to reorder the admin navbar / check the contact page arrived and
was retracted by the owner mid-batch ("discard it"); the investigation agent
was stopped before producing conclusions. Nothing from it entered the tree.
