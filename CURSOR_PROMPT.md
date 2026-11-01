You are continuing a software project in this repo (Build My Version, an AI consultancy in a browser). Work on branch `step1-honest-failure`. Do not push, merge, deploy or open a PR. Roy (the owner) tests locally at the end.

Read first, in this order:
1. `HANDOVER.md` (repo root): state, how to run and check, known problems, rules.
2. `docs/superpowers/plans/2026-11-01-step3-output-shape.md`: the plan you are executing (12 tasks). Its recon is `docs/superpowers/plans/2026-11-01-step3-output-shape.recon.md`.
3. `docs/superpowers/specs/2026-10-31-package-to-a-firms-standard-design.md`, section "Step 3": the spec the plan argues from. If the plan and the spec disagree, the spec wins; write the call you made in `docs/superpowers/plans/step3-ledger.md` as `Ruling: <what> - <why> - <cost if wrong>` and keep going.

Do this:
- Execute the plan's tasks in order (1, 2, 3, then 5 and 10, then 4, 6, 7, then 8 and 9, then 11, then 12). For each task: write the failing tests named in the plan, watch them fail, implement, watch them pass, commit. One small commit per step, message says why.
- Python: use `consultant-service/.venv/Scripts/python.exe` (the system Python has no reportlab). Run `pytest ... -p no:cacheprovider`. The whole suite: add `--basetemp=D:/bmv-pytest-tmp`, run it in the background (about 9 minutes) and read its exit code. Known baseline failures are listed in HANDOVER.md section 3; any other red is yours to explain.
- Frontend: `npx tsc --noEmit -p tsconfig.app.json` must exit 0; `npm run lint` must have 0 errors. Check every changed screen at 390px and 1440px with Playwright and a mocked API, and confirm there is no horizontal scroll.
- Edits to files under `consultant-service/app/pipeline`, `app/prompts`, `tools` and top-level `consultant-service/tests/*.py` are allowed but are hash-frozen: do NOT re-freeze until Task 12, exactly as that task says.
- Never print or paste the contents of `.env*`, `*.pem`, `credentials.json`. Tests never call a live model.

Hard rules (the product's promise): no invented numbers (every number on a new page is a typed figure that the number law accepts); no hedging language in client output; nothing that varies per business is fixed (use bounded settings in `app/config.py`); nothing is cut by character count; a part with no data is absent, not filled; plain client words.

When all 12 tasks are done and the checks pass, stop and write Roy a short report: what changed, the commands you ran and their results, what you did not run, the rulings you made, and the one decision you need. Then wait. Do not start Step 4 until Roy says so; Steps 4 to 7 each need their own plan first (see HANDOVER.md section 5).
