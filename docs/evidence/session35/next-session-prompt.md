# Kickoff — take the generation to $0.39, and prove quality held

**The goal this session is cost.** I want a generation to land at
**$0.39 nominal** instead of today's $0.537, and I want evidence that the
screens did not get worse. The 3-minute clock matters to me less than the
money right now — if the wall stays where it is, or even drifts up slightly,
say so plainly and keep going. If it improves, that is a bonus, not the
target.

**Budget: $10.** Bracket every funded step against `ai_usage_events` and
report the running total. Stop and report at **$8** spent, whatever state
you are in — I would rather decide with two thirds of the evidence than
find out afterwards.

**Every generation must be visible on the portal.** `scripts/bakeoff.py`
runs the real customer path since session 35, so every run you make has a
`/studio/<id>`. Put that link next to every number you report. A run I
cannot open is a run I cannot judge.

## Where you are starting

Work on `main` (clean, pushed, suite **288 green**). Use explicit git
pathspecs — parallel sessions share this checkout.

Read first, in this order:

1. `docs/evidence/session35/results.md` — what session 35 landed, and the
   one real customer run (request 90: **$0.797, 254s**, three screens)
2. `docs/evidence/session34/next-session-runbook.md` — amended; its commands
   now run the full pipeline
3. `consultant-service/app/pipeline/images.py` — the candidate and
   regeneration mechanics; this is where the change lands

The cost anatomy that produced this target:
https://claude.ai/code/artifact/b7c9cfa1-d632-4a7d-b057-2f0f4eeac406

## The change, in two parts

### Part 1 — one anchor candidate

`DASHBOARD_CANDIDATES=1`. Today the anchor fans out two composition
variants concurrently and the judge picks; dropping to one saves a
pro-class image, **$0.14578**, every single run.

What it costs me, stated so nobody discovers it later: the anchor's bytes
are the style reference every follow-up screen copies. Removing best-of-two
removes the only quality selection applied to the artifact the rest of the
demo is built from. Across 55 recorded anchors the first variant
(`hero-intelligence`) was approved 92.7% of the time by the judge's own
flag, but only 76.4% under today's enforced floor — so this is a real
one-in-four bet, not a free saving.

**Measure it with an env override first. Do not change the default until
the numbers say so.**

### Part 2 — regenerate on a hard failure, not on a marginal score

Today the regeneration at `images.py:424` fires whenever nothing was
approved. On request 90 that bought a $0.147 anchor re-roll which produced
an 8.7 carrying two confirmed defects and was thrown away — the original
7.9 shipped either way.

Change it to fire only when:

- every candidate errored (**keep this — it is the only recovery from a
  transient provider failure, and concurrent candidates fail together**), or
- the best candidate failed **text-truth**, or
- the best candidate carries a **verifier-confirmed defect**

and not when the only complaint is a score below the floor.

**The consequence I need you to state back to me before you land it:**
triggering a regeneration is the *only* channel by which the enforced 8
floor changes what ships — on a score-only failure, the approval path and
the best-effort fallback select the same image. So after this change,
**DoD line 2's floor clause becomes a logged number rather than a gate.**
That is the same defect session 33 caught in `QA_MIN_SCORE`, arrived at
deliberately this time.

If that trade looks bad once you see it in code, there is a middle path
worth costing: keep the score trigger but only for a *bad* screen (best
candidate below, say, 7.0), so a marginal 7.9 ships and a 6.3 still
re-rolls. Only 3 of 16 recorded regenerations were score-only, so measure
which of the two you are actually choosing between before you spend on it.

## What I want back

### The number, honestly bracketed

Nominal $0.386 is arithmetic. The number I will budget against is the
**realised mean across the golden set**, which includes whatever
regenerations still fire — expect roughly **$0.42–$0.47** at the observed
rate. Report both, and report the spread, not just the mean.

### The quality comparison

Same briefs, both arms, full pipeline, separate labels. For each arm:
screens below 8, screens shipping a confirmed defect, text-truth failures,
and the `/studio/<id>` links so I can look at them myself. The instruments
are already in the path; `scripts/aggregate_run.py <label>` prints the
table.

**Suggested spend, adjust if the early numbers surprise you:**

| step | ~cost |
|---|---|
| 1. one target-config run, to confirm $0.39 on the real path | $0.40 |
| 2. control arm — today's defaults, 4 briefs | $2.40 |
| 3. target arm — the new config, 4 briefs | $1.60 |
| 4. headroom for re-runs and anything you find | $3.00 |

That is ~$7.40 of the $10 with real slack. Do step 1 before steps 2–3 — if
the config does not land near $0.39 on the real path, the arithmetic is
wrong and the A/B is wasted money.

### Fix what you find

If the runs surface defects — and they will — fix them in the pipeline, not
in an output, and land each fix with a pin. Report anything you chose not
to fix and why.

## Traps, all of them paid for already

- **`_env_or` returns the DEFAULT for an empty string.** Setting
  `IMAGE_SIZE_FOLLOWUP=''` is a no-op, not a revert. A whole rung of the
  cost ladder was wrong because of this.
- **Do not parallelise the per-candidate QA loop** at `images.py:365`
  without giving each thread its own session. `qa.py:293`'s "no Session
  crosses a thread" invariant holds *only* because that loop is serial;
  breaking it corrupts the very ledger every number here is measured from.
- **Do not raise the QA thread-pool width to buy speed.** More in-flight
  calls means more of OpenRouter's 429-inside-HTTP-200, an exhausted judge
  retry fails **open** with `approved=true` and `score=None`, and the floor
  is guarded by `score is not None` — so concurrency silently disarms the
  gate.
- **Read spend via `/api/requests/{id}/admin`**, never by opening
  `consultant.db` while the service is running.
- **Never run two bakeoff batches concurrently** — `results.json` is
  rewritten wholesale.
- **Never mix `pipeline: full` and `pipeline: frozen` rows under one
  label.** `aggregate_run.py` warns; do not average past the warning.
- The ad-hoc `bmv-consultant` container on 8002 is still absent from
  `docker-compose.yml` and reports unhealthy because its healthcheck probes
  port 8000. Cosmetic, but it will bite whoever composes it.

## Settled — do not re-litigate, and do not "save money" here

- **2K follow-ups stay.** They killed the collapsed-letterform class
  ("Cilents", "Portfollo", "Highiights") on a recorded same-brief A/B, and
  `tests/test_image_size.py` pins them. +$0.033/image is the cheapest
  quality in the stack.
- **The pro-class anchor stays.** It won the swap-tested pairwise 2–0 with
  one tie; exact UI microtext is the product.
- **Both gates stay on.** The text-truth gate is decided in code and never
  by a judge; the two-stage defect check refuted 16 false claims on the s33
  golden set. Together they are $0.012 of a $0.797 run — they are not the
  cost problem, and turning either off to hit a number is not a cost saving,
  it is a different product.
- **Three screens stay.** Two screens is a cheaper demo, not a cheaper
  generation.
- The cinematic register ships. The QA judge is held fixed while generators
  vary. Watermark on every byte under `/uploads`. Glamour composited in PIL,
  never asked of the image model.

## The thing I actually want to hear about

The reason a generation costs what it does is that we buy six images and
ship three. Knobs move that a little; **first-shot quality moves it a lot** —
every point of first-pass approval deletes a serial ~50s, ~$0.15 re-roll.
If, while you are in there, you can see why the first candidate keeps
missing (JOB 6's charts contradicting their own axes is the standing
suspect), tell me. That is the lever with no quality downside, and it is
the one I would fund next.

Do not push to origin without telling me. Report the running spend as you
go.
