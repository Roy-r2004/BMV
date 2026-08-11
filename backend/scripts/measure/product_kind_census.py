#!/usr/bin/env python3
"""Census 0.5 — the REAL product_kind distribution over stored runs.

QUESTION. Where should Phase 3 spend: the 6 public-reachable skeletons or the
9 ops skeletons? That turns on the actual kind mix of real customer runs, so:
what is the per-kind distribution (and public vs ops split) over (a) the 47
archived kind_contexts and (b) the kind decisions stored per-request in the
live DB — reported separately AND merged with dedup?

METHOD.
  Corpus A — docs/evidence/preview-routes.json: 47 entries keyed by REQUEST ID
  (verified: business_name of ids 1/17/19/47 matches the DB row), each carrying
  `kind_context` — the exact classifier-input string plan_phase.py built at
  generation time (industry + description + problem + outcome + customers +
  name + full_context[:800]). Each context is re-classified with TODAY's
  deterministic `resolve_product_kind_contract` (no model call, no network).

  Corpus B — live DB `requests.generated_pages` -> `experience_plan` ->
  `product_kind` / `product_kind_subtype`: the decision the run actually
  stamped, persisted by finalize.py via `_plan_for_persistence` (which keeps
  the kind keys). Coverage is stated exactly: total requests, rows with
  generated_pages, rows with a stored kind, and every uncovered id with why.
  Checked and ruled out as alternatives: no `product_kind` column exists on
  `requests`; `app_spec_revisions.source_snapshot_json` does NOT persist the
  product_face guidance (capture_request_source only — verified over latest
  revisions, 0/114 carry it); v2 `preview_contract` blobs hold artifact refs,
  no kind.

  Merged — union by request id (the archive keys ARE request ids, so dedup is
  id equality, guarded by a business_name cross-check). Two merge policies are
  printed because they answer different questions:
    stored-wins    — what the runs actually decided (historical truth);
    rederived-wins — what today's classifier says about the same real briefs
                     (uses the archived exact input where it exists, else the
                     stored decision). The gap between the two is the
                     classifier drift, listed id by id.

JUDGMENT CALLS.
  * Corpus A re-derivation uses the CURRENT classifier: the archive stores the
    input, not the decision, so A measures "today's pipeline over real
    historical briefs", not "what the run decided then". Corpus B is the
    historical decision. Both are printed; neither is passed off as the other.
  * Rows without a stored kind are reported as uncovered, never silently
    re-classified into corpus B.
  * Public vs ops uses PUBLIC_KINDS / OPS_KINDS imported from the live
    product_kind module — never a literal copy that could drift.
  * Skeleton exercise counts (home + per-page) are reported for corpus A only:
    re-derived contracts on exact archived inputs are what Phase 3 will
    actually exercise; stored contracts may predate skeleton renames.

INVOCATION (in-container; /app/backend is the only mount, docs/ is NOT there,
so copy the archive in first and the JSON out after):
  docker cp docs/evidence/preview-routes.json bmv-api:/tmp/preview-routes.json
  docker exec -w /app/backend bmv-api python3 scripts/measure/product_kind_census.py \
      | tee docs/evidence/session25/product-kind-census.txt
  docker cp bmv-api:/tmp/product-kind-census.json \
      docs/evidence/session25/product-kind-census.json

RED-EXITS (sys.exit(2), loud): routes file missing/unparseable; kind_context
count != 47; an entry without a kind_context; DB unreachable; requests table
or generated_pages column missing; a stored kind outside the 4 known kinds;
business_name mismatch between archive and DB on a shared id (the dedup
identity assumption would be wrong).

Read-only against the DB. No model calls. No network beyond Postgres.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

# House pattern (boundary_variant_census.py): the backend dir on sys.path so
# `app.*` imports resolve when the script is run by path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

EXPECTED_ROUTES = 47  #: baked corpus size — drift means the archive changed.


def red(msg: str) -> None:
    print(f"\nRED-EXIT: {msg}", file=sys.stderr)
    print(f"RED-EXIT: {msg}")
    sys.exit(2)


def pct(n: int, total: int) -> str:
    return f"{(100.0 * n / total):.1f}%" if total else "n/a"


def split(counter: Counter, public_kinds, ops_kinds) -> tuple[int, int]:
    pub = sum(v for k, v in counter.items() if k in public_kinds)
    ops = sum(v for k, v in counter.items() if k in ops_kinds)
    return pub, ops


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--routes", default="/tmp/preview-routes.json",
                    help="path to the archived preview-routes.json (docker cp'd in)")
    ap.add_argument("--json-out", default="/tmp/product-kind-census.json",
                    help="machine-readable census output (docker cp'd out)")
    args = ap.parse_args()

    # ---- live classifier + kind sets (derive, never duplicate) -------------
    try:
        from app.application.preview_app.product_kind import (
            OPS_KINDS,
            PUBLIC_KINDS,
            resolve_product_kind_contract,
        )
    except Exception as exc:  # pragma: no cover
        red(f"cannot import product_kind module ({exc!r}) — run in-container "
            "with -w /app/backend")
    known_kinds = frozenset(PUBLIC_KINDS) | frozenset(OPS_KINDS)

    # ---- corpus A: archived kind_contexts, re-derived ----------------------
    routes_path = Path(args.routes)
    if not routes_path.is_file():
        red(f"routes archive missing at {routes_path} — "
            "docker cp docs/evidence/preview-routes.json bmv-api:/tmp/ first")
    try:
        archive = json.loads(routes_path.read_text())
    except Exception as exc:
        red(f"routes archive unparseable: {exc!r}")
    if not isinstance(archive, dict):
        red(f"routes archive is {type(archive).__name__}, expected dict keyed "
            "by request id")
    contexts = {}
    for key, entry in archive.items():
        kc = (entry or {}).get("kind_context") if isinstance(entry, dict) else None
        if not (isinstance(kc, str) and kc.strip()):
            red(f"archive entry {key!r} has no kind_context — shape drifted")
        contexts[int(key)] = (kc, entry.get("business_name") or "")
    if len(contexts) != EXPECTED_ROUTES:
        red(f"archive holds {len(contexts)} kind_contexts, baked assumption is "
            f"{EXPECTED_ROUTES} — corpus changed, re-derive the question first")

    a_rows: dict[int, dict] = {}
    for rid, (kc, name) in sorted(contexts.items()):
        c = resolve_product_kind_contract(kc)
        a_rows[rid] = {
            "business_name": name,
            "kind": c.kind,
            "subtype": c.subtype,
            "home_skeleton_id": c.home_skeleton_id,
            "page_skeletons": [p.skeleton_id for p in c.pages],
        }
    a_kinds = Counter(r["kind"] for r in a_rows.values())

    # ---- corpus B: stored decisions in the live DB -------------------------
    try:
        import sqlalchemy as sa
        from app.core.config import settings
        engine = sa.create_engine(settings.DATABASE_URL)
        conn = engine.connect()
    except Exception as exc:
        red(f"live DB unreachable via settings.DATABASE_URL ({exc!r})")
    try:
        db_rows = conn.execute(sa.text(
            "SELECT id, business_name, generated_pages FROM requests ORDER BY id"
        )).fetchall()
    except Exception as exc:
        red(f"requests/generated_pages query failed — schema drifted? ({exc!r})")

    total_requests = len(db_rows)
    b_rows: dict[int, dict] = {}
    with_generated = 0
    uncovered: list[dict] = []  # id + why, every one of them
    for rid, name, blob in db_rows:
        if not blob:
            uncovered.append({"id": rid, "why": "no generated_pages (never finalized)"})
            continue
        with_generated += 1
        try:
            bundle = json.loads(blob)
        except Exception:
            uncovered.append({"id": rid, "why": "generated_pages unparseable"})
            continue
        ep = bundle.get("experience_plan") if isinstance(bundle, dict) else None
        kind = (ep or {}).get("product_kind")
        if not kind:
            keys = sorted(bundle.keys()) if isinstance(bundle, dict) else []
            why = ("experience_plan without product_kind (pre-kind era)"
                   if ep else f"no experience_plan (bundle keys: {keys})")
            uncovered.append({"id": rid, "why": why})
            continue
        if kind not in known_kinds:
            red(f"request {rid} stored kind {kind!r} outside the known set "
                f"{sorted(known_kinds)} — public/ops split would be wrong")
        b_rows[rid] = {
            "business_name": name,
            "kind": kind,
            "subtype": (ep or {}).get("product_kind_subtype") or "",
        }
    b_kinds = Counter(r["kind"] for r in b_rows.values())

    # ---- dedup guard: shared ids must be the same business -----------------
    overlap = sorted(set(a_rows) & set(b_rows))
    for rid in overlap:
        a_name = a_rows[rid]["business_name"].strip().casefold()
        b_name = (b_rows[rid]["business_name"] or "").strip().casefold()
        if a_name and b_name and a_name != b_name:
            red(f"id {rid}: archive business_name {a_rows[rid]['business_name']!r} "
                f"!= DB {b_rows[rid]['business_name']!r} — archive keys are not "
                "request ids, the merge dedup is invalid")

    drift = [
        {"id": rid, "stored": b_rows[rid]["kind"], "rederived": a_rows[rid]["kind"],
         "business_name": b_rows[rid]["business_name"]}
        for rid in overlap if a_rows[rid]["kind"] != b_rows[rid]["kind"]
    ]

    # ---- merged, both policies --------------------------------------------
    union_ids = sorted(set(a_rows) | set(b_rows))
    merged_stored = Counter(
        (b_rows.get(rid) or a_rows.get(rid))["kind"] for rid in union_ids
    )
    merged_rederived = Counter(
        (a_rows.get(rid) or b_rows.get(rid))["kind"] for rid in union_ids
    )

    # ---- print the census --------------------------------------------------
    def show(title: str, kinds: Counter, n: int) -> tuple[int, int]:
        pub, ops = split(kinds, PUBLIC_KINDS, OPS_KINDS)
        print(f"\n{title} (n={n})")
        for kind in sorted(known_kinds):
            print(f"  {kind:<18} {kinds.get(kind, 0):>3}  ({pct(kinds.get(kind, 0), n)})")
        print(f"  PUBLIC (storefront+booking) {pub:>3}  ({pct(pub, n)})")
        print(f"  OPS (saas+internal)         {ops:>3}  ({pct(ops, n)})")
        return pub, ops

    print("PRODUCT KIND CENSUS 0.5 — stored runs, both corpora")
    print(f"archive: {routes_path}  |  DB: requests.generated_pages"
          " -> experience_plan.product_kind")

    show("CORPUS A — 47 archived kind_contexts, re-classified by TODAY's "
         "classifier", a_kinds, len(a_rows))
    a_sub = Counter((r["kind"], r["subtype"]) for r in a_rows.values())
    print("  subtypes: " + ", ".join(
        f"{k}/{s}={n}" for (k, s), n in sorted(a_sub.items())))
    home_sk = Counter(r["home_skeleton_id"] for r in a_rows.values())
    page_sk = Counter(sk for r in a_rows.values() for sk in r["page_skeletons"])
    print("  home skeletons (A): " + ", ".join(
        f"{k}={n}" for k, n in home_sk.most_common()))
    print("  page skeletons (A): " + ", ".join(
        f"{k}={n}" for k, n in page_sk.most_common()))

    show("CORPUS B — kind decisions STORED per-request in the live DB",
         b_kinds, len(b_rows))
    b_sub = Counter((r["kind"], r["subtype"]) for r in b_rows.values())
    print("  subtypes: " + ", ".join(
        f"{k}/{s}={n}" for (k, s), n in sorted(b_sub.items())))
    print(f"  coverage: {total_requests} requests total, {with_generated} with "
          f"generated_pages, {len(b_rows)} with a stored kind, "
          f"{len(uncovered)} uncovered")
    for u in uncovered:
        print(f"    uncovered id {u['id']}: {u['why']}")

    print(f"\nOVERLAP — ids in both corpora: {len(overlap)} "
          f"(A-only {len(a_rows) - len(overlap)}, B-only {len(b_rows) - len(overlap)})")
    print(f"  stored vs re-derived kind AGREE on {len(overlap) - len(drift)}"
          f"/{len(overlap)}; drift on {len(drift)}:")
    for d in drift:
        print(f"    id {d['id']} ({d['business_name']}): stored={d['stored']} "
              f"-> today={d['rederived']}")

    ms_pub, ms_ops = show(
        "MERGED (dedup by request id) — STORED-WINS (what the runs decided)",
        merged_stored, len(union_ids))
    mr_pub, mr_ops = show(
        "MERGED (dedup by request id) — REDERIVED-WINS (what today's pipeline "
        "would decide)", merged_rederived, len(union_ids))

    print("\nPHASE-3 SPEND READING (small corpora — 47/66/"
          f"{len(union_ids)} runs; report as directional, not gospel):")
    print(f"  merged stored-wins:    public {ms_pub} ({pct(ms_pub, len(union_ids))}) "
          f"vs ops {ms_ops} ({pct(ms_ops, len(union_ids))})")
    print(f"  merged rederived-wins: public {mr_pub} ({pct(mr_pub, len(union_ids))}) "
          f"vs ops {mr_ops} ({pct(mr_ops, len(union_ids))})")

    # ---- machine-readable archive ------------------------------------------
    out = {
        "question": "product_kind distribution over stored runs; public vs ops "
                    "split for the Phase-3 skeleton spend decision",
        "expected_routes": EXPECTED_ROUTES,
        "corpus_a": {
            "source": "docs/evidence/preview-routes.json kind_context, "
                      "re-classified by today's resolve_product_kind_contract",
            "n": len(a_rows),
            "kinds": dict(a_kinds),
            "subtypes": {f"{k}/{s}": n for (k, s), n in sorted(a_sub.items())},
            "public_ops_split": dict(zip(("public", "ops"),
                                         split(a_kinds, PUBLIC_KINDS, OPS_KINDS))),
            "home_skeletons": dict(home_sk),
            "page_skeletons": dict(page_sk),
            "per_request": {str(rid): r for rid, r in sorted(a_rows.items())},
        },
        "corpus_b": {
            "source": "requests.generated_pages -> experience_plan.product_kind "
                      "(live DB, stored at generation time)",
            "requests_total": total_requests,
            "with_generated_pages": with_generated,
            "n": len(b_rows),
            "kinds": dict(b_kinds),
            "subtypes": {f"{k}/{s}": n for (k, s), n in sorted(b_sub.items())},
            "public_ops_split": dict(zip(("public", "ops"),
                                         split(b_kinds, PUBLIC_KINDS, OPS_KINDS))),
            "uncovered": uncovered,
            "per_request": {str(rid): r for rid, r in sorted(b_rows.items())},
        },
        "overlap": {
            "ids_in_both": overlap,
            "n": len(overlap),
            "agree": len(overlap) - len(drift),
            "drift": drift,
        },
        "merged": {
            "dedup": "union by request id (archive keys verified as request "
                     "ids via business_name cross-check)",
            "n": len(union_ids),
            "stored_wins": {
                "kinds": dict(merged_stored),
                "public_ops_split": {"public": ms_pub, "ops": ms_ops},
            },
            "rederived_wins": {
                "kinds": dict(merged_rederived),
                "public_ops_split": {"public": mr_pub, "ops": mr_ops},
            },
        },
        "alternatives_ruled_out": {
            "requests.product_kind column": "does not exist",
            "app_spec_revisions.source_snapshot_json": "capture_request_source "
                "only; derived_context/product_face not persisted (0/114 latest "
                "revisions carry it)",
            "v2 preview_contract blobs": "artifact refs only, no kind",
        },
    }
    Path(args.json_out).write_text(json.dumps(out, indent=2, sort_keys=False))
    print(f"\njson written: {args.json_out}")


if __name__ == "__main__":
    main()
