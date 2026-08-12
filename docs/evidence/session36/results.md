# Session 36 — the $0.39 config, measured against today's, on the customer path

*2026-08-12, `main`. Nine funded requests, **$5.99** ledger-attributed of a
$10 budget ($8 stop line, never reached). Suite 288 → 305. Every run is a
full customer run and every link below was verified serving 200 before this
file was written.*

## The number

**Nominal at the target config is confirmed: $0.390** (arithmetic said
$0.386; the $0.004 gap is per-brief text-stage variance). Measured two
independent ways: request 96 landed at **$0.3849 realised** with zero
regenerations, and stripping the regeneration line-items from probe 91's
ledger leaves $0.3901.

| arm | config | mean/brief | spread | walls |
|---|---|---|---|---|
| control (`s36-control`) | 2 anchor candidates, old regen policy | **$0.7093** | $0.535–0.917 | 194–436s, mean 291s |
| target (`s36-target`) | 1 anchor candidate, hard-fail+bad-screen regen | **$0.6255** | $0.385–0.756 | 184–360s, mean 268s |

The realised mean moved **−11.8%** while the nominal moved −27%. The gap is
regeneration tail, now entirely hard-failure-driven — and the session found
and fixed the two defect classes that *were* most of that tail (below), so
the realised mean should close toward the owner's $0.42–0.47 projection.
**That claim is a projection, not a measurement**: n=4 per arm with wide
spread. One more 4-brief target batch (~$1.60–2.50) is the confirmation
gate before `DASHBOARD_CANDIDATES=1` becomes the shipped default. The
default is unchanged this session and `test_the_shipped_anchor_candidate_count_is_two`
still pins 2 — the brief's rule was "not until the numbers say so", and
n=4 says *probably*, not *so*.

Runs, all of them:

