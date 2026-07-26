# Preview Generator v2 — Phase 4 Runtime Validation

Phase 4 deterministically builds and validates the immutable Tier 1 candidate
created by Phase 3B. It does not generate or repair product UI with AI, accept
the candidate as a served preview, promote it, or start Phase 5.

## Feature and lifecycle boundary

Phase 4 runs only when both feature flags are enabled:

- `PREVIEW_GENERATOR_V2=true`
- `V2_RUNTIME_VALIDATION_ENABLED=true`

`V2_RUNTIME_VALIDATION_ENABLED` defaults to `false`. Turning it off restores
the Phase 3B `candidate_build_pending` stopping boundary without deleting
Phase 4 history. Turning off `PREVIEW_GENERATOR_V2` retains the frozen v1
selection behavior.

Phase 4 never updates `candidate_revisions.status`. The Phase 3B revision
remains `candidate_build_pending`. Its effective runtime state is derived from
the newest append-only validation summary:

- `candidate_runtime_validated`
- `candidate_build_failed`
- `candidate_runtime_failed`

The phase cannot produce `ready`, `degraded`, `promoted`, or `served`.
`PREVIEW_APPS_DIR` and serving pointers are not written.

## Immutable validation workspace

The source candidate remains under `PREVIEW_CANDIDATES_DIR`. Each runtime
attempt creates a copy-only workspace under:

```text
PREVIEW_VALIDATIONS_DIR/
  <request-id>/<candidate-revision-uuid>/
    .staging/<attempt-uuid>/
      .runtime-attempt.json
      candidate/
      repair-<short-uuid>/       # present only after the one repair
      evidence/screenshots/
```

The copy uses `shutil.copy2`; every manifest file is checked with
`os.path.samefile` to reject mutable hardlinks. Symbolic links and paths that
escape a workspace are rejected. The complete Phase 3B file manifest is
reparsed and rehashed before the copy, after the copy, after build/runtime
execution, and in the terminal summary. A source pre/post mismatch fails
closed.

An allowlisted repair always copies the base validation candidate into a new
derived workspace. It never edits the Phase 3B source or the previous
validation copy. The attempt directory is atomically moved from `.staging` to
`attempts/<attempt-uuid>` at the terminal boundary.

An interrupted attempt can resume only when its database provenance,
metadata, source hash, policy, limits, and tool hashes still match. Invalid or
missing resume state is not trusted.

## Build execution and dependency integrity

No package manager is invoked. The exact commands are argument arrays with
`shell=False`:

```text
node <preview-template>/node_modules/typescript/bin/tsc -b --pretty false
node <preview-template>/node_modules/vite/bin/vite.js build --mode production --outDir dist --emptyOutDir
node <preview-template>/node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port <reserved-port> --strictPort
```

Before build, the candidate package declaration and lock declarations must
match, the candidate lock must match the checked-in template lock
semantically, and every directly declared installed package version must
match the pinned lock. The dependency runtime is snapshotted before and after
build. Candidate source never executes as a Node command; only the checked-in
TypeScript and Vite entrypoints run.

The local tool snapshot on the Phase 4 implementation machine is:

| Tool | Version |
|---|---|
| Node | `v24.13.1` |
| TypeScript | `5.8.3` |
| Vite | `8.1.3` |
| Playwright | `1.61.0` |
| Browser bundle | `chromium-1228` |

Tool versions, policy revision, and all limits are persisted per attempt.

## Loopback-only network isolation

Every Node build and preview process preloads the checked-in
`network_guard.cjs`. Startup verification must prove that it blocks:

- external DNS;
- external HTTP;
- external HTTPS;
- non-loopback TCP sockets; and
- non-loopback TLS sockets.

The process environment is reduced, update/audit/funding behavior is disabled,
and npm is marked offline even though no package-manager process is allowed.
The guard emits bounded `BMV_NETWORK_BLOCKED` diagnostics and fails closed if
installation or verification fails.

