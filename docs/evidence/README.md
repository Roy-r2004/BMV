# Evidence archives

The raw material behind the Phase 1 numbers in [`PREVIEW_ROADMAP.md`](../PREVIEW_ROADMAP.md).
Committed because both sources are **ephemeral infrastructure, not repository state**: the logs came
from a session scratchpad that was about to be cleaned up, and the workspaces live in a docker
volume that a `docker volume prune` removes without warning. Every offline analysis in
[`backend/scripts/measure/`](../../backend/scripts/measure/) reads one or the other.

| archive | what |
|---|---|
| `preview-trio-logs.tar.gz` (123 KB) | `api.log` … `api7.log` — container logs for trios 1-7. `api6.log` is the **void** trio: the OpenRouter account ran out of credits mid-run. Kept only so nobody re-derives numbers from it by accident. `api7.log` is the **first funded** trio (92-94), and is the record behind two claims that exist nowhere else: that no call in the window was refused for credit, and that request 93's `listing_not_schedule_rail` fire names `[public-service]` — the gate instrument's first live output. It is the container's own log from its 17:29:54 restart to the end of run 3, 914 lines |
| `api_duo1.log` (inside the archive above) | **Duo 1 (95-96), 2026-08-04** — the 1.13 proof run, and the record behind the finding that **neither of 1.13's bounds fired**. Two runs, not three, on the briefs of requests 92 and 94 verbatim. Grep it for `stopped_low_downstream_runway` and `call_budget_exhausted` and you get nothing, which is the point: both runs shipped `ready` and the new code never executed its new paths |
| `preview-workspaces.tar.gz` (4.0 MB) | **67** generated preview workspaces, requests 1-102 — the shipped `src/` of each, plus its `.bmv-debug/` (raw model responses, pipeline traces). Refreshed 2026-08-05 from 58; requests 1, 93-98 and 101-102 were added, which is what makes the palette and menu censuses re-derivable. **62 of them shipped a `mock.ts` at the time of the census, and those 62 hold only 18 distinct briefs and 12 distinct business names** — 25 are one art gallery. Any "N of 62" claim is closer to "N of 18" than it reads. **101 and 102 are the odd ones: both stored no `preview_app` (a provider outage killed codegen) but both built a workspace**, which is how the derived palette is production-proven — `101/src/data/mock.ts` carries `#1d7b4c` and `102/src/data/mock.ts` carries `#b62bb6` where every earlier run of those two briefs carried `#0f766e` |
| `request-briefs.json` (new, 2026-08-05) | `id`, `business_name`, `industry`, `business_description` for all **84** stored requests (1-98). The workspace archive holds what each run *produced*; this holds what each run was *asked for*, which is what the palette and product-kind censuses key on. Without it, "candidate (a) gives 3 distinct colours" cannot be re-derived from the repo at all |
| `session11-run-logs.tar.gz` (new, 2026-08-05) | The launch logs for duo 2 (97-98), the enforcement spike (99, 100) and the proof runs (101, 102), plus the container logs covering runs 99-102. **Duo 2's own container log does not exist** — it was destroyed by a `docker compose up --force-recreate` run one command before it was dumped, which is why `slot_fill`'s contract-rejection *distribution* is still unmeasured. What did survive is in `api_run102.log`: **four rejections with their exact validator errors**, two of them the same `public-detail` painting-first contract failing on an About page, in two unrelated industries |
| `preview-routes.json` (new, 2026-08-05 session 12) | The **full** route dicts of all **47** stored runs — 637 routes — plus each run's exact `kind_context`, the blob `classify_product_kind` was given. It supersedes `architect-routes.json` for anything about page identity: that file holds 42 runs and drops `purpose`, which is the one field that identifies a *gap-filled* route (`_inject_blueprint_routes` copies `bp.purpose` verbatim, and "Catalogue grid of products or artworks." is a repository literal no model wrote). Storing `kind_context` is deliberate: `context_from_request` reads seven request fields, so a census that rebuilds the blob from `request-briefs.json` alone would classify differently from the live pipeline. `gallery_gapfill_census.py --routes` reads it and needs no database |
| `architect-routes.json` (160 KB) | The architect route list of all **42** stored runs — 553 routes — lifted out of `requests.generated_pages -> preview_app -> routes`, which `finalize` persists verbatim from `architect["routes"]`. Every DoD 7 number comes from it (`backend/scripts/measure/route_bijection.py`). Committed because the postgres volume is as removable as the workspace one, and the workspace archive alone cannot answer a route question: it holds `src/App.tsx`, which is the *shipped* router, and that diverges from the declared table — request 85's architect declared 18 routes and its `App.tsx` serves 24, the extra six being synthesised `:id`/`:slug` aliases |

## What the workspace archive contains, and what it deliberately does not

Each entry is `<request_id>/src/…` and `<request_id>/.bmv-debug/…`.

**`src/ui/` is excluded.** It is the template's component kit, copied byte-for-byte into every
workspace — 58 identical duplicates of a tree that is already in the repo at
`backend/preview-template/src/ui/`. Including it took the archive from 2.4 MB to 10.8 MB and added
nothing recoverable. If an analysis needs the kit, read it from the template; the pipeline restores
template-owned files before shipping (`restore_template_owned_files`), so a workspace's copy is the
template's copy.

`node_modules/` and `dist/` are excluded for the same reason with less nuance.

## Restoring

```bash
mkdir -p /tmp/workspaces && tar -xzf docs/evidence/preview-workspaces.tar.gz -C /tmp/workspaces
```

Tools that expect a live `PREVIEW_APPS_DIR` layout — `replay.py`, `resolve_probe.py` — read the
container's volume by default. Point them at an extracted copy only if the volume is gone; the
extracted tree has no `src/ui`, so anything that resolves a template import will need the template
alongside it.

## The rule these archives exist to enforce

A number in the roadmap that cannot be re-derived is a claim, not a measurement. Both trios and
workspaces have already been one cleanup away from making several published figures unverifiable.
If you produce a number from something outside the repo, archive the something.
