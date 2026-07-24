# Preview Generator v2 — Phase 5 Visual Evaluation

Phase 5 evaluates a complete, immutable Phase 4
`candidate_runtime_validated` result. It adds evidence verification, a
provider-aware multimodal critic/reviewer boundary, deterministic acceptance,
and at most one allowlisted source refinement. It does not promote, serve,
polish, finalize, generate Tier 2/3, or begin Phase 6.

## Feature boundary and rollback

Phase 5 is disabled by default:

```text
PREVIEW_GENERATOR_V2=false
V2_RUNTIME_VALIDATION_ENABLED=false
V2_VISUAL_EVALUATION_ENABLED=false
```

It runs only when all three settings are true. Disabling
`V2_VISUAL_EVALUATION_ENABLED` returns the exact Phase 4 stopping result. The
append-only Phase 5 tables and evidence remain intact; rollback does not
rewrite or delete history.

The original Phase 3B candidate, its Phase 4 validation workspace, any legacy
accepted preview directory, and any serving state remain immutable. A visual
refinement creates a new `candidate_revisions` row and a new frozen candidate
workspace.

## Immutable input replay

Before a provider call, Phase 5:

1. requires `candidate_runtime_validated`;
2. resolves the same-request candidate, runtime attempt, build, and terminal
   Phase 4 summary;
3. reparses every typed Phase 3A/3B/4 artifact and verifies stored hashes;
4. recomputes the Phase 3B source manifest hash;
5. recomputes the final dist manifest and build hash, including the build
   identity;
6. requires the complete canonical Tier 1 page × mobile/tablet/desktop
   matrix;
7. requires passing route, journey, accessibility, and screenshot evidence;
8. recomputes every screenshot hash and the ordered screenshot-set hash;
9. decodes each PNG and requires exact capture dimensions; and
10. rejects missing, stale, cross-request, cross-build, or cross-contract
    references.

No AI call can run before these checks and the model capability policy pass.

## Dedicated model capability registry and routing

The Phase 5 registry is an allowlist for the repository's OpenRouter
OpenAI-compatible content-parts message format. It does not query a remote
model endpoint and no canary is run.

| Stage | Default model | Family | Capability | Timeout |
|---|---|---|---|---:|
| visual critic | `openai/gpt-4o` | OpenAI | multimodal chat | 150 s |
| independent reviewer | `google/gemini-2.5-flash` | Google | multimodal chat | 120 s |
| screenshot-aware refinement | `openai/gpt-4o` | OpenAI | multimodal chat | 240 s |
| narrow technical repair | `deepseek/deepseek-v4-pro` | DeepSeek | text chat | 150 s |

The critic and reviewer must resolve to different families. Unknown models,
unknown providers, a missing multimodal capability, or a family mismatch fail
before invocation. The registered economy vision model is never selected
silently; `V2_VISUAL_ECONOMY_FALLBACK_ENABLED` defaults to false and the
initial implementation performs no automatic fallback.

Every call record includes the resolved provider, model, family, capability,
message format through the routing artifact, prompt revision, temperature,
token limit, token usage, synthetic/local fixture cost, latency, and transport
retry count.

## Provider-aware evidence bundles

Screenshots stay in canonical page order and the Phase 4 viewport order.
Grouping takes the stricter critic/reviewer values for:

- maximum images;
- maximum bytes per image; and
- maximum aggregate image bytes.

The service prefers one coherent call. When it cannot fit, it groups complete
routes deterministically; it never makes one call per screenshot or splits a
route's viewport evidence. Every group has a content hash and appears in the
persisted grouping manifest. The service computes required critic + reviewer
calls before invoking and fails when the approved six-call ceiling cannot
hold the current path.

Screenshots are not silently resized or recompressed. The current image policy
therefore preserves the Phase 4 pixels, aspect ratio, dimensions, and hashes.

## Deterministic hard gates

The pre-critic report covers:

- Phase 4 terminal, candidate, build, contract, and evidence integrity;
- the exact route/viewport and journey matrices;
- PNG decoding, dimensions, byte hashes, and screenshot-set hash;
- blank, transparent, and materially uniform images;
- Phase 4 action/evidence reachability, clipping, and overflow;
- visible deterministic placeholder text;
- known prohibited scaffold/catalogue component markers; and
- duplicate route shells.

