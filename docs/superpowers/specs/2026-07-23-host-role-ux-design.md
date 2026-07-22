# Host Role UX — Design

**Date:** 2026-07-23  
**Status:** Approved (host-only chrome; option C)  
**Goal:** Make role switching and page discovery feel like touring a real product, not thin chips over an iframe.

## Problem

`PreviewAppPreview` exposes role chips (e.g. Patient / Front Desk) but buyers don’t get:

1. Clear **“viewing as…”** framing for the active product face  
2. A **page map** of that role’s routes even when `preview_app.routes` already exists

## Approach

**Host-only chrome upgrade** (no iframe / codegen changes).

Reuse persisted `preview_app.roles` + `preview_app.routes`. Optionally pass `tagline` from plan/architect roles into `roles_out`.

## Behavior

### Viewing as…

- Header (or URL chrome right) shows **Viewing as {Role label}** plus a one-line blurb.
- Blurb source order: `role.tagline` → short derived line from label (e.g. “Patient view”, “Front Desk view”).
- Role chips remain; active chip uses role accent.
- Role change remounts iframe at `defaultPath` and resets the page strip to that role’s routes.

### Page map

- Horizontal page tabs for the **active role only**, filtered from `routes` by `role_id`.
- Routes with missing/`""` `role_id` attach to the public / first role only (never duplicated across staff roles).
- Exclude `/ai-features` from the strip (AI chip stays separate).
- Clicking a tab navigates via the same host remount path used for role switch.
- Active tab follows `currentPath` from the preview-url bridge (prefix / exact match).
- Mobile: horizontal scroll; no layout collapse of the iframe.

### Out of scope

- In-app injected tours  
- Full left sidebar product map  
- New API endpoints  
- Changing how roles are generated

## Data

| Field | Source |
|-------|--------|
| `roles[].id/label/icon/accent/defaultPath` | existing `finalize` `roles_out` |
| `roles[].tagline` | optional; from architect/plan role when present |
| `routes[].path/title/role_id` | existing `route_list` |

Frontend types: extend `PreviewAppRole` with optional `tagline`.

## Files

- `frontend/src/components/preview/PreviewAppPreview.tsx` — chrome UX  
- `frontend/src/styles/index.css` — page strip / viewing-as styles  
- `frontend/src/types/request.ts` — `tagline?`  
- `backend/.../pipeline/finalize.py` — include `tagline` on `roles_out`  
- Small unit helpers + tests for route filtering (pure functions preferred)

## Success

On a multi-role preview (clinic): buyer can switch Patient ↔ Front Desk, see a clear “Viewing as…” line, and jump to Doctors / Book / Staff pages from the host without hunting inside the iframe nav.
