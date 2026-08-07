# Model research — every slot, its job, and what should fill it (2026-08-06, session 16)

> **RESULTS (2026-08-07, session 18 — the funded session).** Every experiment below was run;
> verdicts with numbers in the "Funded-session results" section at the bottom. The adopted
> config: `TEXT_MODEL=google/gemini-3-flash-preview` (ADOPTED — cut pre-codegen serial time
> from ~342-389s to ~245-247s on both runs), `FIX_MODEL=z-ai/glm-5.2:nitro` (ADOPTED on a
> direct provider A/B probe — 3× throughput; the slot is unreachable in-pipeline on healthy
> briefs), `PREVIEW_APP_MODEL=deepseek/deepseek-v4-pro` (v4-flash REVERTED — cheaper but
> quality flat-to-slightly-worse and it does not touch the real bottleneck).

Researched overnight on the owner's request. Two inputs: the pipeline's OWN telemetry
(`ai_usage_events`, 3,200+ calls — the ground truth for what these models do HERE) and the
August-2026 OpenRouter landscape (web research; sources at the bottom). **No model was changed:
zero credits means zero verification runs, and a model swap without an A/B beside it would be a
guess wearing a lab coat.** Every recommendation below is staged as an experiment for the funded
session.

## The headline findings

1. **The two models that hurt are the page writer and the fixer.** `deepseek-v4-pro`
   (PREVIEW_APP_MODEL): 77 s average latency, 33% of outputs unusable. `z-ai/glm-5.2`
   (FIX_MODEL): 107 s average, **52% failure rate** — the slowest, most failing model in the
   stack is the one called when the build is already broken.
2. **GLM-5.2's failures are routing, not the model.** Artificial Analysis clocks GLM-5.2 at
   **189 tokens/sec** globally — the fastest of the candidates — while our local calls average
   107 s with half failing. OpenRouter's default "Balanced" routing is evidently handing us a
   bad provider. That means the fix might be one suffix (`:nitro` = route by speed), not a
   model change.
3. **The workhorse is fine but carries 80% of the bill and a deprecation date.**
   `gemini-2.5-flash` (TEXT_MODEL + vision): 2,727 calls, 14 s average, solid — but $24.21 of
   the $30.75 ever spent, because its output price ($2.50/M) is 15× the current budget coding
   models, and Google has scheduled 2.5-flash's Vertex retirement for 2026-10-16.
4. **The landscape moved.** Coding on OpenRouter is now dominated by DeepSeek V4 Flash
   (7.7T tokens served), Xiaomi MiMo-V2.5 (29% programming share), MiniMax-M3, and Tencent Hy3.
   The interesting property: the new leaders are BOTH faster and 4-15× cheaper than what we run.

## Per-slot analysis

Format: what the job actually is (from code), measured behavior (local telemetry, credit-error
noise excluded), candidates (Aug-2026 prices per 1M in/out), and the recommendation.

### PREVIEW_APP_MODEL — the page writer (the p50 lever)
- **Job:** writes every generated page: `slot_fill` (fills scaffold slots per page),
  `mock.ts` synthesis, utility pages (`codegen/generate.py`, `codegen/mock.py`). The dominant
  term in generation time — codegen is 315-437 s of AI per run.
- **Measured:** `deepseek/deepseek-v4-pro` — 61 calls, **77.4 s avg**, 28% fail,
  **33% unusable**. Also the host of the "truncated" class (HTTP 200, `finish_reason: error`,
  0 completion tokens) that burns slot_fill retries.
- **Candidates:**
  | model | $/1M in/out | speed | notes |
  |---|---|---|---|
  | `deepseek/deepseek-v4-flash` | 0.083 / 0.167 | 116-121 t/s | same family, efficiency-MoE (284B/13B active), 1M ctx, #1 by coding tokens served |
  | `xiaomi/mimo-v2.5` | 0.112 / 0.224 | 90 t/s | #1 programming usage share (29%) |
  | `minimax/minimax-m3` | 0.24 / 0.96 | — | multimodal, strong coding |
  | current v4-pro | 0.435 / 0.87 | 66.5 t/s | highest reasoning ceiling of the four |
