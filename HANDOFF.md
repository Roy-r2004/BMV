# Session handoff — the blast radius is measured, and the doubled clause dies at the seal (2026-08-05, session 14)

Successor to session 13's handoff (in git history at `1aa3489`). Still-binding parts are restated
below; do not go back for them. Process notes, not product docs.

---

## Session 14, in one page

**Zero generations, and not by choice — the account is empty for the third session running.**
Probed first, before anything was restarted: `total_credits 330, total_usage 330.229`,
byte-identical to sessions 12 and 13. Two measurement commits plus docs. **No pipeline code
changed this session** — everything landed in `scripts/measure/` and the docs. Suite re-run the
documented way afterwards: **1,867 passed / 1 skipped / 0 failed, unchanged.** Vitest and
`tsc -b` were **not** re-run — no template or frontend file was touched.

With the account empty, items 1 (the duo), 2 (1.12's reachability — the unroutable-model trick
only isolates a branch if every *other* stage can complete a real call), 3 (`slot_fill`'s
distribution) and the colour-fix verification run were all offline. The session did the two
things that run without credits, and both changed what the backlog says:

### 1. The classifier's blast radius — measured, and the owner can now rule (filed item 4)

`scripts/measure/boundary_variant_census.py` (`86c6c1d`) runs the CURRENT resolver and two
boundary variants over the 20 synthetic briefs AND the 47 stored kind_contexts — which are
archived in `docs/evidence/preview-routes.json`, so no database is needed. The variant **wraps
the real function**: `_blob` is patched to return a str subclass whose `__contains__` matches on
boundaries, so `classify_product_kind` and `resolve_product_kind_contract` run untouched, and a
self-check proves the patch reaches the classifier before any number prints.

Two variants, because the hint table holds deliberate prefix stems (`reconcil`, `bookkeep`) that
a boundary on both sides silently kills: **word** (both sides) and **prefix** (left only).

| | |
|---|---|
| **the 47 stored kind_contexts** | **0 change kind or subtype, under either variant** |
| the 20 synthetic briefs | **the only change anywhere is SB-07 itself** — the guest house drops `internal_ops/trading` for its intended `storefront`; 15/20 → 16/20 |
| the other four misses | **do not move.** Driving school still takes the storefront default; the three staff-only desks still resolve `saas_workspace`. Reachability gaps in the hint table, not substring accidents |
| the word variant's cost | **it deadens plurals** — `collector`@collectors, `painting`@paintings, `appointment`@appointments, `reservation`@reservations, `menu`@menus, `trader`@traders, `cafe`@cafes. 48 of 67 rows lose ≥ 1 hit and no verdict changes **only because every affected row has redundant hits**; a one-signal brief falls to the default |
| the prefix variant's cost | almost exactly the defect class — `spa` mid-word ×16 (including "white**spa**ce"), `oms`@Rooms — plus **two genuine suffix matches**: `shop`@bookshop, `therapy`@physiotherapy |

Not fixed, per the brief. If the ruling is to move: prefix-anchored kills the filed class with
minimal collateral; a full word boundary needs a plural/stem story first.

### 2. Session 13's finding 2 is WRONG as filed — the doubled clause never reaches a prompt (filed item 5)

The filed claim was *"prompt pollution on every run … it changes a prompt on the HEALTHY path,
so it wants a run beside it."* Measured instead of assumed:

- **All 47 stored `preview_app.design_direction` values contain zero `PRODUCT_KIND=`
  occurrences.** Counted from the database, all 47 runs with a stored preview_app.
- The append is real — twice per dict, and **three times on ops/accounting kinds**, because the
  `internal_desk`/`saas_accounting` forcers (`plan_phase.py:204/:208`) read the polluted
  direction back **through `classify_product_kind`** and re-apply the contract. A genuine
  feedback loop; self-reinforcing only, on the current design notes.