| run | request | cost | wall | note |
|---|---|---|---|---|
| probe dental, target config | [/studio/91](http://localhost:8002/studio/91) | $0.6517 | 231s | nominal $0.390 after stripping 2 regens |
| control hedgefund | [/studio/92](http://localhost:8002/studio/92) | $0.6978 | 287s | score-only anchor regen, 7.5→7.8 shipped |
| control law | [/studio/93](http://localhost:8002/studio/93) | $0.9171 | 436s | brand-variant spec: 3 text regens, all lost |
| control salon | [/studio/94](http://localhost:8002/studio/94) | $0.5348 | 194s | clean nominal run, $0.537 projection ±$0.003 |
| control retail | [/studio/95](http://localhost:8002/studio/95) | $0.6876 | 247s | brand-variant spec again ("Northgate Roastery") |
| target hedgefund | [/studio/96](http://localhost:8002/studio/96) | $0.3849 | 184s | **the target number, hit live**; 7.0 shipped logged |
| target law | [/studio/97](http://localhost:8002/studio/97) | $0.6090 | 242s | two 4.5-scoring follow-ups re-rolled to 7.8s — policy correct |
| target salon | [/studio/98](http://localhost:8002/studio/98) | $0.7559 | 284s | defect-heavy roll; every regen legitimately triggered |
| target retail | [/studio/99](http://localhost:8002/studio/99) | $0.7520 | 360s | 6.8 anchor re-rolled and lost; ships 6.8 (same under old policy) |

**The clock, said plainly:** the wall did not get worse (mean 291s → 268s)
and it is still nowhere near the 180s DoD line under the full pipeline.
Untouched this session per the owner's instruction that cost was the
target.

## Quality, both arms (aggregate_run, full tables in `results.json`)

| | control | target |
|---|---|---|
| screens below 8 | 2 | **5** (7.0, 7.8, 7.9, 7.8, 6.8) |
| shipped with confirmed defect | 0 | **3** |
| text-truth failures | 4 | 0 |

Honest attribution, because the raw table overstates the config's guilt:

- The five below-8 ships are the regeneration policy doing what the owner
  approved: marginal screens (7.0–7.9) ship logged instead of buying
  ~$0.145 re-rolls that three consecutive runs (90, 91, 92) showed mostly
  change nothing. The 6.8 (request 99) is below the 7.0 floor — it *did*
  buy its re-roll, which lost on rank; the old policy ships the same 6.8.
- Of the three defect ships, two are on **follow-up screens whose config is
  identical in both arms** (law and salon analytics) — that is dice, the
  spec/model drawing defect-prone content, not the candidate cut. One
  (salon dashboard, duplicated button) is plausibly the lost second anchor
  candidate: with two candidates there is a second chance at a clean
  anchor. That is the real quality price of Part 1 and it showed up once
  in four runs.
- Control's 4 text-truth failures vs target's 0 is entirely spec dice
  (which arm's ui_spec roll invented a brand variant), not policy.

## DoD line 2, as landed

Regeneration was the only channel by which the enforced 8 floor changed
what ships. With `QA_REGEN_SCORE_FLOOR=7` (owner-approved, middle path):
**between 7.0 and 8.0 the floor is a logged number, not a gate** — request
96's customers screen shipped at exactly 7.0 with nothing spent. Below 7.0
the floor still buys one re-roll (requests 97's two 4.5s → both 7.8s).
The same class of gap session 33 closed in `QA_MIN_SCORE`, arrived at
deliberately this time, priced by three recorded runs. Pinned in
`test_qa_and_selection.py`; the consequence is stated in `config.py` where
the knob lives. ROADMAP's DoD wording is the owner's to amend.

## Defects found by the runs, fixed in the pipeline

1. **Bakeoff runs were invisible at /studio** (`d1a5866`). The shared
   SQLite file over the bind mount: a long-lived pooled connection's WAL
   view goes stale across containers — /studio/91 and /92 404'd while a
   fresh connection inside the same container read both. Session 35's
   "every cell viewable" rule had never been verified live for a
   bakeoff-created request. Fix: NullPool for sqlite + bakeoff checkpoints
   the WAL on exit. Verified in production mid-session: requests 94–99
   all served with no restart.
2. **ui_spec invents brand variants the gate then rejects** (`966da66`).
   Every recorded shipped text-truth failure in the corpus — "by hartwell
   & grey" (93), "northgate roastery" (95, 12), "lumière studio os" (22) —
   was the spec ordering a brand paraphrase drawn while the gate demanded
   the exact name; the model obeyed the spec every time, which is why the
   re-rolls all failed too (law control: ~$0.36 burned in one run).
   The deterministic half (legal-suffix truncation) is restored in code;
   the paraphrase half is a template constraint, deliberately NOT
   code-enforced: any rule fuzzy enough to catch "Northgate Roastery"
   also mangles "Northgate RoasterFlow AI". The gate stays the measure of
   whether the constraint works.
3. **The defect verifier confirms arithmetic its own reason refutes**
   (`966da66`). Request 84: ticks 0,15,30,45,60,75,90 claimed "not evenly
   stepped", verifier confirmed while restating the even 15-step; the
   false confirm bought a regeneration. Evenly-steppedness of quoted
   values is now checked in code, narrowly: "stepped" claims only, never
   geometry, and a non-numeric tick ('6+', request 87's real defect)
   keeps its claim.

## The first-shot lever (the thing the owner asked to hear about)

Measured across 112 corpus screens: **17% of first candidates fail, and
15 of the 19 failures are hard** (8 defect, 7 text-truth), not score.
Analytics screens — the chart-heavy ones — miss 7/35, all hard.

- The **text-truth half is now addressed**: all 7 of those corpus failures
  were the brand-variant class fixed above. If the fix holds, first-pass
  text approval goes to ~100% and its regen tail disappears.
- The **defect half is the charts**, and the mechanism is now precise:
  `_chart_block` computes trend/peak annotations in code "so the model has
  concrete text to render instead of inventing one" — then demands
  "polished axis tick labels" **without providing tick values**. The model
  must invent a y-scale, i.e. do arithmetic, its weakest skill (the
  prompt's own line 393 says so). Confirmed axis defects this session:
  4800→4500→4100→3600 (90), 18200→19000→21000→22000→23800 (98), '6+' at a
  unit interval (87).

  **Proposed, not landed:** compute nice round ticks in code and hand them
  to the model as literal strings to copy — the exact pattern the
  annotations already use. Not landed because it is an image-prompt change
  and those get their own measured A/B on this repo (art packs, register
  and 2K all did); the scaffolding-renders-as-UI risk needs eyes on real
  output. It composes with, not replaces, JOB 6 (PIL-composited charts),
  which also fixes what no prompt can: marker-to-tick alignment (87's
  misaligned Wk 1/Wk 6).

## Chose not to fix, and why

- **Chart ticks in the prompt** — above; next session's A/B, ~$1 per arm.
- **Code-enforcing the brand-paraphrase constraint** — blast radius; the
  template constraint is measured by the gate at zero added cost.
- **The `bmv-consultant` compose wart** — still an ad-hoc container with a
  wrong-port healthcheck; unchanged, still cosmetic, still worth an ops
  half-hour some session.
- **Request 99's shipped 6.8** — not a policy casualty (old policy ships
  it too). It is the strongest single argument for JOB 6: its analytics
  anchor failed on chart quality twice.

## Ledger notes

Spend was bracketed per request via `/api/requests/<id>/admin` (verified
against bakeoff's own ledger print to the cent on request 94). The
OpenRouter key is shared; balance deltas were not used for attribution.
Two OpenRouter 429-inside-HTTP-200s and two SSL transport errors were
absorbed by the existing retry ladders; zero image calls failed across all
nine runs.

Commits this session (none pushed): `d1a5866` (visibility), `daac33d`
(regeneration policy), `966da66` (gate contradictions). `main` was already
one commit ahead of origin at session start (`454db9f`, the session-35
brief).