Playwright independently aborts every request whose host is not
`localhost`, `127.0.0.1`, or `::1`. Those attempts are bounded and persisted
as runtime network diagnostics.

## Production output gate

The deterministic dist gate requires:

- `index.html`;
- all referenced local scripts, styles, images, and sources to exist;
- no remote imports or runtime assets;
- no unexpected environment names;
- no source-map files or source-map references;
- no absolute local paths;
- a canonical file manifest and build identity;
- a fresh preview server that serves the expected candidate/build identity;
- direct-route SPA behavior; and
- configured bundle/file budgets.

Default budgets:

| Limit | Default |
|---|---:|
| Total dist | 5 MiB |
| Largest JavaScript asset | 2 MiB |
| Total CSS | 512 KiB |
| File count | 200 |
| Source maps | 0 |

All values, including the source-map count, are configuration-backed.

## Route, journey, and screenshot gates

Every Tier 1 route runs at:

| Viewport | Size | Touch |
|---|---:|---|
| mobile | 390 × 844 | yes |
| tablet | 768 × 1024 | yes |
| desktop | 1440 × 900 | no |

The route gate verifies load, exact page and role markers, business-component
markers, action/evidence/acceptance hooks, direct navigation, reload, history,
horizontal overflow, critical clipping of active components/actions, primary
action reachability, IA mobile bindings, page errors, console errors, local
request failures, and external network attempts.

Journeys are projected without AI from `InteractionContract`,
`ContentDataPlan`, and canonical browser assertions. Input values come only
from canonical seed records and field bindings. Controls and hooks must be
unique. Each journey proves its initial state, input binding, action,
transition, resulting state, visible evidence, and acceptance assertions.
Unsupported or ambiguous assertions fail closed.

Every required interaction is also executed with reduced motion. The action,
state transition, evidence, and assertions must remain functional.

Screenshots are captured at all three viewports as evidence only. Phase 4
does not score, compare, send, critique, or refine them with AI. Each record
contains its route, viewport, candidate/build provenance, browser version,
capture policy, relative path, byte count, and content hash.

## Baseline accessibility gate

The in-repository scanner is named `BaselineAccessibilityScanner`. It checks a
deterministic baseline that includes accessible names, form labels, image alt
behavior, heading hierarchy, main landmarks, required-action keyboard
reachability, visible focus, open-dialog focus containment, reduced-motion
operation, and obvious computed-style contrast failures. Serious or critical
findings fail Phase 4.

This scanner is not Axe-equivalent, is not full WCAG certification, and is not
a replacement for Axe or expert accessibility review. Phase 4 does not fetch
Axe or any other package at runtime.

The accessibility artifact includes scanner name and policy plus each
finding's rule ID, severity, selector, and diagnostic evidence, along with
route and viewport provenance. A future pinned Axe adapter can emit the same
typed route result and participate in the existing validation summary without
changing its model.

## Append-only persistence and migration

Phase 4 adds seven tables:

1. `candidate_runtime_validation_attempts`
2. `candidate_build_attempts`
3. `candidate_route_results`
4. `candidate_journey_results`
5. `candidate_accessibility_findings`
6. `candidate_screenshots`
7. `candidate_validation_summaries`

They reference the immutable candidate revision and runtime attempt. Build
repairs additionally reference their parent build attempt. Terminal result
rows and the summary are inserted in one transaction; any flush/commit failure
rolls them all back. A validated summary is rejected unless its build passed,
all exact result hashes match, the complete route × viewport and journey
matrices pass, the baseline accessibility scans pass, and every screenshot
exists with the persisted size and hash.

This repository uses additive SQLAlchemy metadata creation rather than
Alembic. The Phase 4 models are imported before `Base.metadata.create_all`,
and the SQLite-to-Postgres importer includes all seven tables in dependency
order. Operational rollback is the feature flag; it preserves append-only
history. No destructive down migration is run automatically.

