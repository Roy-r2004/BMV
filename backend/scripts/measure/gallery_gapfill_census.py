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

**What stands in for the plan merge.** The rule asks what page contract a route resolves
to. ``_normalize_architect`` answers that question twelve lines later via
``infer_page_contract({**plan_page, **route})`` and persists the answer as the route's
``skeleton_id``. The plan is **not stored**; the resolved ``skeleton_id`` is, and a stored
route carries it, so replaying the gap-fill over a stored table reaches the same verdict
the plan would have produced. On a live run the plan is what supplies it — the route alone
is measurably different (request 98's ``/rooms`` resolves to ``public-catalog`` with the
plan merged and ``public-service`` without it), which is why
``apply_product_kind_to_architect`` takes the plan.

**Two defects in this script's own first version, both worth knowing about.** It called
``resolve_product_kind_contract(*context_from_request(req))`` — and ``context_from_request``
returns a *string*, so the splat passed it one character per argument and every run
classified ``storefront``. And it re-implemented the rule instead of calling it, which
diverged on ops kinds, where neither branch of ``apply_product_kind_to_architect`` fires at
all. Both columns are now the production function; the "before" column wraps it to force
the old behaviour.

    docker compose exec api python /app/backend/scripts/measure/gallery_gapfill_census.py

Without a database, `--routes docs/evidence/preview-routes.json` reads the same
47 route tables from the archive, which is what makes every number here
re-derivable next session:

    docker run --rm -v "$REPO:/repo" -w /repo/backend \\
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \\
      -c 'python3 scripts/measure/gallery_gapfill_census.py --routes ../docs/evidence/preview-routes.json'
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


def _added(declared: list[dict], contract, *, needs_based: bool) -> list[str]:
    """Run the real gap-fill and report what it appended.

    Simulating the rule here was wrong twice over: an earlier version of this
    script re-implemented it and diverged from the code on non-public kinds,
    where neither branch of `apply_product_kind_to_architect` fires at all. The
    "before" column forces the old behaviour by wrapping the same function, so
    both columns are the production code and neither is a paraphrase of it.
    """
    from app.application.preview_app import product_kind

    original = product_kind._inject_blueprint_routes
    if not needs_based:

        def _forced(*args, **kwargs):
            kwargs["only_when_unserved"] = False
            return original(*args, **kwargs)

        product_kind._inject_blueprint_routes = _forced
    try:
        before = {str(r.get("path") or "") for r in declared}
        architect = product_kind.apply_product_kind_to_architect(
            {"routes": [dict(r) for r in declared], "files_to_generate": []},
            contract,
        )
    finally:
        product_kind._inject_blueprint_routes = original
    return [
        str(r.get("path") or "")
        for r in architect["routes"]
        if str(r.get("path") or "") not in before
    ]


class _ArchivedRequest:
    """The four fields this census reads, from `docs/evidence/preview-routes.json`."""

    def __init__(self, request_id: str, row: dict) -> None:
        self.id = int(request_id)
        self.business_name = row.get("business_name") or ""
        self.industry = row.get("industry") or ""
        self.kind_context = row.get("kind_context") or ""
        self.generated_pages = {"preview_app": {"routes": row.get("routes") or []}}


def _requests(routes_file: str | None):
    if routes_file:
        archive = json.loads(Path(routes_file).read_text())
        return [
            _ArchivedRequest(rid, row)
            for rid, row in sorted(archive.items(), key=lambda kv: int(kv[0]))
        ]
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    return SessionLocal().query(Request).order_by(Request.id).all()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="emit machine-readable rows")
    parser.add_argument(
        "--routes",
        default=None,
        help="docs/evidence/preview-routes.json — read the archive instead of the database",
    )
    args = parser.parse_args()

    from app.application.preview_app.product_kind import (
        context_from_request,
        resolve_product_kind_contract,
    )

    rows = []
    try:
        for req in _requests(args.routes):
            routes = _routes_of(req)
            if not routes:
                continue
            # The archive stores the blob the live classifier saw, so an offline
            # replay cannot drift from the database one on classification.
            context = getattr(req, "kind_context", "") or context_from_request(req)
            contract = resolve_product_kind_contract(context)
            blueprints = contract.pages
            declared = [r for r in routes if not _is_injected(r, blueprints)]
            injected = [
                str(r.get("path") or "") for r in routes if _is_injected(r, blueprints)
            ]
            now = _added(declared, contract, needs_based=False)
            new = _added(declared, contract, needs_based=True)
            by_path = {str(r.get("path") or ""): r for r in routes}

            def _pages(added: list[str], skeleton: str) -> list[str]:
                out = [
                    str(r.get("path") or "")
                    for r in declared
                    if str(r.get("skeleton_id") or "") == skeleton
                ]
                out += [
                    p
                    for p in added
                    if str((by_path.get(p) or {}).get("skeleton_id") or "") == skeleton
                    or any(bp.path == p and bp.skeleton_id == skeleton for bp in blueprints)
                ]
                return sorted(set(out))

            catalogue_now = _pages(now, "public-catalog")
            catalogue_after = _pages(new, "public-catalog")
            detail_now = _pages(now, "public-detail")
            detail_after = _pages(new, "public-detail")
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
                    "catalogue_now": catalogue_now,
                    "catalogue_after": catalogue_after,
                    "detail_now": detail_now,
                    "detail_after": detail_after,
                    # The only losses that matter: a page the app HAD before the
                    # rule changed and does not have after it.
                    "loses_last_catalogue": bool(catalogue_now) and not catalogue_after,
                    "loses_last_detail": bool(detail_now) and not detail_after,
                }
            )
    finally:
        pass

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
        if any(row["loses_last_catalogue"] for row in group):
            lost_catalogue += 1
        if any(row["loses_last_detail"] for row in group):
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
    no_cat = [r for r in rows if r["loses_last_catalogue"]]
    no_det = [r for r in rows if r["loses_last_detail"]]
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
        f"runs LOSE their last public-catalog page{': ' + str(sorted(r['id'] for r in no_cat)) if no_cat else ''}; "
        f"{lost_detail} of {len(by_brief)} briefs and {len(no_det)} of {len(rows)} "
        f"LOSE their last public-detail page{': ' + str(sorted(r['id'] for r in no_det)) if no_det else ''}."
    )
    print(
        f"{len(still)} of {len(rows)} runs are still gap-filled a catalogue because "
        f"they declared none: {sorted(r['id'] for r in still)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
