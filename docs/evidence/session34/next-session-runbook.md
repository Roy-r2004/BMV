# Runbook — the three blocked measurements, then JOB 6

Everything below was blocked on 2026-08-12 by the shared OpenRouter key
running out of credits (402 mid-batch; hedgefund spent $0). The code all
landed and is pinned; these are measurements, one command each. **Top up
the key first**, then bracket every step against `ai_usage_events` as
usual. Budget the lot at ~$2.50 single-pass, ~$5 with the 2× image-work
rule.

## 1. Complete the control set — hedgefund (~$0.60)

```
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service \
  -e DATABASE_URL=sqlite:////repo/consultant-service/consultant.db \
  -e GOLDEN_BRIEFS_DIR=golden/briefs-v2 \
  --entrypoint sh bmv-consultant-py -c 'python scripts/bakeoff.py --brief hedgefund \
    --anchor-model google/gemini-3-pro-image \
    --followup-model google/gemini-3.1-flash-image --label s34-full'
```

Then re-run the aggregate for the 15-screen table:
```
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service --entrypoint sh \
  bmv-consultant-py -c 'python /repo/docs/evidence/session34/aggregate_fullset.py s34-full'
```
Watch for: s33's hedgefund carried "Portfollo" (follow-up → expect dead
at 2K), a duplicated "Recent Trades" panel, and cards hanging outside the
frame (crop refuses those by geometry — the defect check should catch).

## 2. The v3 title arm — law + retail (~$1.30)

Same command with `-e GOLDEN_BRIEFS_DIR=golden/briefs-v3` and
`--label s34-v3`, briefs `law` then `retail` (never concurrently — the
results.json trap). These two briefs invented four of the six s33 module
titles. Success = the AI panel's kicker reads the spec'd label
("Lead Prioritization", "Next Best Action", "Smart Reorder", "Churn
Risk") and nothing else; compare against the s34-full v2 run of the same
briefs, which is the control.

## 3. The clock, end to end (~$0.60)

```
sh docs/evidence/session34/run_e2e_request.sh
```
Everything is scripted: service container up, a fresh business
("Beacon Physiotherapy") through the public intake, progress polled with
a stopwatch, cost read via /admin (the WAL trap), clean stop. The number
that matters: **wall ≤ 180s** on the parallel path with the defect check
on. Bakeoff walls of 116–173s per brief (which include text stages'
absence but also sequential-candidate QA) say it should fit; it is not
measured until this runs. If it misses: `SECONDARY_CANDIDATES` and the
verify pool are the knobs to look at before touching quality gates.

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
