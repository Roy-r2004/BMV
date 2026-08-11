#!/usr/bin/env python3
"""Phase 0's 0.2, measured: P(refine fires) per run, and does a slot-filled
page keep the scaffold marker?

The row exists because it sets two ledger entries: how often the refine pass
actually spends money, and whether the `fallback_pages` signal — which reads
scaffold bookkeeping — tells the truth about what shipped. 0.8's warning is
the second half of that: after the Phase 2 flip the literal-marker signal
reads 0 forever or 12 forever, both silently. Before trusting it as a
baseline, this census checks whether it is even honest today.

    python3 backend/scripts/measure/refine_scaffold_census.py \
        --workspaces DIR [--workspaces DIR2] --critiques DIR \
        --fallback FILE --db-json FILE [--json OUT] [--check ARCHIVED.json]

**Inputs, and where they come from (all offline artifacts):**

- `--workspaces`: one or more roots of `<request_id>/src/pages/**/*.tsx` — the
  58-workspace archive (`docs/evidence/preview-workspaces.tar.gz`) and/or an
  extraction of the api volume (`/app/data/preview-apps`). When a request is in
  both, the LAST given root wins — the volume is the current state; the archive
  is a session-13 snapshot.
- `--critiques`: extracted `docs/evidence/visual-critique-reports.tar.gz`
  (the 41 stored `_bmv_visual_critique.json` reports, requests 37-122).
- `--fallback`: `id|json-list` lines of the stored per-request
  `preview_app.fallback_pages` (psql -Atc over `requests.generated_pages`;
  archived at `docs/evidence/session24-parallel/stored-fallback-pages.txt`).
- `--routes`: same shape, the stored `preview_app.routes[].component_file`
  lists (archived at `docs/evidence/session24-parallel/stored-route-files.txt`)
  — finalize only inspects ROUTED files with a skeleton, so an unrouted marker
  page was never examined at all.
- `--db-json`: refine telemetry extract (archived at
  `docs/evidence/session24-parallel/refine-telemetry.json`). The `refine`
  stage scope exists only from request 72 — before that, critic/refine rows
  are indistinguishable inside the unscoped `stage=''` bucket, so the
  telemetry denominator is the scoped era only, stated as such.

**The marker judgment call.** A page counts as scaffold-marked when its source
contains the literal `deterministic catalogue contract scaffold` — the same
predicate `generate.py` uses for its own bookkeeping. Two discrepancy classes,
counted per run against the stored `fallback_pages`:

- `marker_not_reported` — the file ships scaffold content but telemetry called
  the page AI-authored. This is 0.2's exact question: a slot-filled page that
  kept the marker.
- `reported_no_marker` — telemetry called it a fallback but the file carries
  no marker (a later pass — refine, fix agent, quality repair — rewrote it, or
  the record predates the current marker).

**What the marker is NOT.** `fallback_pages` is not "marker present": finalize
clears any routed marker page that passes `_scaffold_page_is_acceptable`
(AppSpec action/evidence coverage), so a filled page that merely kept the
scaffold's comment line is deliberately not reported. The census therefore
splits kept-marker pages into routed (the pipeline looked and accepted) and
unrouted (the pipeline never looked). The consequence for 0.8 stands either
way: the LITERAL marker survives fill and refine wholesale, so any signal that
reads the literal — `files_with_scaffold_marker`, or a naive content-density
proxy — is already dead today, not merely after the Phase 2 flip.

Read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MARKER = "deterministic catalogue contract scaffold"


def load_pages(roots: list[Path]) -> dict[int, dict[str, bool]]:
    """request_id -> {page relpath: has_marker}; later roots win."""
    out: dict[int, dict[str, bool]] = {}
    for root in roots:
        for req_dir in sorted(root.iterdir()):
            if not req_dir.is_dir() or not req_dir.name.isdigit():
                continue
            pages_root = req_dir / "src" / "pages"
            if not pages_root.is_dir():
                continue
            pages = {}
            for tsx in pages_root.rglob("*.tsx"):
                rel = "src/pages/" + tsx.relative_to(pages_root).as_posix()
                try:
                    pages[rel] = MARKER in tsx.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
            if pages:
                out[int(req_dir.name)] = pages
    return out


def load_fallback(path: Path) -> dict[int, list[str] | None]:
    out: dict[int, list[str] | None] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        rid, _, body = line.partition("|")
        body = body.strip()
        out[int(rid)] = None if body == "ABSENT" else [
            p.replace("\\", "/") for p in json.loads(body)]
    return out


def run_census(roots, critiques_dir, fallback_path, routes_path, db_json_path) -> dict:
    pages_by_run = load_pages(roots)
    fallback = load_fallback(fallback_path)
    routed = load_fallback(routes_path)
    db = json.loads(db_json_path.read_text(encoding="utf-8"))

    per_run = []
    for rid in sorted(pages_by_run):
        pages = pages_by_run[rid]
        marked = sorted(p for p, m in pages.items() if m)
        reported = fallback.get(rid)
        row = {"request": rid, "pages": len(pages), "marker_pages": marked,
               "stored_fallback_pages": reported}
        if reported is not None:
            row["marker_not_reported"] = sorted(set(marked) - set(reported))
            row["reported_no_marker"] = sorted(
                p for p in reported if pages.get(p) is False)
            route_files = routed.get(rid)
            if route_files is not None:
                row["kept_marker_routed"] = sorted(
                    set(row["marker_not_reported"]) & set(route_files))
                row["kept_marker_unrouted"] = sorted(
                    set(row["marker_not_reported"]) - set(route_files))
        per_run.append(row)

    runs_with_record = [r for r in per_run if r["stored_fallback_pages"] is not None]
    total_pages = sum(r["pages"] for r in per_run)
    total_marked = sum(len(r["marker_pages"]) for r in per_run)
    kept = [(r["request"], p) for r in runs_with_record
            for p in r.get("marker_not_reported", ())]
    ghost = [(r["request"], p) for r in runs_with_record
             for p in r.get("reported_no_marker", ())]
    kept_routed = sum(len(r.get("kept_marker_routed", ())) for r in runs_with_record)
    kept_unrouted = sum(len(r.get("kept_marker_unrouted", ())) for r in runs_with_record)

    # P(refine fires): the stored reports are ground truth where they exist;
    # telemetry covers the scoped era only.
    reports = {}
    for path in sorted(Path(critiques_dir).glob("*/_bmv_visual_critique.json")):
        reports[int(path.parent.name)] = json.loads(path.read_text(encoding="utf-8"))
    judged = {rid: r for rid, r in reports.items()
              if r.get("review_status") not in (None, "no_routes", "unmeasured")}
    refined = {rid for rid, r in judged.items() if r.get("refined")}
    refine_ids = set(db["refine_request_ids"])
    scoped = db["scoped_era_request_ids"]

    return {
        "method": "see module docstring",
        "marker": {
            "corpus_runs": len(per_run),
            "runs_with_stored_record": len(runs_with_record),
            "total_pages": total_pages,
            "pages_with_marker": total_marked,
            "marker_share_pct": round(100 * total_marked / total_pages, 1),
            "slot_filled_pages_that_kept_the_marker": len(kept),
            "kept_marker_routed_pipeline_accepted": kept_routed,
            "kept_marker_unrouted_never_inspected": kept_unrouted,
            "runs_affected_kept": sorted({r for r, _ in kept}),
            "reported_fallback_without_marker": len(ghost),
            "runs_affected_ghost": sorted({r for r, _ in ghost}),
            "kept_detail": [{"request": r, "page": p} for r, p in kept],
            "ghost_detail": [{"request": r, "page": p} for r, p in ghost],
        },
        "refine": {
            "reports_total": len(reports),
            "reports_judged": len(judged),
            "reports_with_refine_fired": sorted(refined),
            "p_refine_given_judged_pct": round(100 * len(refined) / len(judged), 1)
            if judged else None,
            "telemetry_scoped_era_runs": len(scoped),
            "telemetry_scoped_era_span": [min(scoped), max(scoped)] if scoped else None,
            "telemetry_refine_runs": sorted(refine_ids),
            "p_refine_scoped_era_pct": round(100 * len(refine_ids) / len(scoped), 1)
            if scoped else None,
            "refine_rows": db["refine_rows"],
        },
        "per_run": per_run,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspaces", type=Path, action="append", required=True)
    ap.add_argument("--critiques", type=Path, required=True)
    ap.add_argument("--fallback", type=Path, required=True)
    ap.add_argument("--routes", type=Path, required=True)
    ap.add_argument("--db-json", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--check", type=Path,
                    help="archived census JSON; red-exit on drift in marker/refine blocks")
    args = ap.parse_args()

    result = run_census(args.workspaces, args.critiques, args.fallback,
                        args.routes, args.db_json)

    m, rf = result["marker"], result["refine"]
    print(f"marker: {m['corpus_runs']} runs, {m['total_pages']} pages, "
          f"{m['pages_with_marker']} with marker ({m['marker_share_pct']} %)")
    print(f"  slot-filled pages that KEPT the marker (telemetry said AI-authored): "
          f"{m['slot_filled_pages_that_kept_the_marker']} across runs "
          f"{m['runs_affected_kept']}")
    print(f"    of which routed (finalize looked and accepted): "
          f"{m['kept_marker_routed_pipeline_accepted']}; unrouted (never "
          f"inspected): {m['kept_marker_unrouted_never_inspected']}")
    print(f"  reported fallback with NO marker on disk: "
          f"{m['reported_fallback_without_marker']} across runs {m['runs_affected_ghost']}")
    print(f"refine: fired on {len(rf['reports_with_refine_fired'])} of "
          f"{rf['reports_judged']} judged reports "
          f"({rf['p_refine_given_judged_pct']} %); telemetry scoped era "
          f"{rf['telemetry_scoped_era_span']}: {len(rf['telemetry_refine_runs'])} of "
          f"{rf['telemetry_scoped_era_runs']} runs ({rf['p_refine_scoped_era_pct']} %), "
          f"{rf['refine_rows']} refine calls")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"wrote {args.json}")

    if args.check:
        archived = json.loads(args.check.read_text(encoding="utf-8"))
        drift = [k for k in ("marker", "refine") if archived.get(k) != result.get(k)]
        if drift:
            print(f"DRIFT against {args.check}: {', '.join(drift)} — the corpus or "
                  "the predicate changed; re-derive before citing the archived numbers",
                  file=sys.stderr)
            raise SystemExit(1)
        print(f"check OK — matches {args.check}")


if __name__ == "__main__":
    main()
