# Session handoff — an offline architecture review: one dead prompt section wired, two timing findings filed (2026-08-06, session 16)

Successor to session 15's handoff (below in this file — session 15 closed at `c791c12`; sessions
14 and earlier are in git history). Process notes, not product docs.

---

## Session 16, in one page

**Still $0 — no probe run this session because no generation was attempted.** The owner asked for
an offline architecture/logic review ("something to optimize, maybe prompts"). One fix landed,
one audit became a standing tool, two timing findings are FILED (not fixed — each needs a run or
an owner call).

### The fix: the mock-synthesis prompt's prop-shape section had never reached a model (`d28df68`)

A new template/call-site variable audit (`scripts/measure/prompt_variable_audit.py`, red exit on
any missing variable) found `preview_app_mock_synthesize.j2`'s **CATALOGUE ITEM SHAPES section
guarded by `is defined` and passed by NO production call site** — the producer
`catalogue_prop_shape_block()` was authored for that exact call (its docstring says so), the
render-level tests passed it, and the test file even said "codegen/mock.py does not pass the
block yet". Wired at `codegen/mock.py`; the catching test drives `synthesize_mock_data` itself
and captures the prompt off a fake provider. 2 mutations, 0 survivors
(`mutate_mock_prop_shapes.py`). The audit's only other flag (fix_agent's build-error render) was
benign — the typecheck block is guarded — and that site now passes explicit falsy values with a
byte-equality test, so the audit gates clean at exit 0. **Suite: 1,881 / 1 / 0.**

### Filed finding 1 — shadow appspec is ~100-125 s of serial critical path with no functional reader

Request 102's telemetry timeline: blueprint ends at 10 s, then **three serial appspec calls until
102 s**, then demo to 125 s — all before planning starts. Every functional consumer of
`ctx.app_spec_result`/`app_spec_scope` (plan seed at `plan_phase.py:86`, architecture seed at
`:326`, hooks in finalize) is behind `enforce_app_spec`; under `APPSPEC_MODE=shadow` only
provenance is recorded. Moving the shadow pass off the critical path (concurrent with
plan_phase, or per-run skip) would cut p50 by roughly the gap to the 500 s DoD — but APPSPEC
mode and the p50 row are both owner-parked, and any change here needs a funded run beside it.
**Related: `validate_and_expand_plan` costs 70-94 s/run and is reached only because
`canonical_seed` is None under shadow** — seeding it from the shadow spec would be
enforcement-lite, also the owner's call.

### Filed finding 2 — slot_fill's "truncated" rejections are provider errors adjudicated as answers

Already measured in duo 1 (roadmap codegen census): 14 of 28 rejections carry
`finish_reason: error`, 0 completion tokens, ~1,165 chars of partial body over HTTP 200 — a
transport failure recorded as a judged model answer, burning a full contract retry. The
reclassification fix should land WITH the funded slot_fill distribution measurement (backlog
item 3), not before it.

### What I got wrong in session 16

- **I ran the suite without `PREVIEW_TEMPLATE_DIR` once** (merged the audit and pytest into one
  container run and dropped the env) and read 14 template-dependent failures as a regression.
  The documented command has THREE load-bearing parts: the image, the pip install, and the env.

---

## Session 15, in one page

**Zero generations — the account is empty for the FOURTH session running.** Probed first, before
anything was restarted: `total_credits 330, total_usage 330.229`, byte-identical to sessions
12, 13 and 14. Items 1–4 of the session prompt (the duo, 1.12's reachability, `slot_fill`'s
distribution, the colour-fix run) were offline again, said so plainly, not attempted.

**The classifier ruling was NOT given at session start** — the prompt carried the unfilled
template `[prefix-anchored / word-boundary / leave it]`, a menu, not a choice, so the first half
of the session treated it as pending. **Mid-session the owner ruled "yes, fix it" on the prefix
recommendation, and uploaded a CI screenshot** — two items unblocked in one message.

The session landed five things (the owner also stated the product goal, which is now the
recorded yardstick for kind decisions: **the demo must match the business — a workflow tool, a
menu site, a portfolio, a company site — storefront is not the universal answer**):

### 1. The classifier is prefix-anchored — ruled, adopted, wrap-measured (`9c5b383`)

- `_blob` returns `_HintBlob`, a str subclass whose `in` requires the hint to start at a word
  edge (`(?<!\w)`, applied only when the hint's first char is alphanumeric — `"hr "` keeps its
  own delimiter); the right side stays free for the deliberate stems (`reconcil`, `bookkeep`).
