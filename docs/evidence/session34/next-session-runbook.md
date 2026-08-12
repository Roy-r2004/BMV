# Runbook — the three blocked measurements, then JOB 6

> **AMENDED 2026-08-12 (session 35), owner's rule: every generation is a
> customer run.** `scripts/bakeoff.py` no longer replays frozen
> UIDemoSpecs. A cell now submits the brief's intake and calls
> `orchestrator.run` — the same entry point `POST /api/requests` uses — so
> all six text stages execute, the spec is derived live, and the screens
> land under `/uploads` where **every cell is viewable at
> `/studio/<request_id>`**. Three consequences for the commands below:
>
> - **+~$0.018/brief** for the text stages, and the screen count now comes
>   from the plan stage rather than the brief's frozen list.
> - **`golden/briefs-v2` vs `briefs-v3` is no longer a control arm.**
>   ui_spec runs live at whatever prompt version is shipping, so
>   `GOLDEN_BRIEFS_DIR` now only chooses which intake is submitted. Item 2
>   below is rewritten accordingly.
> - **`aggregate_fullset.py` no longer finds anything** for a full run — it
>   globs the frozen output directory. Use
>   `scripts/aggregate_run.py <label>`, which reads both layouts and takes
>   cost from the ledger bakeoff recorded rather than from the SQLite file
>   (the WAL trap). The session-34 script stays as the record of how that
>   session's table was made.
>
> `--frozen-specs` reproduces the old behaviour for one job only: checking a
> session 31-34 cell. It is never the default and its screens do not appear
> at `/studio/<id>`.

Everything below was blocked on 2026-08-12 by the shared OpenRouter key
running out of credits (402 mid-batch; hedgefund spent $0). **The key is
still dead** — a `/studio` run at 07:43 on 2026-08-12 (request 89, "Jeanne
Art") failed with `402 "requires more credits"` on blueprint, technical
plan, ui_spec and all three image calls. The code all landed and is pinned;
these are measurements, one command each. **Top up the key first**, then
bracket every step against `ai_usage_events` as usual. Budget the lot at
~$2.60 single-pass, ~$5 with the 2× image-work rule.

## 1. Complete the control set — hedgefund (~$0.60)

```
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service \
  -e DATABASE_URL=sqlite:////repo/consultant-service/consultant.db \
  -e GOLDEN_BRIEFS_DIR=golden/briefs-v2 \
  --entrypoint sh bmv-consultant-py -c 'python scripts/bakeoff.py --brief hedgefund \
    --anchor-model google/gemini-3-pro-image \
    --followup-model google/gemini-3.1-flash-image --label s34-full'
```

Then aggregate:
```
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service --entrypoint sh \
  bmv-consultant-py -c 'python scripts/aggregate_run.py s34-full'
```
Watch for: s33's hedgefund carried "Portfollo" (follow-up → expect dead
at 2K), a duplicated "Recent Trades" panel, and cards hanging outside the
frame (crop refuses those by geometry — the defect check should catch).

**Note the label.** A full-pipeline hedgefund cell does not complete
`s34-full`'s frozen table — different spec, possibly a different screen
count. Give it a new label (`s35-full`) and re-run the other four briefs
under it if you want a comparable set; `aggregate_run.py` warns rather
than averages if a label mixes the two.

## 2. The v3 title arm — REWRITTEN (~$1.30)

The original plan was a frozen A/B: `briefs-v3` against `briefs-v2` as the
control. Under the full pipeline there is no v2 control — ui_spec always
runs at the shipping prompt version, which is v3. Two honest options:

- **Measure it live** (preferred, and free of extra runs): every full cell
  now fills `ai.title` from the spec stage, and the result page prints the
  AI module under each screen. Success = the kicker on the AI panel reads
  the spec'd label and nothing invented ("HERO INTELLIGENCE", "OPINION" —
  the session-33 class). This is now checkable on every run at
  `/studio/<id>` at no extra cost, and `spec_json` on the row is the
  receipt.
- **Reproduce the designed A/B** with `--frozen-specs` and
  `-e GOLDEN_BRIEFS_DIR=golden/briefs-v3` vs `briefs-v2`, `--label s34-v3`,
  briefs `law` then `retail` (never concurrently — the results.json trap).
  Only worth the money if the live check above shows an invented title.

## 3. The clock, end to end (~$0.60)

```
sh docs/evidence/session34/run_e2e_request.sh
```
Everything is scripted: service container up, a fresh business
("Beacon Physiotherapy") through the public intake, progress polled with
a stopwatch, cost read via /admin (the WAL trap), clean stop. The same
run can be watched through the new `/studio` page (frontend on 5173,
`VITE_CONSULTANT_API_BASE_URL=http://localhost:8002`) — the script stays
the measured instrument; the page is the customer's view of it. The number
that matters: **wall ≤ 180s** on the parallel path with the defect check
on.

Since session 35 a bakeoff cell runs the same orchestrator this script
drives, so its `wall_s` is now a real answer to the clock question too —
the only thing `run_e2e_request.sh` still adds is the HTTP intake and the
progress polling a browser does. The s34 walls of 116–173s no longer
apply: they were frozen replays with no text stages. If the clock misses:
`SECONDARY_CANDIDATES` and the verify pool are the knobs to look at before
touching quality gates.

## 4. JOB 6 — the charts, now with a baseline

The full set shipped exactly three confirmed defects, all
`malformed_data_display` (3 of 12 screens). That is the in-path baseline
JOB 6 must beat. The brief's scoping stands: composite ONE archetype's
chart in PIL over the region the model leaves, side by side against the
model-drawn version, owner's eye decides before any rollout. The spec
already carries exact chart values (`ChartSpec.labels/values`).

## 5. Worth one look while there

- An offline sweep at s33 thoroughness over the s34-full screens — the
  honest apples-to-apples for the "13/15 → ?" defect-rate claim.
- `ai.title` as a text-truth checked string is a candidate GATE
  TIGHTENING: do not add it without its own measured golden-set run
  (the relaxations memory rule).
- The pro anchor's residual letterform risk ("SLB" class): observed once
  in s33, not reproduced since. If it recurs, the fallback is per-string,
  not JOB 4's nav compositing — the instance was a configurator value.
