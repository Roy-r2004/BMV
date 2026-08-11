# Foundry primitives are registered but unreachable by generated pages

Found 2026-08-10 while pricing what a funded run could actually confirm.
**No money was spent to find it** — the check is a catalogue read.

## The hole

All 18 mined primitives are registered in `registry.ts`, exported from
`src/ui/index.ts`, present in `catalogue.json`, manifested in
`PROVENANCE.json`, and attributed. The foundry tests pin every one of those
links. But codegen never sees them:

```python
# ui_catalogue.compact_skeleton_contract
allowed = set(skeleton.get("allowedComponents") or [])
...
for name in sorted(allowed):        # only skeleton-allowed names survive
```

The contract handed to the generator — and used by
`catalogue_contract.validate` to build `allowed_ui_names` — is scoped to the
**skeleton's** `allowedComponents`, not the catalogue. Measured across all
15 skeletons: **0 list any of the 18**. So a generated page cannot emit one,
and if the model somehow did, the validator would reject it as a
`forbidden @/ui component`.

## Why the existing pins did not catch it

`test_foundry_components.py` pins both directions of the registry↔barrel
relationship (registered-but-not-exported, manifested-but-not-registered).
Neither direction covers registered-but-not-**allowed**. The arsenal is
real, complete, and inert.

## What this means for validation cost

A funded run today confirms:

- **Stage A** — the plumbing refactor is a rendering no-op (already proven
  offline at 17/17 byte-identical); a run re-proves the pipeline generates.
- **3.10 motion wiring** — ships automatically: the identity travels in
  `site-design.ts`, which every workspace receives, and both engines read it.
- **NOT the 18 primitives** — zero can appear in output.

So no amount of run budget validates Stage B's mining until reachability is
wired. That wiring is a **composition decision, not a validation step**:
dropping 18 decorative primitives into every skeleton's allow-list without
per-recipe steering invites the model to sprinkle effects at random, which
is precisely the "sameness by another route" the foundry was built to avoid.
The personality tags that would steer it (`recipe_personalities` in
`PROVENANCE.json`) are **consumed by nothing** — grep finds them only in the
manifest and one test.

## Recommended shape (owner call, Stage C/D adjacent)

Per-skeleton, per-personality allow-lists rather than a blanket append:
each skeleton gains the handful of primitives its recipe personalities
already claim in the manifest, so `dense-ops` never gets `AuroraText` and
`nocturne` does. That turns `recipe_personalities` from metadata into the
routing key it was written to be, and it is the natural first half of
Stage D's composition work.
