# Step 3 recon (2026-11-01): how the package is produced today

Facts verified by read-only scouts on branch step1-honest-failure at 8ef72d6. File:line as the scouts gave them.

## Constraints
- `app/pipeline/**`, `app/prompts/**`, `tools/**`, top-level `tests/*.py` are hash-frozen (`tests/engine/r30_manifest.json`). Editing them is allowed; the last task re-freezes (`refreeze_r30.py --commit <sha>`; two constants in `tests/engine/test_engine_r30_frozen.py:81` and `test_engine_mutation_manifest.py:526`). A new module under `app/pipeline` is frozen too; one outside it is not.
- The engine imports private names from the two export modules and must keep working: `app/engine/work_products/render_pdf.py:55-66` (`_EngagementDoc, _S, _SECTION_COUNTER, _h1, _markdown_flowables, _page_chrome, _rich, _table, strip_page_chrome, F_SB, LINE`), `render_deck.py:28-37` (`MARGIN, SLIDE_H, SLIDE_W, _add_bg, _add_bullets, _add_text, _hairline, _hex_to_rgb, _kicker`). Also `engine/gates/presentation.py:141,377` (`strip_page_chrome`, `presentation_findings`), `gates/release.py:68` (`STATUS_LABELS`), `gates/laws.py:626` and `figures/audit.py:130` (`release_status`), `legacy/r30_adapter.py:542` (`build_pdf(row, kind)`, `VOLUME_KINDS`).

## Today's files
- Volume I blueprint, II technical, III operations: `export_pdf.build_pdf(req, kind)` (`export_pdf.py:1873`), reportlab platypus; `_volume_flows` (2097) = cover + TOC + per-section flowables; blueprint order hard-coded 2111-2156; technical 2157-2160; operations 2161-2168 (raises ValueError "operations manual not ready" without procedures/org/checklists). Body frame A4, 18 mm margins; no per-page layout, content flows; `_h1` (295-305) CondPageBreak(55mm).
- Volume IV system screens: `app/screens/export.py:65 build_system_pdf`, HTML `app/screens/templates/proposal.html` (11 `<section class="page">`), Playwright Chromium.
- Deck: `export_pptx.build_presentation` (331), `_build_presentation` (384); route builds inputs at `requests.py:1443-1471`. Titles are hard-coded literals (475, 524, 567, 763, 815, 841).
- No roadmap PDF. No storyline object. Neither PDF nor deck reads `answer_json` or `action_plan_json` (only Volume IV does: `screens/export.py:44-51`). No charts/exhibits anywhere (no reportlab.graphics, no add_chart). No footnote/Note/Source feet.
- ZIP: `build_zip` `requests.py:1345-1382`, hard-coded three PDFs + system PDF; the deck is not in it. Shared route `shared.py:96-105` serves only `zip` + `PDF_KINDS` (`requests.py:1401` = blueprint, technical, operations, system); `pptx` 404s on a share link; shared `documents` is a fixed 3-key dict (`shared.py:79-83`).
- `produced.documents_for` (`app/produced.py:38-64`) is the only titled list (five entries + ai_team); served on the progress poll only (`requests.py:522`).
- Review editor: `POST /{ref}/review/docs` (`requests.py:1244`) accepts only `mvp_blueprint` and `technical_plan`; UI `StudioPage.tsx:3255-3270`.

## Release law and page identity
- PDF choke point `_rich` (275-282) calls `law.check`; `_drawn` skips; `DrawnCell` marks renderer-written cells. Deck: `_add_text(..., drawn=False)` / `_checked` (129-187), page = slide number. Volume IV: Jinja finalize `render.py:56-60`. `law.DOCUMENTS` (`law.py:64-67`) = Volume I..IV page, The deck slide. Page numbers found after build by `law.locate_pages` (PyMuPDF text search, header/footer bands excluded). `labels.LABEL_WORDS` already includes exhibit, table, footnote, slide, page, appendix, volume.
- PDF cache: `uploads/exports/{id}-{kind}.pdf` reused while newer than `req.updated_at` and stamped state equal (`export_pdf.py:1905-1910`); `rl_config.invariant = 1` makes bytes deterministic (test pins it).
- Release states: `STATUS_LABELS` (646) DRAFT / FINAL — CONSULTANCY DELIVERABLE / CLIENT APPROVED; `release_status` (649-718).

