# Step 1: Honest Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When our side breaks, the client is told in plain words, the team is emailed the same minute, the run stops, and nothing canned ever stands in for work we did not do.

**Architecture:** One exception type, `StageFailed(stage, cause)`, raised by every stage that today swallows a failure and substitutes content. The orchestrator catches it in one place, `failure.fail_run`, which stops the run, writes a client-safe reason, emails the team synchronously and records the facts in a new `failure_json` column. The interview endpoints stall with a 503 instead of serving stock questions. `/progress` carries the client-safe failure and a list of documents actually produced; the frontend renders those and nothing else.

**Tech Stack:** FastAPI, SQLAlchemy (SQLite), pytest, Jinja prompts, reportlab; React 19 + Vite + TypeScript.

**Spec:** `docs/superpowers/specs/2026-10-31-package-to-a-firms-standard-design.md` (Step 1; decisions under "Decided by the owner" and "Calls made"). Research it rests on: `docs/superpowers/specs/2026-10-31-what-top-consultancies-deliver.md`.

This is plan 1 of 7, one per design step. Steps 2 to 7 are planned one at a time after this ships, because each uses interfaces the previous one creates.

## Global Constraints

- Nothing client-facing says "try again" for a fault of ours, shows an exception, a stage id, a model name or "pipeline". Copy is plain words.
- No human-review or "AI is not confident" language anywhere. The method page states how the work was done as a record, never as a disclaimer.
- No canned content stands in for work not done: the front-desk recommendation, the invented pain points and the stock interview questions are deleted, not hidden.
- Everything that should vary per business is bounded in `consultant-service/app/config.py`; no new fixed counts.
- `app/pipeline/`, `app/prompts/` and the top-level `tests/*.py` are byte-frozen by `tests/engine/r30_manifest.json`. Every task edits some of them; Task 10 re-freezes. Until then `test_engine_r30_frozen.py` is expected to fail on hash mismatches. That is the only expected new red.
- `tests/test_hollow_run_is_not_done.py` reads orchestrator source for the exact line `if not (req.mvp_blueprint or req.technical_plan):` before `req.status = "done"`. Keep it.
- Run checks from `consultant-service/` with `TMP=/d/bmv-pytest-tmp TEMP=/d/bmv-pytest-tmp .venv/Scripts/python.exe -m pytest <target> -q -p no:cacheprovider` (create the folder first; pytest's temp dir on C: breaks the engine universality tests on this laptop). Frontend checks from `frontend/`: `npx tsc -p tsconfig.app.json --noEmit` (expect no output) and `npm run lint` (expect 0 errors, no more than the 14 warnings that exist today, none in touched files).
- Never read or print `.env*`, `*.pem`, `*.db`. Tests use stubs, never the live provider.
- Commit after each task with a message that says why. Do not push. Commit trailer: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Each task's result is checked by a verifier who did not write it, who runs the task's command and quotes the output.

## Review Focus

Each line below has its test in the task named.

1. A build the client superseded (pushed back mid-write) whose stage then raises must not mark the run failed or email the team. Task 2.
2. SMTP not configured: the run still fails cleanly, `team_notified` is false, and the client copy makes no claim that anyone was told. Task 1 and Task 2.
3. Exception text, including provider errors carrying URLs or key fragments, never reaches `/progress`, the failure page or an email subject. It goes only in the team email body and `failure_json`. Task 7.
4. Legacy failed rows with raw `Generation failed: ...` text and no `failure_json` must not leak it through `/progress`. Task 7.
5. A provider outage must not flood the team mailbox with one email per interview round. Task 6.

## File Structure

- Create `consultant-service/app/pipeline/failure.py`: `StageFailed`, `STAGE_WORK`, `client_reason`, `fail_run`, `stall`.
- Create `consultant-service/app/produced.py`: `documents_for(req)`.
- Create `consultant-service/app/pipeline/method_note.py`: `method_note(req, release)`.
- Create `consultant-service/tests/test_honest_failure.py`: the failure matrix and contract tests.
- Create `consultant-service/tests/engine/refreeze_r30.py`: regenerates the manifest (under `tests/engine`, which the freeze excludes).
- Modify `app/mailer.py`, `app/models.py`, `app/config.py`, `app/routers/requests.py`, `app/routers/discovery.py`, and the stage modules named per task.
- Modify frontend `src/api/consultant.ts`, `src/routes/StudioPage.tsx`, `src/components/consult/{Answer,Interview,Thinking}.tsx`, `src/utils/runBoard.ts`.

---

### Task 0: Baseline

**Files:** none changed. Scratch output only.

- [ ] **Step 1:** `mkdir -p /d/bmv-pytest-tmp`, then run the full consultant suite with `-rf` and save the failing node ids, sorted, to `<scratchpad>/baseline-failures.txt`. Expected summary today: `45 failed, 1734 passed, 1 skipped`. If the count differs, record the real one; it is the baseline.
- [ ] **Step 2:** Run `npx tsc -p tsconfig.app.json --noEmit` and `npm run lint` in `frontend/`; record `0 errors` and the warning count.
- [ ] **Step 3:** Record `git rev-parse --short HEAD`. No commit.

---

### Task 1: The failure module, the mailer, the column

**Files:**
- Create: `app/pipeline/failure.py`
- Modify: `app/mailer.py`, `app/models.py` (add `failure_json: Mapped[str | None] = mapped_column(Text, nullable=True)` after `progress_detail`), `app/config.py` (add `STALL_MAIL_WINDOW_SECONDS: int = int(_env_or("STALL_MAIL_WINDOW_SECONDS", "300"))`)
- Test: `tests/test_honest_failure.py`

**Interfaces:**
- Produces, in `app/mailer.py`:
  `send_now(to: str | None, subject: str, body: str) -> bool` (synchronous; `False` when `to` is empty, SMTP is unconfigured, or the send raises; never raises).
  `notify_team_failure(ref: str | int, business_name: str, stage: str, cause: str) -> bool` (to `settings.SMTP_USER`; subject `Run failed: {business_name} ({stage})`; body has the run URL via `_run_url`, the stage, the time, and `cause[:500]`).
  `notify_team_stall(kind: str, business_name: str | None, round: int | None, cause: str) -> bool`.
  `notify_owner_ready(...)` keeps its arguments and now returns `bool` by sending through `send_now`.
- Produces, in `app/pipeline/failure.py`:
  `class StageFailed(Exception)` with `__init__(self, stage: str, cause: str | BaseException)` and attributes `stage: str`, `cause: str` (text of the cause, at most 500 characters).
  `STAGE_WORK: dict[str, str]`, mapping a stage key to the plain-words work in progress. Required keys: `reading, researching, analyzing, capacity, diagnosing, challenging, consulting, answering, planning, decomposing, shaping, blueprint, technical, playbook, roadmap, quality, screens, email`. Values read after "we were", for example `blueprint` is `writing your blueprint`, `playbook` is `writing your operations manual`, `decomposing` is `breaking your business down into its parts`.
  `client_reason(stage: str, team_notified: bool) -> str`: `Our side failed while we were {work}.` plus ` We have been told and are looking into it.` only when `team_notified`; an unknown stage uses `working on your engagement`.
  `fail_run(db: Session, request_id: int, stage: str, cause: str) -> bool`: returns `team_notified`.
  `stall(kind: str, *, business: str | None, round: int | None, cause: str) -> bool`: throttled to one mail per `kind` per `settings.STALL_MAIL_WINDOW_SECONDS` using a module-level dict keyed by kind and `time.monotonic()`.

- [ ] **Step 1: Write the failing tests** in `tests/test_honest_failure.py`:
  - `test_client_reason_claims_notification_only_when_it_happened`: `client_reason("blueprint", True)` contains `We have been told`; `client_reason("blueprint", False)` does not; neither contains `try again`, `Exception` or `pipeline`.
  - `test_every_stage_the_orchestrator_emits_has_plain_words`: `STAGE_WORK` holds every required key.
  - `test_send_now_returns_false_when_unconfigured`: with `SMTP_PASSWORD` empty, `send_now("a@b.c", "s", "b")` is `False` and nothing raises.
  - `test_fail_run_stops_the_run_and_records_the_facts` (uses a real `Request` row and a monkeypatched `mailer.send_now` recorder): after `fail_run(db, id, "blueprint", "OpenRouter 503: sk-or-v1-SECRET")` the row has `status == "failed"`, `is_failed`, `not is_generating`, `stage == "failed"`; `progress_detail == client_reason("blueprint", True)`; `failure_json` parses to `{stage, at, cause, team_notified: True, reason}`; exactly one email went to `settings.SMTP_USER`; the stored `progress_detail` and `stage_label` do not contain `SECRET`.
  - `test_fail_run_with_mail_down_still_fails_cleanly` (`send_now` returns `False`): same row state, `team_notified` false, `progress_detail` has no `We have been told`. (Review Focus 2.)
  - `test_stall_is_throttled`: two `stall("interview", ...)` calls inside the window send one mail and the second returns `False`; after advancing the monotonic clock past the window (monkeypatch `time.monotonic`) a third sends. (Review Focus 5.)
- [ ] **Step 2:** Run `tests/test_honest_failure.py`. Expected: FAIL, `ModuleNotFoundError: app.pipeline.failure`.
- [ ] **Step 3:** Implement `send_now`, make `_send` reuse it, and add the two notify functions in `app/mailer.py`. Implement `failure.py`; `fail_run` does `db.rollback()` first, loads the row, sets the failed fields, writes `failure_json`, then `emit(db, id, "failed", "Our side failed and the run stopped", pct, detail=client_reason(...))`. Add the model column and the config setting.
- [ ] **Step 4:** Run `tests/test_honest_failure.py`. Expected: all pass.
- [ ] **Step 5:** Commit `feat(failure): one place where a run fails, tells the client plainly and emails the team`.

---

### Task 2: The orchestrator uses it

**Files:**
- Modify: `app/pipeline/orchestrator.py`
- Test: `tests/test_honest_failure.py`

**Interfaces:**
- Consumes: `StageFailed`, `fail_run` from Task 1.
- Produces: `run`, `run_build` and the stage runners fail through `fail_run`; a bare exception is attributed to the stage in `row.stage` at the moment it escaped.
- Test harness produced for later tasks: fixture `pipeline_with_only(real: str)` in `tests/test_honest_failure.py` that creates a `Request` row, monkeypatches every stage entry point the orchestrator calls (`research.research_business`, `analyze.analyze_business`, `capacity.read`, `diagnose.diagnose`, `decide.decide`, `answer.write`, `plan.plan_integration`, `decompose.decompose_business`, `extras.build_extras`, `blueprint.write_blueprint`, `blueprint.write_technical_plan`, `playbook.write_playbook`, `action_plan.write`, `qa_experts.review_quality`, `integrity.enforce`, `screens.generate.build`) to stubs returning minimal valid values, except the one named, and makes `app.ai.provider.chat` raise `AiProviderError("OpenRouter 503: sk-or-v1-SECRET")`. It records `mailer.send_now` calls. Tasks 3 to 5 add one parametrized row per stage.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_stage_that_raises_stage_failed_stops_the_run`: stub `analyze.analyze_business` to `raise StageFailed("analyzing", "boom")`; after `orchestrator.run(id)` the row is failed with `failure_json.stage == "analyzing"` and one team email.
  - `test_a_bare_exception_is_attributed_to_the_stage_that_was_running`: stub `blueprint.write_blueprint` to `raise RuntimeError("db locked")`; `failure_json.stage == "blueprint"`.
  - `test_a_failure_in_a_superseded_build_is_not_a_failure` (Review Focus 1): in the stub, set `row.phase_started_at` to a new value then raise `StageFailed`; after `run_build` the row is not marked failed and no email was sent.
  - `test_decomposition_that_returns_nothing_stops_the_run`: stub `decompose.decompose_business` to return `None`; the run fails with stage `decomposing` and never reaches the `done` status.
  - Matrix row `capacity`: with only `orchestrator._read_capacity` real and `capacity.read` returning `(None, None, "boom")`, the run fails with stage `capacity`.
  - `test_an_undelivered_ready_email_alerts_the_team`: a finished run whose `mailer.notify_owner_ready` returns `False` while `mailer.enabled()` is true ends `done` (the package exists) and one `notify_team_failure(..., "email", ...)` is sent.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Replace `_fail` in `orchestrator.py` with a call to `failure.fail_run`. In `run` and `run_build` add `except StageFailed as exc: fail_run(db, request_id, exc.stage, exc.cause)` before the generic `except Exception`, which reads the stage from `db.get(Request, id).stage`. In `_decompose_with_preflight`, delete `if not decomposition: return None`; when `decompose_business` returns nothing raise `StageFailed("decomposing", "the breakdown returned nothing usable")`. In `_build_stages`, remove the `try/except` around `screens_stage.build` so exceptions propagate, wrapped as `StageFailed("screens", exc)`. In `_read_capacity`, after logging usage, `raise StageFailed("capacity", error)` when `error is not None`. At the end of `_build_stages`, use the boolean `mailer.notify_owner_ready` now returns: when it is `False` and `mailer.enabled()` is true, log at error level and call `mailer.notify_team_failure(ref, business_name, "email", "the ready email to the client was not delivered")`; the run stays `done`. Leave the preflight-exhausted DRAFT path and the hollow-run guard unchanged.
- [ ] **Step 4:** Run `tests/test_honest_failure.py` and `tests/test_hollow_run_is_not_done.py`. Expected: pass.
- [ ] **Step 5:** Commit `fix(orchestrator): a failed stage stops the run and tells everyone, once`.

---

### Task 3: Delete the canned answers

**Files:**
- Modify: `app/pipeline/analyze.py`, `app/pipeline/consult.py`, `app/pipeline/decide.py`, `app/pipeline/plan.py`
- Modify (if only `consult()` uses it): delete `app/prompts/consult.j2`
- Test: `tests/test_honest_failure.py`; update `tests/test_consultancy_layers.py`, `tests/test_run5*.py` or any other test that asserts the fallbacks (find them with `Grep` for `Front-Desk`, `_fallback`, `Missed inquiries`, `consult.consult`)

**Interfaces:**
- Produces: `analyze.analyze_business(db, request_id) -> dict` and `decide.decide(db, request_id, analysis) -> dict` raise `StageFailed("analyzing", exc)` and `StageFailed("consulting", exc)`; `plan.plan_integration` raises `StageFailed("planning", exc)`. `consult.py` keeps only `_format_diagnosis(req) -> str`.

- [ ] **Step 1: Write the failing tests**, three rows in the matrix (`analyzing`, `consulting`, `planning`): with only that stage real and `provider.chat` raising, the run ends failed with that stage, one team email, and afterwards `business_analysis_json`, `consulting_recommendations_json` and `roles_json` contain none of `front-desk`, `Front-Desk AI`, `AI Analyst`, `Missed inquiries`. Add `test_decide_does_not_default_a_confidence`: a model reply without `confidence` leaves `result.get("confidence") is None`.
- [ ] **Step 2:** Run. Expected: FAIL (the fallbacks still return content).
- [ ] **Step 3:** In `analyze.py` delete `_fallback` and raise `StageFailed` in the `except`. In `decide.py` replace the fall-back-to-`consult.consult` with `raise StageFailed("consulting", exc)` and stop defaulting `confidence` to `"medium"` (drop the key when invalid). In `consult.py` delete `consult()` and `_fallback`; `Grep` for `consult.consult` and for `consult.j2` first and delete the prompt only if nothing else renders it. In `plan.py` delete `_fallback` and raise `StageFailed("planning", exc)`; keep `_normalize`.
- [ ] **Step 4:** Run the matrix and the updated older tests; then the whole top-level suite. Expected: no failure outside the baseline set and the frozen-hash tests.
- [ ] **Step 5:** Commit `fix(pipeline): no canned recommendation, analysis or roles stands in for a stage that failed`.

---

### Task 4: The document stages stop instead of thinning the package

**Files:**
- Modify: `app/pipeline/decompose.py` (lines near 491, 499, 539, 587), `app/pipeline/extras.py` (near 526 and the results loop), `app/pipeline/blueprint.py` (`_markdown_call`), `app/pipeline/playbook.py` (near 84), `app/pipeline/action_plan.py` (near 152 and 169), `app/pipeline/answer.py` (near 275 and 292)
- Test: `tests/test_honest_failure.py`

**Interfaces:**
- Produces: `decompose.decompose_business` raises `StageFailed("decomposing", ...)` on a failed call, an empty module list, or any module whose `spec` or `tech` call failed. `extras.build_extras` raises `StageFailed("shaping", ...)` when any layer errored, after its usage is logged. `blueprint._markdown_call(db, request_id, purpose, prompt, *, stage: str, max_tokens=4000) -> str` raises `StageFailed(stage, exc)`; callers pass `"blueprint"` or `"technical"`. `playbook.write_playbook` raises `StageFailed("playbook", ...)`. `action_plan.write` still saves `{"status": FAILED}` and also raises `StageFailed("roadmap", ...)`; any caller outside the orchestrator (find with `Grep` for `action_plan.write`) catches it, keeps the saved FAILED state, and calls `mailer.notify_team_failure`. `answer.write` raises `StageFailed("answering", ...)` when the call fails or no candidate survives its retries.
- Left alone on purpose: `qa_experts` (the release gate already states a missing audit as the reason a package is a draft), the playbook's post-processing `except Exception: pass`, site research, evidence reading (Step 6).

- [ ] **Step 1: Write the failing tests**, one matrix row each for `decomposing`, `shaping`, `blueprint`, `technical`, `playbook`, `roadmap`, `answering`, `screens`: the run ends failed with that stage and one team email, the client-visible fields contain no `SECRET`, and `status` is never `done`. Add `test_one_module_spec_failing_stops_decomposition` (stub `provider.chat` to fail only the `module_spec` calls) expecting stage `decomposing`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Make the changes above. Keep each stage's `log_usage(success=False, ...)` call before raising so the cost ledger still records the failure.
- [ ] **Step 4:** Run the matrix and the top-level suite. Expected: no new failures outside the baseline and the frozen-hash tests.
- [ ] **Step 5:** Commit `fix(pipeline): a document stage that fails stops the run instead of shipping a thinner package`.

---

### Task 5: The diagnosis tells the truth about what ran

**Files:**
- Modify: `app/pipeline/diagnose.py`, `app/pipeline/consult.py` (`_format_diagnosis`), `app/routers/requests.py` (`_thinking`, and the decision payload near line 133 so `not_tested` reaches the client)
- Test: `tests/test_honest_failure.py`, `tests/test_consultation_flow.py` if it pins the old shape

**Interfaces:**
- Produces: `diagnose.diagnose(...)` raises `StageFailed("diagnosing", ...)` when the model call fails, when fewer than `MIN_HYPOTHESES` usable explanations come back, or when every hypothesis test crashed. A single crashed test stays in the diagnosis with `test.not_tested == True`. Narrated `verdict` lines carry `not_tested: bool`. `_thinking(req)` and the decision payload pass `not_tested` through.

- [ ] **Step 1: Write the failing tests:** matrix row `diagnosing`; `test_all_tests_crashing_stops_the_run`; `test_one_crashed_test_is_marked_not_tested_and_the_diagnosis_continues` (stub `_call` to raise for one statement); `test_not_tested_reaches_the_narrated_trail`; `test_the_prompt_text_says_not_tested_not_untestable` for `consult._format_diagnosis`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Do not call `narrate` or touch the session from a pool worker (the file documents why).
- [ ] **Step 4:** Run those tests and `tests/test_consultation_flow.py`. Expected: pass.
- [ ] **Step 5:** Commit `fix(diagnosis): a test we could not run is not reported as the client's figures being too thin`.

---

### Task 6: The interview stalls honestly

**Files:**
- Modify: `app/routers/discovery.py`
- Test: `tests/test_honest_failure.py`; rewrite or delete the fallback tests in `tests/test_discovery.py` (lines 53 to 109) and `tests/test_consultancy_layers.py` (line 344)

**Interfaces:**
- Consumes: `failure.stall`.
- Produces: `/api/discovery/scope` and `/api/discovery/interview` answer a failed model call, or an empty first round, with HTTP 503 and `detail` set to the plain sentence `Our side stalled while we were preparing your next question. We have been told. Your answers so far are still on this page.` (a scope-specific sentence for `/scope`: `...while we were writing the questions we need to ask you...`). `/api/discovery/questions` is deleted along with `_FALLBACK_OPERATING`, `_FALLBACK_OPENING`, `_FALLBACK_CAPABILITY`. `fallback_facts` stays, used only to guarantee the two launch-required facts (`business_name`, `business_description`) on `shape_scope`; `shape_scope` no longer pads to `FACTS_MIN` from the generic list and no longer returns `source: "fallback"`.

- [ ] **Step 1: Write the failing tests:** `test_scope_failure_is_a_503_and_mails_the_team_once`; `test_interview_round_failure_is_a_503`; `test_an_empty_first_round_is_a_stall_not_stock_questions`; `test_questions_endpoint_is_gone` (404); `test_shape_scope_pads_only_the_two_required_facts`; `test_repeated_interview_stalls_send_one_mail` (Review Focus 5, through the endpoint).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the above. `Grep` for other readers of the deleted names before removing them.
- [ ] **Step 4:** Run `tests/test_honest_failure.py`, `tests/test_discovery.py`, `tests/test_consultancy_layers.py`, `tests/test_consultation_flow.py`. Expected: pass.
- [ ] **Step 5:** Commit `fix(interview): when our side stalls the client is told, not handed stock questions or told they are done`.

---

### Task 7: What `/progress` tells the client

**Files:**
- Create: `app/produced.py`
- Modify: `app/routers/requests.py` (`get_progress`)
- Test: `tests/test_honest_failure.py`

**Interfaces:**
- Produces: `produced.documents_for(req) -> list[dict]`, each `{"key": str, "title": str, "state": "ready" | "writing"}`, in order: `blueprint` (ready when `mvp_blueprint` is set, writing when `stage == "blueprint"`), `technical` (`technical_plan` / `"technical"`), `operations` (`playbook_json` / `"playbook"`), `roadmap` (a loaded action plan with phases / `"roadmap"`), `system` (`screens_json` / `"screens"`), `ai_team` (only when `consulting_recommendations_json` holds a non-empty `recommended_ai_employees`; always `ready`). A document neither ready nor being written is omitted.
- `/progress` gains `"failure": {"reason": str, "team_notified": bool} | None` read from `failure_json`, and `"documents": documents_for(req)`. For a row with `is_failed` true, `label` and `detail` come from `failure_json.reason` when present; with no `failure_json` they are `Our side failed and the run stopped.` and `None`.

- [ ] **Step 1: Write the failing tests:** `test_documents_follow_what_exists` (a row with only a blueprint and `stage == "technical"` yields `[blueprint ready, technical writing]`); `test_no_ai_team_row_when_no_agents`; `test_progress_failure_carries_only_the_client_reason` (Review Focus 3: a failed row with `SECRET` in `failure_json.cause` and in the legacy fields; the JSON response contains no `SECRET`); `test_a_legacy_failed_row_does_not_leak_its_raw_detail` (Review Focus 4: `stage_label = "Generation failed: Traceback..."`, `failure_json` null).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `documents_for` as a pure function and extend `get_progress`.
- [ ] **Step 4:** Run `tests/test_honest_failure.py`. Expected: pass.
- [ ] **Step 5:** Commit `feat(progress): tell the client what failed in plain words and which documents exist`.

---

### Task 8: The failure and stall screens

**Files:**
- Modify: `frontend/src/api/consultant.ts`, `frontend/src/routes/StudioPage.tsx`, `frontend/src/components/consult/Interview.tsx`
- Delete from `consultant.ts`: `fetchDiscoveryQuestions`; from `StudioPage.tsx`: `LOCAL_DISCOVERY_FALLBACK` and its use at the first-round catch

**Interfaces:**
- Produces, in `consultant.ts`: `class StalledError extends Error { kind: 'ours' | 'connection'; message: string }`, thrown by `fetchScope` and `fetchInterviewRound` (kind `ours` for a 503, using `response.data.detail` as the message; kind `connection` when there is no response, message `Your connection dropped. Continue when it is back.`). `StudioProgress` gains `failure?: { reason: string; team_notified: boolean } | null` and `documents?: { key: string; title: string; state: 'ready' | 'writing' }[]`.
- `Interview.tsx` accepts `stalled: { message: string; onContinue: () => void } | null` and, when set, renders a `role="alert"` block in place of the next question with a single `Continue` button.

- [ ] **Step 1:** In `StudioPage.tsx` hold `stalled` state. In `startBrief` and `askRound`, on `StalledError` set `stalled` with a `onContinue` that clears it and re-runs the same call (`startBrief` after resetting `discoveryKey.current`, or `askRound(n)`); remove the branches that call `askRound(1, [])` and `setInterviewDone(true)` on error.
- [ ] **Step 2:** In the `failed` act, render `progress.failure?.reason` as the paragraph; with no `failure`, render `Our side failed and the run stopped.`; never render `p.detail`; replace the `Try again` button with `Start a new engagement`, full width below the `sm` breakpoint. Remove the `Something in the pipeline failed...` string. Change `setFailureDetail(p.detail ?? null)` to read `p.failure?.reason`.
- [ ] **Step 3:** Run `npx tsc -p tsconfig.app.json --noEmit` and `npm run lint`. Expected: no output; 0 errors, no new warnings.
- [ ] **Step 4:** Using the `run` skill, start the service with a scratch `DATABASE_URL` and Vite; seed one failed row with a `failure_json` and open it, then force `/api/discovery/interview` to return 503 (a one-off monkeypatch in a throwaway script, not committed). Capture screenshots of the failed page and the stall block at 390 px and 1440 px width. Expected: no horizontal scroll, button reachable, no text clipped, no `try again`, no `pipeline`. Save the screenshots in the scratchpad and quote their paths.
- [ ] **Step 5:** Commit `fix(site): the failure and stall pages say what happened, plainly, on a phone and a desktop`.

---

### Task 9: The answer screen stops promising what it cannot keep

**Files:**
- Modify: `frontend/src/components/consult/Answer.tsx`, `frontend/src/components/consult/Thinking.tsx`, `frontend/src/utils/runBoard.ts`, `frontend/src/routes/StudioPage.tsx`, `frontend/src/api/consultant.ts`

**Interfaces:**
- `Answer` gains props `documents: { key: string; title: string; state: 'ready' | 'writing' }[]` and `mailPromise: boolean`; the fixed `DOCS` array and `docState` progress ranges are deleted. `BoardHypothesis` gains `notTested?: boolean`.

- [ ] **Step 1:** `Answer.tsx` renders one row per entry in `documents` (`ready` shows `Ready`, `writing` shows `Writing`); with none it shows `Your plans start in a moment.` The line `You don't need to wait here. We'll email you when it's ready.` renders only when `mailPromise` is true; otherwise `This page updates itself as each document is finished.` Remove the `?? 'medium'` default: confidence is shown only when the decision carries one.
- [ ] **Step 2:** `StudioPage.tsx` passes `documents={progress?.documents ?? []}` and `mailPromise={Boolean(progress?.notify?.enabled)}` to every `<Answer>`.
- [ ] **Step 3:** `runBoard.ts` reads `not_tested` from the narrated verdict step into `notTested`. `Thinking.tsx` `Verdict` returns a chip reading `We couldn't run this test` when `notTested`; the chip `Couldn't check with your figures` stays only for a real `untestable` verdict. The decision-screen list in `Answer.tsx` (the `Couldn't check` label) shows the same distinction.
- [ ] **Step 4:** Run `npx tsc -p tsconfig.app.json --noEmit` and `npm run lint`. Expected as in Task 8.
- [ ] **Step 5:** With the `run` skill, load a seeded building row and a thinking row with one `not_tested` hypothesis; screenshot at 390 px and 1440 px; expected: rows follow `documents`, promise line follows `notify.enabled`, chip text correct, no horizontal scroll.
- [ ] **Step 6:** Commit `fix(site): the document list, the email promise and the test verdicts say only what is true`.

---

### Task 10: The method page, then re-freeze

**Files:**
- Create: `app/pipeline/method_note.py`, `tests/engine/refreeze_r30.py`
- Modify: `app/pipeline/export_pdf.py` (`_evidence_flowables`, the closing paragraph near line 1307 and the sources bullet near 1248), `tests/engine/r30_manifest.json`, `tests/engine/test_engine_r30_frozen.py` (line 79), `tests/engine/test_engine_mutation_manifest.py` (line 526)
- Test: `tests/test_honest_failure.py`

**Interfaces:**
- Produces: `method_note(req, release: dict) -> dict` with keys `how: str`, `checks_ran: list[str]`, `not_verified: list[str]`. `how` is exactly `Build My Version's analysis system produced this engagement from the facts you gave us and the files you sent.` `checks_ran` lists the quality-bench checks that passed (`"{label}"` from `qa_report_json.checks` where `passed`) and `The integrity layer ran on this content.` when `integrity.current_report(req)` exists. `not_verified` is `release["reasons"]`.
- `python tests/engine/refreeze_r30.py --commit <short-sha>` rewrites `r30_manifest.json` from `collect_frozen_files()` and `sha256_of()` in `test_engine_r30_frozen.py`, setting `commit`, `file_count` and `files`.

- [ ] **Step 1: Write the failing tests:** `test_method_note_for_a_draft_lists_what_was_not_verified`; `test_method_note_for_a_final_run_lists_the_checks_and_nothing_outstanding`; `test_the_method_page_no_longer_says_every_claim_was_checked_before_release`: render `_evidence_flowables` for a draft request and assert no paragraph contains `was checked against` or `before release`, and that `how` appears; `test_the_method_page_has_no_review_or_confidence_language` (no `reviewed`, `human`, `not confident`, `AI-generated` in any paragraph).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `method_note`; in `_evidence_flowables` call it with `release_status(req)`, replace the unconditional closing sentence and the sources bullet "each numerical claim checked" with `how`, one line per `checks_ran`, and under a `Not verified` sub-head the `not_verified` reasons (omitted when empty).
- [ ] **Step 4:** Run `tests/test_honest_failure.py`, `tests/test_consultancy_layers.py`, `tests/test_deck_layout.py`. Expected: pass.
- [ ] **Step 5:** Commit all code from Tasks 1 to 10 if any remain uncommitted. Note the last code commit's short sha `S`.
- [ ] **Step 6:** Write `tests/engine/refreeze_r30.py`; run `python tests/engine/refreeze_r30.py --commit S`; change the two asserted constants to `S`.
- [ ] **Step 7:** Run `tests/engine/test_engine_r30_frozen.py`. Expected: all pass. Commit `test(engine): re-freeze r30 at S` (use the real sha).
- [ ] **Step 8: Final verification.** Run the whole consultant suite with the baseline command. Expected: the failing set is a subset of `<scratchpad>/baseline-failures.txt` and the summary shows no more failures than the baseline; the new `tests/test_honest_failure.py` is all green. Run the frontend `tsc` and `lint`. Quote every summary line in the report.

## Self-review

- **Spec coverage (Step 1):** one failure path (Tasks 1, 2); three canned fallbacks deleted and the interview stall (Tasks 3, 6); `not_tested` read and rendered (Tasks 5, 9); a failed breakdown stops the run (Tasks 2, 4); the email promise gated and a failed send treated as ours (Task 9 for the promise; a failed send of the ready email alerts the team in Task 2); document list read from what was produced (Tasks 7, 9); method statement (Task 10); acceptance "a refusal injected at each stage" is the matrix: `capacity` (Task 2), `analyzing`, `consulting`, `planning` (Task 3), `decomposing`, `shaping`, `blueprint`, `technical`, `playbook`, `roadmap`, `answering`, `screens` (Task 4), `diagnosing` (Task 5), and the interview `scope` and `interview` (Task 6). `reading` (the client's files) and `researching` (the client's site) stay fail-open on purpose until Step 6, and `quality` keeps its draft-names-its-reason behaviour.
- **Calls made in this plan, for the owner:** stopping on failure will raise the visible failure rate, because model flubs that used to degrade quietly now end the run; the quality bench, its polish pass, adjudication and the integrity layer keep their existing "draft names its reason" behaviour; site research and file reading keep failing open until Step 6; the interview's team email carries the business name and round but no reference until Step 6 gives the interview a server-side session; the team alert needs `SMTP_PASSWORD` set in production, otherwise `team_notified` is false and the client copy says nothing about being told.
- **Step 1 owes Step 3** the six-file package and the answer page; nothing here changes the PDF structure except the method page.
