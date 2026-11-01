# Handover - Build My Version, "package to a firm's standard" (written 2026-11-01)

For the next person or AI agent (Cursor). You do not need the earlier conversation. Facts below were checked on 2026-11-01 unless marked "from notes".

## 1. Context
Roy (owner of Build My Version, BMV, an AI consultancy in a browser that tells the truth) wants BMV's client output taken to a consultancy firm's standard: answer first, every figure traceable, no hedging language, six named files plus a ZIP, and a web experience that works at phone width 390px and desktop 1440px (public share pages included). The design is in `docs/superpowers/specs/2026-10-31-package-to-a-firms-standard-design.md` (Steps 1-7). Roy agreed that the agent does ALL implementation (UI included), Roy then tests locally, and only then decides on merge/PR. Roy agreed to a LIGHTER review depth for Steps 3-7 (see section 9).

## 2. State of the repo
- Repo `D:\Your Business Version`, branch `step1-honest-failure`, last commit `d1222b6 docs(plan): Step 3, the output shape, with the recon it stands on`. About 108 commits ahead of `main`.
- NOT pushed: the branch has no upstream. Nothing was pushed, merged or deployed.
- Working tree: clean except untracked `backend/buildmyversion.db-shm`, `backend/buildmyversion.db-wal`, `consultant-service/.test-tmp-api-consultation-1/` (all pre-existing, not ours; leave them).
- One worktree only (the main one). Two old stashes exist from September on other branches; not part of this work.
- Background jobs: none running that matter.
- Leftover temp folders on D: for Roy to delete: `D:\bmv-pytest-tmp`, `-check`, `-review`, `-tmp2`, `-tmp3`.

## 3. Done
- Step 1 (honest failure): finished earlier; a stage that cannot finish stops the run with a plain named reason.
- Step 2 (typed figures): finished. Every number is a typed figure (kinds: yours / worked out / our estimate / reference), checked by a strict number law before it reaches a PDF, deck, screen or web page. Code: `consultant-service/app/figures/`. Plan: `docs/superpowers/plans/2026-11-01-step2-typed-figures.md`.
- Verified on 2026-11-01 (HEAD 8ef72d6, `consultant-service`, `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider -rf`): 17 failed, 4026 passed, 5 skipped. 4 failures are old and known (3 in `tests/engine/test_engine_mutation_manifest.py`, plus `tests/engine/test_engine_universality.py::test_an_exempt_word_is_a_word_and_not_a_name`). The other 13 were that universality file failing only because pytest's temp folder is on C: and the repo on D:; with `--basetemp=D:/bmv-pytest-tmp` the file gives 37 passed, 1 failed (the known one). The whole suite was NOT re-run with the D: temp folder.
- Frontend 2026-11-01: `npx tsc --noEmit -p tsconfig.app.json` exit 0; `npm run lint` 0 errors, 14 warnings (old).
- r30 freeze re-recorded at `15ec65a` (commit 8ef72d6).
- Step 3 plan written and committed (`d1222b6`): `docs/superpowers/plans/2026-11-01-step3-output-shape.md` (12 tasks, rulings R1-R9, review focus) and its recon `docs/superpowers/plans/2026-11-01-step3-output-shape.recon.md`.

## 4. In progress
Nothing is half-built. The exact next step: start Step 3 Task 1 of the plan (bounds, move terms stored, flex calculator). No Step 3 code exists yet.

## 5. Pending (in order)
1. Step 3, Tasks 1-12 of the plan (answer page, register, storyline stage, exhibits, page law, PDFs, roadmap file, deck, one file list, web, acceptance and re-freeze).
2. Steps 4-7 from the spec, each with its own plan written first (use the superpowers skills `brainstorming`, `writing-plans`, then execute): 4 deeper thinking (derived facts by code, search-provider reference layer with code-confirmed citations, options with a costed do-nothing, expert panel, partner review), 5 client challenges the story (bounded wait, default 30 minutes), 6 live case file and honest durations, 7 whole-site sweep, browser gate and CI.
3. Roy then tests locally and decides: merge, PR or keep.
Decisions that need Roy (do not decide them): (a) whether a share link carries the whole package or a partner edition (shared links print every Q&A word for word); (b) what to do about export files being served to anyone by sequential id (see section 8); (c) any push, merge or deploy.

