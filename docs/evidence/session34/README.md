# Session 34 — the credibility classes, engineered away and measured

*2026-08-12, branch `consultant-images-pipeline`. Ledger-attributed spend
**$3.87** (+$0.395 direct probe calls, receipts in
[`probe/results.json`](probe/results.json)) against the $15 ceiling.
Suite 228 → 262. Five commits.*

**The session ended on an external stop: the shared OpenRouter key ran
out of credits** mid-way through the final golden-set brief (hedgefund,
402 "can only afford 540 tokens", $0 spent on it). Four of five briefs
completed; three measurements remain blocked and are one command each —
see [`next-session-runbook.md`](next-session-runbook.md).

## What landed, in order

1. **JOB 1 — 2K follow-ups** ([`job1-resolution.md`](job1-resolution.md),
   commit `54c9303`). `image_config` probed on the real salon prompt:
   flash honours 2K (2752×1536, +$0.033/image), pro ignores it on both
   slugs. Five of six s33 collapsed letterforms were flash follow-ups —
   the class is dead on every 2K screen inspected since ("CLIENTS",
   "Full Highlights", law's whole nav, all flawless at matched zoom).
   *Corrected in-session:* the sixth ("SLB") was a pro ANCHOR — residual
   risk resolution cannot fix, owned by the text-truth gate, not
   reproduced in the re-run. JOB 4 not triggered.
2. **JOB 2 — backdrop crop** ([`job2-backdrop-crop.md`](job2-backdrop-crop.md),
   `8941d49`). Deterministic PIL, four independent refusal guards,
   validated on all 28 real images: the 3 salon floats crop cleanly, 25
   full-bleed screens byte-identical. Two false-positive shapes were
   built, killed, and pinned as synthetics on the way.
3. **JOB 3 — the two-stage defect check, in the request path**
   ([`job3-defect-check.md`](job3-defect-check.md), `b847698`). Inspector
   → per-claim refuting verifier, text claims forbidden, fail-open,
   $0.00228/candidate. Paid for by architecture: follow-up screens now
   generate in parallel on their own DB sessions, and the three QA
   instruments fire concurrently — both pinned by barrier tests that
   deadlock if ever serial again. First funded run: a confirmed defect
   bought a regen that went 8.5 → 9.2 clean; a noise claim was refuted
   for $0.0008; and the best-effort path was caught preferring a
   defective 8.1 over a clean 7.8 — fixed, pinned.
4. **JOB 5 — the AI module's own title** (`b958feb`). `ai.title` field,
   filled by ui-spec-v3 with real product labels ("Smart Reorder",
   "Churn Risk", "Next Best Action"), rendered as an exact string. The
   v3 golden set is frozen BESIDE briefs-v2; a v2 brief's prompt is
   byte-identical under the change, pinned — the control arm stays a
   control.
5. **JOB 6 — not started, by the brief's own stop rule**, and its premise
   now has in-path measurement: all three defects the full set shipped
   are `malformed_data_display` (charts contradicting their own axes).
   That is next session's primary target, with a baseline metric.

## The full-set re-measure (4 of 5 briefs, control arm v2)

[`fullset-results.md`](fullset-results.md) has the table, and the proof
sheet of every screen this session generated, annotated with the
instruments' verdicts, is at
https://claude.ai/code/artifact/9abc3d1c-e107-4705-b631-6d832347f6ea
(rebuild: `aggregate_fullset.py` writes the numbers,
`gallery_manifest.json` + the build script in the session scratchpad
render the page). Headlines
against session 33 on the same briefs:

| | s33 | s34 |
|---|---|---|
| screens below 8 | 4 of 15 | **1 of 12** (a best-effort 6.5) |
| screens shipping a confirmed structural defect | 13 of 15 (offline sweep) | **3 of 12** (in-path check; all three are the chart class) |
| text-truth failures shipped | 1 ("Cilents") | **0** |
| mean cost / brief | $0.4415 | **$0.6022** — ON the line; the gates now buy regenerations that used to ship as defects |
| wall / brief (same harness) | 90–101s | 116–173s (includes those regenerations; follow-ups parallel) |

Both carried-in unmeasured questions got funded observations: the
enforced gate at 8 rejected a judge-approved 7.9 live, and the band-path
text-truth gate rejected a 2K candidate for a wrong wordmark ("Lumière
Hair Studio" for "Lumière Studio OS"). A rendered-misspelling catch
remains unobserved — at 2K the class appears to die upstream of the gate.

## Blocked, and exactly how to resume

The key died with three measurements outstanding: the hedgefund control
brief, the v3 title arm (law + retail), and the end-to-end request that
answers the 3-minute clock on the new parallel path
([`run_e2e_request.sh`](run_e2e_request.sh) is written and waiting).
[`next-session-runbook.md`](next-session-runbook.md) is the whole list,
one command each.