Perceptual consistency is advisory. Shared navigation, typography, or product
chrome does not block a candidate. Duplicate-shell rejection requires both an
identical canonical content-region rendering and distinct page-purpose
signatures.

A blocking hard-gate result produces `candidate_visual_rejected` with zero AI
calls. It is conservatively `rejected_not_repairable`; Phase 5 never asks a
model to work around corrupt evidence or canonical/runtime failures.

## Typed critic and reviewer

Both actors score exactly these 14 dimensions in policy order:

1. business specificity;
2. product-story clarity;
3. hierarchy and composition;
4. visual coherence;
5. DesignDNA adherence;
6. content credibility;
7. interaction clarity;
8. conversion strength;
9. mobile quality;
10. responsive consistency;
11. density and readability;
12. evidence visibility;
13. novelty; and
14. trust and professionalism.

Every dimension requires an integer 0–100 score, confidence, evidence IDs,
routes, viewports, an evidence-linked rationale, severity, and a deterministic
support flag. Missing/duplicate dimensions, invalid evidence, unsupported
deterministic claims, or generic rationales fail closed without a schema retry.

The persisted score-band revision anchors:

- 90–100: exceptional, client-ready, strongly differentiated;
- 80–89: strong and professional, only minor weaknesses;
- 70–79: usable but visibly ordinary or inconsistent;
- 50–69: weak, generic, or materially unclear; and
- below 50: broken or commercially unconvincing.

The reviewer receives screenshots, typed contracts, the hard-gate report, and
the critic's typed scorecard. It never receives critic hidden reasoning,
critic provider/model metadata, an implementation preference, or an
instruction to agree. Reviewer disagreements are evidence-linked and can
deterministically reject a critic-accepted candidate.

Grouped partial scorecards and decisions are persisted. Aggregation is
deterministic and weighted by the number of verified images in each whole-route
group.

## Deterministic acceptance

Models cannot write terminal status. The service applies the persisted default
policy:

- weighted overall ≥ 80;
- business specificity ≥ 80;
- DesignDNA adherence ≥ 80;
- conversion strength ≥ 75;
- mobile quality ≥ 75;
- trust/professionalism ≥ 80;
- zero blockers;
- reviewer recommendation `accept`; and
- critic/reviewer agreement.

The score is a fixed weighted projection of the two typed assessments.
Threshold booleans, actor totals, combined dimension values, blocker count,
agreement, and the derived accepted boolean are stored with the terminal
summary.

## Baseline policy

An arbitrary legacy preview directory is not assumed to be an accepted
baseline. A paired comparison is eligible only with a persisted accepted
candidate identity, the same Phase 4 capture policy, and exact or uniquely
matched semantic routes. Phase 5 currently has no promotion-owned accepted
candidate pointer, so original candidates persist `absolute_only` with the
exact reason and make no improvement claim.

Original/refined comparison is available because both candidates are
same-policy runtime-validated. A deterministic attempt hash assigns blind A/B
labels. Candidate age, accepted status, and which identity is new are withheld.
The reviewer compares clarity, business specificity, visual quality, trust,
conversion strength, and mobile quality in the existing refined-review call.

## Repairability and one bounded refinement

Rejected candidates are classified as:

- `rejected_not_repairable`; or
- `rejected_repairable`.

Repairability requires evidence-linked major/blocking visual findings whose
issue types are source-local, canonical ownership resolves to existing page or
business-component TSX files, no more than eight files and four Tier 1 pages
are affected, and no route, dependency, contract, generated-data, foundation,
infrastructure, or full-product change is needed.

The deterministic `RefinementPlan` stores finding/page/component references,
allowed files and original hashes, issue/objective, evidence, immutable
constraints, validations, priority, and expected dimension impact. It contains
no embedded AppSpec or generated page content.

One screenshot-aware call must return every and only allowlisted existing TSX
file with the expected original hash. Phase 5 then:

1. copies the original candidate to a new isolated staging workspace;
2. verifies output paths and hashes;
3. verifies every unaffected file is byte-identical;
4. reruns the full Phase 3B deterministic TypeScript/import/dependency/route/
   contract gate;
5. persists a new immutable candidate revision;
6. runs complete Phase 4 validation and capture;
7. runs complete Phase 5 critic/reviewer evaluation; and
8. performs the blind original/refined comparison.

