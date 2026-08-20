# ADR-001 — Deferred: canonical typed engagement model & claim ledger

**Status:** accepted debt (2026-08-21). The JSON-layered architecture stays; this
records why, what risk that carries, and what would trigger the migration.

## Context

External review proposed a single typed engagement model (facts with provenance,
units, frequency, confidence) plus a claim ledger (formula, substitution, result
per numerical claim) consumed by every volume. The current system instead stores
per-stage JSON columns on the `Request` row (`modules_json`, `business_case_json`,
`procedures_json`, …), written fail-open by independent pipeline stages.

## Decision

Keep the JSON layers. Enforcement lives in four places instead of a schema:

1. **The decomposition is the registry** — modules flow by id/name into every
   downstream prompt; "one capability, one name" is prompt law audited by the
   completeness bench (high finding on drift).
2. **Deterministic sanitizers** — `_sanitize_financial_model` recomputes every
   plain-product claim (±2%, period steps ×1/12/26/52/365) and deletes figures
   whose arithmetic doesn't produce them; `_strip_artifacts` removes notation
   residue at render.
3. **The quality bench** — numbers auditor (trace, attribution, recompute,
   units/frequency drift, contradictions, BMV pricing) + structure auditor
   (canonical sections, phases, naming, scope) persist findings per run.
4. **The release gate** — `release_status(req)` = persisted high findings +
   artifact scan of every client-facing string; any open reason stamps every
   page `DRAFT — REQUIRES VALIDATION`.

## Current risk

- Provenance is positional (evidence page composes from discovery records),
  not attached per-fact; a stage could still restate a figure without its unit
  and only the LLM bench would notice.
- Cross-volume consistency is audited, not guaranteed by construction.
- Frequency ambiguity is prompt law ("ambiguous → missing_inputs"), not a type.

## Existing mitigations

Items 1–4 above, plus the pinned regression suite (530 tests) including the
iCARRY arithmetic fixtures and the frequency/FTE discipline pins.

## Migration triggers (any one)

- A client-visible incident traced to a figure the sanitizer/bench class cannot
  catch (e.g. a unit error inside prose the recompute parser skips).
- A second document family (proposals, audits) needing the same facts —
  duplication of the JSON conventions would then cost more than typing them.
- Multi-consultant editing, where two writers must merge facts safely.

## Proposed migration boundary

Type ONLY the quantitative layer first: a `Fact` table (value, unit, period,
currency, provenance ∈ {client_supplied, external_source, consultant_assumption,
calculated, unconfirmed}, confidence, source ref) + a `Claim` table (inputs → 
formula → substitution → result → rounding). `decompose` writes it; renderers
and QA read it. Prose layers stay JSON. Compatibility: keep writing
`business_case_json` in parallel until two release cycles pass with zero gate
regressions, then cut over readers one at a time.

## Estimated scope

Roughly: 2 tables + ORM, decompose writer, financial renderer reader, bench
context switch, ~40 tests touched. A focused multi-session effort; not a rider
on a feature pass.
