# Session 33 — Phase 1, measured on the real thing

*2026-08-12, branch `consultant-images-pipeline`. Ledger delta **$3.71**.
Suite 164 → 222.*

This session was scoped to finish Phase 1 and declare it shippable. It found
enough to stop that instead.

## Read in this order

1. [`dod-assessment.md`](dod-assessment.md) — all five lines, measured, and
   what each was measured against. **Two fail.**
2. [`results.md`](results.md) — what each job did, what it cost, and the
   findings in full.
3. [`defect-sweep.md`](defect-sweep.md) — the per-screen record: what was
   found on each of the fifteen, after every claim was put to a verifier
   told to refute it.

## The three things worth knowing

**A shipped screen renders "Cilents" and the text-truth gate passed it.**
[`job1/cilents-followup-8x.png`](job1/cilents-followup-8x.png) beside
[`job1/clients-anchor-8x.png`](job1/clients-anchor-8x.png) — the same slot,
same font, same size, on the anchor of the same run. The transcriber read back
the word it expected. Its prompt has told it not to do that since the day it
was written; the model was short of *resolution*, not willingness.

**13 of 15 screens carry a defect DoD line 2 forbids — including both screens
that scored 9.2.** The per-image judge is not the instrument for this line and
cannot be made into one.

**The pairwise judge passes.** Two models had failed it identically. With text
claims forbidden and "tie" made a real answer, it got a known pair right in
both orders, attributed the same defect to the same image under an order swap,
and every structural claim it made across four runs checked out by eye. It is
now the only automated instrument here shown to find real structural defects —
which is what line 2 needs.

## Artifacts

| | |
|---|---|
| [`sign-off/`](sign-off/) | the complete three-screen deliverable per business — the first sheets that show a whole set rather than one screen |
| [`deck/`](deck/) | all seven slides of the rebuilt deck, rendered through Keynote |
| [`job1/`](job1/) | the public path: the tool-screen anchor, its hero composite, the `/admin` payload, and the zoom crops that decided the text finding |

## Reproducing

```
# the golden set (funded)
docker run --rm -v "$PWD:/repo" -w /repo/consultant-service \
  -e DATABASE_URL=sqlite:////repo/consultant-service/consultant.db \
  -e GOLDEN_BRIEFS_DIR=golden/briefs-v2 \
  --entrypoint sh bmv-consultant-py -c 'python scripts/bakeoff.py --brief dental \
    --anchor-model google/gemini-3-pro-image \
    --followup-model google/gemini-3.1-flash-image --label s33-full'

# the sheets, the deck, the cost projection — all $0
python scripts/side_by_side.py --new-label s33-full --full-set
python scripts/deck_sample.py --brief retail \
  --run-dir scripts/out/bakeoff/retail/google_gemini-3-pro-image__s33-full --request 71
python -c "from app.pipeline import cost_model; print(cost_model.projected_request_cost('operations-dashboard'))"
```

`-e` flags go **before** the image name, the repo root is the mount, and
`DATABASE_URL` is passed explicitly — the image bakes in its own. All three
have cost this project money before.

**New trap this session:** SQLite in WAL mode over a bind mount is not
readable by a second process. A ledger bracket taken while the service is
running shows the database as it was before the run, which looks exactly like
nothing was spent. Read through the API, or after a clean `docker stop`.
