# 3.10 consumption half — both motion engines wired to the identity — session 30

Branch `phase3-stage-a`, on top of B3 (`e35719c`). Owner directive: "finish
them" — this is the piece that makes the eight temperaments actually drive
page motion. Trio preconditions still intact: no dependency entered,
`index.css` byte-identical (silhouette **17/17** — motion travels through
TS, never CSS), main frozen.

## What changed

Every timing constant in the two motion engines now derives from
`motionIdentity()` as a **ratio off the legacy base** (travel 18px, stagger
90ms — which are exactly `DEFAULT_IDENTITY`'s values, pinned):

| engine | before | after |
|---|---|---|
| `presets.tsx` (motion/react) | ease `[0.22,1,0.36,1]`, staggerChildren `0.09`, item y `18`, hero step `0.12` — all literals | `identity.ease`, `staggerMs/1000`, `18 * travel`, `staggerMs/750` |
| `anime.ts` (anime.js) | ease `'out(3)'`, defaults y `42/36/56`, stagger `110`, durations `1100/720/920` | ease gated: `motionIsAuthored() ? cubicBezier(identity) : 'out(3)'`; every default scaled by `motionRhythm` (travel/pace/tempo) |
| `AnimeChrome.tsx` call sites | hero delay step `160`, stagger `120`, y `48/40` — literals overriding defaults | all scaled by `motionRhythm.pace`/`.travel`/`.tempo` |

**Bare-recipe parity is arithmetic, not hope:** the accessor's fallback
equals the legacy constants, and every ratio divides by that base — so an
un-recipe'd page computes `90/1000 = 0.09`, `18 × 1 = 18`, `90/750 = 0.12`:
byte-for-byte the old motion. The anime ease keeps its un-authored voice
(`'out(3)'`) via `motionIsAuthored()` — the one place ratios couldn't prove
parity, so it's gated instead.

What the six families feel like now: ops floors enter in 6px hops at 35ms
with durations clamped short; nocturne drifts 22px at 130ms, 1.4× slower;
retail punches 26px at a hard bezier. `tempo` is clamped to [0.45, 1.4] in
both engines — jank protection until 3.11 measures for real.

**Deliberately NOT done tonight:** reveal-SHAPE switching (blur/slide
variants per `reveal` name). That changes what entrances *are*, not just
their rhythm, and it belongs to the post-trio screenshot/critic session.
The `reveal` field keeps consumers waiting for it.

## Gates

| gate | result |
|---|---|
| tsc | exit 0 |
| vite build smoke | clean, 135ms (no dependency change — node_modules untouched) |
| Silhouette | **17/17 byte-identical** |
| Full suite | **2,392 / 1 / 0** — +7 vs B3, exactly accounted: 6 wiring pins + 1 collected-files row |
| Sweep | **7 killed / 0 survived** (`mutate_session30_b4_wiring.py`) — re-hardcoded stagger/ease/delay-step, dropped ease gate, descaled call sites, drifted ratio base, dropped tempo clamp |
| Session sweep total | **60 killed / 0 survived** across seven scripts |
