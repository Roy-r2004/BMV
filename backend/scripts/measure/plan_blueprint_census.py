#!/usr/bin/env python3
"""Which PLAN pages the kind blueprint seeded, and what a serve-aware seed would skip.

Session 19 located the gallery residual's live entry point: under enforced appspec the
shipped ROUTE tables carry no `/gallery` (the architect-stage gap-fill fix `bbe6359`
holds), but request 124's `experience_plan.roles[1].pages` carries blueprint `gallery` +
`gallery_detail` pages and "Gallery"/"Artwork" nav links — `_ensure_role_pages`'s
thin-branch (`product_kind.py`, `len(real) < 2` per role) appends the whole
`_storefront_pages()` blueprint into any thin role with none of the serve-aware
resolution `_inject_blueprint_routes` got. `gallery_gapfill_census.py` replays only the
architect stage over stored ROUTE tables; the plan stage was unmeasured. This tool is
that measurement.

**How a seeded plan page is identified.** `_ensure_role_pages` appends
`_page_plan_dict(bp)` verbatim: `id == bp.id`, `purpose == bp.purpose` (repository
literals no model wrote — "Catalogue grid of products or artworks.") and the single
synthetic section `{"name": "Workspace", "description": bp.purpose, "priority":
"required"}`. A stored plan page matching all three against its own run's STORED
`product_kind_contract["pages"]` is an injection with no ambiguity. The stored contract
dict is the fingerprint source on purpose: old runs seeded under old literals replay
against their own era's blueprint, not today's.

**The self-check (label == resolved).** For every role where fingerprints identify
seeded pages, the tool reconstructs the pre-seed role (seeded pages and their
nav links removed) and replays the REAL `_ensure_role_pages` on it. The replayed
page-id sequence and nav page_id set must reproduce the stored role — a mismatch means
the fingerprint or the reconstruction is wrong and the row's numbers would be fiction,
so mismatches are listed and the exit code is 1. Runs whose contract cannot be rebuilt
are counted and excluded, never silently skipped.

Read-only. Run inside the api container:

    docker compose exec -T api python /app/backend/scripts/measure/plan_blueprint_census.py
    docker compose exec -T api python /app/backend/scripts/measure/plan_blueprint_census.py --json /tmp/plan-census.json
    docker compose exec -T api python /app/backend/scripts/measure/plan_blueprint_census.py 122 124 125
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any

for _candidate in ("/app/backend", str(Path(__file__).resolve().parents[2])):
    if (Path(_candidate) / "app").is_dir():
        if _candidate not in sys.path:
            sys.path.insert(0, _candidate)
        break
else:  # pragma: no cover
    raise SystemExit("cannot locate the backend package")

from sqlalchemy import text  # noqa: E402

from app.application.preview_app.product_kind import (  # noqa: E402
    PageBlueprint,
    ProductKindContract,
    _ensure_role_pages,
    _page_path_hint,
)
from app.infrastructure.db.session import engine  # noqa: E402


def _load_plans(request_ids: list[int]) -> list[tuple[int, dict[str, Any]]]:
    where = "generated_pages IS NOT NULL"
    params: dict[str, Any] = {}
    if request_ids:
        where += " AND id = ANY(:ids)"
        params["ids"] = request_ids
    rows: list[tuple[int, dict[str, Any]]] = []
    with engine.connect() as conn:
        for rid, payload in conn.execute(
            text(f"SELECT id, generated_pages FROM requests WHERE {where} ORDER BY id"),
            params,
        ):
            try:
                data = json.loads(payload)
            except Exception:
                continue
            plan = data.get("experience_plan")
            if isinstance(plan, dict):
                rows.append((int(rid), plan))
    return rows


def _rebuild_contract(plan: dict[str, Any]) -> ProductKindContract | None:
    stored = plan.get("product_kind_contract")
    if not isinstance(stored, dict) or not isinstance(stored.get("pages"), list):
        return None
    try:
        pages = tuple(
            PageBlueprint(
                id=str(p["id"]),
                title=str(p["title"]),
                path=str(p["path"]),
                page_type=str(p["page_type"]),
                component_file=str(p["component_file"]),
                purpose=str(p["purpose"]),
                sample_data_notes=str(p.get("sample_data_notes") or ""),
                skeleton_id=str(p.get("skeleton_id") or "ops-list"),
                surface=str(p.get("surface") or "ops"),
            )
            for p in stored["pages"]
        )
        return ProductKindContract(
            kind=str(stored["product_kind"]),
            recipe_id=str(stored["recipe_id"]),
            home_surface=str(stored["home_surface"]),
            home_skeleton_id=str(stored["home_skeleton_id"]),
            pages=pages,
            template_surface=str(stored["template_surface"]),
            design_note=str(stored.get("design_note") or ""),
            subtype=str(stored.get("subtype") or ""),
        )
    except (KeyError, TypeError):
        return None


def _seeded_ids(role: dict[str, Any], contract: ProductKindContract) -> list[str]:
    """Plan page ids that are byte-level blueprint injections for THIS run's contract."""
    seeded: list[str] = []
    for page in role.get("pages") or []:
        if not isinstance(page, dict):
            continue
        for bp in contract.pages:
            if (
                str(page.get("id")) == bp.id
                and str(page.get("purpose")) == bp.purpose
                and page.get("sections")
                == [
                    {
                        "name": "Workspace",
                        "description": bp.purpose,
                        "priority": "required",
                    }
                ]
            ):
                seeded.append(bp.id)
                break
    return seeded


