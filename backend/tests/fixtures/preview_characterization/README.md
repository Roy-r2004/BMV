# Preview characterization fixtures

These five JSON files freeze Phase 0 observations for v1. Load them with
`app.application.preview_app.characterization.load_frozen_characterization`.
The loader is offline-only: it does not accept an AI provider, run a build, or
touch a preview workspace.

Canonical JSON hashes are asserted in
`tests/preview_app/test_phase0_characterization_fixtures.py`. Update a hash
only when intentionally thawing a baseline and document why in
`docs/architecture/PREVIEW_GENERATOR_V1_BASELINE.md`.

`data_heavy_trading_workflow.json` is intentionally marked
`deterministic_only` / `not_observed` for runtime fields because no matching
live artifact existed and Phase 0 did not authorize a paid canary.
