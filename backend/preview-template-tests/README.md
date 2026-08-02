# preview-template-tests

Vitest suite for `backend/preview-template`. Roadmap item **1.10**.

```
cd backend/preview-template               # required — see "Module resolution"
npm ci
cd ../preview-template-tests
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

## Module resolution — why the template's own `npm ci` is required

The unit under test lives outside this package, so **its** bare imports resolve from **its**
directory: `preview-template/node_modules`, never this package's. That has two edges, and the first
one shipped green on a developer machine and would have failed the first CI run:

- **On a clean checkout that directory does not exist**, and both `tsc -b` and vite fail with
  `Failed to resolve import "react" from ".../SkeletonComposer.tsx"`. It is invisible on any machine
  that has already run the template's install — which is every machine that has built a preview.
  Hence the `npm ci` in `preview-template` above, and the matching CI step.
- **Once it does exist, React resolves twice** — once for the test file from here, once for the
  template source from there. Two React copies break hooks at runtime with an error that names
  neither cause. `resolve.dedupe: ['react', 'react-dom']` collapses them to this package's copy,
  which is pinned to the template's major.

The practical consequence for writing tests: a component that imports a package this test harness
does not have installed still resolves, because the template's own install provides it. Only add a
dependency here when the *test file itself* imports it.

## What belongs here

Assertions about template **behaviour** that Python cannot make without re-implementing React:
composition order, what a component throws on, rendered DOM structure.

What does **not** belong here: anything already asserted in pytest. `catalogue.json` drift against
`registry.ts`, for one, is covered by `tests/preview_app/test_ui_catalogue_drift.py`.

The standing rule: **no test may leave pytest until the CI job in
`.github/workflows/preview-template-tests.yml` is green on `main`.**
