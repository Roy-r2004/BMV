# Model research — every slot, its job, and what should fill it (2026-08-06, session 16)

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

### HTML_MODEL — the legacy HTML pipeline
- **Job:** v1 role-pages HTML + page QA (`pipelines/role_pages.py`, `page_qa.py`). Still
  wired into the orchestrator and an API endpoint; 8 calls since July.
- **Measured:** `openai/gpt-4o` — **the most expensive model in the config** ($2.50/$10) on
  the least-used legacy path.
- **Recommendation: re-point to TEXT_MODEL.** No quality argument survives 8 calls/month on a
  legacy path; this is config hygiene. (Offline-safe in principle, but changing any .env model
  is a production-behavior change — bundled with the funded session's config batch.)

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
3. **HTML_MODEL → TEXT_MODEL, delete the dead llama comment** — hygiene batch.
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
