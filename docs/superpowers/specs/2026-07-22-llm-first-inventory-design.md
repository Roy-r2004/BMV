# LLM-First Product Inventory — Design Spec

**Date:** 2026-07-22  
**Status:** Approved  

## Problem

`product_kind` blueprints overwrite the experience plan / architect inventory, so the system specifies pages/roles more than the customer brief + LLM.

## Target

- **LLM owns** roles, pages, paths, and public vs ops mix (from the brief).
- **product_kind owns** recipe/chrome defaults and **fallback** inventory only when the plan is empty or broken.
- No industry-specific “always add clinic admin” hacks — the brief drives staff/admin when mentioned.

## Rules

1. If a role already has a substantive multi-page inventory → keep it; only repair chrome (e.g. ops kind must not keep a marketing `/` hero).
2. If inventory is empty/thin → seed from kind blueprint defaults.
3. Architect: do not inject the full blueprint page set over a rich LLM route list; fill gaps only when thin.
4. Prompts: invent roles/screens from the brief; kind is chrome guidance, not a page ceiling.
