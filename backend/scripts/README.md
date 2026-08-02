# Backend scripts

Operational helpers — not part of the FastAPI runtime. Run from `backend/` so `app` imports resolve (`PYTHONPATH=.` or `python -m` with cwd=`backend`).

## Layout

| Path | Purpose |
|------|---------|
| `cli/` | Recurring tools (rebuild/finish preview, poll progress, parse debug logs) |
| `ops/migrations/` | One-off database migrations |
| `ops/seeding/` | Seed export helpers |
| `archive/` | Hardcoded / historical one-offs kept for reference — prefer not to run |

## CLI examples

```bash
cd backend
python scripts/cli/parse_bmv_debug.py --help
python scripts/cli/rebuild_preview_request.py <request_id>
python scripts/cli/finish_preview_request.py <request_id>
python scripts/cli/poll_progress.py <request_id>
python scripts/cli/ai_call_census.py --requests 66,67,68,70,71 --overhead 40
python scripts/cli/mutate_extractors.py
```

### `mutate_extractors.py` — proving the JSON-extractor guards actually guard

Reverts each extractor fix in turn and asserts `tests/test_json_extractor_parity.py`
goes red, then restores the sources. Run it after touching any extractor. A
mutation that leaves the suite green names a test that pins nothing — which is
how three extractors carried the same bugs through several sessions of green
suites.

### `ai_call_census.py` — sizing the request deadline (Phase 0.6)

Fits p50/p95 per model and per stage from `ai_usage_events`, then **convolves**
the per-stage distributions over the measured call census to get a whole-run
p95. It exists because p95 cannot be scaled from a mean, and multiplying a
per-call p95 by the call count asks for the probability that every call is
simultaneously at its own tail.

* `--overhead <s>` adds the non-model wall clock (finalize, capture, vite) so
  the printed number is comparable to a request-accepted-to-ready time.
* `--attribute-by-window` folds in rows whose `request_id` never propagated, by
  the request window they fall inside. That is **reconstruction, not
  measurement**, and the output says how many rows were inferred.
* Rows written before the census columns landed carry `usable = NULL` and are
  reported as unadjudicated, never counted as successes.

The arithmetic lives in `app/application/services/ai_call_census.py` and is
tested in `tests/application/test_ai_call_census.py`; this script is only the
database shell around it.

Automated tests live under `tests/` (see `pytest.ini`).
