# Preview 2026 Elevation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship curated modern packages + local `src/ui/` shell + dual-role prompts/critics so BMV live previews look premium 2026 without a dependency zoo.

**Architecture:** Expand `preview-template` deps and allowlist; ship required UI shell components; update plan/architect/codegen/critic prompts; migrate off UiHeadless stubs for motion/dialog; verify on a rebuild of an existing preview.

**Tech Stack:** React 19, Tailwind v4, Vite, framer-motion, Radix primitives, lucide-react, recharts, sonner, clsx, tailwind-merge, date-fns; FastAPI preview pipeline (`safety.py`, `codegen.py`, Jinja prompts).

**Spec:** `docs/superpowers/specs/2026-07-12-preview-2026-elevation-design.md`

---

## File map

| Path | Responsibility |
|------|----------------|
| `backend/preview-template/package.json` | Curated runtime deps |
| `backend/preview-template/package-lock.json` | Lockfile (regenerate) |
| `backend/preview-template/src/ui/**` | Required local shell |
| `backend/preview-template/src/components/UiIcons.tsx` | Lucide-backed icons |
| `backend/preview-template/src/lib/cn.ts` | `clsx` + `twMerge` |
| `backend/app/application/preview_app/safety.py` | Allowlist + stub policy |
| `backend/app/application/preview_app/codegen.py` | Chrome contracts → `src/ui/` |
| `backend/app/application/preview_app/npm_shared.py` | Shared install (fingerprint auto) |
| `backend/app/templates/prompts/ui_experience_plan.j2` | Dual surface + directions |
| `backend/app/templates/prompts/preview_app_architect.j2` | Kit files + surface tags |
| `backend/app/templates/prompts/preview_app_file.j2` | Allowlist + elevation rules |
| `backend/app/templates/prompts/preview_app_mock_synthesize.j2` | Chart/ops data richness |
| `backend/app/templates/prompts/preview_app_critic.j2` | 2026 elevation fail rules |
| `backend/app/templates/prompts/preview_app_visual_critic.j2` | Visual dated/flat fails |
| `backend/preview-template/src/components/UiHeadless.tsx` | Shrink/remove after migration |

---

### Task 1: Add curated packages to the template

**Files:**
- Modify: `backend/preview-template/package.json`
- Regenerate: `backend/preview-template/package-lock.json`

- [ ] **Step 1: Update `package.json` dependencies**

Add exactly (no extras):

```json
"framer-motion": "^12.0.0",
"@radix-ui/react-dialog": "^1.1.0",
"@radix-ui/react-dropdown-menu": "^2.1.0",
"@radix-ui/react-tabs": "^1.1.0",
"@radix-ui/react-select": "^2.1.0",
"@radix-ui/react-switch": "^1.1.0",
"@radix-ui/react-tooltip": "^1.1.0",
"@radix-ui/react-slot": "^1.1.0",
"lucide-react": "^0.500.0",
"recharts": "^2.15.0",
"clsx": "^2.1.0",
"tailwind-merge": "^3.0.0",
"date-fns": "^4.0.0",
"sonner": "^2.0.0"
```

Keep existing `react`, `react-dom`, `react-router-dom`. Do not add MUI/Ant/Chakra/chart.js/three/headlessui.

- [ ] **Step 2: Install and lock inside template**

```bash
cd backend/preview-template && npm install
```

Expected: lockfile updates; `node_modules` present locally for template only (runtime demos still use shared npm).

- [ ] **Step 3: Commit**

```bash
git add backend/preview-template/package.json backend/preview-template/package-lock.json
git commit -m "Add curated 2026 UI packages to preview template."
```

---

### Task 2: Shared utilities + expand allowlist

**Files:**
- Create: `backend/preview-template/src/lib/cn.ts`
- Modify: `backend/app/application/preview_app/safety.py`

- [ ] **Step 1: Add `cn` helper**

