# Preview 2026 Elevation — Design Spec

**Date:** 2026-07-12  
**Status:** Approved for review (hybrid approach)  
**Scope:** Elevate live preview demos to premium 2026 UI — curated toolkit + local shell + dual-role design + prompt/critic upgrades.  
**Out of scope (next ship):** Dedicated “study business → propose AI/automations + detailed flows” pipeline step.

---

## 1. Problem

Generated preview apps are product-capable but often look dated: flat Tailwind-only pages, no real motion, stubbed Headless UI, SVG-div charts, and one visual language for both marketing and ops. The npm allowlist is intentionally tiny (`react`, `react-dom`, `react-router-dom`), which protects build reliability but caps visual quality.

We need **maximum elevation that stays controlled** — premium 2026 UI without a heavy, unstable dependency zoo.

---

## 2. Goals

1. **Public / marketing** surfaces feel bold, premium, AI-native, impressive (full-bleed hero, expressive type, real motion, atmosphere).
2. **Product / admin / ops** surfaces feel polished, clean, structured, SaaS-like (shell, stats, tables, charts, restrained motion).
3. **Reliability:** curated packages only; shared npm; allowlist enforced; demos keep building.
4. **Maintainability:** AI composes a local `src/ui/` shell instead of reinventing chrome every generation.
5. **Quality gate:** critics fail weak/old outputs (emoji icons, flat pages, generic cards, wrong surface language).

### Non-goals

- Adding MUI / Ant / Chakra / Bootstrap / random UI kits.
- Per-demo `npm install` of arbitrary libraries.
- The business elevation / automation-proposal pipeline step (documented as follow-up only).

---

## 3. Approach (Hybrid)

| Layer | Role |
|-------|------|
| **Curated packages** | Real Framer, Radix primitives, Lucide, Recharts, etc. |
| **Local `src/ui/` shell** | Required layouts, marketing blocks, ops primitives, motion presets |
| **Dual-role contracts** | Plan/architect tag every route `surface: "public" \| "ops"` |
| **Prompts + critics** | Teach and enforce 2026 bar; ban dated patterns |

---

## 4. Curated package list

### Runtime dependencies (add to `backend/preview-template/package.json`)

| Package | Purpose |
|---------|---------|
| `framer-motion` | Hero / page / micro motion (replace motion stubs) |
| `@radix-ui/react-dialog` | Modals / drawers |
| `@radix-ui/react-dropdown-menu` | Menus |
| `@radix-ui/react-tabs` | Tabs |
| `@radix-ui/react-select` | Selects |
| `@radix-ui/react-switch` | Toggles |
| `@radix-ui/react-tooltip` | Tooltips |
| `@radix-ui/react-slot` | Composition for kit primitives |
| `lucide-react` | Icons (`UiIcon` wraps this) |
| `recharts` | Ops charts |
| `clsx` | Class composition |
| `tailwind-merge` | Class merging with Tailwind |
| `date-fns` | Dates (no invented date utils) |
| `sonner` | Ops toasts |

### Keep as-is

- `react`, `react-dom`, `react-router-dom`
- Tailwind v4 + Vite toolchain (devDependencies)

### Explicitly forbidden (zoo prevention)

- `@mui/*`, `antd`, `@chakra-ui/*`, `bootstrap`, `@mantine/*`
- `chart.js`, `react-chartjs-2`, `victory`, `nivo`
- `three`, `@react-three/*`
- `@headlessui/react` (prefer Radix + kit; temporary shim only during migration)
- Emoji / icon-font packages (`react-icons` wholesale dumps, etc.)

### Allowlist policy

`_ALLOWED_NPM_IMPORTS` expands to this curated set **only**. Unknown imports still stripped. No open-ended “install whatever the model asks for.”

Shared npm (`PREVIEW_APPS_DIR/_shared_npm/<lock-hash>/`) rebuilds once when the template lockfile changes — expected one-time cost, then fast again.

---

## 5. Local UI shell (`src/ui/`)

Shipped in `preview-template` and copied into every workspace. Architect **always** includes these paths; page codegen fills content into shells — it must not invent parallel Nav/Layout systems.

### Public (bold brand)

| Component | Responsibility |
|-----------|----------------|
| `PublicShell` | Top nav + footer chrome for marketing routes |
| `MarketingHero` | Full-bleed / atmospheric hero + headline + CTA group |
| `FeatureBento` | Asymmetric feature grid (not weak equal cards) |
| `MarqueeStrip` | Optional social proof / capability strip |
| `CTABand` | Mid/bottom conversion band |
| `TestimonialRail` | Quotes with real structure |
| `BrandFooter` | Brand-forward footer |

### Ops (polished SaaS)

| Component | Responsibility |
|-----------|----------------|
| `OpsShell` | Sidebar + topbar + content frame |
| `PageHeader` | Title, subtitle, primary actions |
| `StatCard` | KPI tile |
| `DataTable` | Structured tabular lists |
| `EmptyState` | Useful empty, never “coming soon” on primary pages |
| `FilterBar` | Search / filters row |
| `ChartCard` | Recharts wrapper with title/legend |
| `ConfirmDialog` | Radix dialog for destructive/confirm actions |

### Shared

| Component | Responsibility |
|-----------|----------------|
| `Button`, `Badge`, `Card`, `Input` | Primitives using tokens + `cn()` |
| `Modal`, `Tabs` | Radix-backed |
| `Toast` | Sonner host + helpers |
| `Motion` | Presets: `fadeUp`, `staggerChildren`, `pageFade` |
| `UiIcon` | Thin Lucide wrapper (`name` → icon map + escape hatch) |
| `cn.ts` | `clsx` + `tailwind-merge` |

