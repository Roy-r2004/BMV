#!/usr/bin/env python3
"""Phase 1 DoD evidence for the three concurrent runs (74, 75, 76).

Two questions this has to answer that a wall-clock number cannot:

* Was a degradation CORRECT (the run genuinely had no time left) or an
  ARTIFACT (the run spent its budget blocked on a lock another run held)?
  `blocked_seconds` / `contention` come from the instrumentation added this
  session; without them the two are the same list.
* Is any *logical ask* over 120 s inclusive of failovers? One row of
  `ai_usage_events` is one attempt against one model. A logical ask is the
  group of rows a single `ai_call` scope produced — same (request_id, stage,
  writer), contiguous in time, with `attempt` not resetting to 1.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Runs inside the api container (`/app/backend`) or from a repo checkout.
# Whichever actually holds the `app` package wins.
for _candidate in ("/app/backend", str(Path(__file__).resolve().parents[2])):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover - misplaced checkout
    raise SystemExit("cannot locate the `app` package from either /app/backend or the repo")

from sqlalchemy import text  # noqa: E402

from app.infrastructure.db.session import engine  # noqa: E402

_TRIOS = {
    "1": ([74, 75, 76], {74: 1785651700, 75: 1785651761, 76: 1785651821}),
    "2": ([77, 78, 79], {77: 1785653172, 78: 1785653233, 79: 1785653293}),
    "3": ([80, 81, 82], {80: 1785690348, 81: 1785690409, 82: 1785690469}),
    # Trio 4 is the proof run for the elective guards (visual_critic,
    # quality_repair). Compare against trio 3 on two axes and no others:
    # wall clock, and how many pages actually got a visual verdict. Trio 3
    # reviewed 0 of 18 *with the critic running*, because every vision call
    # was refused — so "the critic no longer runs" is only a regression if
    # the reviewed count drops below that.
    "4": ([83, 84, 85], {83: 1785693563, 84: 1785693624, 85: 1785693684}),
    # Trio 5 is the proof run for the deterministic dead-link guard.
    "5": ([86, 87, 88], {86: 1785697222, 87: 1785697283, 88: 1785697343}),
    # Trio 6 (89-91) is deliberately absent. The OpenRouter account ran out of
    # credits mid-run, so `codegen` degraded for a reason that has nothing to do
    # with the pipeline. It is void; giving it a key here would invite a citation.
    #
    # Trio 7 is the first funded trio, same three briefs as 5 and 6 so questions 8
    # and 11 stay controlled comparisons. Credits confirmed before launch with a
    # 28,000-max_tokens probe against both production models, and the api log has
    # zero credit refusals across the window — this one is valid.
    "7": ([92, 93, 94], {92: 1785778218, 93: 1785778280, 94: 1785778340}),
    # Duo 1 is the 1.13 proof run: TWO runs, and the briefs are requests 92 and
    # 94 verbatim so the bound is the only variable. Two because the questions
    # are binary — did the reservation fire, did appspec cap per request, did
    # the duplicate authoring pass go away — not distributional. It is not a
    # wall-clock comparison against the trios: two concurrent runs put less
    # pressure on `_SESSION_LOCK` than three.
    "duo1": ([95, 96], {95: 1785863897, 96: 1785863958}),
}
#: Void on credits, and present rather than absent on purpose — see `tail.py`.
_TRIOS["6"] = None


def select_trio(argv: list[str]) -> tuple[list[int], dict[int, int]]:
    """Resolve the trio key. Called from `main`, never at import time.

    Parsing `sys.argv` at module scope made this file unimportable — under
    pytest `sys.argv[1]` is a test path, so the module raised `KeyError` before
    a single function could be reached, and that is why the arithmetic in here
    went four trios without a test while reporting a key nothing wrote.
    """

    key = argv[0] if argv else "1"
    if key not in _TRIOS:
        raise SystemExit(f"unknown trio {key!r}; known: {', '.join(sorted(_TRIOS))}")
    selected = _TRIOS[key]
    if selected is None:
        raise SystemExit(
            f"trio {key} is void — its numbers must not be cited. "
            "Pass the run ids to a tool that takes them if you really mean those requests."
        )
    return selected


def appspec_health(rows) -> dict:
    """Summarize one request's AppSpec revisions.

    Pure on purpose — `main` does the SQL, this does the arithmetic, and the
    tests drive this. Both measurement tools in this directory have shipped a
    defect that only a test would have caught: `analyse.py` read a
    `gate_issues` key nothing ever wrote, and `tail.py` hardcodes a run list and
    silently reports nothing for any other trio.

    `rows` are `app_spec_revisions` for one request, oldest first, each with
    `status`, `app_spec_sha256`, `parent_revision_id`, the deterministic
    validation payload and the generation metadata.

    Three of these numbers exist because reading the raw table by hand misled
    me first:

    * `revisions` **overcounts attempts.** A candidate is persisted before and
      after the graph-repair pass, so a repair that changed nothing stores the
      same `app_spec_sha256` twice — requests 92 and 94 show 8 and 4 revisions
      for 6 and 3 distinct candidates. Compare `distinct_candidates`.
    * `fresh_authoring_chains` is the defect 1.13 fixed, made visible. A null
      `parent_revision_id` is an authoring call that started over rather than
      repairing what came before. Request 92 did it **three** times. On a run
      after `27b12bf` this should be 1, and 2 only if the stage was re-entered
      with nothing accepted to reuse.
    * `final_blocking` is the run's actual verdict. Counting issue codes across
      *all* revisions says `state_ids` dominates; per final revision, requests
      92, 93 and 94 failed on three different things. Superseded revisions are
      history, not causes.
    """

    ordered = list(rows)
    if not ordered:
        return {"revisions": 0, "accepted": 0, "note": "no AppSpec revision stored"}

    def _meta(row) -> dict:
        try:
            return json.loads(row.get("generation_metadata_json") or "{}")
        except Exception:
            return {}

    final = ordered[-1]
    try:
        final_validation = json.loads(final.get("deterministic_validation_json") or "{}")
    except Exception:
        final_validation = {}

    codes: Counter = Counter()
    paths: Counter = Counter()
    for issue in final_validation.get("issues") or []:
        codes[str(issue.get("code") or "")] += 1
        detail = issue.get("detail")
        if isinstance(detail, list):
            for entry in detail:
                if isinstance(entry, dict) and entry.get("loc"):
                    paths[".".join(str(part) for part in entry["loc"])] += 1

    return {
        "revisions": len(ordered),
        "distinct_candidates": len({r.get("app_spec_sha256") for r in ordered}),
        "accepted": sum(1 for r in ordered if r.get("status") == "accepted"),
        "fresh_authoring_chains": sum(
            1 for r in ordered if r.get("parent_revision_id") is None
        ),
        "terminal_reasons": sorted(
            Counter(str(_meta(r).get("terminal_reason") or "-") for r in ordered).items()
        ),
        "final_revision_id": final.get("id"),
        "final_is_valid": bool(final_validation.get("is_valid")),
        "final_blocking": sorted(codes.items()),
        "final_blocking_paths": sorted(paths.items(), key=lambda kv: (-kv[1], kv[0]))[:8],
    }


def _p(values, q):
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def run_row(
    gp: dict,
    *,
    request_status: str | None = None,
    created: float | None = None,
    updated: float | None = None,
    launch_epoch: float | None = None,
) -> dict:
    """One run's row, from its stored `generated_pages` bundle.

    Extracted from `main` so it can be called without a database. Every defect
    this tool has shipped has been in exactly this dict — a key read that
    nothing writes — and none of them was reachable by a test while the
    arithmetic lived inside the query loop.
    """

    pa = gp.get("preview_app") or {}
    return {
        "request_status": request_status,
        "preview_status": pa.get("status"),
        # `viewable` was read here for every trio and **never written**:
        # it is a local in `finalize`, and duo 1 reported `viewable:
        # None` on two runs that both shipped `ready`. It is exactly
        # `status == "ready"`, so it is derived rather than stored — a
        # second key free to disagree with the first is the defect this
        # is fixing, one layer down. `None` still means "no record".
        "viewable": None if not pa else pa.get("status") == "ready",
        # Written by `finalize` as of this session, always present and
        # `None` when the preview is served. A run before that stores
        # nothing, so `None` here is ambiguous for runs <= 96 only.
        "withheld_reason": pa.get("withheld_reason"),
        "degraded": pa.get("degraded"),
        "degradations": pa.get("degradations"),
        "deadline_seconds": pa.get("deadline_seconds"),
        "elapsed_seconds": pa.get("elapsed_seconds"),
        "deadline_exceeded": pa.get("deadline_exceeded"),
        "blocked_seconds": pa.get("blocked_seconds"),
        "contention": pa.get("contention"),
        # This key was read here for four trios and **never written** —
        # every table this tool produced said `gate_issues: 0`, including
        # the ones the roadmap quotes, and the real per-code counts came
        # from grepping container logs. Written by `finalize` as of session
        # 8, with the failing page's `skeleton_id` beside each code, which
        # is what pre-flight question 5 needs and could not get. A run
        # before that stores nothing, so `None` here means "not recorded",
        # never "no issues".
        "gate_issues": (
            None if pa.get("gate_issues") is None else len(pa["gate_issues"])
        ),
        "gate_codes": sorted(
            Counter(
                str(i.get("code") or "")
                for i in (pa.get("gate_issues") or [])
            ).items()
        ),
        "gate_codes_by_skeleton": sorted(
            Counter(
                f"{i.get('code')}@{i.get('skeleton_id') or '-'}"
                for i in (pa.get("gate_issues") or [])
            ).items()
        ),
        # `None` here means the run predates 2026-08-03 — trios 4 and 5
        # stored nothing when the critic was skipped. It does NOT mean
        # "reason unknown". Runs after that report one of
        # `visual_critic.VISUAL_NOT_RUN_REASONS` instead. Those rows are
        # left as they were stored; rewriting collected evidence to match
        # a later schema is how a corpus stops being evidence.
        "visual_review_status": pa.get("visual_review_status"),
        "visual_pages_reviewed": len(
            [
                p
                for p in (pa.get("visual_review") or {}).get("pages", [])
                if (p or {}).get("verdict")
            ]
        )
        if isinstance(pa.get("visual_review"), dict)
        else None,
        "pages": len(pa.get("pages") or gp.get("pages") or []),
        "db_created_epoch": created,
        "db_updated_epoch": updated,
        "launch_epoch": launch_epoch,
    }


def main() -> None:
    IDS, LAUNCH = select_trio(sys.argv[1:])
    out: dict = {"runs": {}, "asks": {}}
    with engine.connect() as conn:
        for rid in IDS:
            row = conn.execute(
                text(
                    "SELECT status, generated_pages, "
                    "extract(epoch from created_at) AS created, "
                    "extract(epoch from updated_at) AS updated "
                    "FROM requests WHERE id = :i"
                ),
                {"i": rid},
            ).mappings().first()
            if row is None:
                out["runs"][rid] = {"error": "no such request"}
                continue
            out["runs"][rid] = run_row(
                json.loads(row["generated_pages"] or "{}"),
                request_status=row["status"],
                created=row["created"],
                updated=row["updated"],
                launch_epoch=LAUNCH.get(rid),
            )

        # --- AppSpec acceptance --------------------------------------------
        # The stage's own record lives in `app_spec_revisions`, which nothing in
        # this tool ever read. Trio 7 was 0-accepted-of-18 and no report said so;
        # the finding came out of querying the table by hand. It is the durable
        # evidence for 1.13's second half, so it is read here rather than
        # denormalized into `preview_app` the way `gate_issues` had to be — that
        # key needed writing because gate issues were ephemeral. These are not.
        for rid in IDS:
            revisions = conn.execute(
                text(
                    "SELECT id, revision, status, app_spec_sha256, parent_revision_id, "
                    "deterministic_validation_json, generation_metadata_json "
                    "FROM app_spec_revisions WHERE request_id = :i ORDER BY id"
                ),
                {"i": rid},
            ).mappings().all()
            out.setdefault("appspec", {})[rid] = appspec_health(
                [dict(r) for r in revisions]
            )

        # --- logical asks -------------------------------------------------
        rows = conn.execute(
            text(
                "SELECT request_id, stage, writer, model, attempt, latency_ms, "
                "success, usable, extract(epoch from created_at) AS ts "
                "FROM ai_usage_events WHERE request_id = ANY(:ids) "
                "ORDER BY request_id, created_at, id"
            ),
            {"ids": IDS},
        ).mappings().all()

    per_run_rows: dict[int, list[dict]] = {r: [] for r in IDS}
    for r in rows:
        per_run_rows[r["request_id"]].append(dict(r))

    for rid, rs in per_run_rows.items():
        asks: list[dict] = []
        current: list[dict] = []

        def _flush() -> None:
            if not current:
                return
            total = sum((c["latency_ms"] or 0) for c in current) / 1000.0
            asks.append(
                {
                    "stage": current[0]["stage"],
                    "writer": current[0]["writer"],
                    "seconds": round(total, 1),
                    "rows": len(current),
                    "models": sorted({c["model"] for c in current}),
                    "start_ts": current[0]["ts"],
                }
            )
            current.clear()

        for r in rs:
            same_scope = bool(
                current
                and r["stage"] == current[-1]["stage"]
                and r["writer"] == current[-1]["writer"]
            )
            # attempt resetting to 1 starts a new logical ask; a rising attempt
            # (retry) or a different model at the same attempt (failover) does
            # not — that is exactly the "inclusive of failovers" the DoD means.
            continues = same_scope and int(r["attempt"] or 1) > 1
            if not continues:
                _flush()
            current.append(r)
        _flush()

        # Stage spans. The `WatchBmv` log lines ("build+fix-loop finished in
        # Ns") carry no request id, so with three runs interleaved they cannot
        # be attributed. `ai_usage_events` can: span = first call start to last
        # call end, per (request, stage).
        spans: dict[str, dict] = {}
        for r in rs:
            stage = r["stage"] or "(none)"
            start = float(r["ts"])
            end = start + (r["latency_ms"] or 0) / 1000.0
            s = spans.setdefault(
                stage, {"start": start, "end": end, "calls": 0, "ai_seconds": 0.0}
            )
            s["start"] = min(s["start"], start)
            s["end"] = max(s["end"], end)
            s["calls"] += 1
            s["ai_seconds"] += (r["latency_ms"] or 0) / 1000.0
        out.setdefault("stage_spans", {})[rid] = {
            stage: {
                "span_s": round(v["end"] - v["start"], 1),
                "ai_s": round(v["ai_seconds"], 1),
                "calls": v["calls"],
            }
            for stage, v in sorted(spans.items(), key=lambda kv: -kv[1]["ai_seconds"])
        }

        # Calls per writer, for `appspec` specifically. 1.13 made the ceiling
        # per request rather than per entry into the stage; the way to see
        # whether it binds is this row against `APPSPEC_MAX_CALLS`. Trio 7 read
        # 7, 6 and 10 against a configured 6.
        appspec_rows = [r for r in rs if (r["stage"] or "") == "appspec"]
        if appspec_rows:
            out.setdefault("appspec", {}).setdefault(rid, {})["calls_by_writer"] = sorted(
                Counter(str(r["writer"] or "(none)") for r in appspec_rows).items()
            )
            out["appspec"][rid]["calls_total"] = len(appspec_rows)

        durations = [a["seconds"] for a in asks]
        out["asks"][rid] = {
            "logical_asks": len(asks),
            "rows": len(rs),
            "p50_ask_s": round(_p(durations, 0.5), 1),
            "max_ask_s": round(max(durations) if durations else 0.0, 1),
            "over_120s": [a for a in asks if a["seconds"] > 120.0],
            "ai_seconds_total": round(sum(durations), 1),
        }

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
