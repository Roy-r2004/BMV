# BuildMyVersion — preview-app quality roadmap (for Cursor)

Context: this is a FastAPI + React preview-app generation pipeline
(`backend/app/application/preview_app/`, `backend/app/application/pipelines/`).
This file lists what's done, what's left, and the exact evidence behind each
item — found by reading real generated output (request #4, "PlateSync ERP")
and, where noted, by actually running the code, not just reading it.

**Reconciliation note**: this supersedes an earlier draft of this file that
listed the icon-mismatch and empty-seed bugs as "confirmed, not yet fixed."
Both were already fixed in an earlier session. This version also reflects
that the visual critique pass has now been production-tested against a real
running preview and a real vision-model call, not just code-reviewed.

## Already done — do not redo

- `PREVIEW_SKIP_CRITIC=false` in `backend/.env` — design-critic review/refine pass is on.
- `ARCHITECT_MODEL`/`CRITIC_MODEL` set to `anthropic/claude-haiku-4.5` (`backend/app/core/config.py`, `backend/.env`).
- `PREVIEW_APP_MODEL`/`FIX_MODEL` set to `deepseek/deepseek-v4-pro` (was `deepseek/deepseek-chat`).
- Nav/PublicLayout/AdminLayout/UiIcons are AI-authored per brand instead of copied from a static template — see `_CHROME_DEFAULTS` in `backend/app/application/preview_app/pipeline.py` and `_CHROME_CONTRACTS` in `backend/app/application/preview_app/codegen.py`. Template-revert fallback (not the generic page stub) lives in `backend/app/application/preview_app/fallback.py` (`is_chrome_path`, `write_template_fallback`).
- Chrome contracts now lock color usage to `brand`/`brand-dark` + Tailwind defaults only (`_COLOR_CONSTRAINT` in `codegen.py`) — found and fixed after a real bug where AI-authored Nav/Layout used invented classes (`bg-navy-800`, `text-primary-600`) that don't exist in `index.css`'s `@theme` block and silently rendered as no color at all.
- Stock image reuse fixed: `backend/app/application/services/industry_images.py` now rotates per-request (seeded) and uses the client's own reference-site `og:image` when available (`backend/app/infrastructure/web/reference_scraper.py`).
- Removed two business-specific hardcoded strings (`plate_sync_admin`, `restaurant_owner`) from generic route-scoring logic in `backend/app/application/preview_app/assemble.py`.
- Fixed an unconfigured `openai/gpt-4o` fallback accidentally used by the React planning stage — `backend/app/application/services/page_experience.py` now uses `settings.ARCHITECT_MODEL` instead of `settings.HTML_MODEL` in 4 places (the real HTML-fallback path in `role_pages.py`/`page_qa.py` still legitimately uses `HTML_MODEL`, untouched).
- OpenRouter/Ollama timeouts shortened, retry attempts reduced, heartbeat logging added so slow calls are visible instead of looking hung (`backend/app/infrastructure/ai_providers/retry.py`, `openrouter_provider.py`, `ollama_provider.py`). A 15-minute wall-clock budget caps the AI fix-loop (`MAX_FIX_LOOP_SECONDS` in `pipeline.py`).

- **Icon-name mismatch guard — FIXED.** `safety.py::ensure_ui_icon_coverage()`
  scans every generated file for `<UiIcon name="...">` usages, locates the
  icon map inside `UiIcons.tsx` dynamically (not by hardcoding a variable
  name), and appends a generic fallback SVG entry for any key pages use that
  the icon set never defined — correctly handling the case where the
  existing icon map has no trailing comma before its closing brace (verified
  against real `tsc --noEmit` output on reconstructed TSX, not just a Python
  string-equality check). Wired into `apply_workspace_guards()`, so it runs
  before every build attempt.

- **Empty-seed-data guard — FIXED.** `safety.py::find_empty_seed_pages()`
  detects pages where a `useState([])` variable is later `.map()`'d in
  render with zero `data/mock` import anywhere in the file — the exact
  `MenuManager.tsx` failure mode. `pipeline.py` (right after the text-critic
  pass, before build) reinforces that page's instructions with the specific
  violation and regenerates via the existing `_run_batch` machinery, rather
  than trying to synthesize fake seed data itself. Verified against both the
  true-positive shape (empty array + `.map()` + no mock import) and
  known false-positive shapes (e.g. a legitimately-empty `selectedIds: []`
  multi-select array), and confirmed it's a no-op when zero pages are
  flagged.

- **Post-build visual critique — built AND production-tested this session
  (previously only code-verified). Still ships OFF by default.**
  - New file `backend/app/application/preview_app/screenshot.py`:
    `capture_route_screenshot()` launches headless Chromium via Playwright,
    waits for `#root` to actually have children (not just `networkidle` —
    these are client-rendered SPAs where `index.html` loads almost instantly
    before React paints anything), then full-page screenshots.
  - New critic path: `codegen.py::critique_file_visual()` sends the
    screenshot to `ai_provider.ask_vision(settings.CRITIC_MODEL, ...)` using
    prompt `backend/app/templates/prompts/preview_app_visual_critic.j2`, same
    JSON return shape (`score`/`verdict`/`issues`/`revision_instructions`) as
    the existing text critic so it feeds into the same `refine_file()`.
  - Wired into `pipeline.py`: `_select_visual_critique_routes()` caps at
    `MAX_VISUAL_CRITIQUE_PAGES = 6` (homepage + each role's landing page,
    backfilled from the full route list). `_run_visual_critique()` only runs
    after a successful build (`if ok and not settings.PREVIEW_SKIP_VISUAL_CRITIC`),
    screenshots+critiques each selected route, and if any page is flagged:
    snapshots source (`snapshot_source`), refines flagged files, rebuilds
    once. If that rebuild fails, restores the pre-critique snapshot
    (`restore_source`) and rebuilds again to confirm the rollback itself
    still builds. Every stage is try/excepted so a crash here degrades to
    "keep the existing build," never breaks the request.
  - Config: `PREVIEW_SKIP_VISUAL_CRITIC` (default `true`, i.e. OFF) and
    `INTERNAL_BASE_URL` (default `http://localhost:8000`) in `config.py` +
    `.env`.
  - Docker: both `Dockerfile` and `Dockerfile.app` run
    `playwright install --with-deps --no-shell chromium`.
  - **Implementation deviation from the original spec, and why**:
    `screenshot.py` launches with `channel="chromium"` (Chromium's "new"
    headless mode) instead of plain `headless=True`. Plain headless mode
    needs a separate `chromium-headless-shell` binary whose download stalled
    repeatedly in the dev sandbox — confirmed the CDN itself was fine (a
    direct `curl` to the same URL completed in under 5 seconds), so this was
    specifically Playwright's own downloader hanging on that one file, not a
    real network problem. `channel="chromium"` reuses the regular Chromium
    build (which downloaded fine) and is Microsoft's own recommended forward
    path as the old headless mode is deprecated. Both Dockerfiles use
    `--no-shell` accordingly, saving ~150-200MB of image size for a binary
    the code no longer needs.
  - **What was actually run and verified, not just read**:
    - Real screenshot captured against a live running preview app (request
      #4, PlateSync ERP, on the actual dev server) — confirmed full rendered
      content (hero image, headline, feature cards), proving the
      `#root`-children wait works rather than capturing the pre-render blank
      shell.
    - That exact screenshot fed through `critique_file_visual()` against the
      live OpenRouter API with `claude-haiku-4.5` — confirmed the model
      accepts image input (not just per docs — an actual API round-trip) and
      returned genuinely screenshot-only defects (a too-dark hero image, and
      an abrupt page-ending with no footer/CTA section) that a text-only
      critic reading source could never catch.
    - Rollback path forced-tested: copied a real built workspace, mocked
      `refine_file` to inject deliberately broken JSX (unterminated
      tags/parens) in response to a forced "revise" verdict, confirmed the
      rebuild failed as expected, confirmed `restore_source` brought back the
      original file byte-for-byte, and confirmed the restored workspace
      rebuilt successfully.
    - No-op test: confirmed that with `PREVIEW_SKIP_VISUAL_CRITIC=true` (the
      actual default), zero calls are made into
      screenshot/critique/refine/snapshot, and zero files change.
    - Exception-safety test: forced `_run_visual_critique` itself to raise,
      confirmed the call-site `try/except` in `generate_preview_app` catches
      it and the request completes instead of crashing.
  - **UPDATE — this has now been run for real.** Flipped
    `PREVIEW_SKIP_VISUAL_CRITIC=false` for a single process (not the checked-in
    `.env`) and ran a genuine fresh `generate_preview_app()` against request
    #4 (PlateSync ERP) — confirmed beforehand that neither the API layer nor
    the pipeline function has any "already generated" short-circuit, so this
    was real planning → architect → wiped-and-recreated workspace → full
    per-file codegen → build → fix-loop → text critic → **visual critique**,
    not a rebuild of existing files. Result: **`status: ready`**, the visual
    critique ran for real inside the actual pipeline and worked correctly:
    - Screenshotted and critiqued all 6 selected pages; flagged 4
      (`owner/Dashboard.tsx` scored 15/100 — see why below — plus
      `AboutPage.tsx`, `DemoPage.tsx`, `owner/MenuManagement.tsx`).
    - Refined all 4, rebuilt once, rebuild succeeded — kept the
      visually-refined version (didn't even need the rollback path this
      time, which was separately forced-tested earlier).
    - **Concrete before/after**: `owner/Dashboard.tsx` had been reduced to a
      generic placeholder by the build-failure safety net
      (`write_safe_stub`) earlier in this same run, after repeated
      `fix_build_errors` JSON-parse failures burned through the fix-loop.
      The visual critic correctly scored that stub 15/100 and flagged it —
      exactly the failure mode this feature exists to catch, since a stub
      compiles cleanly and a text-only critic reading source wouldn't
      necessarily flag "this is a generic placeholder" the way seeing it
      rendered does. After refinement it became a real, populated,
      on-brand admin dashboard (sidebar nav, stat cards, recent-activity
      feed) — confirmed by screenshotting the live route post-run.
  - **Real-world side discoveries from this run** (not new work, just
    surfaced by actually running the full pipeline instead of isolated
    tests):
    - A transient DNS resolution failure hit OpenRouter mid-run
      (`Failed to resolve 'openrouter.ai'`) — the existing `call_with_retry`
      caught it and continued without crashing the request. Good
      unplanned confirmation that the retry logic added earlier this
      project actually holds up against a real network blip, not just
      synthetic ones.
    - The `MAX_FIX_LOOP_SECONDS = 900` budget genuinely triggered
      (`fix loop budget exceeded (1043s > 900s)`) after `fix_build_errors`
      repeatedly returned malformed JSON (`Unterminated string...`,
      `Expecting value: line 1 column 1`) from `deepseek-v4-pro`. This is a
      **pre-existing fix-agent reliability issue, unrelated to the visual
      critique work**, but it's a real, not synthetic, trigger of the
      15-minute ceiling added earlier this project — and the deterministic
      regen/stabilize fallback below it worked correctly, ending in
      `stabilized — build now succeeds`.
    - **`PREVIEW_PARALLEL_WORKERS` was silently `1`, not the `.env`'s `4`.**
      There's a persistent Windows **user-level environment variable**
      `PREVIEW_PARALLEL_WORKERS=1` set outside the repo, which
      `python-dotenv`'s `load_dotenv()` does not override (it only fills in
      variables that aren't already set). This made codegen and the text
      critic run fully sequentially instead of 4-way parallel, which was the
      single biggest contributor to this run taking as long as it did.
      **This is worth checking on whatever machine actually runs
      production** — if the same env var is set there, the pipeline is
      silently running single-threaded and nobody would know from the code
      or `.env` alone.
    - Because of the two issues above, total wall time for this run was
      **78.6 minutes** — but that number is dominated by the sequential
      codegen/critic passes and the fix-loop exhausting its full budget on a
      flaky fix agent, not by the visual critique itself. Isolating just the
      visual critique stage (from its start log line to the final rebuild
      confirmation): roughly **9-10 minutes for 6 pages** (screenshot +
      vision-critique for 6 pages, refine for 4, one rebuild) — call it
      ~90s/page average. That's the number to weigh against production
      latency tolerance, not the 78.6-minute total.
  - **Known Ollama gap, not addressed**: under `AI_PROVIDER=ollama`,
    `CRITIC_MODEL` defaults to a text-only model (`llama3.1:8b`), not
    vision-capable. If Ollama is the active provider with visual critique
    enabled, `ask_vision` calls will likely fail per page — caught by the
    per-route try/except (so it won't crash), but the feature is effectively
    inert on Ollama until a separate vision-capable model is configured for
    it specifically. Nobody's asked for this yet; flagging it so it isn't a
    surprise later.

Known limitation on the timeout fix: `requests`' timeout is a per-read
timeout, not total-duration — a slowly-trickling response can still exceed
the configured timeout in wall-clock terms. A true hard deadline would need
to extend the heartbeat-thread mechanism already in `retry.py` to give up
after N seconds regardless of thread state.

## Confirmed bugs — status

1. **Icon-name mismatch** (pages reference `UiIcon` names the generated icon
   set doesn't define) — **FIXED**, see `ensure_ui_icon_coverage` above.
2. **Pages ship with no seed data** (`MenuManager.tsx`-style empty CRUD
   lists) — **FIXED**, see `find_empty_seed_pages` above.

## Not built — ranked by leverage

**1. Faster chat-based iteration loop.**
`backend/app/application/preview_app/chat_refinement.py` already scopes
edits correctly (doesn't re-run plan/architect), but every edit still
triggers a full production `vite build`. Swap to a persistent Vite dev
server (HMR) per workspace instead, stream progress over the existing
progress-emit system (`backend/app/application/services/progress.py`).

**2. Layout/structural variety beyond color and typography.**
Every business still gets the same page shape (hero → cards → sections, top
nav). Real variety needs the architect (`call_architect` in `codegen.py`,
prompt in `backend/app/templates/prompts/preview_app_architect.j2`) to
choose a layout archetype per business type (sidebar dashboard vs.
single-page scroller vs. tabbed interface), not just a color palette.

**3. Curated component/chart library (e.g. `recharts`) behind a strict allowlist.**
Currently pages can't import any npm package at all — see the "IMPORTS
ALLOW-LIST" section of `preview_app_file.j2`. This is deliberate, because
it's what keeps builds reliable. Opening it up trades reliability for visual
range. Do this only after the items above are stable and proven — it
multiplies failure modes.

**4. Version history / multi-step undo for chat refinement.**
`chat_refinement.py` currently keeps exactly one rollback point
(`snapshot_source`/`restore_source`, `backup_dist`/`restore_dist` in
`workspace.py`). Lovable-style multi-step history needs a data model change
(store a list of past states, not just the latest) plus UI work.

**5. Automated deterministic quality guardrails beyond the AI critic.**
Cheap, no model call needed: Lighthouse/axe-core for accessibility/
performance baseline, a broken-image-link checker, a minimum-content-density
check. Different failure class than the AI critic (text or visual) catches,
near-zero marginal cost per request.

**6. HTML-fallback path bespoke treatment.**
`backend/app/application/pipelines/role_pages.py` +
`backend/app/templates/pages/*.j2` — only hit when the React build fails
outright. Lowest priority; should get hit less often once the items above
land.

## Suggested order

1. ~~Fix confirmed bug #1 (icon guard)~~ — **done**.
2. ~~Fix confirmed bug #2 (empty-state guard)~~ — **done**.
3. ~~Run one real, complete business end-to-end through `generate_preview_app()`
   with `PREVIEW_SKIP_VISUAL_CRITIC=false`~~ — **done**, see the "UPDATE —
   this has now been run for real" note above. Caught and fixed a real
   stubbed-out page in the actual pipeline; ~90s/page is the number to weigh
   against latency tolerance before flipping the flag on by default.
4. **Check whether `PREVIEW_PARALLEL_WORKERS=1` is set as a user-level env
   var on whatever machine actually runs production** — see the discovery
   above. If it is, the pipeline has been running fully sequential (not the
   `.env`'s intended 4-way parallel) without it being visible anywhere in
   the repo or logs except by noticing codegen never overlaps in the output.
5. Investigate `fix_build_errors` JSON reliability on `deepseek-v4-pro` —
   the run above burned its entire 900s fix-loop budget on repeated
   malformed-JSON responses (`Unterminated string...`,
   `Expecting value: line 1 column 1`) before falling back to
   regen/stabilize. The fallback worked correctly, but if this is common,
   the fix-loop is regularly paying its full 15-minute cost for nothing.
   Worth checking whether a stricter prompt, a lower temperature, or a
   JSON-repair pass before `extract_json_from_text` reduces this.
6. Everything in "not built" is real, multi-day-or-more work — sequence
   based on what actually matters for your specific businesses under test,
   not just this list's order.