- **Wrap-measured before/after: exactly one verdict changes anywhere — SB-07 to its intended
  `storefront/storefront` (16/20); 0 of the 47 stored kind_contexts move.** Before/after JSON
  archived in `docs/evidence/boundary-adoption-session15.json`. This is byte-for-byte the
  variant session 14 measured — the fix reuses the census's exact regex semantics.
- The forcers (`internal_desk.py`/`saas_accounting.py`) build their own plain blobs, were never
  patched by the census, and are deliberately untouched — the change covers exactly what was
  measured.
- `boundary_variant_census.py` is re-anchored to the adopted baseline: its self-check asserts
  the SHIPPED blob refuses mid-word hints and keeps stems, and `main()` now **red-exits on any
  per-row drift** between the shipped classifier and the measured prefix variant. Proven red
  under an in-memory substring revert, for the filed reason.
- 4 tests, 4 mutations, 0 survivors (`mutate_classifier_boundary.py`) — including the overshoot
  to a both-sides word boundary, which stays rejected.
- **Per the same ruling, still open and untouched: `internal_ops` reachability (the three
  staff-only desks) and the driving-school default.** Boundaries never touched them; the
  synthetic census's four remaining misses are exactly those.

### 2. 1.10 is CLOSED — CI observed green by a human

The owner opened run #11 of `preview-template-tests.yml` (push of `f019d39`) in a browser:
**Success, vitest 39/39 across 4 files, 27 s, 1 warning annotation.** First human observation
of this repo's CI; the row demanded exactly that and is done.

### 3. Dead nav data — measured, then deleted (`1df35e3`)

Three sessions listed, zero touched — closed by measuring first: extracted all 67 archived
workspaces (`docs/evidence/preview-workspaces.tar.gz`) and counted. 65 navigation objects,
every one with `public`+`admin`; the extra keys are per-role ids (`customer` ×48, `owner` ×18,
`staff` ×8, …) and **never `member`**, the only other key `app-nav.ts` reads; **zero imports**
of the `navItemsAdmin`/`adminNavItems` aliases — every page's `adminNavItems` is the
`useAdminNavItems()` hook local. Both writers deleted from `sync_mock_roles_navigation`
(`assemble.py`): the per-role loop and the alias block. Behaviour-identical on every archived
app. The existing test pinned the dead keys being WRITTEN — it now pins them staying dead, and
that the role routes still reach the sidebar through the admin list. 2 mutations (each writer
re-added), 0 survivors. No template file touched, so vitest is untouched.

### 4. The classifier's two remaining gaps — ruled "fix" on both, closed (`87cd085`)

- **Fix A (internal_ops reachability):** an internal-facing ASSERTION (`staff-only`,
  `not a public website`, `no customer ever`, `nobody outside`, `staff tool`, `internal tool`)
  beside ops/transactional language resolves `internal_ops` — guarded by `saas == 0`, because
  "an internal tool our design studio uses to run client projects" (SB-11) names an audience,
  not a product, and must stay a workspace. **The first cut flipped SB-11; the guard is what
  put it back, and it is mutation-pinned.** `back office` joins the ops hints.
- **Fix B (the zero-hint default):** `lesson` and `instructor` join the booking hints; the
  driving school books lessons instead of taking the art-gallery default.
- Wrap-measured (`docs/evidence/reachability-session15.json`): exactly the four intended
  synthetic briefs change; **20/20 on kind AND subtype for the first time; 0 of the 47 stored
  kind_contexts move.** All census tools re-run green — the synthetic corpus now drives
  `internal_ops/ops` from plain English.
- 6 tests, 5 mutations, 0 survivors (`mutate_internal_reachability.py`) — each of the rule's
  three guards has its own distinct catching fixture.

### 5. The `design_direction` dedupe guard — landed (`38d66f5`, earlier in the session)

- Both append sites (`apply_product_kind_to_plan` at `product_kind.py:877`,
  `apply_product_kind_to_architect` at `:1157` pre-change) now append the kind clause **once per
  dict**. Re-application — which `plan_phase`'s forcer path does 2-3× per run — is a no-op.
- **The guard keys on the full `PRODUCT_KIND={kind}/{subtype}` marker, not the bare
  `PRODUCT_KIND=` idiom** from the instructions site at `:1152`. Deliberate: if a forcer ever
  flips the kind (session 14 finding 1 — today it only re-confirms), the flipped kind still
  appends its own note, so the feedback loop keeps today's information content in all cases.
  A bare-prefix guard would silently swallow a flipped kind's note — that exact mutation is in
  the sweep and is caught.