## Cache policy

Build and dist cache keys include the candidate and lock hashes, schema/policy
revisions, tool versions, network-guard revision, and dist limits. A hit is
reparsed, rehashed, copied, and verified before use.

Route, journey, accessibility, and screenshot caches are independent. Their
keys additionally include the exact upstream contract hashes, viewport or
capture policy, browser bundle, and scanner revision as appropriate. Reuse
always follows this order:

1. reverify candidate and build provenance;
2. restore the exact canonical dist;
3. start a fresh isolated loopback preview server;
4. verify its served build identity;
5. reparse cached typed records and verify record hashes;
6. restore screenshot files and verify their hashes; and
7. launch the local browser before accepting browser cache results.

A database cache key alone never bypasses server startup or served-build
identity verification. Cache rows are scoped to one complete prior attempt so
repeated successful attempts cannot accidentally form an oversized mixed
result set.

## Pre-build and diagnostic contract

Before execution, Phase 4 validates required candidate files, JSON manifests,
required scripts, and known host-specific absolute paths. This gate is
deliberately bounded; TypeScript and Vite remain the authorities for language,
module-resolution, and production-bundle correctness.

The verified template dependency installation is exposed inside the isolated
candidate workspace only while TypeScript and Vite run. Candidate-local
incremental metadata is redirected away from the shared installation, and the
temporary dependency view and configuration overlay are removed afterward.
The frozen Phase 3B source and shared dependency tree are hash-checked.

Build and runtime summaries persist a typed `failure_code` and first relevant
source location where available. Runtime attempts also persist Node, npm,
Python, platform, TypeScript, Vite, Playwright, browser, policy, limits,
commands, bounded output, hashes, and repair ancestry.

Trusted operators can inspect this evidence through:

`GET /api/admin/requests/{request_id}/runtime-validation-attempts`

The customer preview contract remains bounded and exposes the terminal status
and safe typed failure fields without providing an execution surface.

## Deterministic repair policy

At most one repair is allowed, in a derived validation workspace, for:

- SPA route fallback configuration;
- dist identity/manifest wiring;
- local asset path normalization;
- uniquely targetable deterministic test-hook wiring; or
- narrowly recognized Vite build configuration.

The implementation rejects ambiguous hook repair and any code outside the
allowlist. It never rewrites visible page or business-component design. There
is no AI repair.

## Configured default limits

- TypeScript: 90 seconds
- Vite build: 120 seconds
- combined build stage: 180 seconds
- preview startup: 20 seconds
- route: 15 seconds
- journey: 30 seconds
- accessibility scan: 15 seconds per route
- screenshot: 10 seconds
- whole phase: 600 seconds
- browser contexts/pages: 2/2
- console/network diagnostics: 100/100
- stdout/stderr: 64 KiB per command
- deterministic repairs: 1
- provider calls: 0

## Local verification

The focused suite is local-only:

```powershell
cd backend
python -m pytest -q -p no:cacheprovider tests/runtime_validation/test_phase4_runtime_validation.py
python -m compileall -q app
git diff --check
```

It covers the real TypeScript/Vite/browser happy path, immutable copy
boundaries, five-layer network blocking, dependency lock/version checks,
timeouts and failures, dist budgets, the full route matrix, deterministic
journeys and reduced motion, real baseline-scanner findings, screenshot
hashes, independent caches, fresh-server cache reuse, interrupted resume,
transaction rollback, incomplete-result rejection, and both feature flags.

The Phase 0–3B regression suites remain the authority for the frozen v1 and
earlier v2 boundaries. The known Windows `.pytest_cache`/`tmp_path` ACL warning
is environmental; Phase 4 uses repository-local isolated fixture roots.

No paid provider, canary, promotion, serving action, Phase 5 critic, visual
refinement, Tier 2/3 generation, polish, or finalize path is authorized here.
