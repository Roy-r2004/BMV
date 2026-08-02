# Preview measurement tools

The evidence behind the Phase 1 numbers in [`docs/PREVIEW_ROADMAP.md`](../../../docs/PREVIEW_ROADMAP.md).
Rescued from a session scratchpad, which is why the trio ids are baked in: they
are the runs the roadmap actually cites, not examples.

Everything here is **read-only** with the exception of `launch_trio*.sh`, which
creates real generation requests. Nothing writes to a preview workspace — the
standing rule is that a generated preview is never edited to make a defect go
away, and these workspaces are the audit trail.

Run the Python tools inside the api container:

```bash
docker compose exec api python /app/backend/scripts/measure/analyse.py 5
```

They also run from a repo checkout with the backend deps installed; each one
resolves `/app/backend` or the checkout, whichever holds the `app` package.

| tool | the question it answers |
|---|---|
| `analyse.py <trio>` | Per-trio DoD evidence: wall clock, degradations, contention, and logical asks *inclusive of failovers*. Distinguishes a **correct** degradation (no time left) from an **artifact** one (the run sat blocked on a lock another run held) — without `blocked_seconds` those are the same list. Knows trios 1-5 by launch epoch; add yours the same way. |
| `tail.py` | Decomposes post-deadline time into AI vs non-AI. This is what found the elective-stage defect, and what showed the tail is **127 s AI / 255 s non-AI** over nine runs — so `RESERVE_SECONDS = 60`, fitted to the render-smoke and capture pass, was fitted to the smaller third. |
| `replay.py` | Replays the dead-link guard over the stored workspaces in memory. How "31 dead hrefs → 0" was measured. Reports the repair *kind* per run — `retargeted` / `unlinked` / `homed` — because a link homed to `/` improves the gate metric while making the artifact worse. |
| `resolve_probe.py` | How much of the real dead-link population each resolver rule can retarget. Written *before* the resolver, so the rules were fitted to hrefs the pipeline actually produced rather than ones that were easy to imagine. |
| `appspec_cost.py [runs…]` | Splits the AppSpec stage — the pending p50 decision turns on it. Separates authoring from review from repair, first attempts from re-asks, and successful spend from `usable=false` spend. Also prints per-run AI seconds against wall span, so orchestration overhead is visible separately from model time. **Its per-writer breakdown is empty for trios 2-5**: appspec had no `ai_call` scope until session 6, so every historical row is `writer = NULL, attempt = 1`. It fills in on the next funded trio. |

## `launch_trio*.sh` — the trio launchers

Three generations, 60 s apart, one with a `reference_url`, one with a
`reference_file`, one plain, **a different industry each**. Trio N's script is
the provenance of trio N: `launch_trio.sh` is trio 1, `launch_trio5.sh` is trio
5, and so on.

They exist mostly because they encode the operating traps, every one of which
has cost real time:

- **`industry` is `Form(None)`.** Omit it and it silently resolves to `generic`
  and produces convincing garbage. Always set it.
- Port **8001**, **multipart** not JSON.
- **No trailing slash**: `POST /api/requests/` 307-redirects and drops the body.
- **60 s spacing**, and three *different* industries — three art galleries only
  prove the art-gallery path.
- Run 3 is the plain one on purpose: it is the run most likely to sit behind
  both locks, and a reference on it would confound the cause of any degradation.

```bash
OUT=/tmp/trio7 sh backend/scripts/measure/launch_trio5.sh
```

`OUT` is where the launch log lands (default `$PWD`). Record the launch epochs
it prints — `analyse.py` needs them.

**Do not run a pytest container while a timed trio is in flight.** It
contaminates the measurement.

## The raw logs

[`docs/evidence/preview-trio-logs.tar.gz`](../../../docs/evidence/preview-trio-logs.tar.gz)
holds `api.log` … `api6.log`, the container logs behind every number in the
roadmap's Phase 1 section. Trio 6 (`api6.log`) is **void** — the OpenRouter
account ran out of credits mid-run — and is kept only so nobody re-derives
numbers from it by accident.
