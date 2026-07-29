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

- **Use this invocation.** Both previously documented commands report phantom
  failures, in opposite directions, because two different path roots must line up
  with the mounted repo:

  ```bash
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api \
    -c 'pip install -q pytest; python -m pytest tests/ -q'
  ```

  - Plain `docker run -v "$PWD:/repo"` fails template-dependent tests, because
    the image sets `PREVIEW_TEMPLATE_DIR=/app/backend/preview-template` and that
    env var wins over `Settings`' path discovery — so the tests read the
    **template baked into the image** while your edits sit unread under `/repo`.
    Symptom: `test_task5_deterministic_fixture` reports `src/ui/**` drift that
    does not exist in the repo. Hence the explicit `-e` override above.
  - `docker compose exec api` fixes the template (compose mounts `./backend` onto
    `/app/backend`) but fails `tests/security/test_admin_build_info.py::test_deploy_files_stamp_the_code_policy_revision`,
    which walks to `parents[3]` for the repo root and finds `/app` — where
    `Dockerfile.app` and `docker-compose.coolify.yml` are not mounted.
  - Neither is a code defect. Confirm any suspected regression under the
    invocation above before believing it.

- `pytest` is **not** in `backend/requirements.txt`; install it per run, and note
  that recreating the container loses it. A dev-requirements file would remove
  this step.
- `tests/appspec/` cannot always be collected as a whole directory: importing
  `app.domain.appspec.validation` before `app.application.appspec` triggers a
  circular import between those packages. Naming individual test files works.
