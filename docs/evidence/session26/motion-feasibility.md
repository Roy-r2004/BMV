# Motion feasibility scan — session 26 evidence

*Produced 2026-08-08 by a read-only subagent during the wow-demo build-off (workflow wy1uj516a, 8 agents). Quality-bar demos published the same night: STACKLAB (vector) and MAILLARD (photoreal), claude.ai/code/artifact/5ff20e6f-3dc7-4d33-811e-716917be02d6; static design-corpus candidate sheet: claude.ai/code/artifact/347da548-1342-40d5-9e4e-5d4e819e3a4c.*

---

# Motion feasibility scan — BMV preview kit (read-only, 2026-08-08)

## 1. What exists today
- Deps: no framer-motion, no GSAP — but `motion` ^12.42.2 (framer's successor) and `animejs` ^4.5.0 already ship (`backend/preview-template/package.json:22,17`); Tailwind v4 (`tailwindcss` ^4.3.2 + `@tailwindcss/vite`, `package.json:36,31`).
- Usage is entrance-only, not scroll-scrubbed: motion/react variants (heroEntrance, sectionReveal, stagger) in `backend/preview-template/src/ui/motion/presets.tsx:14-56`; anime.js one-shot IntersectionObserver reveals in `src/ui/motion/anime.ts:97-127`; CSS keyframes (kenburns/light-sweep/marquee/float) `src/index.css:143-169` with reduced-motion kill switches `src/index.css:66-68`. Grep finds zero `animation-timeline`/`ScrollTimeline`/`useScroll` in src/.
- Targets: `vite.config.ts:6-14` sets no `build.target` → Vite 8.1.3 default `baseline-widely-available` (~Safari 16/Firefox 104 class); tsc ES2022 (`tsconfig.app.json:4`). CSS `animation-timeline: scroll()/view()` is outside that baseline (Firefox stable still flag-gated; Safari only ≥26), so **CSS-only scroll-driven animation cannot be the mechanism — a JS progress driver is required**. Good news: `motion`'s scroll()/useScroll is already in the dependency set (native ScrollTimeline where present, rAF fallback) → zero new deps.

## 2. Where a motion system lives
- Token flow: recipe `tokens` dicts (9 recipes, `backend/app/application/preview_app/design_recipes.py:8-33`) plus mood-overlay `token_overrides` (`design_overlay.py:320`) merge in `write_index_css` (`assemble.py:831-850`) → rendered as `@theme` CSS vars by `backend/app/templates/codegen/index_css.j2:5-23`; per-recipe personality lives in `[data-recipe=…]` blocks (`index_css.j2:174-239`), stamped on the DOM via `write_recipe_id` (`assemble.py:819-827`) and `src/main.tsx:8`.
- Motion identity slots in cleanly as a `motion` sub-dict per recipe → new j2 vars (`--motion-ease`, `--motion-stagger-ms`, `--motion-travel`, `--motion-reveal`) in `@theme`; `presets.tsx`/`anime.ts` already centralize easing at one constant each (`presets.tsx:7`, `anime.ts:12`), so they can read the CSS vars. One-dependency-set constraint holds: node_modules is a fingerprint-keyed shared install keyed on package-lock (`npm_shared.py:5-6,43-44`) — primitives must use the installed motion/animejs, no additions.

## 3. Where per-industry scenes live
- Packs are metadata-only JSON (id, tags, recipe_hint, section_order, signature_moves, imagery_roles, prompt_hints, mock_seed — `packs/restaurant-cafe-home.json`). `imagery_roles` are stock-photo *search phrases*, consumed as queries (`industry_templates/apply.py:61-77`, `pipeline/plan_phase.py:212-232`), resolved to remote URLs at runtime (`src/ui/lib/KitImage.tsx:10-12` — "one remote photo failed to load"). **No pack ships an actual asset today.**
- But nothing blocks it: the loader accepts arbitrary keys with no schema (`industry_templates/loader.py:58-66`), and the kit already inlines vector art as data-URI SVG (`index_css.j2:108,133`). Pattern: a `SceneRenderer` primitive in `src/ui` registered in `registry.ts` → `catalogue.json` (generated pages may only import from `@/ui`, `catalogue.json:5`), plus a new `scene` key (layered SVG + choreography map) in each pack, forwarded in `apply.py` alongside `imagery_roles` (`apply.py:150-155` pattern).

## 4. Honest estimate (engineer-weeks)
- (a) Scroll-progress engine in kit: **2–3 wk** — ScrollScene/PinnedStage/LayerParallax on motion's scroll(), reduced-motion parity, registry+catalogue entries, codegen prompt/critic awareness so generated pages actually use it, and keeping `prime_scroll_reveals` screenshots deterministic (`screenshot.py:113`).
- (b) Motion tokens as within-recipe axes: **1–2 wk** — plumb through design_recipes → overlay → assemble → index_css.j2 → presets/anime; 9 recipes × values, seed-stable axis picks mirroring moods.
- (c) One authored scene per pack (27 packs, `ls packs/*.json` = 27): **13–20 wk serial** at ~0.5–0.75 wk/scene for assembly-grade layered SVG + choreography + reduced-motion fallback + review; parallelizes across authors; run a 3-pack pilot (~3 wk) before committing. This dominates the cost.
- (d) Performance gate: **2–3 wk** — extend the existing headless scroll driver (`screenshot.py:99-123`) with CDP tracing (frame times, long tasks, CLS) under scripted scroll, budgets per recipe, wired into `quality_gate.py` + the DoD9 pytest CI job. No perf instrumentation exists today (grep: none).

**Total: ~18–28 eng-weeks; engine+tokens+gate ≈ 5–8, scenes are the long pole. Recommended order: (b) → (a) → pilot 3 scenes → (d) → remaining 24 scenes.**
