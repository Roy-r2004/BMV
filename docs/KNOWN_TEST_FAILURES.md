# Known pre-existing test failures

Failures that exist on `main` independently of any current change. Each was
confirmed by stashing local edits and re-running, so a red result here is not a
signal that your change broke something.

Keep this list short. If you fix one, delete its row.

## Backend

| Test | Notes |
|---|---|
| `tests/preview_contract/test_appspec_v2_policy.py::test_v2_generation_rejects_fallback_instead_of_marking_it_complete` | Fixture scripts one provider response but the authoring loop asks for a second, so it raises `fixture attempted an unplanned provider call` instead of the expected fallback error. |

Expect exactly **1 failed** from `pytest tests/` in the API container using the
invocation below (863 passed as of the P0-1 imagery fix).

`tests/rollout/test_phase7e_ops_dashboard.py::test_known_preexisting_failures_documented`
reads this file from the repo root and skips only when `docs/` is absent. Under the
invocation below the whole repo is mounted, so it runs for real — meaning a row
naming a test that no longer exists fails the suite. Delete rows when you fix them.

### Resolved — do not re-add

- `test_task3_catalogue_guards.py::test_catalogue_fallback_typechecks_with_template`
  hardcoded `node_modules/.bin/tsc.cmd` (the Windows shim), so on Linux it raised
  `FileNotFoundError` and never typechecked. It now resolves the compiler through
  the production `typecheck_workspace`, and the 3 real template errors it then
  found are fixed: `AppLink` required `children`, which forbade the full-area
  overlay click pattern (`absolute inset-0` + `aria-label`, no children) used
  three times in `ProductShowcase.tsx`. Every generated app inherited those.
- `test_task3_security.py::test_workspace_writes_fail_closed` and
  `test_task4_prompt_contract.py::test_production_callsites_render_with_strict_undefined`
  were fixed on `chore/remove-preview-generator-v2`; both were partly vacuous.

### If the catalogue typecheck test skips

It skips when `backend/preview-template/node_modules` is an **incomplete** install,
naming the missing packages. That directory is gitignored, and a partial install
surfaces as `TS2307 Cannot find module` — which reads exactly like a template
defect but is not one. Real generations install from the lockfile into the
fingerprinted shared cache (`preview_app/npm_shared.py`) and never see it. Fix with:

```bash
cd backend/preview-template && npm ci
```

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