- 3 tests in `tests/preview_app/test_product_kind.py`, 6 mutations in
  `scripts/cli/mutate_design_direction_dedupe.py`, **0 survivors** — including the inverted
  guard, both bare-prefix variants, and the skip branch's normalising assignment (pinned by a
  whitespace fixture so it is not a guard that cannot fail).
- `design_direction_census.py` re-run after the fix: **`transient_duplicate_chars` 0 on every
  kind**, was 263–591 per run. No production run needed and none spent — the seal already
  discarded the duplicates; nothing observable changes, exactly as session 14's demotion said.

**Suite: 1,873 passed / 1 skipped / 0 failed** (+6 over session 14: three dedupe tests, three
classifier tests). Vitest/`tsc -b` not re-run from here — no JS/TS touched; CI's own vitest run
is the 1.10 observation above.

**Pushed, twice.** The first push (`f019d39`) was this session's call — four sessions of
unpushed work on one disk was the risk the session-13 push existed to close — and it is the push
whose CI run the owner then observed. The classifier commits are pushed on the same standing.

---

## What I got wrong in session 15

- **First test run omitted the `pip install -q pytest` half of the documented command** — "No
  module named pytest" from the image, not a broken suite. The documented command's pip install
  is load-bearing; the failure is loud, but read it as the harness, not the code.
- **My first guest-house fixture did not bind (blind spot 1), and the mutation sweep caught me.**
  I gave it `gallery` + `menus`, so `storefront >= 2` short-circuited before the strong-signal
  branch the defect lives in — three of four mutations SURVIVED against it. The fix was SB-07's
  brief verbatim, which has a single storefront hit and genuinely reaches the branch. A sweep
  with survivors is the system working: read the survivor list before blaming the mutations.
- **A `git add` failed on pathspec because the working directory had drifted into `backend/`** —
  the operating note exists; use absolute paths or `cd` at the start of the compound command.

## Mutation results

- `mutate_design_direction_dedupe.py`: **6 mutations, 0 survivors, one sweep.**
- `mutate_classifier_boundary.py`: **4 mutations, 0 survivors** — after the fixture fix above;
  the first run had 3 survivors and each one was the fixture's fault, not the tests' subject.
- `mutate_dead_nav_data.py`: **2 mutations, 0 survivors** — each re-adds a deleted dead writer.
- `mutate_internal_reachability.py`: **5 mutations, 0 survivors** — the internal-facing rule's
  three guards each die to a different fixture, plus both new hint classes.
- `boundary_variant_census.py`'s adoption guard: **proven red under an in-memory substring
  revert**, failing with "shipped _blob regressed to bare substring matching" — red for the
  filed reason, file restored from the in-memory backup.
Run one at a time, every file restored from in-memory backups.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **session 15 callout** at the top of **Status**; session 14's callout and the classifier row
  UPDATE below it are still the live measurement record.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).**

---

## State of the repo, in four lines

- **`main` is `d28df68` (the prompt wiring) after session 15 closed at `c791c12`, pushed.**
- **Suite: 1,881 passed / 1 skipped / 0 failed** (documented command). Vitest 39/39 — on CI,
  observed.
- **Credits: $0. `total_usage 330.229` of `total_credits 330`** — FOURTH identical reading. The
  ~$40 mystery spend is still unexplained and is the owner's call.
- **CI OBSERVED GREEN for the first time** — run #11 on `f019d39`, by the owner, in a browser.
  1.10 is closed.

---

## The next step

**There is no meaningful offline work left.** The next session should not start unless at least
one of these is true, or it will burn a session confirming this paragraph:

0. **Credits are topped up or the key is rotated** — probe FIRST, the one-liner below, before
   anything is restarted:

   ```bash
   docker compose exec -T api python -c "
   import requests
   from app.core.config import settings
   print(requests.get('https://openrouter.ai/api/v1/credits',
       headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'}, timeout=20).json())"
   ```

If credits returned, the funded backlog is unchanged from session 14 and in this order:

