"""Wrap-measure run 135's ops-home seed fix over the stored corpus.

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh \
      bmv-local-api -c 'python3 scripts/measure/ops_home_seed_census.py'

Two parts, both driving the REAL functions (never a paraphrase):

* Part A — regression: for each of the 47 stored kind_contexts
  (docs/evidence/preview-routes.json), resolve the contract from the stored
  context text with the real resolver and run the real
  `lock_chrome_on_architecture_seed` over that run's stored route table.
  Every stored ship record already has its home, so the run-135 fix must
  change ZERO route paths anywhere. Red exit on any drift.

* Part B — the filed defect on the filed artifact: run 135's ACCEPTED spec
  (docs/evidence/session21/run135-accepted-spec.json) is projected through
  the real `select_preview_scope` -> `to_architecture_seed`, which must
  reproduce the defect (no `/` route), and the locked seed must carry the
  ops home and pass the exact gate that refused the ship
  (`ops_kind_missing_home`). Red exit if the defect is not reproduced
  pre-lock (the census would be measuring nothing) or not fixed post-lock.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REPO = BACKEND.parent
ROUTES_JSON = REPO / "docs/evidence/preview-routes.json"
RUN135_SPEC = REPO / "docs/evidence/session21/run135-accepted-spec.json"
RUN135_REQUEST = REPO / "docs/evidence/session21/run135-request.json"

from app.application.appspec.projection import (  # noqa: E402
    select_preview_scope,
    to_architecture_seed,
)
from app.application.preview_app.product_kind import (  # noqa: E402
    context_from_request,
    lock_chrome_on_architecture_seed,
    resolve_product_kind_contract,
    validate_product_kind_chrome,
)


def part_a_stored_corpus() -> int:
    stored = json.loads(ROUTES_JSON.read_text())
    drifted = 0
    kinds: dict[str, int] = {}
    for request_id, record in sorted(stored.items(), key=lambda kv: int(kv[0])):
        context = str(record.get("kind_context") or "")
        routes = [dict(rt) for rt in record.get("routes") or []]
        if not context or not routes:
            continue
        contract = resolve_product_kind_contract(context)
        kinds[contract.kind] = kinds.get(contract.kind, 0) + 1
        before = [str(rt.get("path") or "") for rt in routes]
        locked = lock_chrome_on_architecture_seed(
            {"routes": copy.deepcopy(routes), "roles": []}, contract
        )
        after = [str(rt.get("path") or "") for rt in locked.get("routes") or []]
        if before != after:
            drifted += 1
            print(
                f"  DRIFT request {request_id} ({contract.kind}): "
                f"{before} -> {after}"
            )
    print(f"part A: {sum(kinds.values())} stored contexts replayed, kinds={kinds}")
    if drifted:
        print(f"part A RED: {drifted} stored route tables drifted — fix regresses")
        return 1
    print("part A: 0 route paths changed anywhere — no regression")
    return 0


def part_b_run135() -> int:
    spec = json.loads(RUN135_SPEC.read_text())
    request = json.loads(RUN135_REQUEST.read_text())
    context = context_from_request(SimpleNamespace(**request))
    contract = resolve_product_kind_contract(context)
    # Label assertion: the census must RESOLVE internal_ops from the real
    # request text, not assume it — red exit if the fixture does not bind.
    if contract.kind != "internal_ops":
        print(f"part B RED: run 135 resolved {contract.kind!r}, not internal_ops")
        return 1
    scope = select_preview_scope(spec)
    seed = to_architecture_seed(spec, scope)
    pre_paths = [str(rt.get("path") or "") for rt in seed.get("routes") or []]
    if "/" in pre_paths or "/home" in pre_paths:
        print(
            "part B RED: the projection already seeds a home "
            f"({pre_paths}) — this census reproduces nothing"
        )
        return 1
    locked = lock_chrome_on_architecture_seed(seed, contract)
    post_paths = [str(rt.get("path") or "") for rt in locked.get("routes") or []]
    issues = validate_product_kind_chrome(locked)
    print(f"part B: pre-lock paths {pre_paths} -> post-lock {post_paths}")
    print(f"part B: chrome gate issues on the locked seed: {issues or 'none'}")
    if "/" not in post_paths:
        print("part B RED: the locked seed still has no ops home")
        return 1
    if "ops_kind_missing_home" in issues:
        print("part B RED: the exact run-135 gate still refuses the seed")
        return 1
    home = next(rt for rt in locked["routes"] if str(rt.get("path")) == "/")
    if str(home.get("surface")) != "ops" or str(home.get("skeleton_id", "")).startswith(
        "public"
    ):
        print(f"part B RED: the seeded home is not ops chrome: {home}")
        return 1
    print(
        "part B: run 135's accepted spec now seeds its ops home "
        f"(page {home.get('page_id')}) before codegen"
    )
    return 0


def main() -> int:
    rc = part_a_stored_corpus()
    rc |= part_b_run135()
    if rc:
        print("CENSUS RED")
    else:
        print("census green: 47-corpus untouched, run 135's defect fixed at the seed")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
