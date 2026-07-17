# Canonical AppSpec pipeline

AppSpec is the product contract between customer intake and UI generation. It
owns product intent, requirements, roles, entities, capabilities, pages, states,
actions, transitions, evidence, journeys, acceptance tests, and traceability.
It deliberately does not own colors, motion, component libraries, skeletons,
section slots, file paths, or generated code.

The runtime order is:

1. Capture a PII-safe, stable snapshot of direct customer input and reference
   evidence. Keep blueprint/preview prose in separate non-authoritative context.
2. Ask the AppSpec author for one complete object against the live Pydantic JSON
   schema.
3. Run deterministic graph/reference/state/journey/traceability validation.
4. Ask an independent coverage reviewer to compare the candidate directly with
   customer input.
5. Repair the complete object within the AppSpec-only call budget. Never repair
   by truncating or dropping scope.
6. Persist the final attempt as an immutable accepted or rejected revision.
7. Select complete primary journeys within the 6–8 page preview limit.
8. Project canonical roles/pages/contracts into the experience planner,
   architect, React codegen, runtime data, and future browser checks.

An accepted revision requires both deterministic validation and semantic
coverage. When AppSpec is on, rejection, stale provenance, over-cap required
journeys, missing code hooks, fallback pages, or build failure stop the pipeline;
they cannot fall back to independent role-page generation or emit completion.

## Rollout

Set `APPSPEC_MODE` to one of:

- `off`: legacy behavior.
- `on`: author, review, persist, and enforce the AppSpec for every preview.

Legacy rollout values (`shadow`, `required_new`, `required`) are still accepted
and treated as `on` so existing configs keep working.

## Inspection

Public preview responses expose only a safe revision summary. Generated page
JSON stores only `app_spec_ref` provenance, never the full contract.

Admin endpoints:

- `POST /api/admin/requests/{id}/generate-app-spec`
- `GET /api/admin/requests/{id}/app-specs`
- `GET /api/admin/requests/{id}/app-specs/{revision}`

The complete valid developer fixture is
`tests/fixtures/app_spec/valid_booking.json`. Focused executable checks are
the five `tests/appspec/test_app_spec_*.py` files (`pytest` from `backend/`).
