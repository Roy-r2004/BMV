# Kickoff — Phase 1 images: build it astonishing, start to finish (2026-08-10)

You are on the BMV repo at ~/Documents/Dev/BMV. Work happens ONLY on branch
`consultant-images-pipeline` (local, ahead of origin; contains main through
`849d845`, merge `7c5eae4`, hardening `29c28ef`, roadmap `e638a52`). Main is
NOT to be touched this session. The governing plan is
`consultant-service/ROADMAP.md` — read it first; this prompt compresses its
sessions A–E into three jobs and settles what was already decided.

## Settled rulings — do not re-litigate
- Model choice is decided by the W1 bake-off, not by preference. Candidates:
  `google/gemini-3-pro-image` (incumbent), `openai/gpt-5.4-image-2`,
  `google/gemini-3.1-flash-image`. All verified reachable on the shared
  OpenRouter key (2026-08-10). Re-probe availability before spending.
- The QA judge stays FIXED (`QA_MODEL` as configured) while generators vary.
  Never vary judge and generator together.
- Design for tiering: pro-class anchor, flash-class follow-ups conditioned
  on the anchor. Adopt it only if the bake-off's tiering trial holds up.
- Text truth is a hard gate: brand-critical strings (business name, product
  name, nav labels) must match the spec EXACTLY or the screen regenerates.
  Aesthetic score never overrides a misspelled client name.
- Presentation glamour (browser chrome, device frames, backdrops, shadows)
  is composited deterministically with PIL. NEVER ask the image model for
  perspective/device mockups — it garbles UI text.
- Watermark policy stands: every image byte under /uploads is watermarked
  (pinned by test_images_hardening.py — keep it green).

## Jobs, in order

JOB 1 — bake-off + packs + text gate (budget cap $6, bracket the ledger).
1. Wire `model` as a per-call variable through provider.generate_image →
   _generate_candidates → generate_demo_screens (mirror how composition
   variants became first-class). Pin it.
2. Author 3 golden briefs across distinct archetypes (dental ops dashboard
   exists in tests — add e.g. a bookings/CRM archetype and an analytics
   archetype from app/archetypes.py). Commit them as fixtures.
3. Run the matrix: 3 briefs × 3 models, anchor(3 variants)+2 follow-ups,
   QA-scored + ONE pairwise pass per brief-pair. Persist per-image cost
   from the service's own usage log (never the balance — the key is shared;
   attribute only the ledger delta, no leak alarms).
4. Write per-archetype defaults into config + an evidence doc
   (`docs/evidence/session31/images-bakeoff.md`) with the matrix, costs,
   verdicts, and the tiering trial result.
5. W2: per-archetype art-direction packs (named type pairing, spacing/
   density rules, chart styling, light/dark stance, exact hex palette
   derived from brand color) as versioned prompt packs; A/B one pack vs the
   current prompt through the same judge before adopting all.
6. W3: transcribe-and-diff text gate in qa.py (spec strings are ground
   truth), hard-fail set = {business_name, product name, nav labels},
   auto-regen on failure, pins for gate + regen path.

JOB 2 — deterministic glamour ($0).
7. W4: PIL compositor — browser chrome + device frame + brand-gradient
   backdrop + soft shadow; outputs hero shot + 1–2 detail crops per screen;
   pptx upgraded to a branded deck using the composited frames. The pptx
   has a history of distortion/overlap bugs (dd181b8, d6e8959): open the
   generated deck and LOOK at it; commit a rendered sample as evidence.
8. W6: surface per-request cost in the admin payload; keep candidates
   hygiene pinned.

JOB 3 — eval, sign-off, bridge (budget cap $3).
9. W5 experiment: design-system-sheet conditioning vs anchor-as-reference,
   same fixed judge; adopt only on a win.
10. Full golden-set run (5 briefs) with everything on; produce the
    side-by-side sheet (old default vs new pipeline) and STOP for the
    owner's eye — the DoD's pairwise criterion is theirs to judge.
11. After sign-off: W7 bridge — `blueprint → BMV brief` mapper + tests so a
    closed Phase-1 client upgrades into Phase 2 without re-intake.

## Gates (every job)
- Service suite green in the container:
  `docker run --rm -v "$PWD/consultant-service:/svc" -w /svc --entrypoint sh
  bmv-local-api -c 'pip install -q -r requirements.txt; python -m pytest tests/ -q'`
- Every behavior change lands with a pin. No silent caps — if you bound
  coverage, say so in the evidence doc.
- Bracket every funded step: read the service usage ledger before/after;
  attribute only our delta (shared key).
- Host python is externally managed — run python through the container or
  the session venv; never pip install --user on the host.
- OPENROUTER_API_KEY: read it from the running bmv-api container env into
  the service's .env at session start; never commit it.
- Total session spend ceiling $10 unless the owner raises it. Abort a
  funded step if the pre-step balance probe shows the key overdrawn.

## Definition of done (from ROADMAP.md — all five)
1. Brand-critical text accuracy 100% on shipped screens.
2. Every shipped screen QA ≥ 8/10; anchors ≥ 9 on ≥ 4 of 5 golden briefs.
3. Pairwise: new pipeline beats the old default on ≥ 4/5 briefs — judge AND
   owner; the owner's eye is final.
4. Cost ≤ $0.60/request with tiering; wall ≤ 3 min.
5. Zero unbranded bytes reachable under /uploads (pin stays green).

First moves, exactly: `git checkout consultant-images-pipeline` → tree
clean check → service suite green → balance + model-availability probes →
JOB 1. When all five DoD lines hold and the owner has signed the pairwise
sheet, update ROADMAP.md statuses, write the closing evidence doc, and
declare Phase 1 shippable.
