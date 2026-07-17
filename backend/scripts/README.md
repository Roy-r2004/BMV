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
```

Automated tests live under `tests/` (see `pytest.ini`).
