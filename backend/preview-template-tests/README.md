# preview-template-tests

Vitest suite for `backend/preview-template`. Roadmap item **1.10**.

```
cd backend/preview-template-tests
npm ci
npm test
```

## Why this is a sibling package and not `preview-template/package.json`

Because the template's `package.json` is load-bearing for the generation clock.

`shared_npm_root()` keys the shared `node_modules` cache on a sha256 of the template's
`package.json` **and** `package-lock.json`
(`app/application/preview_app/npm_shared.py:29-44`). Any byte added to either file — a
`devDependencies` entry included — changes the fingerprint, so the next generation misses the cache
and pays a full cold `npm ci` **inside the run**, holding `_install_lock` through `contended_lock`
for the whole install while every concurrent run waits it out. Trios 4 and 5 cleared the 600 s DoD
with 9-17 s of margin; a cold install is minutes.

Second reason: `workspace.py` copies the template into every generated workspace and only skips
`node_modules`, `dist` and `.git`. Test files under `preview-template/src/` would ship inside every
preview app and be typechecked by `tsc -b` (`tsconfig.app.json` has `"include": ["src"]`).

So the tests import the template's source across the directory boundary instead. The template's
fingerprint is untouched and generation pays nothing.

`vitest.config.ts` maps `@` to `../preview-template/src`, the same alias the template's own
`vite.config.ts` and `tsconfig.app.json` define, so template-internal imports resolve unchanged.

## What belongs here

Assertions about template **behaviour** that Python cannot make without re-implementing React:
composition order, what a component throws on, rendered DOM structure.

What does **not** belong here: anything already asserted in pytest. `catalogue.json` drift against
`registry.ts`, for one, is covered by `tests/preview_app/test_ui_catalogue_drift.py`.

The standing rule: **no test may leave pytest until the CI job in
`.github/workflows/preview-template-tests.yml` is green on `main`.**
