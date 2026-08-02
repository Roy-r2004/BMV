# Session handoff — preview latency and the degradation contract (2026-08-02, session 4)

Successor to session 3's handoff (preserved in git history at `6294583`; the still-binding parts are
restated below). Process notes, not product docs.

- The plan and its evidence: **[docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md)** — read its
  **Status** table first, it is current as of this commit.
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [Where this stands](#where-this-stands).**

## TL;DR

Session 3 fixed what live runs exposed. Session 4 did two things: closed the navigation defects the
owner reported, then landed **Phase 1 of the roadmap — the 600 s guarantee** — minus 1.10.

| | before | after |
|---|---|---|
| same brief, deadline armed | request 72: **~37 min** | request 73: **579 s** |
| overrun past the 540 s deadline | ~1,700 s | **38.7 s**, then three ELECTIVE stages skipped and recorded |
| suite | 1,107 | **1,245 passed / 1 skipped / 0 failed** (1,246 collected) |

**9 commits** on `chore/remove-preview-generator-v2` (`90f4d5f`…`a0ecff8`), working tree clean,
`tsc` clean, `docs/KNOWN_TEST_FAILURES.md` empty.

| commit | what |
|---|---|
| `90f4d5f` | nav: a link must land where its label points |
| `614c086` | the roadmap, costed against the tree |
| `ac10c9b` | three guards that reported success while the defect shipped |
| `d8ef2e9` | gate: count occurrences, not findings |
| `a4f8b55` | telemetry: measure what the pipeline spends, and on what |
| `c534fdf` | **the request-scoped clock, and a contract for running out of it** |
| `a919f86` | coverage: stop letting the cap decide which defects are findable |
| `58b4956` | **deadline: zero means do not call, and a cap must fire when it says** |
| `1b5e0d1` | repair: refuse a plan for its paths before writing any of them |
| `a0ecff8` | 0.3 answered, and it reverses the branch 2.6 had chosen |

---

# Where this stands

## The nav defects the owner reported — all four fixed, verified on pixels

Fixed **in the pipeline**, not in a generated app. That constraint was explicit and it holds: nothing
under `data/preview-apps/**` was edited.

| reported | cause | fix |
|---|---|---|
| navigation keeps the scroll position | no scroll reset existed | `ScrollToTop` inlined into `app_tsx.j2`, `behavior:'instant'` |
| image and header into each other | hero clearance sat inside tailwind-merge range, so the caller's `className` won | clearance moved out of merge range + `min-h` |
| detail page shows "why Jane art" before the painting | three of six recipes ordered the detail page arbitrarily | all six ordered hero → credentials → inquire |
| "contact to purchase" lands mid-section | `index_css.j2` never carried a `scroll-margin-top` floor | it does now |
| footer in a huge wordmark | footer inherited the band's type scale | footer paints its own plane, below merge range |

**The header fix took three attempts and the third is the one to keep.** The template flipped
`sticky`↔`fixed` past 24 px, which collapses the document by 114 px *mid-scroll*. Fix 1 measured the
header and inserted a spacer — that just moved the jolt to first paint. Fix 3 is `sticky` for every
non-immersive layout: the document reserves the space, and nothing is measured at runtime.

**Do not pin these by source grep.** `docs/PREVIEW_ROADMAP.md` § *The nav guarantees* explains why —
every one of these five fixes would pass a grep. `tests/preview_app/test_nav_contract.py` asserts
rendered DOM through the Playwright path.

## Phase 1 — what the clock actually buys

`backend/app/application/services/request_deadline.py` is the whole mechanism. Three things about it
that are not obvious from the code:

1. **The scope is re-entrant for the same request, on purpose.** `orchestrator` calls
   `generate_preview_app` twice on failure. A nested scope inheriting a fresh budget would let a
   failing run spend 124 + 540 + 540.
2. **It is a degradation contract, not a kill switch.** MANDATORY stages fall through to their
   deterministic default and record `deterministic_fallback_past_deadline`; ELECTIVE stages skip and
   record `skipped_past_deadline`. Both are published by `finalize`. Two of three audited runs
   already shipped nothing — a deadline that just aborts trades a slow preview for no preview.
3. **540 s, not the 480 s the plan proposed.** The census killed 480: at t=480 all six measured runs
   were still inside build or codegen, and 124 + 480 + 60 > 600 does not close.

## The two defects I shipped into the deadline itself

Both found by **running** it. Written up at `58b4956`; repeated here because the shape recurs.

- **`ask_budget()` had a 1 s floor**, on the reasoning that a socket timeout must never be zero — and
  I pinned that reasoning in a test. Past the deadline every ask got 1 second, which does not mean
  "hurry", it means "attempt something that cannot finish". Each failed with a transport error, which
  is *retryable*, so it retried, then failed over. **AppSpec spent 29 minutes past an expired
  deadline.** Zero now means *do not call*, and `call_with_retry` refuses before the first attempt.
- **`_run_with_heartbeat` only checked its cap once per heartbeat.** A 1 s cap under a 20 s heartbeat
  fired at 20 s. **This predates the deadline work** — any caller passing `hard_deadline < 20` has
  always been silently rounded up. `test_a_short_ask_budget_is_honoured_within_it_not_a_heartbeat_later`
  reproduces the production log line verbatim.

## What is not done

1. **1.10, the vitest runner.** `preview-template/package.json` has `dev`/`build`/`typecheck` only.
   No `.github/`. Two Phase 2 DoDs depend on a runner that does not exist. **The only Phase 1 code
   left.**
2. **Phase 1's DoD is evidenced at n=1.** No 3-runs-60 s-apart set, no `reference_url` run, no
   `reference_file` run. Concurrency is exactly where `_SESSION_LOCK` and `_install_lock` make the
   deadline most likely to bind, so this is the highest-information thing left in Phase 1.
3. **Request 73 was still withheld** — 4 gate issues, incl. a severe visual defect on `/about-artist`
   and a dead link. Phase 1 bought the clock and the honesty. The ceiling is Phase 3.
4. **`/gallery` + `/collection` duplicate browse pages.** The surface-priority fix orders correctly,
   but 14 routes against a 6-page critic cap still leaves the storefront page unjudged on some runs.
   The duplication is the bug; the cap is not.
5. **5 of 88 repair ops changed nothing at all**, and were paid for. Worth a ticket.
6. **0.1** (replay 60 days of `industry` strings through `pick_template_id`) and **0.4** (are the
   critic's `revision_instructions` expressible as content-key edits) need production data.
   0.1 sizes 1.8's token work; 0.4 gates 2.6.

## The correction worth carrying forward

**My first 0.3 measurement was wrong and would have sent Phase 2 the wrong way.** I pattern-matched
the repair's *output* and reported 34 % layout. Artifact: almost any TSX blob contains `className`,
so layout won every tie. Diffing what actually **changed** (`difflib` over `old`→`new`) drops layout
to **4.5 %**. The plan said *"if mostly layout, demote `visual_defect_severe` to WARN in the same
commit that deletes the repair"* — that branch is dead. Build the spec-level actor and keep the BLOCK.

Same class as session 3's lesson: measure the delta, not the artifact.

---

# Process notes — verify before trusting, but these cost real time

## Branch and deploy constraints — unchanged, still binding

- **Nothing has deployed.** `main` and `origin/main` are untouched; no PR opened.
- **Pushing `main` auto-deploys to production** via Coolify (`DEPLOY.md`).
- **Do not force-push. Do not amend `5fcae7c`.**
- **`.env.prod` is gitignored and holds real production values.** Do not undo the `.gitignore` rules
  denying `.env` / `.env.*` at any depth.

## Use this test command — both documented ones lie

```bash
docker run --rm -v "$PWD:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
  --entrypoint sh bmv-local-api \
  -c 'pip install -q pytest; python -m pytest tests/ -q'
```

- Plain `docker run -v "$PWD:/repo"` fails template-dependent tests: the image sets
  `PREVIEW_TEMPLATE_DIR=/app/backend/preview-template`, and that env var **wins over** `Settings`'
  path discovery — so tests read the template *baked into the image* while your edits sit unread
  under `/repo`. Hence the explicit `-e` override.
- `docker compose exec api` fixes the template but fails
  `test_admin_build_info.py::test_deploy_files_stamp_the_code_policy_revision`, which walks to
  `parents[3]` for the repo root, finds `/app`, and cannot see the deploy files.

**Read the summary line, not the exit code.** Session 3 committed `42f81b9` with 14 tests red because
`pytest … | tail -5` inside an `&&` chain masked it. **I did the same thing again this session** —
exit 0 with 11 failures. Always `grep -E '^(FAILED|ERROR)'` *and* read the counts line.

## Running a generation

```bash
docker compose restart api                    # `exec api` does NOT reload code
curl -s -X POST http://localhost:8001/api/requests \
  -F 'business_name=…' -F 'business_description=…' -F 'email=…' -F 'industry=…'
```

**Set `industry`.** The endpoint declares `industry: str = Form(None)`. Omitting it resolves silently
to `generic` — no warning, no derivation. I created requests 66/67/68 without it and then escalated
the resulting garbage (SIGMA camera packaging in an art gallery) as the product's most urgent problem,
across three runs. Request 70, same brief with the field set, produced 9 of 11 real paintings. **This
is the single most expensive mistake available in this repo.**

- Host port is **8001**, not 8000. Creation auto-starts the pipeline. **Multipart, not JSON.**
- The **trailing slash** on `/api/requests/` 307-redirects and drops the body.
- `reviewing` is a **transient** state, not terminal. A watcher that stops there reports a run
  finished when it has not. Watch `is_generating`.
- Container log timestamps run behind the host clock; compare log lines to each other, not to `date`.
- A run is ~10 min now (was 15–20). Inspect with `scripts/preview-qa.sh <id> [tag]`, the stored
  `preview_app` result, and
  `docker compose exec api sh -c 'cd /app/data/preview-apps/<id> && ./node_modules/.bin/tsc --noEmit -p tsconfig.app.json'`.

## Other environment facts that cost time

- `awk` and `timeout` are absent from the host shell.
- `psql` exists only inside the `db` container
  (`docker compose exec -T db psql -U bmv -d buildmyversion`), where `sum(bool)` fails — use
  `count(*) FILTER (WHERE …)`. The `requests.status` column reads `new` long after a preview
  finishes; preview state is not there.
- **The working directory drifts between tool calls.** A `cd` into `backend/preview-template` broke a
  later `$PWD` docker mount for me this session. Use absolute paths.
- `write_file` renames `src/pages/*.tsx` to canonical `*Page.tsx` and unlinks the original.
- **Do not write a banned phrase into source, even in a comment.** I wrote one verbatim into a
  comment in `AdminDashboardPage.tsx`, which made the leak check flag that file permanently.
  `CTABand.tsx` carries a note explaining exactly why not to.

## Team Maverick

`.claude/agents/{maverick-pm,maverick-frontend,maverick-qa,maverick-logreader,maverick-master}.md`
exist and load at session start. `maverick-qa` deliberately has **no write tools** — a measurer that
can edit what it measures eventually does. They were created mid-session-3 and so were not
dispatchable in the session that wrote them; they are available to you now.

---

# Standing rules, earned the hard way

1. **Fix the pipeline, never the generated preview.** Editing `data/preview-apps/**` to make a defect
   go away is the one thing that is always wrong here.
2. **A guard that reports success while the defect ships is the recurring failure of this codebase.**
   `docs/PREVIEW_ROADMAP.md` § *Do not do this* #16 is the worked example — three layers each wrong
   in a different way, and the auditing agent nearly closed it as unreproducible.
3. **Mutation-test any guard whose success looks like its failure.** Break the fix, confirm the test
   goes red, restore. Session 4's 1.7 test passed with the fix reverted.
4. **A measurement with no reader is indistinguishable from one never taken.** (Session 3.)
5. **A repair must be better than the thing it replaces, and that must be checked.** (Session 3's
   `seed.showcase` lesson — the guard was right about the absence and wrong about what to do with it.)
6. **Never edit a generated preview app to make a defect go away.** Restating #1 because it is the
   one that gets rationalised.
