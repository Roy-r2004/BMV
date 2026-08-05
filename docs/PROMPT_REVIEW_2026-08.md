# Prompt review — honest opinion, one fix landed, five suggestions filed (2026-08-06, session 16)

Owner-requested review of the prompts the pipeline sends, against current best practice
(sources at bottom). Scope: the three hot templates — `preview_app_file.j2` (the per-page
writer, ~1,170 calls), `preview_app_slot_fill.j2` (the scaffold filler), and
`preview_app_architect.j2` — plus the render-site audit that already ran this session
(`scripts/measure/prompt_variable_audit.py`).

## The honest verdict

**These are above-average production prompts.** Most codebases' prompts are a paragraph of
vibes; these are contracts. Specifically strong, and worth keeping exactly as-is:

- **Bans are grounded in real shipped bugs, with the failure spelled out.** "A generated page
  added `after:bg-blend-multiply…` and turned the headline white-on-white" beats any abstract
  "ensure contrast" rule. This is the single best practice in the whole set and it appears
  consistently.
- **The consequence is taught, not just the rule.** "A wrong prop name does not fail the
  build — it renders an EMPTY component" tells the model *why* the prop contract is the
  highest-value rule on the page. Explained rules get followed; bare rules get traded away.
- **The schema legend** ("How to read it: `requiredProps`… `?` marks an optional member")
  teaches the model to read the machine contract instead of hoping it guesses.
- **Output contracts are explicit** ("Output ONLY the file contents — no markdown fences";
  the architect's full JSON shape inline).
- **Prompt bans are mirrored in code** (`copy_hygiene.py` enforces the meta-demo ban the
  slot_fill prompt states) — defense in depth instead of trusting the model.

The weaknesses are the weaknesses of a prompt that grew by accretion under fire — every line
earned its place in some incident, and nobody has ever been allowed to delete.

## Landed tonight (offline-provable)

**Two instruction blocks addressed to files this prompt never generates** rendered into every
page call: the 9-line "For App.tsx:" block (4 CRITICALs) and the `src/index.css` CRITICAL.
Both files are assembler-owned (`write_app_tsx`, `write_index_css` — deterministic templates),
and **0 of 42 archived architect worklists contain either file**. The pipeline's own test
philosophy already listed them as "assembler_owned" in the *architect* prompt check — the file
prompt just never got the same treatment. Now gated on `file_path` (conditional, not deletion),
pinned by `test_assembler_owned_file_instructions_never_reach_a_page_prompt`, 4 mutations /
0 survivors (`mutate_prompt_file_gates.py`). Also landed earlier this session: the
CATALOGUE ITEM SHAPES wiring (`d28df68`) and the standing variable audit.

## Filed — worth doing, but each needs a run or a judgment call

1. **`preview_app_file.j2` has two different sections titled "For page components
   (kind=page):"** with different content (~line 175 and ~line 248). Models resolve duplicate
   headers unpredictably (second-wins, or blended). Merging them is a wording change — 20
   minutes of editing, but unverifiable without generations. Do it beside a funded run.
2. **The density demand appears four times** ("thin pages fail", "~180+ lines", "pages must
   feel dense, cinematic", "production density") across PRODUCT IMMERSION / QUALITY BAR /
   CONTENT RULE. Deliberate repetition of critical constraints is good practice — twice.
   Four times dilutes everything else. Same treatment: consolidate beside a run.
3. **Cache-hostile ordering.** Within one run, `full_context` + `architect_json` +
   `design_system_json` are identical across all ~20+ page calls — a natural cacheable prefix —
   but the static rule blocks sit AFTER the per-page sections, so providers with automatic
   prefix caching (DeepSeek: "60-80% cheaper"; Gemini implicit caching) can only cache the
   run-stable head. Reordering to `static rules → run-stable context → per-page tail` would
   maximize provider-side cache hits at zero quality intent change — but position affects
   attention, so it needs an A/B, not a hunch.
4. **The architect asks for JSON by prose contract, not by enforcement.** OpenRouter exposes
   structured outputs (`response_format: json_schema`) on several of our candidate models.
   The planning chain burns 70-94 s/run partly on validate/repair loops; schema-enforced
   decoding could cut the repair tail. Needs per-model support verification + a run.
5. **`scaffold_source[:16000]` is a raw slice with no truncation marker** (slot_fill).
   `_bounded_json` marks its truncations; this one silently hands the model a cut-off file
   while demanding "the COMPLETE file" back — a guaranteed rejection when it fires. Proxy
   measurement: 5 of 883 archived pages exceed 15k chars, so it's rare but real. Cheapest
   robust fix is code, not prompt: skip slot-fill and keep the deterministic scaffold when it
   doesn't fit the window. Small fixture-testable change; bundle with the next codegen work.

## What I deliberately did NOT do

No wording edits, no consolidation, no reordering. Prompt behavior is only measurable with
generations, and the binding rule is that a fix needing a run lands WITH the run. The two
gates landed tonight are the exception precisely because unreachable content is provable
offline — reachability is a fact about the worklist, not about model behavior.

## Sources

- [Anthropic: Prompt engineering best practices for 2026](https://claude.com/blog/best-practices-for-prompt-engineering)
- [A Practitioner's Guide to Prompt Engineering in 2026](https://www.getmaxim.ai/articles/a-practitioners-guide-to-prompt-engineering-in-2025/) — instruction ordering/hierarchy; structured-output brittleness
- [Prompt Engineering Best Practices 2026](https://pecollective.com/blog/prompt-engineering-best-practices/) — few-shot counts, contradiction handling
- OpenRouter model pages for provider-side caching notes (see MODEL_RESEARCH_2026-08.md)