## Answer module
- `app/pipeline/answer.py` (458 lines); `write` at 380, called from `orchestrator.py:271`; stored in `Request.answer_json`: headline(<=80), turn(<=80), sub(<=420), emphasis, figures[<=2] {value,label,cites,ids}, move {label,value,rounded,money,unit,period,display,working,proposed[],cites[]}, action {weeks,name,figure}. Web payload adds segments + figures map (`figures/payload.py` answer_for_web 283, for_web 364). `confidence` goes into the prompt only, not stored.

## Hedging copy to remove or reword (exact places)
- `export_pdf.py`: 644 BMV_STATEMENT ("Prepared by BMV AI. Recommendations and proposed thresholds require client validation..."), 849-850 and 1849 "DRAFT — REQUIRES VALIDATION...", 415 "AI-native consultancy", 1139/1151/1155/1403/1436 "(proposed — client approval required)" (also hard-coded in registry/pilot gate `adjudicate.py`, `integrity.py:669`), 1396-1397, 1404, 1413, 1432-1438, 1713-1714, 1730-1731, 1421-1430 headings, 1445-1458.
- `method_note.py:27-30`. `export_pptx.py:658` (ai.confidence), 866, 850-854, 715, 494/501 fallback bullets.
- Frontend: `Answer.tsx:232` "What we estimated or couldn't check.", 355, 314, 322, 339-344, 59-62, 208; `Package.tsx:272, 471, 325-326, 292`; `StudioPage.tsx:2641, 2652, 2568, 2872-2880 (story.ai.confidence), 2919`; `Interview.tsx:283`.
- Pinned by tests: `tests/test_consultancy_layers.py` (test_engagement_zip_bundle 394-415 `len(names)==3`; draft watermark 1049/1072; status labels 1158/1177; pdf cache 964; identical bytes 1471), `tests/test_run53_r3.py:41-62,100`, `test_run52_controls.py:179-192`, `test_run53_r4.py:148`, `test_registry_controls.py:924`, `test_deck_layout.py`, `test_deck_palette_and_callouts.py`, `tests/figures/test_law.py` (deck slide, furniture, ZIP sample test), `test_acceptance.py`, `test_audit.py:219`, `test_consultation_flow.py:404-412`, `test_honest_failure.py:1961-1990`, `test_screens.py:80,479`, `engine/test_engine_legacy_adapter.py:840`.

## Frontend
- Owner: `StudioPage.tsx` (3295 lines) state `Act`: decision (2666), building (2685), ready (2710), reveal (2730: `<Package>` + RESULT_TABS), pending (2556). A finished run opens straight in `reveal` (`applyProgress` -> `showResult`, 1707): the answer is not the first screen. Shared: `SharedPage.tsx` (104 lines) renders `<Package readOnly>` only, never `<Answer>`. Reviewer = owner page with `?review=<token>` (1515, 2754, 3217, editor 3249).
- Downloads: hard-coded `Book` cards `Package.tsx:279-339`; `docs` booleans from `StudioPage.tsx:2742-2746`; shared `documents` booleans (`consultant.ts:697`); `StudioExportKind` closed union (1040); `downloadStudioExport` (1046), `downloadSharedExport` (790); deck only in `StudioPage.tsx:1300, 2986`; "ZIP — all three volumes" 1296, `consultant.ts:1032`, `ShowcaseEngagements.tsx:42`.
- Styling: scoped `consult.css` (`.cx` tokens, 530 lines) + Tailwind v4 one-offs; breakpoints 1100/980/720/900/1000; 390px falls under `<720`. No table styles exist in consult.css. No frontend tests; checks = `tsc -b`, `oxlint` (14 warnings today).