- But `seal_design_brief` returns `sealed: True` **unconditionally**, and the sealed brief
  REPLACES the direction at `plan_phase.py:265` — **before `call_architect` at `:288`** — and at
  `:349`, before codegen and before `finalize` persists it. The pollution is transient and its
  only readers are those two forcer keyword checks. No model prompt ever sees it; the sealed
  direction carries the kind note once, by composition.
- Per-kind sizes are in `scripts/measure/design_direction_census.py` (`8786e87`): plan clause
  145–205 chars, architect 112–172, transient duplicate total 263–591 chars per run.

**Demoted**: the fix is a belt-and-braces dedupe guard (the idiom already exists ten lines up at
`product_kind.py:1152`), not a run-blocked prompt fix. The filed "wants a run beside it" is
withdrawn — a run would show nothing, because nothing observable changes.

### 3. A session-13 census claim corrected in place — internal_ops was never driven

`deterministic_paths_census.py`'s internal_ops context ("internal ops back office desk for
warehouse staff") resolves `storefront/storefront` — neither `"internal desk"` nor
`"warehouse floor"` is a substring of it. That is the classifier's own unreachability finding,
biting the census built to be immune to it: session 13's "measured over all seven reachable
kinds" actually drove **five** distinct contracts and measured storefront on three of seven rows.
Fixed (`8786e87`): the context now uses the measured hint pair, an `EXPECTED` label→kind map
turns any silent mislabel into a red summary line — **proven red on the old context** (exit 1,
`MISLABELLED ROW` naming the row) — and all **six** distinct contracts pass every check,
`internal_ops/ops` for the first time.

---

## Findings that were NOT the filed defect

1. **The forcer feedback loop.** `is_internal_desk_brief`/`is_saas_accounting_brief` feed
   `design_direction` — including the PRODUCT_KIND clause the kind lock just appended — back into
   `classify_product_kind`. Today the loop only re-confirms the kind that wrote the clause
   (measured: the third clause appears only on kinds whose own note re-triggers their own
   forcer). Any future design-note wording change can flip a kind through it. Listed, not fixed.
2. **The word-boundary plural trap.** The hint table is singular nouns matched against plural
   text. A both-sides boundary variant looks safe on this corpus only because of hit redundancy —
   the census makes that visible by counting hint losses, not just verdict changes.
3. **The 47 kind_contexts are archived** in `docs/evidence/preview-routes.json` under
   `kind_context` — no database needed. Session 13 wrote them there; nothing said so.

## What I got wrong in session 14

- **My first revert-proof proved nothing, twice.** First run piped through `tail` and echoed
  *tail's* exit code with stderr discarded — "exit=0" while python had crashed. Second run put
  the temp copy at the wrong directory depth and went red on its own `parents[2]` path math — red
  for the WRONG reason. Only the third run was red because of the mislabel it claimed to test.
  A revert-proof is only a proof if it fails for the filed reason, and the exit code you read is
  the exit code of the process you meant.
- **I nearly measured item 5 as "clause size × 2 × 47 runs of prompt pollution."** The stored
  artifacts said zero before the multiplication happened. Check the shipped artifact before
  publishing a mechanism's cost — same rule that caught the route census in session 13.

## Mutation results

**None to report in pytest — no pipeline code changed, no tests added.** The suite is untouched
at 1,867/1/0. The measurement layer got its own revert-proofs: the census label assertion
(red on the old context, green on the new) and `boundary_variant_census.py`'s hard self-checks
(the patch must demonstrably reach the classifier, and the fixture must still hit the
strong-signal branch, or it exits before printing a number).

---

- **The plan and its evidence: [docs/PREVIEW_ROADMAP.md](docs/PREVIEW_ROADMAP.md).** Read the
  **session 14 callout** at the top of **Status**, the **UPDATE in the classifier row**, and the
  **correction block** under the 1.12 update in Phase 1.
