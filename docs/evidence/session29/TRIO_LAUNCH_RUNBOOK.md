# Validation trio — launch runbook (session 29 preflight)

Everything below was executed or verified on 2026-08-09, **before** the top-up.
The trio validates the nine session-29 mechanisms and starts Phase 2 DoD 10's
streak. **The code is frozen at the launch commit — do not land anything
between top-up and launch.**

## Preflight — executed, all green

| check | result |
|---|---|
| Live config (read from the running process, not files) | `APPSPEC_MODE=on`, fallback disabled, `MAX_CALLS=8`, repair attempts 3, schema repairs 1, heals 4, downstream reserve 280 s, `APPSPEC_MODEL=gemini-2.5-flash`, transport rung `claude-haiku-4.5`, `SEED_MODEL=gemini-2.5-flash` |
| API keys | OpenRouter set; **Pexels set** (the per-item photo path needs it — without it the path degrades silently to the pooled search and the 165 read-out is void) |
| Per-item photo search bounded | `_ITEM_QUERY_BUDGET_SECONDS=20`, `_MAX_ITEM_QUERIES=16` — a sick index costs ≤ ~1 timeout, never the 128 s worst case |
| Shared npm cache | warm — `shared_npm_root()` resolves and `vite` is ready (cold `npm ci` inside the clock voided trios before) |
| API health | `:8001` mapped, health endpoint 200, containers healthy, 122 Gi disk free |
| Playwright | importable, chromium-1228 present (screenshot/critic path alive) |
| Reference image | staged at `docs/evidence/session27/refimg/bakery-ref.jpg` (request 160's exact upload, so the file-mode variable stays controlled) |
| Launcher | `docs/evidence/session27/launch_trio.py` — three briefs, three industries set explicitly, simultaneous start (threads, no stagger), posts to `TRIO_BASE` default `127.0.0.1:8001` |
| Readout | `readout_validation_trio.py` dry-run verified against 163 (crash), 165 (withheld), 166 (ready) — all three outcome shapes render correctly |
| Suite / sweeps at freeze | 2,337 passed / 1 skipped; sweeps 19/0 + 11/0 |

## Launch sequence

1. **Top up.** Then `docker cp` the balance probe and record the number
   (`scratchpad/balance_probe.py` pattern — or any credits read). Confirm the
   top-up with **one cheap call** before the trio (request 89's lesson: a
   mid-run empty account looks exactly like defect 1.12).
2. **Restart `bmv-api` and prove behavior, not presence** (uvicorn holds old
   modules; `docker exec python` reads the mount fresh and will lie to you).
   The probe used at freeze: fragment guard booleans, binder re-trace,
   salvage action string, `if _terminal_salvage_pass():` ×3.
3. **Quiet the host.** No pytest container, no mutation sweep, no second trio
   in the window (trio 1 is timing-invalid for exactly this).
4. Launch: `cd docs/evidence/session27 && python3 launch_trio.py`
   (refimg resolves by default; set `TRIO_BASE` only if the port moved).
5. **Bracket the balance** immediately after completion — shared key, only
   the delta is ours.

## Read, in order (each has a script or a query — no sampling)

1. `python3 docs/evidence/session29/readout_validation_trio.py <id1> <id2> <id3>`
   — outcomes (upstream death vs withheld vs ready — DoD 10's split), AppSpec
   revisions + terminal reasons, session-29 mechanism markers in
   `heal_actions`, ask health by writer/finish_reason.
2. Catalogue survival: `check_catalogue_survival.py` (titles + plumbing
   markers, both counted — never the 900-char window).
3. Per-item binding: `docker logs bmv-api | grep -iE "photo|pexels"` — expect
   per-item queries in the log and, on the bakery brief, cake titles bound to
   cake photographs (165's exact failure). The visual critic seeing NO
   subject mismatch on the cake pages is the pass signal.
4. Clock rows: wall seconds from the readout vs the 560 floor / 600 cap —
   only valid if the host stayed quiet.

## What this trio CAN and CANNOT validate

- **Can:** the seed chain (again), per-item photo correspondence, zero
  AppSpec deaths from every fixed class, the clock under the new code, DoD
  10 streak runs 1-3.
- **Cannot:** the AI-hub binder fixes (adoption, re-trace) and most salvage
  rungs — **all three briefs are `needs_ai: "no"`**, so `bind_ai_features_to_
  app_spec` never runs, and a clean run never enters a salvage. Absence of
  markers in `heal_actions` is therefore EXPECTED, not evidence of anything.
  The binder fixes get their live test on the first `needs_ai: yes` brief
  (129-144 corpus shape); keep the briefs controlled this trio, add an
  AI-features brief to the next one.

## Abort criteria

- Balance probe shows the top-up did not land → do not launch.
- Any run's first log entries show a cold npm install → the clock rows are
  void for that run; finish the trio anyway (outcome rows still count).
- Host accidentally ran a sweep in the window → clock rows void, outcomes
  stand (trio 1 precedent).
