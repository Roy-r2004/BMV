# Kickoff — Phase 1 images: finish it and declare it shippable

Work happens ONLY on branch `consultant-images-pipeline` (local, 24 commits
ahead of origin, suite 164/164, tree clean). **Main is not to be touched.**
Read these first, in order: `consultant-service/ROADMAP.md`,
`docs/evidence/session32/results.md`, `docs/evidence/session32/README.md`.

The owner has signed off. Phase 1 is one session from done.

## Settled — do not re-litigate

- **The cinematic register ships.** The owner judged the five sign-off sheets
  and chose it. DoD line 3 **passes on the owner's eye**, which is what that
  line was always written to mean. `IMAGE_REGISTER=cinematic` stays default.
  The light register stays in the tree as the A/B control only.
- **`DASHBOARD_CANDIDATES` drops from 3 to 2**, taking a request from $0.60
  (exactly on the ceiling) to ~$0.45. Land it as a config change with a pin.
- **The pairwise judge gets one rubric rewrite, then a verdict.** Two models
  have now failed it identically — both picked the first-presented image and
  fabricated text errors to justify it. Judges are reliable on STRUCTURE and
  unreliable on TEXT. Rewrite the rubric to forbid text claims outright and
  compare on structure only, then test it on a known pair. **If it still shows
  position bias, retire the instrument** — delete the code path, say so in the
  evidence, and stop paying for it. Do not try a third model as well.
- **Spend ceiling $15** for the session, ledger-attributed. The key is shared:
  bracket every funded step against `ai_usage_events` and attribute only the
  delta, never the OpenRouter balance.
- Everything else settled in sessions 31–32 stands: watermark on every byte
  under `/uploads`; presentation glamour composited in PIL, never asked of the
  image model; text truth decided in code, never by a judge; the QA judge held
  FIXED while generators vary.

## JOB 1 — Prove the real pipeline works  (do this FIRST, ~$0.50)

**This is the biggest unretired risk in the project.** Everything measured in
session 32 went through `scripts/bakeoff.py`, which calls
`generate_demo_screens` directly. The public path — intake → orchestrator →
`/preview` → `/admin` — has not executed once since the spec schema
(`hero`/`concept`/`ai`), the register and the watermark all changed. 164 tests
say the pieces work; nothing says the whole does.

1. Submit a real request through the public intake endpoint against the
   running service and let the orchestrator run end to end.
2. Verify: screens saved and watermarked; `hero_url` / `detail_urls` present
   in `/preview`; `/api/requests/{id}/admin` reports per-image cost, model and
   `text_truth` per screen; the anchor came out as a TOOL screen.
3. Any breakage here outranks everything below. Fix it in the pipeline, pin
   it, and only then continue.

## JOB 2 — The cost knob  ($0)

Set `DASHBOARD_CANDIDATES` default to 2. Pin that a request's projected image
count and cost stay under the $0.60 DoD line. Update the measured cost table
in `docs/evidence/session32/results.md` and the artifact if you republish it.

## JOB 3 — The complete deliverable  (~$2.50)

Every sheet the owner has seen shows ONE screen per business. A real
deliverable is three, and no complete set has ever been produced in this
register.

1. Full golden-set run: 5 briefs × 3 screens, tiered (`gemini-3-pro-image`
   anchor, `gemini-3.1-flash-image` follow-ups), `GOLDEN_BRIEFS_DIR=golden/briefs-v2`.
2. Check every screen for: text-gate pass, register consistency across the
   three screens, and no prompt scaffolding rendered as UI (see traps).
3. Rebuild the sign-off sheets as full sets and commit them.
4. Record the true per-request cost and wall clock from the ledger.

## JOB 4 — The deck  ($0, but LOOK at it)

W4 compositing was verified against a dark screen in session 32 (the hero
composite is correct — browser chrome, brand-derived backdrop, mark on the
backdrop not over the UI). **The `.pptx` itself has not been rebuilt or opened
since the register changed**, and this deck has a documented history of
distortion and overlap bugs (`dd181b8`, `d6e8959`).

Regenerate it from the JOB 3 screens, **open it and look at every slide**, fix
what is wrong in the pipeline, and commit a rendered sample as evidence.
(Keynote's AppleScript `export ... as slide images` works; PowerPoint's
`save as PNG` produces nothing.)

## JOB 5 — The pairwise instrument  (~$0.20)

Per the ruling above: rewrite the rubric to forbid text claims and compare on
structure only. Test it on a pair whose answer is already known — e.g. the
retail v2 regression (nine panels, two cards both titled "Inventory Status")
against the retail v3 anchor, where the correct answer is unambiguous. Run
both orders. If it survives the swap and gets the known pair right, keep it
and note the fix. If not, retire it and say so plainly.