One DeepSeek source-only technical repair is available only after compiler or
deterministic static-gate diagnostics. It receives only allowlisted files,
concrete diagnostics, and immutable contracts. It cannot address visual
findings or redesign the candidate.

The refined candidate must pass every absolute threshold, introduce no
blocker, not regress overall or any blocking dimension, and be preferred by
the blind reviewer. Failure is terminal; there is no second refinement loop.
The original candidate and evidence always remain preserved.

## Calls and budgets

For a one-group bundle:

- accepted original: 2 calls;
- successful refinement: 5 calls; and
- refinement with one technical repair: 6 calls.

Configured ceilings are:

- 6 provider calls;
- 42,000 aggregate output tokens;
- $1.50 aggregate provider cost;
- 1,200 seconds wall time;
- one refinement batch; and
- one technical repair.

Request and daily administrative budgets remain authoritative through the
existing provider layer. Invalid structured output receives no schema retry.
Visually conservative but valid output never causes a retry.

## Append-only persistence

Phase 5 adds exactly ten tables:

1. `candidate_visual_evaluation_attempts`
2. `candidate_visual_evidence_bundles`
3. `candidate_visual_hard_gate_results`
4. `candidate_visual_scorecards`
5. `candidate_visual_findings`
6. `candidate_visual_reviewer_decisions`
7. `candidate_baseline_comparisons`
8. `candidate_refinement_plans`
9. `candidate_refinement_generations`
10. `candidate_visual_summaries`

Records are additive and reference request, candidate, Phase 4 summary, build,
contract hashes, screenshot set, grouping, browser/capture policy, routing and
capability resolution, prompt/policy revisions, budgets, and lineage. A
terminal attempt is flushed in one transaction only after all required typed
artifacts and hash links validate. A synthetic failure after staging proves a
rollback leaves none of the terminal rows.

Derived candidates continue using append-only `candidate_revisions`; the
original revision status and workspace never change.

## Cache and invalidation

Evidence, hard gate, critic partial/aggregate, reviewer partial/aggregate,
baseline, plan, generation, and terminal summary are stored separately with
stage keys. A full terminal hit still:

- reloads the Phase 3B/4 chain;
- recomputes source, build, screenshot, and screenshot-set hashes;
- decodes and reanalyzes PNG evidence;
- reparses strict artifacts;
- rehashes every artifact;
- checks model/prompt/policy/grouping provenance; and
- reruns deterministic hard gates.

Keys consume ordered screenshot hashes, grouping manifest, browser/capture and
image policy, capability resolution, model/family, prompt parameters, score
bands, acceptance policy, limits, baseline identity, and allowlisted source
hashes where applicable. Screenshot, model, prompt, score, acceptance, image
limit, grouping, baseline, or source-hash changes cannot silently reuse the
older terminal.

After a completed refinement, a repeated original input resolves and
revalidates the derived lineage and returns the refined terminal with zero
provider calls. It never starts a second refinement loop.

## Local verification

Fixture providers implement the injected `AIProvider` protocol. They never
construct OpenRouter/Ollama clients and never make a live call.

```powershell
cd backend
python -m pytest -q -p no:cacheprovider tests/visual_evaluation
python -m pytest -q -p no:cacheprovider tests/runtime_validation/test_phase4_runtime_validation.py
python -m compileall -q app
git diff --check
```

The Phase 5 suite covers the three-flag boundary, model capabilities and family
independence, input/hash/PNG gates, placeholder/scaffold and duplicate-shell
policy, all 14 score dimensions and calibration, reviewer disagreement,
deterministic scoring, provider-aware grouping, blind/absolute comparison,
repairability/allowlists, five- and six-call derived lifecycles, Phase 3B/4
reruns, byte-identical unaffected files, no second loop, invalid-refinement
terminal behavior, cache invalidation, budgets, transaction rollback, and the
absence of promotion/serving/Tier 2/3/Phase 6 paths.

The known Windows `.pytest_cache`/`tmp_path` ACL warning remains environmental.
Phase 5 image tests use repository-local isolated fixture paths.

No paid provider call, live canary, commit, push, promotion, serving action,
Tier 2/3 generation, or Phase 6 work is part of Phase 5.
