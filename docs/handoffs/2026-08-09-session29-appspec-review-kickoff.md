# Session 29 kickoff — review the AppSpec workflow and make it state of the art

Paste this whole file as the first message.

---

Read `HANDOFF.md`'s session 28 block and `docs/evidence/session28/` first, then do
the work below. **The goal for this session is that every request reaches the
customer**, and AppSpec is what stands between us and that: since request 129
there have been **15 upstream deaths and 12 are AppSpec**, each ending *"and
fallback is disabled."* Those runs produced nothing a customer could open.

This is a **review of the workflow**, not only a bug hunt. Fix what is broken,
but also answer whether the design is the right one.

## Settled — do not relitigate

- **`APPSPEC_MODE` stays `on`.** An earlier A/B established that apps built with
  AppSpec are better. Do not switch to `shadow` or `off` to raise the ship rate;
  that trade was considered and rejected by the owner on 2026-08-09.
- **Fix the pipeline, never a generated preview.**
- A degraded generic ship is a defect, not a fallback (session 18 ruling).

## What is already known — start from these, do not re-derive

Validator issues across every stored revision since request 129, counted from
`app_spec_revisions.deterministic_validation_json->'issues'`:

    code                              occurrences   requests
    state_assertion_state_required         15           5     fix B landed, UNPROVEN live
    trace_evidence_mismatch                 4           4     OPEN
    app_spec_schema_parse_failed            7           3     OPEN — see collapse below
    page_initial_state_count                3           3     FIXED 62cb26d
    (long tail: missing_required_field 16, unexpected_field 10, … all in 1 request each)

Three specific findings:

1. **`page_initial_state_count` was ours, not the model's.** `ai_features.py`
   injected `STATE-AI-HUB-READY` with a hardcoded `"initial": True` onto
   `PAGE-AI-FEATURES`, guarded only by *"is this id already present"* — which
   cannot see the state the model wrote under its own name. The pipeline added
   the second initial state to a page it requires, and its own validator killed
   the run. **Assume other injectors have the same shape until you have checked
   them** (`bind_ai_features_to_app_spec` and anything else that appends to
   `states`, `pages`, `requirements`, `capabilities`, `evidence`,
   `traceability`).
2. **`app_spec_schema_parse_failed` is collapse, not truncation.** Request 143's
   `schema_repair` returned **473 completion tokens with `finish_reason: stop`**
   where a full spec is 8,000-11,000. The candidate then failed every top-level
   required field. The repair prompt already carries an anti-collapse line and it
   is not holding.
3. **Transport is real but secondary**: 7 of 75 `authoring`+`repair` asks since
   129 returned zero tokens.

Ruled out already, so do not spend time on it: the **full** deterministic report,
including nested `detail` and child issues, *is* passed to the repair prompt
unbounded (`builder.py`, `deterministic_report_json`). The repair model is not
being starved of diagnosis.

Live config, read out of the running process: `APPSPEC_MODE=on`,
`APPSPEC_MAX_CALLS=8`, `APPSPEC_MAX_REPAIR_ATTEMPTS=3`,
`APPSPEC_REPAIR_MAX_TOKENS=24000`, `APPSPEC_MODEL=google/gemini-2.5-flash`
(93 % usable across 129-161, max observed output 15,248 tokens).

## The work, in order

**1. Close the three open failure codes.** `trace_evidence_mismatch` (4
requests, identical message every time — so it is systematic, not creativity),
the `schema_repair` collapse, and confirm fix B's `state_assertion_state_required`
holds. For each, the question is the same one fix B answered: **does the error
tell the model a legal move?** An error with no legal move is a dead run, not a
retry.

**2. Audit every validator rule for whether it should kill a run.** The heal
ladder (`domain/appspec/sanitize/heal.py`) already exists. For each code, decide:
deterministic heal, model repair, or fatal. A rule that is mechanical
(`unexpected_field`, an id that needs uniquifying) and is currently fatal is
costing runs for nothing.

**3. Answer the design question, with a recommendation.** Every repair re-emits
the **entire ~10,000-token document**, so one bad field anywhere costs a full
regeneration, and a regeneration can collapse or die on transport. Is
whole-document repair the right shape? Consider and cost at least: patch-based
repair (RFC 6902 / a targeted edit list), section-scoped repair (re-emit only
`states`, only `traceability`), and moving mechanical codes entirely into
deterministic heals. **Measure the convergence curve before recommending** — how
many repairs do runs that succeed actually take, from `ai_usage_events`.

**4. Then the imagery item, already approved by the owner.** 165 was withheld on
`visual_defect_severe`: its cake gallery is full of bread because the binding
ranks a pool searched for the *business*. Build per-item queries — ask the photo
index with each item's own words. Design note in
`catalogue_contract/photo_binding.py`.

## Gates — every change

- **Full suite green.** Baseline is **2,295 passed / 1 skipped / 0 failed**.
  Exactly this invocation; anything else lies:

      docker run --rm -v "$PWD:/repo" -w /repo/backend \
        -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
        --entrypoint sh bmv-local-api -c 'pip install -q pytest; python -m pytest tests/ -q'

  Plain `docker run` without `--entrypoint sh` hangs. `docker compose exec api`
  fakes failures. Always `cd /Users/maurice/Documents/Dev/BMV` first — a stray
  `cd backend` makes `$PWD` mount the wrong root.
- **A mutation sweep per fix, zero survivors.** Anchor strings on the source
  verbatim (`python3 -c "print(repr(line))"`) — a sweep that reports SKIP is a
  miscount, not a pass. An equivalent mutant must be *proved* with data and
  recorded, never argued.
- **Evidence file per finding** in `docs/evidence/session29/`, with the numbers.

## Traps this project has paid for

- **Count the whole artifact; never conclude from a sampled window.** A
  900-character sample produced a wrong claim in session 28 that had to be
  corrected on the file that carried it.
- **Read `ai_usage_events` by `finish_reason`, not by run outcomes.** A retry
  ladder hides a misclassifier; a quiet deterministic fallback hides a dead
  stage. Both happened.
- **Test fixtures are the usual survivor.** A fixture missing `roles` made four
  AppSpec tests pass while exercising nothing. Before believing a green test,
  check it can fail.
- **`apply_workspace_guards` runs before every build attempt** — nothing
  non-idempotent or networked goes in it.
- **Restart `bmv-api` and prove behaviour, not presence** — `/app/backend` is a
  bind mount but uvicorn holds the old modules (`UVICORN_RELOAD=false`).
- **The OpenRouter key is shared.** Bracket every run with a balance probe and
  attribute only the delta. No leak alarms.

## Money

**$0.176 left — below the cost of one run (~$0.33).** Steps 1-3 are almost
entirely offline: the corpus holds 300 stored revisions and every rejected
payload. **Do the offline work first and say what a trio would answer before
asking for a top-up.** When one is funded, the three briefs are in
`docs/evidence/session28/launch_duo.py` and `session27/launch_trio.py`;
simultaneous start, never the 60 s stagger.

## Definition of done

1. Every open AppSpec code is either fixed, healed, or has a written reason it
   must stay fatal.
2. Every spec injector is audited for the defect `62cb26d` fixed.
3. A recommendation on repair shape, backed by the measured convergence curve.
4. Suite green, sweeps clean, evidence written, `HANDOFF.md` updated with the
   H1 moved.