- **Recommendation: A/B `deepseek-v4-flash` against the current v4-pro on the funded duo.**
  Same vendor (prompt-format continuity), ~2× the speed, ~5× cheaper, and the single most
  plausible p50 cut in the whole config. Judge on: slot_fill acceptance rate, typecheck error
  count, wall clock. If page quality drops, `mimo-v2.5` is the second arm. Also try the
  `:nitro` routing suffix on whichever wins — the provider-variance problem (see FIX_MODEL)
  plausibly affects this slot too.

### FIX_MODEL / QUALITY_FIX_MODEL — the fixer (the worst measured slot)
- **Job:** repairs build errors and TypeScript contract violations (`fix_agent.py`; chain is
  FIX_MODEL → PREVIEW_APP_MODEL → TEXT_MODEL, so a failing primary adds its full latency to
  every repair before the fallback even starts).
- **Measured:** `z-ai/glm-5.2` — 136 calls, **107 s avg, 51.5% fail, 27% unusable**. The
  pipeline's emergency service is its least reliable component.
- **The twist:** GLM-5.2 is benchmarked at **189 t/s** — fastest of all candidates. Our 107 s
  is not the model being slow; it's OpenRouter routing us to a bad/overloaded provider (or
  queueing). Two distinct fixes exist:
  1. **Keep the model, fix the routing:** `z-ai/glm-5.2:nitro` (throughput-prioritized
     routing) — one config token, tests the routing hypothesis directly.
  2. **Swap the model:** `deepseek-v4-flash` (cheaper than glm-5.2: 0.083/0.167 vs 0.28/0.88,
     and no observed provider problem in its family locally — v4-pro's issues are latency, not
     hard failures at glm's rate).
- **Recommendation: try `:nitro` first (zero-risk, reversible), and if failures persist, swap
  to `deepseek-v4-flash`.** Either way this slot needs its own measurement on the funded run:
  fix-loop wall clock and first-attempt success rate.

### TEXT_MODEL — the workhorse (fine today, wrong by October)
- **Job:** everything textual: blueprint, plans, proposals, reference analysis, quality
  repair fallback, plus the planning chain (`page_experience.py` pairs it with
  ARCHITECT_MODEL). 2,727 calls — 85% of all traffic.
- **Measured:** `google/gemini-2.5-flash` — 14.3 s avg, 7% fail, 10% unusable. Reliable.
  **But it carries $24.21 of the $30.75 total spend** (output at $2.50/M does it), and Google
  retires 2.5-flash on Vertex on **2026-10-16** — OpenRouter access may outlive that, but
  planning a successor is now due, not optional.
- **Candidates:** `gemini-3-flash-preview` ($0.50/$3.00 — the anointed successor, near-Pro
  reasoning, multimodal, low latency); `deepseek-v4-flash` ($0.083/$0.167 — 15× cheaper output
  but no vision); MiniMax-M3 ($0.24/$0.96, multimodal).
- **Recommendation: no change now — plan the migration.** The workhorse works, and mid-flight
  swaps of the highest-traffic slot without runs is how quality regressions ship. When funded:
  run one duo on `gemini-3-flash-preview` (like-for-like successor), and separately consider
  routing the pure-JSON planning calls (blueprint/plans/proposal) to `deepseek-v4-flash` —
  that split alone would cut the model bill roughly 5-10× at current mix.

### ARCHITECT_MODEL / CRITIC_MODEL — the architect and the critic
- **Job:** ARCHITECT emits the route/page architecture JSON (`codegen/architect.py`, one
  high-leverage call per run, plus planning-chain fallback). CRITIC judges generated pages
  (`codegen/critic.py`, text mode; vision mode prefers VISION_MODEL).
- **Measured:** `anthropic/claude-haiku-4.5` — only 24 calls (low volume), 29.6 s avg,
  29% fail. n is too small and the period too contaminated to indict it; total spend $0.59.
- **Pricing check (verified):** Haiku 4.5 is $1/$5 per 1M — the cheapest Claude; the next
  Claude tier (Sonnet 5 at $3/$15) is not justified for this pipeline's budget.
- **Recommendation: keep.** The architect's structured-JSON discipline is the thing the whole
  kind-contract system leans on, volume is tiny, and cost is noise. On the funded run, read
  the haiku error strings once — if the 29% is real (not credit-era noise), test
  `gemini-3-flash-preview` as the architect arm.

### VISION_MODEL — the screenshot reader
- **Job:** reference screenshot analysis + visual critic (`reference_analysis.py`,
  `critic.py:51` prefers it over CRITIC_MODEL when set).
- **Measured:** shares gemini-2.5-flash; works. The **commented-out
  `llama-3.2-11b-vision` line in .env is dead config** — 13 calls, 100% fail, last seen
  2026-07-29. Delete the comment block to stop the next reader trying it.
- **Recommendation: keep on gemini; migrate alongside TEXT_MODEL** (same deprecation clock).
  Cheaper multimodal candidate if cost ever matters here: MiniMax-M3.

### CODER_MODEL — tech-plan snippets
- **Job:** technical plan + visual demo HTML (`pipelines/technical_plan.py`,
  `visual_demo.py`). v1-era path, small outputs (162 tok avg).
- **Measured:** `qwen/qwen-2.5-coder-32b-instruct` — 90 calls, 22 s, 8% fail, cheap ($0.03
  total). It is a January-2025 model — ancient — but the job is trivial.
- **Recommendation: fold into whatever wins the PREVIEW_APP A/B** when convenient. Not worth
  its own experiment; one less model in the config is its own win.

### HTML_MODEL — REMOVED (2026-08-06, session 17, owner ruling)
- Was: v1 role-pages HTML + page QA (`pipelines/role_pages.py`, `page_qa.py`) on
  `openai/gpt-4o` — the most expensive model in the config on the least-used path.
- The telemetry closed the case: its 8 recorded calls were a single firing of the
  orchestrator's double-failure fallback (request 59, 2026-07-31), which spent the money and
  still left the request `failed` with no pages stored. The parachute did not open.
- Removed entirely: the modules, three prompt templates, the `/generate-pages` endpoint, the
  orchestrator fallback branches, and the config slot. `PREVIEW_APP_MODEL` now has its own
  default instead of inheriting HTML_MODEL's. A double-failed generation raises honestly;
  the customer keeps the retry endpoint. Pinned by `tests/application/
  test_v1_fallback_removed.py` + `mutate_v1_removal.py` (4 mutations / 0 survivors).

### SITE_CHAT_MODEL — the marketing site chat
- **Job:** the chat widget on the marketing site (`site_chat.py`).
- **Measured:** `openrouter/free` — **zero recorded calls.** Research says this IS a valid
  OpenRouter router id (Feb 2026): routes each request to a random free model that supports
  the request's features. Cost: $0. Quality/latency: whatever the free pool has that minute.
- **Recommendation: verify it actually answers once (one browser visit when funded), then
  leave it — $0 is the right price for a marketing widget.** If quality complaints arrive,
  `deepseek-v4-flash` at these prices is nearly free anyway.

### APPSPEC_* — off by owner ruling (2026-08-06)
Off; slots only matter if the on-vs-off head-to-head revives the stage. If it comes back
**enforced**, the authoring call becomes quality-critical and deserves the architect treatment
(haiku-4.5 or gemini-3-flash), not the cheapest slot — a rejected spec starves the whole run,
so acceptance rate is worth paying for there.

## The funded-session experiment list (in order of expected payoff)

1. **FIX_MODEL: `z-ai/glm-5.2:nitro`** — one token, tests the provider-routing hypothesis on
   the worst measured slot. If still failing: `deepseek/deepseek-v4-flash`.
2. **PREVIEW_APP_MODEL: `deepseek/deepseek-v4-flash` vs current** — the p50 lever. Judge
   slot_fill acceptance, typecheck errors, wall clock.
3. ~~HTML_MODEL → TEXT_MODEL, delete the dead llama comment~~ — DONE offline in session 17:
   the whole v1 path was removed instead (see HTML_MODEL section), llama comment deleted.
4. **TEXT_MODEL succession plan** — one duo on `gemini-3-flash-preview` before October;
   consider splitting pure-JSON planning calls to the cheap coding model.

Change ONE slot per run-pair and keep the seven-fix read-list as the constant judge. The
model-A/B runs must not be the same runs as the appspec on-vs-off experiment.

## Sources

- [OpenRouter: Best AI Models for Coding](https://openrouter.ai/collections/programming) — prices/IDs table
- [OpenRouter rankings analysis, July 2026](https://kvmnode.com/en/blog/2026-0604-openrouter-llm-rankings-trends-routing-guide.html) and [MacGPU weekly snapshot](https://macgpu.com/en/blog/2026-0602-openrouter-ten-dimension-weekly-snapshot-programming-collections-mac-routing.html) — usage shares
- [DeepSeek V4 Flash on OpenRouter](https://openrouter.ai/deepseek/deepseek-v4-flash) · [V4 Pro](https://openrouter.ai/deepseek/deepseek-v4-pro) · [Artificial Analysis: V4 Flash](https://artificialanalysis.ai/models/deepseek-v4-flash) · [V4 Pro](https://artificialanalysis.ai/models/deepseek-v4-pro) — pricing + tokens/sec
- [Artificial Analysis: GLM-5.2 vs V4 Flash](https://artificialanalysis.ai/models/comparisons/glm-5-2-vs-deepseek-v4-flash) · [MiMo-V2.5 comparison](https://artificialanalysis.ai/models/comparisons/deepseek-v4-flash-vs-mimo-v2-5-0424) — speed data
- [Gemini 3 Flash Preview on OpenRouter](https://openrouter.ai/google/gemini-3-flash-preview) · [Gemini 2.5 Flash](https://openrouter.ai/google/gemini-2.5-flash) · [Google: Gemini 3.6/3.5 announcement](https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-6-flash-3-5-flash-lite-3-5-flash-cyber/) — Gemini lineup + 2.5-flash retirement
- [OpenRouter free tier guide](https://klymentiev.com/blog/openrouter-free-tier) · [openrouter/free feature discussion](https://github.com/NousResearch/hermes-agent/issues/40717) — the `openrouter/free` router
- Anthropic first-party pricing via the claude-api reference (Haiku 4.5 $1/$5, Sonnet 5 $3/$15)

---

## Funded-session results (2026-08-07, session 18)

All runs: the duo3 briefs (Osteria Vinci restaurant / Cedar Point Lodge hotel) verbatim, one
.env line changed per run-pair, container force-recreated and the model verified from the
running process before every launch. Full telemetry in `ai_usage_events`; logs + launch logs
in `docs/evidence/session18/`.

### The structural finding that frames every verdict: runway starvation

Both baseline runs shipped `ready` at 578/573s but with 76% call failure — planning +
architect consumed ~342-389s of the 600s cap before the first page was written, then the
tail (visual critic, fix_agent, tech/proposal/build_plans) starved: every critic call (16+12)
and every fix_agent call (6+6) died as `provider_timeout` with runway-sized budgets, $0 cost.
Codegen "failures" are dominated by this, not by model quality. Any model comparison on
slot_fill acceptance alone is confounded until the serial planning cost is attacked.

### Experiment 1 — PREVIEW_APP_MODEL: deepseek-v4-flash vs v4-pro → **REVERTED to v4-pro**

| metric | v4-pro (103/104) | v4-flash (105/106) |
|---|---|---|
| shipped | 2/2 ready, 578/573s | 2/2 ready, 575/572s |
| duo cost | $0.61 | $0.42 (-31%) |
| slot_fill usable | 15/49 (31%) | 5/18 (28%) |
| codegen success latency | 43-51s avg | 32-41s avg |
| typecheck errors at ship | 1+1 | 1+3 |

Faster per call and ~6¢/run cheaper, but acceptance flat, typecheck slightly worse, ship rate
and wall clock identical — the writer is not the bottleneck; the pre-codegen serial cost is.
Verdict per the session rule (revert on unclear): **reverted**. Re-test v4-flash only after
the starvation is fixed — its speed edge would then buy real page coverage.

### Experiment 2 — FIX_MODEL: z-ai/glm-5.2:nitro → **ADOPTED** (probe evidence)

The fixer is unreachable in-pipeline on healthy briefs: 12/12 fix_agent calls across both
duos fired at t≥534s and died in the starved tail. So the routing hypothesis was tested as a
direct A/B from the api container (`docs/evidence/session18/glm_nitro_probe.txt`): default
routing pins glm-5.2 to StreamLake at ~57-66 t/s — at the fixer's real 8-14k-token outputs
that is 120-230s per call, past the 120s per-call cap, mechanically reproducing the measured
107s avg / 52% fail. `:nitro` routes to Fireworks/Parasail at ~178-185 t/s (5/5 success,
matches the 189 t/s benchmark) and lands the same ask in 45-80s. One line, reversible,
prevents a certain arithmetic failure. `QUALITY_FIX_MODEL` left on base glm-5.2 (one line per
change) — **filed: give it the same suffix next session.**

Post-adoption live data point (run 112, the 1.12b reachability run): the nitro fixer's one
in-pipeline `fix_agent primary` call **succeeded** — the first fix_agent success ever recorded
on a funded run — while `quality_repair` on base glm-5.2 failed `provider_truncated_output` in
the same run. Small n, right direction, and the QUALITY_FIX_MODEL filed item now has evidence.

### Experiment 3 — TEXT_MODEL: gemini-3-flash-preview → **ADOPTED**

| metric | gemini-2.5-flash (103/104) | gemini-3-flash-preview (107/108) |
|---|---|---|
| codegen start | 342s / 389s | **245s / 247s** |
| planner call | 59.3s | 26-30s |
| blueprint | 26s | 13s |
| haiku plan_validation downstream | truncated 2/2 (95s + $0.08 wasted/run) | succeeded 2/2 at ~76s |
| duo cost | $0.61 | $0.51 |
| slot_fill (restaurant run) | 8/19 usable | 5/14 usable, retries actually firing (attempt-2: 4 fired / 2 passed) |
| shipped | 2/2 ready | 2/2 ready |

The single biggest lever measured this session: ~100-140s of serial critical path removed on
both runs, zero failures of its own, cheaper, and it is the forced October-2026 migration
anyway. Caveat recorded honestly: typecheck-at-ship rose on the restaurant run (7 vs 1)
because more real pages get written and the fixer still dies in the tail — content volume,
not model regression. VISION_MODEL still shares gemini-2.5-flash — **filed: migrate it beside
TEXT_MODEL after a vision-touching run.**

### Bonus finding — ARCHITECT_MODEL (haiku-4.5) planning calls are budget-capped, not flaky

Both baseline runs: `plan_validation` burned exactly its 14,000-token budget with
`finish_reason: length` and **0 output chars** (95.9s/94.3s, ~$0.08), `design_manifest` the
same at its 1,500 cap — 100% reproducible, looks like reasoning-token burn before any text.
Under gemini-3 plans the validation fits (2/2 success) but `design_manifest` still fails 2/2.
**Filed: either raise/disable reasoning budgets for haiku planning calls or move those two
writers off haiku; needs one run beside it.**

### slot_fill rejection distribution (backlog item 3) — measured over 8 funded runs

49 baseline slot_fill calls: 34 transport (starvation timeouts), 5 contract rejections, 1
truncated-then-retried (attempt 2 PASSED — first observed 2.9 retry success). The contract
class is concentrated: "missing directory face component:PageHeader, missing BRAND_MANIFEST
services binding" fired 5× across the session on catalogue pages, and a with-runway retry
(107) failed attempt 2 with the byte-identical error — the writer does not use that
validator feedback. That is prompt vocabulary (preflight question 5's `public-catalog`
thread), not model quality.

### Experiment 4 (post-close, owner-requested) — APPSPEC_* models: gemini-3-flash-preview → **REVERTED**

With appspec newly ON (owner ruling), the three `APPSPEC_*` slots were moved to
`gemini-3-flash-preview` for one duo (runs 114/115, same briefs) against the 109/110 baseline
(gemini-2.5-flash, 2/2 rev-1 accepts):

| | gemini-2.5-flash (109/110) | gemini-3-flash-preview (114/115) |
|---|---|---|
| spec revisions accepted | **2/2 on revision 1** | **0/5** |
| failure mode | — | 114: `deterministic_validation_failed` ×2 (PAGE-AI-FEATURES authored with two initial states; schema demands exactly one — repair reproduced it). 115: 3 rejects ending `semantic_coverage_failed` |
| outcome | 2/2 shipped ready | 2/2 requests failed honestly (72 s / 168 s — fail-fast worked) |
| duo cost | $0.83 | $0.17 |

The AI calls themselves all succeeded — this is spec-authoring quality against the
deterministic validator, not a provider issue. gemini-3-flash writes better *plans* (the
TEXT_MODEL adoption stands on its own numbers) but worse *specs* under this schema and prompt.
Reverted to gemini-2.5-flash, verified from the running process, appspec stays ON.

**The October migration for the appspec slots is therefore still OPEN.** Candidates for next
time: `anthropic/claude-haiku-4.5` (the architect's structured-JSON discipline is the same
skill; MODEL_RESEARCH's original note said a spec slot is worth paying for), or gemini-3-flash
again after a prompt/schema adjustment for the initial-state cardinality it tripped on. Either
way: one duo, judged on accepts first.

### Session-21 result — APPSPEC_* models: anthropic/claude-haiku-4.5 → **REVERTED**

The haiku duo ran (138 restaurant / 139 hotel, duo3 briefs verbatim, all three slots +
`APPSPEC_TRANSPORT_FALLBACK_MODEL=gemini-2.5-flash` for cross-provider cover):

| | gemini-2.5-flash (cross-session) | haiku-4.5 (138/139) |
|---|---|---|
| spec revisions accepted | 7 accepts / 6 quality-rejects (sessions 18-20); **3-for-3 rev-1 at coverage 100 in session 21** (140/141/142) | **0/2 requests** |
| dominant failure | authoring quality, variable | **3-of-4 authoring asks: `finish_reason=length`, 0 output chars, full 24k budget billed ($0.13, 95-116 s each)** — the reasoning-burn/empty-content class from its planning-writer record, now at the spec slot |
| when it did author | — | 65k-char spec violating a taught rule (`visible_assertion_evidence_required`); its 69k-char repair reproduced the IDENTICAL error at the identical path — the repair model does not apply the verbatim validator report |
| cost per ask | ~$0.04 (50k chars) | ~$0.11-0.14 (0-65k chars) |
| duo cost / accepted spec | — | **$0.70 / ∞** |

One rescue worth recording: run 139's two 0-char burns raised the provider's retryable
empty shape, and the NEW transport fallback asked gemini once — a judged 50k-char candidate
instead of a dead run (it then rejected honestly on `page_initial_state_count`). The
weather-probe caveat for anthropic models: haiku wraps JSON in markdown fences under
`response_format: json_object` (healthy-stream parsing handles it), and the 0-char burn did
NOT reproduce in 6k-token probes — it appears at the 24k-cap ask size. **Both October
candidates (gemini-3-flash, haiku-4.5) are now ruled out as-is; a new candidate (or a
reasoning-params/response-field investigation for haiku's empty-content shape) needs an
owner sign-off before the next duo.** Meanwhile gemini-2.5-flash's session-21 record —
3-for-3 rev-1 accepts at coverage 100 under prompt revision 2026-08-07.1 — is the strongest
acceptance streak on file; keep counting before calling acceptance the bottleneck.

## Session-19 results (2026-08-07, same day)

### The provider had a bad day, and it found a pipeline defect worth more than the day cost

gemini-2.5-flash returned **error-cut streams on the big appspec asks**: HTTP 200,
`finish_reason=error`, 0 input/output tokens, 1k-34.6k chars of partial body (7+ such calls
across requests 117-123; small and 9k-token probes passed throughout — the failure is
ask-size-shaped). The authoring parser's fragment strategies (balanced scan, repair) found
small complete objects inside the cuts, returned them `ok=True`, and the pipeline minted
revisions off them and failed four funded requests (118-121) as spec rejections — request
118's "candidate" was **973 chars extracted from a 15,939-char cut**. This is session 16's
"transport failure adjudicated as a model answer" finding, alive in the appspec path.

**Fixed (parser gate + provider re-ask)**: on `finish_reason=error` only a complete direct
parse may pass; every fragment strategy fails as `app_spec_authoring_json_truncated`
(retryable), so `build_app_spec_candidate` re-asks the provider. 4 tests, 5 mutations /
0 survivors (`mutate_appspec_provider_error.py`). **Live-proven the same hour: run 122's
authoring attempt 1 errored, the gate re-asked, and attempt 2's spec was ACCEPTED on
revision 1 → the run shipped `ready` at 554 s.** Residual gap, filed: the repair/coverage/
schema_repair asks classify honestly now but have no per-call transport re-ask — run 123
died when its schema_repair call errored.

### Appspec acceptance on gemini-2.5-flash is variable, and n=2 was optimistic

Same model, same briefs as the 109/110 head-to-head (2/2 rev-1 accepts): this session's
transport-clean rejects are REAL spec-quality variance — 116 (state_assertion_state_required
×2 across authoring + 3 repairs, all real outputs), 123 (missing_required_field + empty-tuple
page shape across 5 revisions), 126 (call_budget_exhausted on 6 real outputs), 127
(missing_reference: an evidence id the spec cites but never declares). With the transport
class removed, the enforced acceptance record on these briefs is **5 accepts
(109/110/122/124/125) vs 4 quality-rejects (116/123/126/127) across sessions 18-19** — and
the session-19 accepts all landed on revision 1 while the rejects burned full repair chains.
A rejected spec fails the request honestly — the designed behavior, but at ~45% quality-reject
the appspec authoring prompt/schema is the next thing to harden, and the October migration duo
should judge candidates on accepts over MORE than two runs.

### Session-20 addendum — the spec slot's quality problem is now prompt-hardened and better measured

Prompt revision `2026-08-07.1` teaches the five recurring reject shapes (mined from
`app_spec_revisions` 114-128, transport artifacts excluded) and translates the three
recurring codes in the repair prompt. First live data: **129 rejected rev-1 then ACCEPTED
rev-2 — the first spec-repair success on record**; 130/131 still quality-rejected on
freshly-taught rules (`requirement_unaccounted_for`, `state_assertion_state_required`);
132 accepted rev-1. Enforced acceptance on the duo3 briefs across sessions 18-20:
**7 accepts / 6 quality-rejects (~54%)** — gemini-2.5-flash violates stated contract rules
at high variance, which sharpens the October-migration case: judge candidates on accepts
AND on rev-1-vs-repair mix, per prompt revision (the stamp makes reject rates queryable).
The repair paths also now survive transport (`_candidate_ask_with_transport_reask`), so
future reject tallies are clean of the error-cut class by construction.

### Experiment 5 — QUALITY_FIX_MODEL: z-ai/glm-5.2:nitro → **ADOPTED**

Same routing arithmetic as FIX_MODEL (StreamLake 57-66 t/s at real repair sizes vs
nitro 178-185 t/s), plus run 112's direct evidence: base-glm `quality_repair primary`
failed `length/truncated` at 85 s + $0.037 while the same run's nitro `fix_agent` call
succeeded. The confirmation duo could not observe the stage live — run 122 shipped with a
clean quality gate, so `quality_repair` never fired; runs 116-121/123 died at appspec. No
counter-evidence, the arithmetic stands, one reversible line: **adopted, live in `.env` and
verified from the running process.**

### Session-22 note — the page-writer transport fallback slot (new, R1)

`PREVIEW_APP_TRANSPORT_FALLBACK_MODEL` (default `anthropic/claude-haiku-4.5`, config-level
default; cross-provider from deepseek's page writer AND google's spec slots). ONE bounded
ask when a slot_fill ask raises the retryable transport class — 1.12(b)'s unroutable-writer
scenario becomes a judged page instead of a bare scaffold at the gate. The fallback's
answer faces the identical syntactic + contract judge; telemetry rows are attempt=3 under
`writer=slot_fill`, so its firings are queryable the same way the appspec rung's are.
Startup warns (never crashes) if either fallback slot shares a provider prefix with its
primary (R7, generalized). No model verdict changed this session; weather probes on
gemini-2.5-flash were healthy (2× `stop`, ~1,050 completion tokens, 5-7 s).
