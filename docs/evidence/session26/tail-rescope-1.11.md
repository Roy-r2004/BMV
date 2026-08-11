# 1.11 — the post-deadline reserve, re-measured on the current corpus

Session 26, 2026-08-08. Offline, **$0**, read-only.
`backend/scripts/measure/tail.py 129 132 135 140 141 142 144 145`.

1.11 is the last open engineering item in Phase 1. It has been aimed at the wrong target
twice. Before writing a third attempt, the tail was re-decomposed on runs the row has never
seen — the row's numbers all come from trios 2-3 (requests 77-82).

**First correction: the roadmap says `tail.py` "cannot see it without being parameterized
past its hardcoded run list."** That was fixed at some point and never written back — the
script takes a trio key *or* explicit run ids, and refuses trio 6 by name because it is void
on credits. No tooling work was needed.

## The measurement

| run | tail s | AI in tail | non-AI | AI % |
|---|---|---|---|---|
| 129 | 19.0 | 1.2 | 17.8 | 6 % |
| 132 | 19.0 | 0.0 | 19.0 | 0 % |
| 135 | 13.0 | 0.1 | 12.9 | 1 % |
| 140 | 12.0 | 0.1 | 11.9 | 1 % |
| 141 | 24.0 | 0.1 | 23.9 | 0 % |
| 142 | 17.0 | 0.1 | 16.9 | 0 % |
| 144 | 12.0 | 0.1 | 11.9 | 1 % |
| 145 | 29.0 | 1.2 | 27.8 | 4 % |
| **all** | **145.0** | **3.0** | **142.0** | **2 %** |

Against the nine-run baseline the row was written from:

| | baseline (74-82) | now (129-145) |
|---|---|---|
| tail, total | 382 s over 9 runs | **145 s over 8 runs** |
| tail, per run | 42.4 s | **18.1 s** (max 29.0) |
| AI share of tail | 33 % | **2 %** |

## What this kills

**The AI half of 1.11's premise is empirically dead.** The row says *"the gate, the AI repair
and finalize all run past the deadline and nothing bounds them."* Bounding every AI call in
the tail across these eight runs would recover **3.0 seconds total** — 0.4 s a run. There is
no version of that work worth doing.

**`RESERVE_SECONDS = 60` is now over-sized, not under-sized.** The worst observed tail is
29.0 s and the mean is 18.1 s. The reserve is ~2× the worst case and ~3× the mean. The row
was filed when the reserve was *smaller than* what ran inside it; that is no longer true.

## What it does not settle, and this is the whole remaining risk

**Every one of these eight runs recorded `contention: {npm_install: 0.0,
screenshot_session: 0.0}`.** They never collided with anything. So the measurement above is
serial-run evidence and says nothing about the case that actually broke this row: under trio
2's three-way concurrency, `_SESSION_LOCK` queueing added **16.9 s (77), 35.9 s (78) and
16.7 s (79)** to the tail, and request 78's entire overrun was the block — subtract it and
it lands within 0.5 s of its deadline.

That is the same missing evidence as the ≤ 600 s DoD row: **contention has been 0.0 s on
every trio ever run.** Nothing has ever actually collided.

## Recommendation — do not write code

**Re-scope 1.11 from "bound the reserve" to "prove the reserve holds under real
concurrency", and fold it into the concurrency trio rather than giving it its own fix.**

Rationale:

1. The serial tail is 18.1 s mean against a 60 s reserve. There is nothing to bound.
2. The only mechanism that ever blew the tail past the reserve is `_SESSION_LOCK` queueing,
   and the lock-**wait** bound for exactly that already landed (it is what survived the
   reverted first attempt) and **has never fired** — because nothing has ever contended.
3. So a trio started *simultaneously* rather than 60 s apart tests 1.11 and the ≤ 600 s
   concurrency row with the same three runs. If the tail stays inside the reserve,
   **1.11 closes with zero new code.** If it blows out, the lock-wait bound finally fires
   and we learn whether it is sized right — which is a tuning question with a measurement
   behind it, not a third guess.

The failure mode this avoids is the one the row has already hit twice: the first attempt
clipped the capture session's budget, bought nothing on the cap, and cost every judged page
(`visual_pages_reviewed` 10-of-18 → 0-of-18). Writing a fix before the concurrent
measurement exists would be the third attempt at aiming without a target.

## Reproduce

```
docker compose exec -T api python3 /app/backend/scripts/measure/tail.py \
  129 132 135 140 141 142 144 145
```

Contention values read from `requests.generated_pages -> preview_app -> contention`.