- **Before spending a trio: [docs/FIRST_FUNDED_TRIO_PREFLIGHT.md](docs/FIRST_FUNDED_TRIO_PREFLIGHT.md).**
- Why the pipeline shipped bad output: [docs/PREVIEW_QUALITY_FINDINGS.md](docs/PREVIEW_QUALITY_FINDINGS.md).

**If you read one thing: [The next step](#the-next-step).**

---

## State of the repo, in four lines

- **`main` is `1aa3489` (pushed) plus session 14's commits, which are unpushed.** Push
  authorization was session-13-specific; not assumed here.
- **Suite: 1,867 passed / 1 skipped / 0 failed** (re-run this session, documented command).
  Vitest and `tsc -b` not re-run — no JS/TS touched.
- **Credits: $0. `total_usage 330.229` of `total_credits 330`** — third identical reading across
  three sessions. The ~$40 mystery spend is still unexplained and is the owner's call.
- **CI still unobserved.** Private repo, no `gh`, 404 unauthenticated. Unchanged.

---

## The next step

**Ordered. Item 0 gates every item that needs a run.**

0. **Top up or rotate the OpenRouter key, then probe before anything else.**

   ```bash
   docker compose exec -T api python -c "
   import requests
   from app.core.config import settings
   print(requests.get('https://openrouter.ai/api/v1/credits',
       headers={'Authorization': f'Bearer {settings.OPENROUTER_API_KEY}'}, timeout=20).json())"
   ```

1. **Prove the SEVEN unproven fixes on a run that reaches a build.** `launch_duo3.sh` is ready.
   The read-list is unchanged from session 13's handoff (`1aa3489`, "The next step" item 1):
   gallery gone; both reservations routes with different labels; no hero subcopy literal; real
   font name; `grep -c ':slug' src/App.tsx` = 0; second card's slug renders the second item;
   **dump the api log the moment each run finishes** and grep `slot_fill rejected`.
2. **1.12's reachability** — unroutable `ARCHITECT_MODEL`, then `PREVIEW_APP_MODEL`, then
   `TEXT_MODEL`+`ARCHITECT_MODEL` for `build_experience_plan`; one generation each; degraded ship
   INSIDE the cap with the right `degraded` key and a stored `preview_app`. Recreate, never
   restart; dump the log first; put `.env` back and verify from the running process.
3. **`slot_fill`'s rejection distribution** from item 1's logs.
4. **`_design_system_dict` discards four derived colours** — thread the palette through
   `mock_data.py:313/:323/:375`, `brand_contract.py:255/:638`; pair with item 1's run.
5. **The classifier ruling — the numbers are in** (Status row). If adopting boundaries,
   prefix-anchored is the minimal-collateral shape; word-boundary needs a plural/stem story.
   Re-run `boundary_variant_census.py` and `synthetic_kind_census.py` after any change. Also
   still open behind it: `internal_ops` reachability and the driving-school default, which
   boundaries do not touch.
6. **`design_direction` dedupe guard** — demoted tidy-up; nothing observable changes (the seal
   wipes it), so it needs a test but not a run. The forcer feedback loop (finding 1) is the part
   worth a thought before touching.
7. **Dead nav data** — untouched again this session; the measurement corrections took the time.
8. **Someone with a browser still has to look at CI once.**

**Owner decisions, unchanged and still yours:** p50 → Phase 2 under (A); SiteSpec vs AppSpec;
the `state_ids` backfill; relaxing the AppSpec schema; the classifier ruling above; key rotation
and the mystery spend.

---

## Binding owner constraints — these do not expire

- **Fix the PIPELINE, never a generated preview.** Reading workspaces for evidence is fine.
- **Generation must not exceed 10 minutes.** A degraded ship happens INSIDE the cap or not at
  all; none of 1.12's fallbacks buys time.
- **Every fix gets a test that fails with the fix reverted**, proven by mutation from an
  in-memory backup, never `git checkout`.
- **Work the roadmap in order.** Phase 1 is not finished — 1.10 and 1.11 are open.

### The rule that has caught the most defects

**Mutation-test every guard.** Twenty-one drivers in `backend/scripts/cli/mutate_*.py`, one in
`preview-template-tests/tools/mutate.py`. **Run one sweep at a time.**

Ten blind spots, all found the expensive way (1–9 restated from session 13 at `1aa3489`; check
for each by default):

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
10. **NEW — a labelled measurement row measures its label, not its content.** The census's
    "internal_ops" row was a storefront for a full session. Assert `resolved == labelled`
    inside the tool, and make the mismatch a red exit — and when you build a revert-proof,
    make sure it is red for the filed reason and you are reading the right process's exit code.

Assume any DoD row you did not personally mutate is unproven.

---

## Operating notes — every one has cost real time

All of session 13's notes stand (`1aa3489`); the load-bearing ones, plus this session's:

| | |
|---|---|
| **Probe credits BEFORE anything else** | Item 0's one-liner. Third session where this was the first act and the right one |
| **Resolve config from the RUNNING PROCESS** | Never from a previous session's note; `backend/.env` is not tracked |
| **`restart` reloads code; it does NOT reload `env_file`** | `up -d --force-recreate` — and dump the log first, recreate destroys it |
| **The test command** | `docker run`, never `docker compose exec` — three independent lies |
| **The 47 kind_contexts are archived** | `docs/evidence/preview-routes.json`, key `kind_context` — classifier measurements need no DB |
| **`preview_app.design_direction` is the SEALED direction** | Anything appended between the kind locks and the seal is invisible downstream — check the seal before pricing a "pollution" |
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
  -c 'python3 scripts/measure/design_direction_census.py'          # kind-clause pile-on sizes
  -c 'python3 scripts/measure/deterministic_paths_census.py'       # 1.12 per kind — now label-asserted
  -c 'python3 scripts/measure/synthetic_kind_census.py --explain'  # the 20 briefs
```

DB-reading tools run via `docker compose exec api python /app/backend/scripts/measure/...`.
Postgres credentials are `-U bmv -d buildmyversion`.

---

## What is still broken

Ordered by what I would do first. Every item has evidence; none is speculative.

### 1. The account is empty and ~$40 over two days is unaccounted for
Third session blocked on it. Unchanged.

### 2. Seven fixes are mutation-proven and production-unproven
Sessions 11–13's. 1.12's matters most — it is a fallback and a healthy run never exercises it.

### 3. The classifier decides a product kind on bare substrings — MEASURED, awaiting ruling
0 of 47 stored runs move under either boundary variant; only the guest house changes, to its
intended kind. `internal_ops` reachability and the driving-school default are separate gaps
boundaries do not touch.

### 4. Page identity is fixed in shadow and not under enforcement
Unchanged (`capability_ids` unread by `_search_text`).

### 5. p50 is 563-570 s against a ≤ 500 s DoD
Unchanged; recommendation (A); owner ruling pending; the row is not moved.

### 6. `slot_fill` rejects 25 of 42 fills and the distribution is still unmeasured
Needs item 1's log dump.

### 7. `_design_system_dict` discards four of six derived colours
Structural and certain; wants a run beside the fix.

### 8. `design_direction` pile-on — DEMOTED from "prompt pollution" to tidy-up
Transient only; the seal discards it before any reader that matters. The real residue is the
forcer feedback loop (finding 1). Dedupe guard + a test; no run needed.

### 9. 1.11 — the reserve is unbounded as a whole
Unchanged. Measure pages-judged and wall clock separately.

### 10. 1.10 — green on `main` is unverified
Push happened, observation did not. Needs a browser or a token.

### 11. Dead nav data
`navigation.customer/.staff/.features/.manager`, `navItemsAdmin`/`adminNavItems` — read by
nothing. Two sessions listed, zero sessions touched.