### Design tokens

`src/index.css` `@theme` remains source of truth:

- `--color-brand`, `--color-brand-dark`, `--font-sans`
- Optional surface tokens: `--color-surface`, `--color-muted`, `--radius-lg` (still brand-driven, not random hex in pages)

Pages use utilities (`bg-brand`, `text-brand`, token classes) — not scattered hardcoded palettes.

---

## 6. Dual-role design rules

Every route in the experience plan and architect output MUST include:

```json
"surface": "public" | "ops"
```

| Surface | Visual contract | Required building blocks |
|---------|-----------------|--------------------------|
| **public** | Bold, premium, AI-native; atmosphere (mesh/gradient/photo); expressive type; strong but purposeful motion; one job per section | `PublicShell` + `MarketingHero` on home; motion presets; no dense data tables as the hero story |
| **ops** | Polished SaaS; calm density; clear hierarchy; charts/tables/filters; restrained motion | `OpsShell` + `PageHeader`; primary dashboards include stats **and** chart and/or table structure |

### Hard avoid (both surfaces)

- Generic template look interchangeable across businesses
- Emoji as icons
- Weak equal card grids as the only visual idea
- Flat single-color pages with no hierarchy or atmosphere
- Old-looking dashboards (unstyled tables, no KPIs, no shell)
- Meta/demo speak (“This is a preview of…”) in product UI

---

## 7. Prompt & pipeline changes

| Artifact | Change |
|----------|--------|
| `ui_experience_plan.j2` | Require `surface` per page; `design_system.public_direction` + `ops_direction` |
| `preview_app_architect.j2` | Always schedule `src/ui/*` kit; tag routes with surface; forbid reinventing Nav/Layout |
| `preview_app_file.j2` | Expanded import allowlist; mandate shells/Motion/ChartCard by surface; ban flat/emoji/weak-card patterns |
| `preview_app_mock_synthesize.j2` | Chart series + dense realistic ops rows |
| `preview_app_critic.j2` | “2026 elevation” rubric (see §8) |
| `preview_app_visual_critic.j2` | Fail dated flat UI, missing hero depth, ops without structure |
| `codegen.py` chrome contracts | Point at `src/ui/` shells |
| `safety.py` | Expand `_ALLOWED_NPM_IMPORTS`; retire Framer/Headless stubs once real deps land; keep strip for unknown pkgs |

Pipeline stage order unchanged: plan → architect → codegen → text critic → build/fix → visual critic. Elevation is enforced by richer inputs + harder critics, not a new stage in this ship.

---

## 8. Critic bar & guardrails

### Hard fail (text and/or visual)

1. Import outside curated allowlist  
2. Emoji used as icons  
3. Public home without hero depth / atmosphere / motion  
4. Ops primary dashboard without stats **and** chart/table structure  
5. Duplicate Nav/header inside a page when shell already provides chrome  
6. Placeholder / “coming soon” / “fine-tuned” on primary pages  
7. Hardcoded hex chaos ignoring brand tokens  
8. Wrong surface language (pitch marketing cards as the whole ops home, or spreadsheet-only marketing home)

### Score thresholds

- Text critic: keep pass ≥ **88**; elevation failures force `revise` even if copy is fine  
- Visual critic: keep pass ≥ **80**; increase weight on dated/flat/chrome-missing signals  

### Build / runtime

- Shared npm fingerprint invalidates on lockfile change (one reinstall)  
- Unknown packages stripped; allowed packages must resolve from template deps  
- Preview error boundary retained (no silent white screens)  
- Brand-shape + typed mock repairs retained  

---

## 9. Migration notes

1. Add packages → refresh shared npm cache.  
2. Land `src/ui/` in template.  
3. Update allowlist + prompts + critics.  
4. Prefer Radix kit over `@headlessui`; remove UiHeadless motion/dialog stubs once pages use real libs (short compatibility window OK).  
5. Rebuild a known demo (e.g. request 5) and compare public home vs ops dashboard against this bar.  
6. Do **not** widen the package list mid-ship without a new design review.

---

## 10. Success criteria

- New generations: public home feels premium/AI-native; ops hub feels modern SaaS.  
- No emoji icons; Lucide via `UiIcon`.  
- Motion visible on public heroes; ops uses shell + KPIs + chart/table.  
- Builds succeed via shared npm without per-demo dependency sprawl.  
- Critics reject at least one deliberately “flat 2020” fixture pattern in eval/manual check.  
- Package count stays at the curated set in §4 — no drive-by additions.

---

## 11. Follow-up (not this ship)

**Business elevation step:** study the business and propose best AI features *or* non-AI automations, with detailed flow explanations, then force those flows into the live preview. Builds on this visual foundation so proposed automations look as good as they sound.

---

## 12. Spec self-review

| Check | Result |
|-------|--------|
| Placeholders / TBD | None material — package set and shell list are concrete |
| Contradictions | Dual-role + curated max richness aligned; Headless stub retirement is sequential, not contradictory |
| Ambiguity | “AI-native” = bold modern brand presence + intelligent-product cues in marketing UX, not a requirement to add LLM SDKs to the preview |
| Scope | Single subsystem (preview elevation); automation step explicitly deferred |
| Zoo risk | Explicit forbid list + “no widen without review” |
