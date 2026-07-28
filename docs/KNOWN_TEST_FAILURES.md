# Known pre-existing test failures

Failures that exist on `main` independently of any current change. Each was
confirmed by stashing local edits and re-running, so a red result here is not a
signal that your change broke something.

Keep this list short. If you fix one, delete its row.

## Backend

| Test | Notes |
|---|---|
| `tests/preview_app/test_task3_catalogue_guards.py::test_catalogue_fallback_typechecks_with_template` | Catalogue fallback does not typecheck against the current preview template. |
| `tests/preview_app/test_task3_security.py::test_workspace_writes_fail_closed` | Workspace write guard assertion is stale. |
| `tests/preview_app/test_task4_prompt_contract.py::test_production_callsites_render_with_strict_undefined` | `synthesize_mock_data` returns falsy for the restaurant fixture under strict-undefined rendering. |
| `tests/preview_contract/test_appspec_v2_policy.py::test_v2_generation_rejects_fallback_instead_of_marking_it_complete` | Fixture scripts one provider response but the authoring loop asks for a second, so it raises `fixture attempted an unplanned provider call` instead of the expected fallback error. |

Expect exactly **4 failed, 1 skipped** from `pytest tests/` in the API container.
The skip is `tests/rollout/test_phase7e_ops_dashboard.py::test_known_preexisting_failures_documented`,
which reads this file from the repo root and skips when `docs/` is absent — the
container mounts only `./backend`. It runs for real on the host.

## Environment notes

- `pytest` is **not** in `backend/requirements.txt`. To run the suite in the
  container: `docker compose exec api sh -c 'pip install -q pytest && cd /app/backend && python -m pytest tests/ -q'`.
  A dev-requirements file would remove this step.
- `tests/appspec/` cannot always be collected as a whole directory: importing
  `app.domain.appspec.validation` before `app.application.appspec` triggers a
  circular import between those packages. Naming individual test files works.