def _pre_seed_role(role: dict[str, Any], seeded: list[str]) -> dict[str, Any]:
    out = copy.deepcopy(role)
    out["pages"] = [
        p
        for p in out.get("pages") or []
        if not (isinstance(p, dict) and str(p.get("id")) in seeded)
    ]
    nav = out.get("navigation")
    if isinstance(nav, dict) and isinstance(nav.get("links"), list):
        nav["links"] = [
            link
            for link in nav["links"]
            if not (isinstance(link, dict) and str(link.get("page_id")) in seeded)
        ]
    return out


def _role_shape(role: dict[str, Any]) -> tuple[list[str], set[str]]:
    page_ids = [
        str(p.get("id") or "") for p in role.get("pages") or [] if isinstance(p, dict)
    ]
    nav = role.get("navigation") or {}
    links = {
        str(link.get("page_id") or "")
        for link in (nav.get("links") or [])
        if isinstance(link, dict)
    }
    return page_ids, links


def _served_kinds_plan_wide(plan: dict[str, Any], exclude: set[tuple[str, str]]) -> set[str]:
    """Serve set over non-seeded pages — the PRODUCTION rule where it exists.

    Post-fix, `product_kind._plan_served_kinds` is the rule the seeder consults
    (inference + the browse-leaf token half); this column must be that rule, not
    a paraphrase. Pre-fix code has no such function — fall back to bare
    inference so the before archive still renders.
    """
    roles = []
    for role in plan.get("roles") or []:
        if not isinstance(role, dict):
            continue
        role_id = str(role.get("id") or "")
        roles.append(
            {
                **role,
                "pages": [
                    p
                    for p in role.get("pages") or []
                    if isinstance(p, dict)
                    and (role_id, str(p.get("id") or "")) not in exclude
                ],
            }
        )
    try:
        from app.application.preview_app.product_kind import _plan_served_kinds

        return _plan_served_kinds(roles)
    except ImportError:
        from app.application.ui_catalogue import infer_page_contract

        served: set[str] = set()
        for role in roles:
            for page in role["pages"]:
                try:
                    skeleton = str(infer_page_contract(page).get("skeleton_id") or "")
                except Exception:
                    skeleton = ""
                if skeleton:
                    served.add(skeleton)
        return served


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request_ids", nargs="*", type=int)
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args()

    rows = _load_plans(args.request_ids)
    report: list[dict[str, Any]] = []
    mismatches: list[str] = []
    no_contract = 0

    for rid, plan in rows:
        contract = _rebuild_contract(plan)
        if contract is None:
            no_contract += 1
            report.append({"request": rid, "skipped": "no rebuildable contract"})
            continue

        roles = [r for r in plan.get("roles") or [] if isinstance(r, dict)]
        seeded_pairs: set[tuple[str, str]] = set()
        role_rows: list[dict[str, Any]] = []
        for role in roles:
            role_id = str(role.get("id") or "")
            seeded = _seeded_ids(role, contract)
            for sid in seeded:
                seeded_pairs.add((role_id, sid))
            entry: dict[str, Any] = {"role": role_id, "seeded": seeded}
            role_rows.append(entry)

        # Replay pass (separate loop so the seeded_pairs set is complete first).
        # Verdicts: `reproduces` — the current seeder re-appends exactly what is
        # stored (reconstruction proven); `seeds_fewer` — the replay appends a
        # strict subset, which is EITHER a legacy run seeded by older code (the
        # before archive) or the serve-aware fix declining a redundant seed (the
        # after archive) — the two archives' diff is the measurement;
        # `diverges_other` — anything else means the fingerprint or the
        # reconstruction is wrong and the row is fiction: red exit.
        plan_served = None
        for role, entry in zip(roles, role_rows):
            seeded = entry["seeded"]
            if not seeded:
                continue
            if plan_served is None:
                try:
                    from app.application.preview_app.product_kind import (
                        _plan_served_kinds,
                    )

                    pre_seed_roles = [
                        _pre_seed_role(r, _seeded_ids(r, contract)) for r in roles
                    ]
                    plan_served = _plan_served_kinds(pre_seed_roles)
                except ImportError:  # pre-fix code: per-role seeding only
                    plan_served = ()
            candidate = _pre_seed_role(role, seeded)
            pre_pages, _ = _role_shape(candidate)
            if plan_served == ():
                _ensure_role_pages(candidate, contract)
            else:
                _ensure_role_pages(candidate, contract, plan_served_kinds=plan_served)
            got_pages, got_links = _role_shape(candidate)
            want_pages, want_links = _role_shape(role)
            appended = [p for p in got_pages if p not in pre_pages]
            entry["replay_appended"] = appended
            if got_pages == want_pages and got_links == want_links:
                entry["verdict"] = "reproduces"
            elif set(appended) < set(seeded) and all(
                p in want_pages for p in got_pages
            ):
                entry["verdict"] = "seeds_fewer"
                entry["skipped_by_replay"] = sorted(set(seeded) - set(appended))
            else:
                entry["verdict"] = "diverges_other"
                entry["replay_pages"] = got_pages
                entry["stored_pages"] = want_pages
                mismatches.append(f"request {rid} role {entry['role']}")

        served = _served_kinds_plan_wide(plan, seeded_pairs)
        residual_nav = [
            str(link.get("label") or "")
            for role in roles
            for link in ((role.get("navigation") or {}).get("links") or [])
            if isinstance(link, dict)
            and (str(role.get("id") or ""), str(link.get("page_id") or ""))
            in seeded_pairs
        ]
        seeded_catalog_redundant = sorted(
            {
                sid
                for (role_id, sid) in seeded_pairs
                for bp in contract.pages
                if bp.id == sid and bp.skeleton_id in served
            }
        )
        detail_pages_unanchored = [
            {
                "role": str(role.get("id") or ""),
                "page": str(page.get("id") or page.get("title") or ""),
                "path_hint": _page_path_hint(page),
            }
            for role in roles
            for page in role.get("pages") or []
            if isinstance(page, dict)
            and (str(role.get("id") or ""), str(page.get("id") or "")) not in seeded_pairs
            and str(page.get("skeleton_id") or "") == "public-detail"
            and "/:" not in _page_path_hint(page)
        ]
        report.append(
            {
                "request": rid,
                "kind": f"{contract.kind}/{contract.subtype}",
                "roles": role_rows,
                "seeded_total": len(seeded_pairs),
                "served_kinds_excl_seeded": sorted(served),
                "seeded_redundant_by_served_kind": seeded_catalog_redundant,
                "residual_nav_labels": residual_nav,
                "public_detail_pages_without_item_anchor": detail_pages_unanchored,
            }
        )

    seeded_runs = [r for r in report if r.get("seeded_total")]
    redundant_runs = [r for r in report if r.get("seeded_redundant_by_served_kind")]
    unanchored_runs = [
        r for r in report if r.get("public_detail_pages_without_item_anchor")
    ]
    summary = {
        "requests_with_plans": len(rows),
        "contract_not_rebuildable": no_contract,
        "runs_with_blueprint_seeding": len(seeded_runs),
        "runs_where_seeding_duplicates_a_served_kind": len(redundant_runs),
        "runs_with_unanchored_public_detail_plan_pages": len(unanchored_runs),
        "replay_mismatches": mismatches,
    }
    print(json.dumps(summary, indent=2))
    for row in report:
        if row.get("seeded_total") or row.get("public_detail_pages_without_item_anchor"):
            print(json.dumps(row))

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"summary": summary, "rows": report}, indent=1)
        )

    if mismatches:
        print(f"REPLAY MISMATCH on {len(mismatches)} role(s) — numbers above are suspect")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
