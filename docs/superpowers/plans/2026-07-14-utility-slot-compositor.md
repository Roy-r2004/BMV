# Utility Slot Compositor — Implementation Plan

> **For agentic workers:** Slice 1 delivered in this change set.

**Goal:** Compose `public-utility` pages from content JSON so transactional pages stop relying on freeform React.

**Architecture:** Route infers workspace type → AI fills JSON → `utility_compositor.compose_utility_page_tsx` emits kit TSX → catalogue contract validates.

**Tech Stack:** Python compositor, Jinja content prompt, existing SkeletonComposer / catalogue contract.

## Files
- `backend/app/application/preview_app/utility_compositor.py` (new)
- `backend/app/templates/prompts/preview_app_utility_content.j2` (new)
- `backend/app/application/preview_app/codegen.py` (wire)
- `backend/app/application/prompts.py` (template const)
- `backend/scripts/test_utility_compositor.py` (tests)
- `docs/superpowers/specs/2026-07-14-utility-slot-compositor-design.md`

## Done
- [x] Infer cart/checkout/tracking/account/generic from route
- [x] Normalize + compose TSX
- [x] Branch in `generate_file`
- [x] Unit tests green
