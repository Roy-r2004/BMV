# Stage A / A4 — license policy live: manifest, guards, attributions (session 30)

Branch `phase3-stage-a`, on top of A3 (`81b360d`). Stage B cannot start
unmanifested: the manifest exists (empty), every policy rule is enforced by a
pytest in the default suite, and each guard is proven able to fire.

## What landed

- **`backend/preview-template/PROVENANCE.json`** — the manifest, an empty
  array. Append-only from here; one row per borrowed file (policy schema),
  rows of kind `"dependency"` for Lenis/dotLottie when their stages land.
- **`app/application/preview_app/provenance.py`** — the policy's mechanical
  half, one implementation the tests call: allowlist (MIT/ISC/BSD-2/BSD-3/
  0BSD/Unlicense/CC0 + exactly one non-plain entry, `MIT+Commons-Clause`),
  `validate_manifest` (path under `src/ui/**` and exists; full-40-hex sha
  pin; non-empty license_url/retrieved/source_path; `rewritten` flag
  required), `dependency_delta_problems` against the FROZEN Stage-A
  dependency baseline (26 names, pinned literally in the tests so tampering
  with the constant — the easy way around the delta guard — fails loudly),
  and `generate_attributions`.
- **Two owner rulings mechanized, fail-closed:**
  - React Bits bright line: any row whose source matches `react-bits` must
    carry `MIT+Commons-Clause`, never plain `MIT`.
  - Aceternity GATED: any row citing it fails validation until a human check
    finds actual license text and consciously edits the gate.
- **`backend/preview-template/ATTRIBUTIONS.md`** — generator output for the
  empty manifest, committed; a pytest pins the file byte-for-byte to
  `generate_attributions(load_manifest())`, so regeneration is the only
  legal way to change it (MIT notice preservation once rows exist).
- A broken manifest (non-array / invalid JSON) RAISES — it can never read as
  an empty, passing one.

**No dependency changes** — `package.json`/lockfile untouched, so the shared
npm fingerprint (`npm_shared.py:29-44`) does not rotate and clock numbers
stay valid for the trio.

## Gates

| gate | result |
|---|---|
| Guard suite | 16 tests, each rule with a fires-on-violation case |
| Mutation sweep | **10 killed / 0 survived** (`mutate_session30_a4.py`) — allowlist creep, sha-pin relaxation, both ruling gates, baseline tampering, generator bypass, empty-state drift, broken-manifest-as-empty, path containment, existence check |
| Full suite | green after A4 (number in HANDOFF row) |
| Silhouette | 17/17 (A4 writes no CSS; run for the record) |
| Workspace pruning | `test_scaffold_pruned` still green — the two new template files are text, small, and unpruned |
