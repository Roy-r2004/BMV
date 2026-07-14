# Soft SaaS Admin Dashboard — Design Spec

**Date:** 2026-07-14  
**Status:** Approved � implemented  
**Approach:** Kit-level elevation (OpsShell + ops components + `ops-dashboard` skeleton), validated on preview request #7  
**Related:** `2026-07-12-preview-2026-elevation-design.md` (ops surface remains curated local UI; this spec elevates the *look* and *layout*)

---

## 1. Problem

Generated admin dashboards already compose the right *parts* (`OpsShell`, `StatCard`, `ChartCard`, `DataTable`, `ActivityFeed`), but they do not match modern soft-SaaS dashboards:

- Dark “floor control” sidebar instead of a light pastel shell
- Flat stacked sections instead of a main + right-rail composition
- Dense strip KPIs instead of soft card metrics with icons and trend chips
- Activity feed buried under the table instead of a persistent context column

Target reference: light three-column SaaS dashboard (sidebar · main overview · profile/activity rail).

---

## 2. Goals

1. **Every future `ops-dashboard` page** inherits the soft SaaS look without hand-patching.
2. **Match the reference structure:** light sidebar, greeting header, KPI cards, chart, work list, right activity rail.
3. **Keep catalogue contracts:** pages still supply slots; shell/composer own chrome and layout.
4. **No new npm packages** beyond the existing curated allowlist (Recharts, Lucide, Motion already present).
5. **Prove on Northline (#7)** admin dashboard before relying on the next full generation.

### Non-goals

- Pixel-clone of a third-party product (Logip-style mock is directional, not a brand to copy).
- Redesigning public/marketing surfaces in this ship.
- Real auth, messaging, or live WebSocket activity (preview mock data only).
- Per-business dark/light ops recipes in v1 (soft light is the new default for ops).

---

## 3. Approach

Elevate the **shared ops kit** and the **`ops-dashboard` skeleton composition**, then rebuild #7’s admin dashboard with the same kit.

| Layer | Change |
|-------|--------|
| `OpsShell` | Soft light chrome + optional `rail` slot |
| `SkeletonComposer` / ops-dashboard | Main column vs right rail placement for `activity` |
| `StatCard`, `PageHeader`, `ChartCard`, `ActivityFeed`, table rows | Soft card visual language |
| Prompts + catalogue scaffolds | Steer AI/scaffolds toward the new composition |
| Preview #7 | Manual rebuild to validate before next pipeline run |

---

## 4. Visual system (ops soft)

### Tokens (CSS / Tailwind via existing recipe variables)

| Token | Direction |
|-------|-----------|
| Page background | Cool light gray (`~#F4F7FB` / recipe-tinted), not cream floor |
| Sidebar | White / near-white, subtle border, soft shadow |
| Active nav | Soft brand tint pill (pastel blue/brand mix), not white-on-dark |
| Cards | White, large radius (`~1rem+`), soft shadow, no hard chrome |
| Accents | Brand for primary; muted orange/amber for “in progress”; green for done; rose for negative deltas |
| Type | Keep recipe fonts; ops titles slightly less italic-display than marketing |

### Branding rule

Use the generated business name in the sidebar (already `brandName`). Do not hardcode “logip” or mock people from the reference.

---

## 5. Layout

### OpsShell

```
┌──────────┬─────────────────────────────┬─────────────────┐
│ Sidebar  │ Main (scroll)               │ Rail (optional) │
│ brand    │ header / KPIs / chart /     │ profile summary │
│ nav      │ filters / table / risk      │ + ActivityFeed  │
└──────────┴─────────────────────────────┴─────────────────┘
```

**API additions (backward compatible):**

```ts
type OpsShellProps = {
  brandName: string;
  navItems: OpsShellNavItem[];
  children: React.ReactNode;
  topbar?: React.ReactNode;
  rail?: React.ReactNode;          // NEW — right column
  appearance?: 'soft' | 'floor'; // NEW — default 'soft'
  // existing adjustableSidebar props remain
};
```

- Default `appearance="soft"` (light sidebar).
- `appearance="floor"` keeps the current dark sidebar for reference/legacy demos only.
- `rail` renders only on `xl+`; on smaller breakpoints, rail content stacks below main (composer decides order: activity after table).

### ops-dashboard slot placement

| Slot | Placement |
|------|-----------|
| `header`, `kpis`, `risk`, `chart`, `filters`, `table` | Main column |
| `activity` | Right `rail` on desktop; below main on mobile |
| Optional future `profile` slot | Top of rail (not required in v1) |

**Implementation preference:** extend `SkeletonComposer` (or a thin `OpsDashboardComposer` used only for `ops-dashboard`) so pages keep supplying flat `slots` — no page-level CSS grid required.

Update `registry.ts` / `catalogue.json` purpose text and recommended order comments to describe main+rail. Keep required sections the same so existing contracts still validate:  
`shell, header, kpis, chart, filters, table, activity` (+ optional `risk`).

---

## 6. Component polish

### StatCard

- Add `variant?: 'strip' | 'card'` — default **`card`** for new soft ops.
- `card`: individual soft panel, icon chip, value, delta pill (green/red), short hint.
- `strip`: keep current dense border-r row for compact embeds if needed.

### PageHeader (ops)

- Support greeting-style titles (“Hello, {operator}” or business-appropriate “Today at {brand}”).
- Secondary meta on the right: date + optional icon actions (notification affordance is decorative in preview).

### ChartCard

- Prefer soft card chrome; default dashboard chart toward `area` or dual-series line when data allows.
- Keep Recharts; no new chart library.

### Work list (table / tasks)

- Prefer status pills (Badge) over raw status strings.
- Rows can remain `DataTable`; optional denser “task row” styling via className — no new required component in v1 unless table styling cannot hit the bar.

### ActivityFeed

- Timeline styling (avatar/initials optional), soft card shell matching rail.
- Keep alias normalization (`text`/`timestamp` → title/time).

---

## 7. Pipeline / generation

1. **Catalogue scaffolds** (`catalogue_contract.py`): richer KPI/chart/table/activity samples that look like a real dashboard, not “Sample record”.
2. **Prompts** (`preview_app_file.j2`): ops-dashboard guidance — soft cards, greeting header, activity meant for the rail, avoid inventing a second shell.
3. **Chrome guards:** continue enforcing shared `useAdminNavItems` + single `OpsShell` per page.
4. **No change** to PascalCase import collision fix in `assemble.py` (already shipped).

AI pages that fail contract still get scaffolds — scaffolds must already look soft-SaaS so fallbacks are not empty/ugly.

---

## 8. Validation plan (#7 Northline)

1. Update kit components + composer in `preview-template` (source of truth).
2. Sync into preview workspace `/app/data/preview-apps/7` (or rebuild via existing sync path).
3. Rewrite `src/pages/admin/DashboardPage.tsx` to use the new composition (slots only; no one-off layout hacks beyond kit APIs).
4. `vite build` and visual check at `/admin/dashboard`.
5. Smoke other admin routes (`/admin/drops`, `/admin/orders`) still work with soft `OpsShell` (list pages use shell without rail).

---

## 9. Acceptance criteria

- [ ] Soft light `OpsShell` is the default; dark floor remains available via prop.
- [ ] `ops-dashboard` shows activity in a right rail at desktop width.
- [ ] KPI cards match soft card language (not strip-only).
- [ ] #7 `/admin/dashboard` visually reads as soft SaaS overview (sidebar + KPIs + chart + list + rail).
- [ ] Catalogue contract / skeleton IDs unchanged enough that existing validators still pass.
- [ ] No new runtime dependencies.

---

## 10. Implementation order

1. `OpsShell` soft appearance + `rail`
2. `StatCard` card variant + light polish on `ActivityFeed` / `PageHeader`
3. `SkeletonComposer` (or ops-dashboard composer) main/rail split
4. Update `OpsReferencePage` as living example
5. Scaffold + prompt tweaks
6. Apply + rebuild preview #7 dashboard
7. Commit kit changes

---

## 11. Open decisions (resolved for v1)

| Topic | Decision |
|-------|----------|
| Dark sidebar | Keep as `appearance="floor"` only; soft is default |
| Right-rail profile card | Optional polish; activity alone is enough for v1 |
| Scope | Kit + #7 validation; full regen of a new business is follow-up QA |
