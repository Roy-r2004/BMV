"""What an ENFORCED AppSpec would ship, and which stage puts back what it removed.

Session 11 ran the enforcement spike live twice (requests 99 and 100, same brief
as 95/97) and **both shipped nothing**: the authored spec failed deterministic
validation, and ``appspec_gate.py:182`` turns that into a raise when
``enforce_app_spec``. The AppSpec authoring and validation path is byte-identical
in both modes — ``ensure_approved_app_spec`` takes neither a mode nor a policy —
so the rejections are model variance and the *consequence* is what enforcement
changes. On this brief the spec has now been accepted on 95 and 97 and rejected
on 99 and 100: **2 of 4**.

That makes a live A/B unreliable and unnecessary. Everything downstream of an
accepted spec is deterministic, and accepted specs for this exact brief are
stored, so this replays them:

    accepted AppSpec
      -> select_preview_scope            (the contract's own page set)
      -> to_architecture_seed
      -> lock_chrome_on_architecture_seed
      -> merge_architecture_enrichment   projection.py:756 — canonical routes win
      -> apply_product_kind_to_architect plan_phase.py:305
      -> ensure_internal_desk_architect  plan_phase.py:306
      -> ensure_saas_accounting_architect plan_phase.py:310
      -> apply_product_kind_to_architect plan_phase.py:315
      -> ensure_ai_feature_route         plan_phase.py:370

and reports the route set after each step, so every surviving addition is
attributed to the line that made it.

    docker compose exec api python /app/backend/scripts/measure/appspec_enforcement_replay.py 97
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_BACKEND = Path(__file__).resolve().parents[2]
if str(_REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(_REPO_BACKEND))


def _paths(routes) -> list[str]:
    out = []
    for route in routes or []:
        if isinstance(route, dict) and route.get("path"):
            out.append(str(route["path"]))
    return sorted(set(out))


def replay(request_id: int) -> dict:
    from app.application.appspec.projection import (
        merge_architecture_enrichment,
        select_preview_scope,
        to_architecture_seed,
    )
    from app.application.preview_app.ai_feature_surfaces import ensure_ai_feature_route
    from app.application.preview_app.internal_desk import ensure_internal_desk_architect
    from app.application.preview_app.product_kind import (
        apply_product_kind_to_architect,
        context_from_request,
        lock_chrome_on_architecture_seed,
        resolve_product_kind_contract,
    )
    from app.application.preview_app.saas_accounting import ensure_saas_accounting_architect
    from app.application.services.ai_features import (
        ai_features_from_request,
        business_context_from_request,
    )
    from app.core.config import settings
    from app.domain.models.app_spec import AppSpecRevision
    from app.domain.models.request import Request
    from app.infrastructure.db.session import SessionLocal

    db = SessionLocal()
    try:
        req = db.query(Request).filter(Request.id == request_id).one()
        revision = (
            db.query(AppSpecRevision)
            .filter(
                AppSpecRevision.request_id == request_id,
                AppSpecRevision.status == "accepted",
            )
            .order_by(AppSpecRevision.revision.desc())
            .first()
        )
        if revision is None:
            raise SystemExit(f"request {request_id} has no accepted AppSpec revision")
        spec_dict = json.loads(revision.app_spec_json)
        shipped = json.loads(req.generated_pages or "{}").get("preview_app") or {}

        scope = select_preview_scope(
            spec_dict,
            target_pages=settings.APPSPEC_PREVIEW_TARGET_PAGES,
            max_pages=settings.APPSPEC_PREVIEW_MAX_PAGES,
        )
        kind_contract = resolve_product_kind_contract(context_from_request(req))

        steps: list[tuple[str, list[str]]] = []
        steps.append(("AppSpec pages (whole contract)", sorted(
            {str(p.get("route")) for p in spec_dict.get("pages") or [] if p.get("route")}
        )))
        seed = to_architecture_seed(spec_dict, scope)
        steps.append(("select_preview_scope + to_architecture_seed", _paths(seed.get("routes"))))
        seed = lock_chrome_on_architecture_seed(seed, kind_contract)
        steps.append(("lock_chrome_on_architecture_seed", _paths(seed.get("routes"))))

        # The enrichment the architect would have contributed. Under enforcement
        # the merge iterates the CANONICAL routes and takes only skeleton_id and
        # section_slots from the proposal, so the shipped table is a faithful
        # stand-in for what the model proposes.
        architect = merge_architecture_enrichment(
            seed, {"routes": shipped.get("routes") or [], "roles": shipped.get("roles") or []}
        )
        steps.append(("merge_architecture_enrichment  projection.py:756", _paths(architect.get("routes"))))

        architect = apply_product_kind_to_architect(architect, kind_contract)
        steps.append(("apply_product_kind_to_architect  plan_phase.py:305", _paths(architect.get("routes"))))
        architect = ensure_internal_desk_architect(
            architect, context=context_from_request(req)
        )
        steps.append(("ensure_internal_desk_architect  plan_phase.py:306", _paths(architect.get("routes"))))
        architect = ensure_saas_accounting_architect(
            architect, context=context_from_request(req)
        )
        steps.append(("ensure_saas_accounting_architect  plan_phase.py:310", _paths(architect.get("routes"))))
        architect = apply_product_kind_to_architect(architect, kind_contract)
        steps.append(("apply_product_kind_to_architect (again)  plan_phase.py:315", _paths(architect.get("routes"))))
        ensure_ai_feature_route(
            architect,
            ai_features_from_request(req),
            context=business_context_from_request(req),
        )
        steps.append(("ensure_ai_feature_route  plan_phase.py:370", _paths(architect.get("routes"))))

        return {
            "request_id": request_id,
            "revision": revision.revision,
            "coverage_score": revision.coverage_score,
            "product_kind": kind_contract.kind,
            "steps": steps,
            "shipped_in_shadow": _paths(shipped.get("routes")),
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request_ids", nargs="+", type=int)
    args = parser.parse_args(argv)

    for request_id in args.request_ids:
        result = replay(request_id)
        print(f"\n=== request {result['request_id']} "
              f"(accepted revision {result['revision']}, coverage {result['coverage_score']}, "
              f"kind {result['product_kind']}) ===")
        previous: list[str] = []
        for label, paths in result["steps"]:
            added = [p for p in paths if p not in previous]
            removed = [p for p in previous if p not in paths]
            note = ""
            if added:
                note += f"  +{len(added)}: {', '.join(added)}"
            if removed:
                note += f"  -{len(removed)}: {', '.join(removed)}"
            print(f"  {len(paths):>3} routes  {label}{note}")
            previous = paths
        shipped = result["shipped_in_shadow"]
        enforced = previous
        print(f"\n  shipped in SHADOW: {len(shipped)} routes")
        print(f"  under ENFORCEMENT: {len(enforced)} routes")
        gone = [p for p in shipped if p not in enforced]
        kept_extra = [p for p in enforced if p not in shipped]
        print(f"  removed by enforcement ({len(gone)}): {', '.join(gone) or '-'}")
        print(f"  present only under enforcement ({len(kept_extra)}): {', '.join(kept_extra) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