## JOB 6 — W7, the Phase-2 bridge  ($0)

Now unblocked by sign-off. Build the `blueprint → BMV brief` mapper with
tests: the artifact of a Phase-1 image demo becomes the input to a Phase-2
React build, so a closed lead upgrades without re-entering anything. Follow
the W7 section of `ROADMAP.md`.

## JOB 7 — Close it out  ($0)

1. `docs/evidence/session33/dod-assessment.md` — all five DoD lines, measured,
   in the style of session 31's. State plainly which pass, which fail, and
   what each was measured against.
2. Update `ROADMAP.md` statuses.
3. Closing evidence doc + README index for session 33.
4. **If all five DoD lines hold, declare Phase 1 shippable** in ROADMAP.md.
   If any line fails, say which and why, and do not declare it.

## Gates on every job

- Service suite green in the container:
  `docker run --rm -v "$PWD:/repo" -w /repo/consultant-service --entrypoint sh bmv-local-api -c 'pip install -q -r requirements.txt; python -m pytest tests/ -q'`
- Every behavior change lands with a pin. No silent caps — if you bound
  coverage, say so in the evidence doc.
- Bracket every funded step against the service ledger, before and after.
- Host python is externally managed — run python through the container or the
  session venv; never `pip install --user` on the host.
- `OPENROUTER_API_KEY` is already in `consultant-service/.env`. Never commit it.

## Traps — every one of these cost real money or real time in session 32

- **Docker `-e` flags go BEFORE the image name.** One placed after it was
  passed to the shell instead, so the cell silently used the v1 golden briefs
  and the wrong database. Cost $0.29 and a wasted comparison.
- **Never run two bake-off batches concurrently.** `results.json` is rewritten
  wholesale from an in-memory list loaded at start, so the second batch
  silently drops the first's rows. Two cells' records were lost this way (the
  images and ledger survived; the result rows did not).
- **Mount the repo root** (`-v "$PWD:/repo"`), not `consultant-service` — the
  logo lives at `frontend/public/logo.png` and a service-only mount makes the
  watermark silently no-op.
- **Pass `-e DATABASE_URL` explicitly.** The image's baked-in value beats
  `.env`, so every ephemeral container restarts request ids at 1 and cells
  overwrite each other's screenshots.
- **Use `GOLDEN_BRIEFS_DIR=golden/briefs-v2`.** `golden/briefs/` is the v1 set,
  frozen under `ui-spec-v1`, with no `hero`/`concept`/`ai` fields. It is the
  control arm — do not overwrite it.
- **If the model renders your prompt's scaffolding, change the scaffolding.**
  Telling it not to does not work — that was tried and the leaks came from the
  run carrying the instruction. Section headers are sentence-case prose now;
  keep them that way.
- **Trust judges on structure, never on spelling.** The scoring judge is
  saturated (it gave 9.2 to four materially different conditions) and the
  pairwise judge invents text failures. Text truth is decided only by
  `text_truth.py`.
- **Zoom in before believing a text complaint** — and before dismissing one.
  Both have happened.

## Definition of done — current state

| # | line | state entering this session |
|---|---|---|
| 1 | brand-critical text 100% | **holds** — 8/8 on the last measured set; re-verify on JOB 3 |
| 2 | no screen below 8, and no structural defect | **amended 2026-08-11** — the ≥9 anchor threshold was retired by the owner as anti-correlated with quality; verify the new form on JOB 3 |
| 3 | beats the old default, owner's eye final | **PASSES** — owner signed off on the session-32 sheets |
| 4 | ≤$0.60/request, ≤3 min | **holds** — $0.45 after JOB 2; confirm on the JOB 3 full run |
| 5 | zero unbranded bytes under /uploads | **holds**, pinned |

**Line 2 was rewritten by the owner on 2026-08-11** and now reads: *no shipped
screen scores below 8/10 on the fixed QA judge, and none carries a structural
defect — a duplicated panel, clipped or truncated content, a blank or
unlabelled control, prompt scaffolding rendered as UI, or a garbled
axis/label.*

The old form required anchors ≥9 on 4 of 5 briefs. It was retired because the
judge that measures it does not track quality: it scored 9.2 for the retail v2
screen (two panels both titled "Inventory Status", axis labels reading "Low /
Misit / High / High") and 8.7 for the screen the owner chose as the best of
the run.

Assessing the new form is a LOOKING task, not a scoring task. Open every
shipped screen from JOB 3 and check the defect list by eye. The judge's issue
lists are a useful starting point — its structural findings have held up under
inspection every time — but the verdict comes from the image, and a claimed
misspelling is verified by zooming in, never taken on trust.