1. **Prove the SEVEN unproven fixes on a run that reaches a build.** `launch_duo3.sh` is ready.
   Read-list unchanged (session 13's handoff at `1aa3489`, "The next step" item 1): gallery gone;
   both reservations routes with different labels; no hero subcopy literal; real font name;
   `grep -c ':slug' src/App.tsx` = 0; second card's slug renders the second item; **dump the api
   log the moment each run finishes** and grep `slot_fill rejected`.
2. **1.12's reachability** — unroutable `ARCHITECT_MODEL`, then `PREVIEW_APP_MODEL`, then
   `TEXT_MODEL`+`ARCHITECT_MODEL` for `build_experience_plan`; one generation each; degraded ship
   INSIDE the cap with the right `degraded` key and a stored `preview_app`. Recreate, never
   restart; dump the log first; put `.env` back and verify from the running process.
3. **`slot_fill`'s rejection distribution** from item 1's logs (filed questions 2 and 3).
4. **`_design_system_dict` discards four derived colours** — thread the palette through
   `mock_data.py:313/:323/:375`, `brand_contract.py:255/:638`; pair with item 1's run.

Rulings that unblock work without credits:

5. ~~`internal_ops` reachability and the driving-school default~~ — **RULED "FIX" ON BOTH AND
   DONE** (`87cd085`), see the one-pager. The classifier item is fully closed.
6. ~~Dead nav data~~ — **DONE this session** (`1df35e3`), see the one-pager. There is now no
   code item left that runs without credits.

**Owner decisions, unchanged and still yours:** p50 → Phase 2 under (A); APPSPEC_MODE stays
shadow; SiteSpec vs AppSpec; the `state_ids` backfill; relaxing the AppSpec schema; key
rotation and the mystery spend (the owner said 2026-08-05 they would fix the top-up "in a
couple of days"). The classifier rulings are all given and landed — nothing classifier-shaped
is pending.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Reading workspaces for evidence is fine.
- **Generation must not exceed 10 minutes.** A degraded ship happens INSIDE the cap or not at
  all; none of 1.12's fallbacks buys time.
- **Every fix gets a test that fails with the fix reverted**, proven by mutation from an
  in-memory backup, never `git checkout`.
- **Work the roadmap in order.** Phase 1 is not finished — 1.10 and 1.11 are open.

### The rule that has caught the most defects

**Mutation-test every guard.** Twenty-six drivers in `backend/scripts/cli/mutate_*.py`, one in
`preview-template-tests/tools/mutate.py`. **Run one sweep at a time.**

Ten blind spots, all found the expensive way (restated in full in session 14's handoff at
`369d5a7`; check for each by default):

1. Asserting against the case that does not bind.
2. Driving the consumer, never the producer — or the reverse.
3. Guards that cannot fail.
4. Fixtures too small to reach the rule — or the code path at all.
5. A test that adapts until it passes cannot fail — including through the fixture.
   **Fake a model with the model.**
6. Never assert against the constant a mutation would change.
7. A fix that changes no outcome is not a fix.
8. A measurement that paraphrases the code measures the paraphrase — drive the real function;
   execute old code from `git show`, never re-derive it.
9. A mutation can apply cleanly and still be a no-op — anchor on the last statement whose effect
   you mean to destroy.
10. A labelled measurement row measures its label, not its content — assert `resolved ==
    labelled` inside the tool, red exit on mismatch; a revert-proof must be red for the filed
    reason, from the right process's exit code.

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

All of session 14's notes stand (`369d5a7`); the load-bearing ones:

| | |
|---|---|
| **Probe credits BEFORE anything else** | Item 0's one-liner. Fourth session where this was the first act and the right one |
| **Resolve config from the RUNNING PROCESS** | Never from a previous session's note; `backend/.env` is not tracked |
| **`restart` reloads code; it does NOT reload `env_file`** | `up -d --force-recreate` — and dump the log first, recreate destroys it |
| **The test command** | `docker run`, never `docker compose exec` — and its `pip install -q pytest` half is load-bearing, the image does not ship pytest |
| **The 47 kind_contexts are archived** | `docs/evidence/preview-routes.json`, key `kind_context` — classifier measurements need no DB |
| **`preview_app.design_direction` is the SEALED direction** | Anything appended between the kind locks and the seal is invisible downstream — and as of `38d66f5` it is one clause per dict anyway |
| **No `git` in the test image** | Extract old files on the host (`git show ref:path > file`) |
| **`industry` is `Form(None)`** | Always set it. Host port **8001**, multipart, no trailing slash |
| pytest | **Read the SUMMARY LINE, never the exit code** |
| Working directory | Drifts between tool calls — absolute paths |
| Archive what you measure | Or it is unverifiable next session |

### Running the offline census tools

```bash
docker run --rm -v "$REPO:/repo" -w /repo/backend \
  -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
  -c 'python3 scripts/measure/boundary_variant_census.py'          # classifier variants, both corpora
  -c 'python3 scripts/measure/design_direction_census.py'          # kind-clause sizes — duplicates now 0
  -c 'python3 scripts/measure/deterministic_paths_census.py'       # 1.12 per kind — label-asserted
  -c 'python3 scripts/measure/synthetic_kind_census.py --explain'  # the 20 briefs
```

DB-reading tools run via `docker compose exec api python /app/backend/scripts/measure/...`.
Postgres credentials are `-U bmv -d buildmyversion`.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. The account is empty and ~$40 over two days is unaccounted for
FOURTH session blocked on it. Nothing on this list moves until it does.

### 2. Nine fixes are mutation-proven and production-unproven
Sessions 11–15's (the dedupe guard and the classifier adoption join the seven; the dedupe needs
no run, and the classifier is corpus-proven over all 47 stored contexts + 20 briefs — a funded
run adds one live data point, not the proof). 1.12's matters most — it is a fallback and a
healthy run never exercises it.

### ~~3. The classifier~~ — fully closed this session
Boundary matching adopted (`9c5b383`), both reachability gaps ruled "fix" and landed
(`87cd085`). 20/20 exact on the synthetic corpus, 0 of 47 stored runs moved, all sweeps clean.
What remains classifier-adjacent is only the live data point a funded run adds.

### 4. Page identity is fixed in shadow and not under enforcement
Unchanged (`capability_ids` unread by `_search_text`).

### 5. p50 is 563-570 s against a ≤ 500 s DoD
Unchanged; recommendation (A); owner ruling pending; the row is not moved.

### 6. `slot_fill` rejects 25 of 42 fills and the distribution is still unmeasured
Needs item 1's log dump.

### 7. `_design_system_dict` discards four of six derived colours
Structural and certain; wants a run beside the fix.

### 8. 1.11 — the reserve is unbounded as a whole
Unchanged. Measure pages-judged and wall clock separately.

~~1.10 — green on `main` is unverified~~ — **closed**, observed green by the owner (run #11).

### ~~9. Dead nav data~~ — closed this session (`1df35e3`)
Measured over the 67 archived workspaces before deleting: per-role navigation keys read by
nothing (never `member`, the one other key the template reads), aliases imported by nothing.
Both writers deleted from `sync_mock_roles_navigation`; 2 mutations, 0 survivors.

~~design_direction pile-on~~ — **closed**, `38d66f5`, this session.

---

## Next session's prompt, ready to paste

```
Read HANDOFF.md first — "Session 15, in one page" and "The next step". Then the roadmap's
session-15 callout and the classifier row's session-15 UPDATE. Don't re-derive them.

main is PUSHED through the session-16 close. Suite 1,881 / 1 / 0. Credits were $0 at last
check; I said I would fix the top-up within a couple of days of 2026-08-05 — so this session
may be the funded one. The classifier is FULLY CLOSED — do not reopen it. My product goal,
recorded: the demo must match the business — storefront is not the universal answer. CI was
observed green once; 1.10 is closed. Session 16 filed two timing findings (HANDOFF one-pager):
shadow appspec's ~100-125 s serial cost and slot_fill's provider-errors-as-answers class —
BOTH need a funded run or my ruling before anyone touches them.

BEFORE ANYTHING ELSE: probe credits — HANDOFF "The next step" item 0. No restarts first.
IF STILL EMPTY: there is NO offline code work left. State the reading, update nothing, stop.

1. IF CREDITS RETURNED: launch_duo3.sh and the fixes' read-list (HANDOFF item 1) — the seven
   plus the classifier's live data points (the kind each run resolves, from the log).
   Dump the api log the moment each run finishes; grep `slot_fill rejected`.
2. 1.12's reachability — the three unroutable-model runs (HANDOFF item 2). Recreate, never
   restart; log dumped first; .env restored and verified from the running process.
3. slot_fill's rejection distribution from item 1's logs — filed questions 2 and 3.
4. _design_system_dict's four discarded colours — land the fix WITH item 1's run beside it.
5. Also read FIRST_FUNDED_TRIO_PREFLIGHT.md before spending anything.

DECISIONS THAT ARE MINE: p50 -> Phase 2 under (A) stays put; APPSPEC_MODE stays shadow;
SiteSpec vs AppSpec pending; state_ids backfill pending; AppSpec schema untouched; key
rotation and the mystery spend.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time; suite via docker run WITH its pip install half; roadmap in order;
10-minute cap; config from the running process; archive what you measure. TEN blind spots —
read the list in HANDOFF; a fixture that short-circuits before the branch under test is
blind spot 1 wearing a new coat.

BEFORE YOU FINISH: next prompt written out; roadmap corrected in place; HANDOFF updated with
what landed, what was NOT the filed defect, mutation results, and what you got wrong.
```
