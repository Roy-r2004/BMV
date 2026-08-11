# Pipeline review sweep — the non-AppSpec stages, before the validation trio

Session 29, 2026-08-09. Read-only sweep of every stage OUTSIDE the freshly
hardened AppSpec/photo paths, hunting trio-wasters. **Ruling for this trio: no
code changes.** Every finding below is pre-existing behavior the last eight
funded runs already carried — changing any of it now would contaminate the
controlled comparison the trio exists to make. They are the post-trio backlog,
ranked. Two environmental checks were re-verified green in the execution
container (`typescript.js` present, npm root warm at fingerprint
`f87d5d5148156fb2`).

## Would void a trio (environmental / structural)

1. **`npm_shared.py:118` — the npm install lock has no timeout.** The one
   `contended_lock` call site with no `timeout=`; a cold shared root means two
   of three simultaneous runs block up to 600 s with the deadline ticking, and
   the cache-hit short-circuit is *inside* the lock. Mitigated for this trio:
   root verified warm; the code freeze keeps the fingerprint stable. Backlog:
   pass a timeout + move the `_vite_ready` check outside the lock.
2. **`codegen/mock.py:117-126` — the seed validator fails closed, silently,
   on a missing toolchain.** No node / no `typescript.js` → every seed answer
   recorded as `UNUSABLE_REJECTED` (a *model* failure) on all three chain
   links, plumbing mock kept, then `pack_copy_shipped` withholds the run.
   One missing file = three withheld previews wearing model-failure labels.
   Verified present locally; **Render deploys only test for `package.json`**
   (`render.yaml:20-21`) — this WILL fire on a Render trio. Backlog: log +
   degradation marker + resolve the compiler like `typecheck.py:401` does.
3. **`fix_agent.py:173-203` + `quality_repair.py:368-406` — one "fix attempt"
   can be 720 s of chained model asks** (3 models × 120 s × primary+retry),
   budget-checked only at the top of each attempt; the quality-repair chain
   has no runway floor at all (contrast `mock.py`'s 70 s floor). Clamped by
   `ask_budget_seconds()` so it cannot cross the deadline — but it can eat
   the entire remainder in one place. Backlog: runway floor between links,
   mirroring the seed chain.
4. **`build_phase.py:388-484` — post-fix-loop ladders (regen, stub, nuclear)
   have no clock**; up to five uninterruptible 300 s vite builds can run past
   the 540 s mark. Backlog: deadline check between rounds.

## Would skew a number (read these when interpreting the trio)

5. **`fix_agent.py:148` — `_FAILED_FIX_MODELS` is process-global.** The first
   run to see a model time out disables it for runs 2 and 3; three runs may
   silently repair on different models. The only trace is the log line
   `"fix agent skipping %s — already failed this process"` — **grep for it in
   the readout** before comparing repair behavior across the trio. (All prior
   trios carried this too, so the comparison stays apples-to-apples.)
6. **`finalize.py:410` — the remeasure critic path skips the elective gate**
   and can leave repaired pages `unmeasured` (WARN by default) while the run
   ships `ready`. **Readout check: `_bmv_visual_critique.json` →
   `unmeasured` list on any run that took visual repairs.**
7. **`orchestrator.py:96-103, 190-195` — silent swallows**: reference intake
   and visual-demo generation fall back with no log/marker; a trio could run
   on the fallback theme invisibly. **Readout check: `visual_demo_json`
   carries a real theme, not the generic fallback.**
8. **Architect chain (3×120 s) and blueprint ladder (3×120 s) have no runway
   floor between links**; codegen's `max_fix_seconds` is computed once and
   spent twice (`build_phase.py:357` and `:198`); whole-page serial recovery
   (`codegen_phase.py:295-316`) has no clock. All pre-existing; backlog.

## Checked, safe (ground covered — do not re-derive)

`apply_workspace_guards` is deterministic/local (grep-verified, zero network);
every provider ask is wall-clock bounded incl. backoff sleeps; the
whole-generation retry is runway-gated and cannot mint a fresh budget;
`consume_stage_call` is request-scoped with refunds; the quality-gate AI loop
is elective-gated and self-terminating; the seed failover has its 70 s floor
and honest markers; the new import-token rejection cannot false-positive on
prose ("we import our beans" tokenizes as a string literal); dist backup
lives outside the workspace tree; screenshot contention is bounded and
published per-run (`blocked_seconds` — the first number to read if a trio
member degrades).

**One deploy-config note worth keeping:** under `render.yaml` the seed chain
collapses to ONE link (`SEED_MODEL` unset, architect/app models both
gemini-2.5-flash) and the compiler check (finding 2) is untested. A Render
trio is a different experiment from a local one.