## 6. How to run and check
Service root: `consultant-service/` (FastAPI, SQLAlchemy/SQLite, reportlab, python-pptx). Frontend: `frontend/` (React 19, Vite, TypeScript).
- Use the project venv: `consultant-service/.venv/Scripts/python.exe`. The system Python has no reportlab and fails on PDF tests.
- Tests: `cd consultant-service && .venv/Scripts/python.exe -m pytest <paths> -q -p no:cacheprovider -rf`. For the whole suite add `--basetemp=D:/bmv-pytest-tmp` (the repo is on D:, and some engine tests break when the temp folder is on C:). The whole suite takes about 9 minutes: run it in the background and read its exit code, not the launcher message.
- A baseline of 4 known failures is listed in section 3; anything else red is new.
- Frontend: `cd frontend && npx tsc --noEmit -p tsconfig.app.json` and `npm run lint`.
- No live model calls in tests: an autouse fixture in `tests/conftest.py` blocks the OpenRouter post; stub `provider.chat` where a test needs a model reply.
- Environment variable names that matter (values live in `.env*` files; never print them): `OPENROUTER_API_KEY`, `DATABASE_URL`, `UPLOADS_DIR`, `SMTP_*`, `MAX_CONCURRENT_GENERATIONS`. Tests set `DATABASE_URL` and `UPLOADS_DIR` themselves.
- Windows 11. Git Bash is POSIX. `jq` is not installed (use `node -e` for JSON). Python writes CRLF by default here: pass `newline='\n'`.
- Frozen files: `consultant-service/app/pipeline/**`, `app/prompts/**`, `tools/**` and the top-level `tests/*.py` are hash-checked by `tests/engine/r30_manifest.json`. Editing them is allowed but turns `tests/engine/test_engine_r30_frozen.py` red until the LAST task re-freezes with `python tests/engine/refreeze_r30.py --commit <sha of the last frozen change> --after "..."`, then updates two constants (`tests/engine/test_engine_r30_frozen.py` line 81 and `tests/engine/test_engine_mutation_manifest.py` line 526) and commits `test(engine): re-freeze r30 at <sha>`. To find the sha use `git log -1 --format=%h -- app/pipeline app/prompts tools ':(glob)tests/*.py'` (the plain `tests/*.py` pathspec wrongly matches subfolders).
- The engine (`app/engine/**`) imports private names from `export_pdf.py` and `export_pptx.py` (list in the recon file, "Constraints"); do not rename them.
- Visual checks: Playwright with a mocked API. The earlier harness is in `C:\Users\User\AppData\Local\Temp\claude\d--Your-Business-Version\b5fa4762-a795-4021-8f6b-384ac074ef7c\scratchpad\` (`r6/e2e.py`, `step2-evidence/shots`); it may not survive, so rebuild it if missing.

## 7. Production and external state
Nothing was changed on any server, database, key or third-party service by this work. No deploy, no push. Rollback: not applicable.
From notes (not re-checked today): during Step 1 about 4 live OpenRouter calls leaked from tests before the guard existed, so Roy may want to look at the OpenRouter usage for 2026-10-31. Pushing `main` triggers an auto-deploy through Coolify (`DEPLOY.md` line 31), so never push `main`.

## 8. Known problems and bugs found
- Deploy blocker, pre-existing: `consultant-service/main.py` line 47 mounts all of the uploads folder, so every export file is downloadable by anyone who guesses the sequential id. Keep the server on localhost until Roy decides. Not fixed on purpose (Roy's call).
- Shared links print every client answer word for word in their export (decision (a) in section 5).
- Real-model behaviour is unknown: all end-to-end evidence used stub replies. The first paid local run will show how often the number law drops model sentences.
- Reader/binder classes parked on purpose (Step 2 ledger): "2 quarters", phone numbers and links, opening-hours forms, European dotted thousands, KPI shorthand, "Room 12", single-quoted quotes. A generic-noun count can certify an unrelated model count of the same value (e.g. "2 others" vs "2 instructors").
- Hedging copy still in the product (Step 3 removes it, plan ruling R9): "DRAFT - REQUIRES VALIDATION", "Prepared by BMV AI ...", "AI-native consultancy", deck `ai.confidence` line, the answer card's "What we estimated or couldn't check."
- Interview case-file panel is not wired in the UI (Step 6).
- Thresholds like "100,000 historical orders" stay a plain count (the registry stores no noun).
- Numbers quoted from the client's own website research are not in the known set yet (Step 4).
- `app/engine` router is mounted with raw exception text in responses; `evidence.py` has a repeated-claim-id bug; production `SMTP_*` settings are unset. All pre-existing, untouched.
- The step ledger `.superpowers/sdd/2026-11-01-step2-typed-figures/progress.md` is git-ignored; it holds every ruling made in Step 2 with its cost.

## 9. Rules to keep
- Deploys, pushes, merges and anything irreversible wait for Roy. Approval for one action does not carry to the next.
- Never print or paste `.env*` files, `*.pem`, `credentials.json` or `~/.claude/config.json`. Refer to variable names only.
- No invented figures. Sample data stays a labelled sample. Nothing that varies per business is fixed: min/max bounds live in `consultant-service/app/config.py` (`_env_int_within` pattern).
- Fail honestly: a stage that cannot finish stops with a plain named reason. A part with no data is absent, never filled.
- No hedging language in client output ("AI is not confident", "human review", "requires validation"). Trust comes from what was checked.
- Plain client words in everything printed or shown. Remove dead code. Match the surrounding style.
- Root cause before fix; run the real check and read its output before saying something passes. Small commits whose messages say why.
- Review depth for Steps 3-7 (agreed with Roy 2026-11-01): one reviewer per task plus at most one scoped re-review; one adversarial review of the whole step at the end; park low-severity findings instead of fixing them in rounds.
- Report to Roy in a few lines: what changed, what was verified (command and result), what was not, the one decision needed.
