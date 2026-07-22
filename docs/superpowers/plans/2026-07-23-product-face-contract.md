# Product Face Contract Implementation Plan

> **For agentic workers:** Implement task-by-task. Spec: `docs/superpowers/specs/2026-07-23-product-face-contract-design.md`

**Goal:** LLM/brief `product_face` owns copy + page_intent; packs only gap-fill empty fields.

**Architecture:** New `product_face.py` normalize/merge/materialize; pack apply becomes gap-fill; scaffolds prefer `page_intent`.

**Tech Stack:** Python backend, existing experience plan + industry packs.

---

### Task 1: `product_face.py` + tests
### Task 2: Pack apply gap-fill only
### Task 3: Wire plan_phase + prompt
### Task 4: Scaffold intent routing
### Task 5: Commit + push