```ts
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 2: Expand `_ALLOWED_NPM_IMPORTS`**

Include every package from Task 1 plus existing react packages. Keep `_STUBBED_NPM_IMPORTS` only for `@headlessui/react` → temporary kit shim path (or remove once Task 6 lands). **Do not** stub `framer-motion` anymore once it is a real dependency — allow it.

- [ ] **Step 3: Unit-smoke allowlist in a tiny test or script**

Assert `framer-motion`, `lucide-react`, `recharts`, `@radix-ui/react-dialog` are allowed; `antd` / `@mui/material` are not.

- [ ] **Step 4: Commit**

```bash
git commit -m "Allow curated UI packages in preview safety guards."
```

---

### Task 3: Build shared `src/ui/` primitives

**Files (create under `backend/preview-template/src/ui/`):**
- `cn` re-export or import from `../lib/cn`
- `Button.tsx`, `Badge.tsx`, `Card.tsx`, `Input.tsx`
- `Modal.tsx` (Radix Dialog)
- `Tabs.tsx` (Radix Tabs)
- `Toast.tsx` (Sonner)
- `Motion.tsx` (`fadeUp`, `staggerChildren`, `pageFade` using framer-motion)
- `index.ts` barrel export

- [ ] **Step 1: Implement primitives with brand tokens** (`bg-brand`, `text-brand`, radius tokens) — no random purple theme defaults.

- [ ] **Step 2: `Motion.tsx` presets**

```tsx
export const fadeUp = { /* initial/animate/transition */ };
export const staggerChildren = { /* ... */ };
export const pageFade = { /* ... */ };
```

- [ ] **Step 3: Commit**

```bash
git commit -m "Add shared ui primitives and motion presets to preview template."
```

---

### Task 4: Public shell + ops shell

**Files:**
- Create: `PublicShell.tsx`, `MarketingHero.tsx`, `FeatureBento.tsx`, `MarqueeStrip.tsx`, `CTABand.tsx`, `TestimonialRail.tsx`, `BrandFooter.tsx`
- Create: `OpsShell.tsx`, `PageHeader.tsx`, `StatCard.tsx`, `DataTable.tsx`, `EmptyState.tsx`, `FilterBar.tsx`, `ChartCard.tsx`, `ConfirmDialog.tsx`
- Export from `src/ui/index.ts`

- [ ] **Step 1: Public components** — hero is full-bleed / atmospheric; FeatureBento is asymmetric (not six equal weak cards).

- [ ] **Step 2: Ops components** — sidebar shell, StatCard, DataTable, ChartCard wrapping Recharts `ResponsiveContainer` + one of `AreaChart`/`BarChart`.

- [ ] **Step 3: Smoke-build template**

```bash
cd backend/preview-template && npm exec -- vite build
```

Expected: build succeeds (even if App still uses old pages).

- [ ] **Step 4: Commit**

```bash
git commit -m "Add public and ops UI shells for preview apps."
```

---

### Task 5: Lucide-backed `UiIcon`

**Files:**
- Modify: `backend/preview-template/src/components/UiIcons.tsx`
- Modify: `backend/app/application/preview_app/safety.py` (icon coverage still works)

- [ ] **Step 1: Map common names to `lucide-react` icons**; keep `name` API stable so existing pages don’t break.

- [ ] **Step 2: Ensure `ensure_ui_icons` / coverage guards still copy or preserve the template file.

- [ ] **Step 3: Commit**

```bash
git commit -m "Back UiIcon with lucide-react in the preview template."
```

---

### Task 6: Workspace copy + retire motion stubs

**Files:**
- Modify: `backend/app/application/preview_app/workspace.py` (ensure `src/ui/` and `src/lib/` copy with template)
- Modify: `backend/app/application/preview_app/safety.py` — remove framer/motion from stub map; optionally map `@headlessui/react` → thin Radix-compat file under `src/ui/headlessCompat.tsx` or delete after prompt ban
- Modify or delete: `UiHeadless.tsx` (keep only if short compat needed)

- [ ] **Step 1: Verify `create_workspace` / template copy includes new folders.**

- [ ] **Step 2: Stop rewriting `framer-motion` to UiHeadless.**

- [ ] **Step 3: Commit**

```bash
git commit -m "Ship ui kit with workspaces and stop stubbing framer-motion."
```

---

### Task 7: Prompt updates (plan + architect + file)

**Files:**
- Modify: `backend/app/templates/prompts/ui_experience_plan.j2`
- Modify: `backend/app/templates/prompts/preview_app_architect.j2`
- Modify: `backend/app/templates/prompts/preview_app_file.j2`
- Modify: `backend/app/templates/prompts/preview_app_mock_synthesize.j2`
- Modify: `backend/app/application/preview_app/codegen.py` (`_CHROME_CONTRACTS`, `_COLOR_CONSTRAINT` / import allowlist text)

- [ ] **Step 1: Experience plan** — require each page `"surface": "public"|"ops"`; add `design_system.public_direction` and `ops_direction`.

- [ ] **Step 2: Architect** — always list `src/ui/*` kit files as existing/required; every route has `surface`; ban reinventing Nav/Layout.

- [ ] **Step 3: File codegen** — update IMPORTS ALLOW-LIST to curated packages + `../ui/*` + `../lib/cn` + mock + UiIcon; mandate:
  - public home → `MarketingHero` + Motion
  - ops dashboard → `OpsShell` + stats + ChartCard/DataTable
  - never emoji icons; never flat single-color primary pages

- [ ] **Step 4: Mock synthesize** — ask for chart series arrays and dense ops rows.

- [ ] **Step 5: Commit**

```bash
git commit -m "Teach preview prompts dual-role 2026 UI and curated imports."
```

---

### Task 8: Critic bar

**Files:**
- Modify: `backend/app/templates/prompts/preview_app_critic.j2`
- Modify: `backend/app/templates/prompts/preview_app_visual_critic.j2`

- [ ] **Step 1: Text critic** — hard-fail elevation checklist from spec §8 (emoji, flat public home, ops without structure, duplicate chrome, placeholders, wrong surface).

- [ ] **Step 2: Visual critic** — fail dated/flat/missing hero depth / ops without shell hierarchy; keep thresholds (≥88 text, ≥80 visual).

- [ ] **Step 3: Commit**

```bash
git commit -m "Raise preview critics to enforce 2026 elevation bar."
```

---

### Task 9: Shared npm refresh + end-to-end verify

**Files:** none new (runtime cache under `PREVIEW_APPS_DIR/_shared_npm/`)

- [ ] **Step 1: Restart/rebuild API container if needed so template mount + new lockfile are visible.**

- [ ] **Step 2: Invalidate shared npm** by deleting `_shared_npm/<old-hash>/` or letting fingerprint miss → reinstall.

- [ ] **Step 3: Rebuild an existing request** (e.g. id 5) via `apply_workspace_guards` + `run_build`, **or** generate a new business.

- [ ] **Step 4: Manual checklist**

  - Public home: motion + atmospheric hero, no emoji, not flat  
  - Ops dashboard: OpsShell + stats + chart/table  
  - No white-screen / missing import errors  
  - `package.json` in workspace matches curated set only  

- [ ] **Step 5: Final commit** (any leftover prompt/guard tweaks) + push when user asks.

```bash
git commit -m "Verify elevated preview toolkit on a live rebuild."
```

---

## Plan self-review vs spec

| Spec section | Tasks |
|--------------|-------|
| §4 Curated packages | Task 1–2 |
| §5 Local UI shell | Task 3–5 |
| §6 Dual-role rules | Task 7 |
| §7 Prompt/pipeline | Task 7–8 |
| §8 Critic/guardrails | Task 2, 6, 8 |
| §9 Migration | Task 6, 9 |
| §10 Success criteria | Task 9 |
| §11 Follow-up automation step | Explicitly not in this plan |

**Placeholder scan:** No TBD/TODO steps.  
**Zoo control:** Task 1 forbids extras; Task 2 allowlist is closed; Task 9 checks workspace deps.

---

## Execution options (after you approve this plan)

1. **Subagent-driven** — implement task-by-task with review between tasks  
2. **Inline** — execute the plan in this chat sequentially  

No coding starts until you say go.
