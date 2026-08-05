# Session handoff — the offline remainder is spent, and the account is still empty (2026-08-05, session 15)

Successor to session 14's handoff (in git history at `369d5a7`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

---

## Session 15, in one page

**Zero generations — the account is empty for the FOURTH session running.** Probed first, before
anything was restarted: `total_credits 330, total_usage 330.229`, byte-identical to sessions
12, 13 and 14. Items 1–4 of the session prompt (the duo, 1.12's reachability, `slot_fill`'s
distribution, the colour-fix run) were offline again, said so plainly, not attempted.

**The classifier ruling was NOT given.** The prompt carried the unfilled template
`[prefix-anchored / word-boundary / leave it]` — a menu, not a choice. The classifier is
untouched and the ruling is still open, with its numbers ready in the roadmap's classifier row.

The session did the one sanctioned offline item and the housekeeping:

### The `design_direction` dedupe guard — landed (`38d66f5`)

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

**Suite: 1,870 passed / 1 skipped / 0 failed** (the +3 over session 14 are exactly the three new
tests). Vitest and `tsc -b` not re-run — no JS/TS touched.

**Pushed.** `main` was four commits ahead on one disk (`bd58502..38d66f5` plus docs); the
session-15 prompt said push was this session's call, and four sessions of unpushed work on one
disk is the risk the session-13 push existed to close.

---

## What I got wrong in session 15

- **First test run omitted the `pip install -q pytest` half of the documented command** — "No
  module named pytest" from the image, not a broken suite. The documented command's pip install
  is load-bearing; the failure is loud, but read it as the harness, not the code.

## Mutation results

`mutate_design_direction_dedupe.py`: **6 mutations, 0 survivors, one sweep.** Baseline green
(18 passed across `test_product_kind.py` + `test_design_brief.py`), every mutation restored from
the in-memory backup. No other sweep run — no other pipeline code changed.

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **session 15 callout** at the top of **Status**; session 14's callout and the classifier row
  UPDATE below it are still the live measurement record.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).**

---

## State of the repo, in four lines

- **`main` is `38d66f5` plus the session-15 docs commit, pushed** (this session's call, delegated
  in the prompt).
- **Suite: 1,870 passed / 1 skipped / 0 failed** (documented command). Vitest/`tsc -b` not re-run.
- **Credits: $0. `total_usage 330.229` of `total_credits 330`** — FOURTH identical reading. The
  ~$40 mystery spend is still unexplained and is the owner's call.
- **CI still unobserved.** Private repo, no `gh`, 404 unauthenticated. This push queued another
  run nobody has seen.

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

5. **The classifier ruling** — the numbers are in (Status row); the session-15 bracket was left
   unfilled. If adopting boundaries, prefix-anchored is the minimal-collateral shape;
   word-boundary needs a plural/stem story. Re-run `boundary_variant_census.py` and
   `synthetic_kind_census.py` after any change. `internal_ops` reachability and the
   driving-school default are SEPARATE and stay unfixed absent their own ruling.
6. **Dead nav data** (`navigation.customer/.staff/.features/.manager`,
   `navItemsAdmin`/`adminNavItems` — read by nothing) is the only code item left that needs no
   run, and it is pure deletion; three sessions listed, zero touched. Small enough to pair with
   any funded session rather than spend one on.
7. **Someone with a browser still has to look at CI once** — two unobserved pushes now.

**Owner decisions, unchanged and still yours:** p50 → Phase 2 under (A); APPSPEC_MODE stays
shadow; SiteSpec vs AppSpec; the `state_ids` backfill; relaxing the AppSpec schema; the
classifier ruling above; key rotation and the mystery spend.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Reading workspaces for evidence is fine.
- **Generation must not exceed 10 minutes.** A degraded ship happens INSIDE the cap or not at
  all; none of 1.12's fallbacks buys time.
- **Every fix gets a test that fails with the fix reverted**, proven by mutation from an
  in-memory backup, never `git checkout`.
- **Work the roadmap in order.** Phase 1 is not finished — 1.10 and 1.11 are open.

### The rule that has caught the most defects

**Mutation-test every guard.** Twenty-two drivers in `backend/scripts/cli/mutate_*.py`, one in
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

### 2. Eight fixes are mutation-proven and production-unproven
Sessions 11–15's (the dedupe guard joins the seven, though it is the one that genuinely needs
no run). 1.12's matters most — it is a fallback and a healthy run never exercises it.

### 3. The classifier decides a product kind on bare substrings — MEASURED, awaiting ruling
0 of 47 stored runs move under either boundary variant; only the guest house changes, to its
intended kind. The session-15 ruling bracket came back unfilled. `internal_ops` reachability
and the driving-school default are separate gaps boundaries do not touch.

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

### 9. 1.10 — green on `main` is unverified
Two pushes now, zero observations. Needs a browser or a token.

### 10. Dead nav data
Read by nothing; pure deletion; three sessions listed, zero touched. Pair with a funded session.

~~design_direction pile-on~~ — **closed**, `38d66f5`, this session.

---

## Next session's prompt, ready to paste

```
Read HANDOFF.md first — "Session 15, in one page" and "The next step". Then the roadmap's
session-15 callout. Don't re-derive them.

main is at the session-15 docs commit, PUSHED. Suite 1,870 / 1 / 0. Credits were $0 at last
check, FOURTH session running.

BEFORE ANYTHING ELSE: probe credits — HANDOFF "The next step" item 0. No restarts first.
IF STILL EMPTY: there is NO offline work left worth a session. State the reading, update
nothing, and stop — unless I have filled in a ruling below.

1. IF CREDITS RETURNED: launch_duo3.sh and the SEVEN fixes' read-list (HANDOFF item 1).
   Dump the api log the moment each run finishes; grep `slot_fill rejected`.
2. 1.12's reachability — the three unroutable-model runs (HANDOFF item 2). Recreate, never
   restart; log dumped first; .env restored and verified from the running process.
3. slot_fill's rejection distribution from item 1's logs — filed questions 2 and 3.
4. _design_system_dict's four discarded colours — land the fix WITH item 1's run beside it.
5. MY RULING on the classifier: [prefix-anchored / word-boundary / leave it]. If I rule to
   move: wrap-measured before/after with boundary_variant_census.py and
   synthetic_kind_census.py re-run after; internal_ops reachability and the driving-school
   default are SEPARATE and stay unfixed unless I say otherwise.
6. Dead nav data — pure deletion, pair it with item 1's session, don't spend one on it.

DECISIONS THAT ARE MINE: p50 -> Phase 2 under (A) stays put; APPSPEC_MODE stays shadow;
SiteSpec vs AppSpec pending; state_ids backfill pending; AppSpec schema untouched; key
rotation and the mystery spend.

NON-NEGOTIABLE: pipeline never previews; every fix mutation-proven from in-memory backup,
one sweep at a time; suite via docker run WITH its pip install half; roadmap in order;
10-minute cap; config from the running process; archive what you measure. TEN blind spots —
read the list in HANDOFF.

BEFORE YOU FINISH: next prompt written out; roadmap corrected in place; HANDOFF updated with
what landed, what was NOT the filed defect, mutation results, and what you got wrong.
```
