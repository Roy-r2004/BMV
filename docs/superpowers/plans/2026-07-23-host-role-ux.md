# Host Role UX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Host chrome shows “Viewing as…” + per-role page tabs using existing preview roles/routes.

**Architecture:** Pure helpers for route filtering; `PreviewAppPreview` UI; finalize adds optional `tagline`.

**Tech Stack:** React + CSS (frontend), Python finalize (backend).

---

### Task 1: Route filter helper + tests (frontend)

**Files:**
- Create: `frontend/src/components/preview/roleRoutes.ts`
- Create: `frontend/src/components/preview/roleRoutes.test.ts` (or vitest path used by repo)

Steps: filter routes by role, attach orphan routes to first role, exclude `/ai-features`, derive blurb.

### Task 2: PreviewAppPreview chrome

**Files:**
- Modify: `frontend/src/components/preview/PreviewAppPreview.tsx`
- Modify: `frontend/src/styles/index.css`
- Modify: `frontend/src/types/request.ts`

### Task 3: Finalize tagline

**Files:**
- Modify: `backend/app/application/preview_app/pipeline/finalize.py`
- Optional small backend test if pattern exists

### Task 4: Commit + push
