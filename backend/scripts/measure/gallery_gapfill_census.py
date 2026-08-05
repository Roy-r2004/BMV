"""Which pages a needs-based blueprint gap-fill would add, and which it would stop adding.

Session 11 located the trattoria's art gallery: ``product_kind.py:1008-1010`` gap-fills
``_storefront_pages()`` into every ``PUBLIC_KINDS`` app **even when the architect's route
table is already substantive**, and ``_storefront_pages()`` declares ``/gallery`` and
``/gallery/:id -> ArtworkDetailPage.tsx`` as literals. The gap-fill's only test for
"already served" is an exact **path string** match, so an app with ``/menu`` or ``/rooms``
is still told it is missing a catalogue.

This script measures the alternative before it is shipped: a gap-fill that adds a
blueprint page only when the app has no route that already **serves** it.

**How an injected route is identified.** ``_inject_blueprint_routes`` appends a dict built
from the ``PageBlueprint`` — ``page_id == bp.id``, ``component_file == bp.component_file``
and ``purpose == bp.purpose`` verbatim. That purpose string ("Catalogue grid of products
or artworks.") is a repository literal no model wrote, so a stored route carrying it at a
blueprint path is an injection with no ambiguity. Routes the blueprint merely *stamped*
(a path match runs ``setdefault``) keep the architect's own ``page_id`` and are counted as
declared, which is what they are.

**What stands in for the plan merge.** The rule under test asks what page contract a route
resolves to. ``_normalize_architect`` answers exactly that question twelve lines later via
``infer_page_contract({**plan_page, **route})`` and the answer is persisted as the route's
``skeleton_id``. The plan is not stored; the resolved ``skeleton_id`` is, so the census
reads it rather than re-inferring from the route alone — re-inferring from the route alone
is measurably different (request 98's ``/rooms`` resolves to ``public-catalog`` with the
plan merged and ``public-service`` without it).

    docker compose exec api python /app/backend/scripts/measure/gallery_gapfill_census.py
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

_REPO_BACKEND = Path(__file__).resolve().parents[2]
if str(_REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(_REPO_BACKEND))


def _routes_of(request) -> list[dict]:
    pages = request.generated_pages
    if isinstance(pages, str):
        try:
            pages = json.loads(pages)
        except ValueError:
            return []
    if not isinstance(pages, dict):
        return []
    app = pages.get("preview_app")
    if not isinstance(app, dict):
        return []
    return [r for r in (app.get("routes") or []) if isinstance(r, dict)]


def _is_injected(route: dict, blueprints) -> bool:
    """True when this route is a blueprint dict appended verbatim by the gap-fill."""
    for bp in blueprints:
        if (
            str(route.get("path") or "") == bp.path
            and str(route.get("page_id") or "") == bp.id
            and str(route.get("component_file") or "") == bp.component_file
            and str(route.get("purpose") or "") == bp.purpose
        ):
            return True
    return False


def _parent_path(path: str) -> str:
    """`/gallery/:id` -> `/gallery`; "" when the path is not a parameterized child."""
    head, sep, tail = path.rpartition("/")
    if not sep or not tail.startswith(":"):
        return ""
    return head or "/"


def _added_under_current_rule(declared: list[dict], blueprints) -> list[str]:
    served = {str(r.get("path") or "") for r in declared}
    added = []
    for bp in blueprints:
        if bp.path in served:
            continue
        served.add(bp.path)
        added.append(bp.path)
    return added


def _added_under_needs_rule(declared: list[dict], blueprints) -> tuple[list[str], dict]:
    """The rule under test. Returns (added paths, why each blueprint was skipped)."""
    served_paths = {str(r.get("path") or "") for r in declared}
    served_kinds = {
        (str(r.get("surface") or ""), str(r.get("skeleton_id") or ""))
        for r in declared
        if r.get("skeleton_id")
    }
    reasons: dict[str, str] = {}
    added = []
    for bp in blueprints:
        if bp.path in served_paths:
            reasons[bp.path] = "path already declared"
            continue
        parent = _parent_path(bp.path)
        if parent:
            # A detail page is not free-standing: it is reached from one listing.
            # Its equivalent is that listing's own detail child and nothing else,
            # so an unrelated detail page elsewhere does not make it redundant.
            if parent not in served_paths:
                reasons[bp.path] = f"parent {parent} is not served"
                continue
            if any(_parent_path(p) == parent for p in served_paths):
                reasons[bp.path] = f"{parent} already has a detail child"
                continue
        elif bp.path != "/" and (bp.surface, bp.skeleton_id) in served_kinds:
            reasons[bp.path] = f"{bp.skeleton_id} already served"
            continue
        served_paths.add(bp.path)
        served_kinds.add((bp.surface, bp.skeleton_id))
        added.append(bp.path)
    return added, reasons


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable rows")
    args = parser.parse_args()

    from app.application.preview_app.product_kind import (
        context_from_request,
        resolve_product_kind_contract,
    )
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    rows = []
    try:
        for req in db.query(Request).order_by(Request.id).all():
            routes = _routes_of(req)
            if not routes:
                continue
            contract = resolve_product_kind_contract(*context_from_request(req))
            blueprints = contract.pages
            declared = [r for r in routes if not _is_injected(r, blueprints)]
            injected = [
                str(r.get("path") or "") for r in routes if _is_injected(r, blueprints)
            ]
            now = _added_under_current_rule(declared, blueprints)
            new, reasons = _added_under_needs_rule(declared, blueprints)
            catalogue_after = [
                str(r.get("path") or "")
                for r in declared
                if str(r.get("skeleton_id") or "") == "public-catalog"
            ] + [p for p in new if p == "/gallery"]
            detail_after = [
                str(r.get("path") or "")
                for r in declared
                if str(r.get("skeleton_id") or "") == "public-detail"
            ] + [p for p in new if p.endswith("/:id")]
            rows.append(
                {
                    "id": req.id,
                    "business": req.business_name or "",
                    "industry": req.industry or "",
                    "kind": f"{contract.kind}/{contract.subtype}",
                    "declared": len(declared),
                    "injected_observed": injected,
                    # True when replaying today's gap-fill on the reconstructed
                    # architect table reproduces the injections the run actually
                    # shipped. False means the run was generated under a different
                    # classification or a different gap-fill, so its "before" is
                    # today's code on an old route table, not what happened.
                    "round_trips": sorted(set(injected)) == sorted(set(now)),
                    "added_now": now,
                    "added_new": new,
                    "stops_adding": [p for p in now if p not in new],
                    "reasons": reasons,
                    "catalogue_after": catalogue_after,
                    "detail_after": detail_after,
                }
            )
    finally:
        db.close()

    if args.json:
        print(json.dumps(rows, indent=1))
        return 0

    print(f"{len(rows)} runs with a stored route table\n")
    header = (
        "  id  business                  kind          rt  now                "
        "new                catalogue after      detail after"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for row in rows:
        print(
            "  %-3s %-25s %-13s %-3s %-18s %-18s %-20s %s"
            % (
                row["id"],
                row["business"][:25],
                row["kind"][:13],
                "ok" if row["round_trips"] else "DRIFT",
                ",".join(row["added_now"]) or "-",
                ",".join(row["added_new"]) or "-",
                ",".join(row["catalogue_after"]) or "NONE",
                ",".join(row["detail_after"]) or "NONE",
            )
        )

    by_brief: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_brief[(row["business"], row["industry"])].append(row)

    print(f"\n{len(by_brief)} distinct (business, industry) briefs\n")
    print("  brief                                   runs  stops adding            catalogue after   detail after")
    print("  " + "-" * 100)
    lost_catalogue = 0
    lost_detail = 0
    for (business, industry), group in sorted(by_brief.items()):
        stops = sorted({p for row in group for p in row["stops_adding"]})
        cat = sorted({p for row in group for p in row["catalogue_after"]})
        det = sorted({p for row in group for p in row["detail_after"]})
        if not cat:
            lost_catalogue += 1
        if not det:
            lost_detail += 1
        print(
            "  %-38s %-5s %-23s %-17s %s"
            % (
                f"{business[:26]} ({industry[:9]})",
                len(group),
                ",".join(stops) or "-",
                ",".join(cat) or "NONE",
                ",".join(det) or "NONE",
            )
        )

    changed = [r for r in rows if r["stops_adding"]]
    drift = [r for r in rows if not r["round_trips"]]
    clean = [r for r in rows if r["round_trips"]]
    no_cat = [r for r in rows if not r["catalogue_after"]]
    no_det = [r for r in rows if not r["detail_after"]]
    still = [r for r in rows if "/gallery" in r["added_new"]]
    print(
        f"\n{len(changed)} of {len(rows)} runs change "
        f"({len([r for r in changed if r['round_trips']])} of {len(clean)} on the "
        f"round-tripping subset); {len(drift)} runs DRIFT — today's classifier or "
        f"gap-fill disagrees with what they shipped, so their 'before' is a replay, "
        f"not a record."
    )
    print(
        f"{lost_catalogue} of {len(by_brief)} briefs and {len(no_cat)} of {len(rows)} "
        f"runs end with no public-catalog page; "
        f"{lost_detail} of {len(by_brief)} briefs and {len(no_det)} of {len(rows)} "
        f"runs end with no public-detail page."
    )
    print(
        f"{len(still)} of {len(rows)} runs are still gap-filled a catalogue because "
        f"they declared none: {sorted(r['id'] for r in still)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
