# Utility slot compositor (public-utility)

**Date:** 2026-07-14  
**Status:** Implementing slice 1

## Problem
Transactional catalogue pages were AI-authored freeform React. That invented props/imports, failed contract checks, and fell back to identical scaffolds.

## Solution
For `skeleton_id == "public-utility"`:
1. Infer workspace type from route (`cart` | `checkout` | `tracking` | `account` | `generic`).
2. Ask AI for **content JSON only** (copy, line items, fields, status steps).
3. Deterministically compose TSX: `PublicShell` + `SkeletonComposer` + typed workspace.
4. On invalid JSON, compose from recipe/brand defaults — never blank, never freeform invent.

## Uniqueness
Shared frame per job; uniqueness from recipe CSS tokens, brand copy, business-specific line items/fields/statuses. Optional later: recipe → layout variants (`dense` / `card`).

## Out of scope (slice 1)
Marketing skeletons, ops pages, freeform TSX for utility pages.
