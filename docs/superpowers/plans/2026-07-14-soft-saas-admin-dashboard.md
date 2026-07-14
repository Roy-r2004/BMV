# Soft SaaS Admin Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) or subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elevate the ops kit to a soft SaaS admin look (light shell, card KPIs, main + activity rail) and prove it on preview #7 `/admin/dashboard`.

**Architecture:** Default `OpsShell` to soft light chrome with optional `rail`. `SkeletonComposer` places `activity` into the rail for `ops-dashboard`. Polish `StatCard`/`ActivityFeed`/`PageHeader`. Sync kit into #7 and rebuild.

**Tech Stack:** React 19, Tailwind 4, Recharts, existing `@/ui` catalogue, Vite preview workspaces.

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/preview-template/src/ui/ops/OpsShell.tsx` | Soft appearance + rail column |
| `backend/preview-template/src/ui/ops/StatCard.tsx` | `card` / `strip` variants |
| `backend/preview-template/src/ui/ops/PageHeader.tsx` | Meta/actions layout polish |
| `backend/preview-template/src/ui/ops/ActivityFeed.tsx` | Soft timeline chrome |
| `backend/preview-template/src/ui/ops/ChartCard.tsx` | Soft card shell if needed |
| `backend/preview-template/src/ui/compose/SkeletonComposer.tsx` | Main/rail split for ops-dashboard |
| `backend/preview-template/src/ui/registry.ts` | ops-dashboard purpose text |
| `backend/preview-template/src/ui/examples/OpsReferencePage.tsx` | Living example |
| `backend/app/application/preview_app/catalogue_contract.py` | Richer dashboard scaffold samples |
| `backend/app/templates/prompts/preview_app_file.j2` | Soft dashboard guidance |
| Preview `#7` `DashboardPage.tsx` + synced `src/ui` | Validation target |

---

### Task 1: OpsShell soft + rail

**Files:**
- Modify: `backend/preview-template/src/ui/ops/OpsShell.tsx`

- [ ] Add `appearance?: 'soft' | 'floor'` (default `soft`) and `rail?: React.ReactNode`
- [ ] Soft: white sidebar, cool gray page bg, brand-tint active nav
- [ ] Floor: preserve current dark sidebar styles
- [ ] Desktop: flex main + optional sticky rail (~20rem); mobile: rail omitted from shell (composer stacks activity)

### Task 2: StatCard card variant

**Files:**
- Modify: `backend/preview-template/src/ui/ops/StatCard.tsx`

- [ ] Add `variant?: 'card' | 'strip'` default `card`
- [ ] Card: soft bordered panel, icon chip, value, colored delta, hint
- [ ] Strip: keep existing dense border-r layout

### Task 3: ActivityFeed + PageHeader polish

**Files:**
- Modify: `backend/preview-template/src/ui/ops/ActivityFeed.tsx`
- Modify: `backend/preview-template/src/ui/ops/PageHeader.tsx`

- [ ] Softer feed card for rail use
- [ ] PageHeader supports optional `meta?: React.ReactNode` for date/actions row

### Task 4: SkeletonComposer main/rail

**Files:**
- Modify: `backend/preview-template/src/ui/compose/SkeletonComposer.tsx`
- Modify: `backend/preview-template/src/ui/registry.ts`

- [ ] For `ops-dashboard`, render main slots in a column; pass `activity` via render prop or return structure
- [ ] Prefer: composer wraps content so **pages** that use OpsShell can do:

```tsx
<OpsShell rail={rail}>{main}</OpsShell>
```

  Implementation: export helper `composeOpsDashboardSlots(slots)` returning `{ main, rail }` OR enhance SkeletonComposer to accept `onCompose` — simplest path:

  **Chosen:** Add `composeSkeletonLayout(skeletonId, slots)` returning `{ main: ReactNode, rail?: ReactNode }`. Pages/OpsReference use it and pass `rail` to OpsShell. Keep `SkeletonComposer` for flat layouts (ops-list).

- [ ] Update OpsReferencePage + #7 Dashboard to use compose helper

### Task 5: Pipeline scaffolds + prompt

**Files:**
- Modify: `backend/app/application/preview_app/catalogue_contract.py`
- Modify: `backend/app/templates/prompts/preview_app_file.j2`

- [ ] Richer ops-dashboard slot samples (3 KPIs with deltas, chart data, 3 table rows, 3 activities)
- [ ] Prompt note: soft SaaS ops; activity is rail content; use StatCard variant card

### Task 6: Apply to #7 + rebuild

**Files:**
- Sync UI into `/app/data/preview-apps/7/src/ui/`
- Rewrite `.../pages/admin/DashboardPage.tsx`
- `npm exec -- vite build` in workspace 7

### Task 7: Thorough testing

- [ ] Template typecheck / vite build in preview-template if feasible
- [ ] Preview #7 build succeeds
- [ ] Grep bundle for soft markers / dashboard copy
- [ ] Curl preview assets 200
- [ ] Smoke: App.tsx still PascalCase for Admin routes
- [ ] Regression: `_ident` / collision still PascalCase
- [ ] Visually confirm via fetching built CSS classes present (soft sidebar classes in bundle)

---

## Spec coverage

| Spec section | Task |
|--------------|------|
| Soft OpsShell + rail | 1 |
| StatCard card | 2 |
| Activity/PageHeader | 3 |
| ops-dashboard main+rail | 4 |
| Scaffolds + prompts | 5 |
| #7 validation | 6 |
| Acceptance / no new deps | 7 |
