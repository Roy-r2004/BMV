"""Census 0.1 — replay every stored industry string through the REAL pick_template_id.

    docker exec -w /app/backend bmv-api python3 scripts/measure/industry_replay_census.py

QUESTION
    Roadmap 1.8 (the pack thesis) assumes industry -> pack matching works well
    enough to be worth token-length investment. Does it? For each of the 116
    stored requests with a non-empty `requests.industry` (12 distinct values),
    what does the real `pick_template_id`
    (app/application/preview_app/industry_templates/loader.py:97) return, and is
    the returned pack the right industry family?

METHOD — the real function, the real arguments, stored data only
    No model calls anywhere on this path: `gather_full_context`,
    `resolve_product_kind_contract` and `pick_template_id` are pure functions.

    * Call sites mirrored: `apply_industry_template_to_plan` (apply.py:125,
      surface="public") and `apply_ops_industry_template_to_plan` (apply.py:183,
      surface="ops"), as dispatched by `run_plan_phase`
      (pipeline/plan_phase.py:153-181): OPS kinds take the ops pick, everything
      else takes the public pick as its identity-bearing template. These are the
      calls that stamp `industry_template_id` on the plan — `template_recipe_hint`
      (apply.py:229) reuses the identical pick and is not separately replayed.
    * industry: for this corpus `ctx.industry == req.industry.strip()` exactly,
      because `resolve_industry` (pipeline/appspec_gate.py:24) returns the
      declared column verbatim when non-empty, and the corpus is non-empty-only.
    * seed: `requests.id` — the pipeline passes `ctx.request_id` (plan_phase.py
      :157/:170). Seed only breaks score ties, so same-industry rows can land on
      different packs when two packs tie.
    * surface: the pipeline branches on
      `resolve_product_kind_contract(industry_context).kind in OPS_KINDS`
      (plan_phase.py:153); this replay recomputes that same predicate from the
      same context string. (`apply_industry_template_to_plan`'s internal flip at
      apply.py:122-124 tests the same two kind names, so the dispatch here is
      equivalent.)
    * context: rebuilt exactly as plan_phase.py:61-73 builds `industry_context`,
      from stored request columns plus `gather_full_context(req, demo)[:800]`
      using the REAL `gather_full_context`. Judgment call: live code passes demo
      through `ensure_brand_brief` first (appspec_gate.py:197), which this
      replay must not touch (it can reach model paths; the key is exhausted);
      demo here is `json.loads(req.visual_demo_json)` raw. That difference can
      only matter if demo text lands inside the first 800 chars of full_context
      — the demo summary is appended after ~10 request fields plus a ~340-char
      static NOTE — so the script MEASURES it: rows where
      `gather_full_context(req, demo)[:800] != gather_full_context(req, None)
      [:800]` are counted and reported. If that count is 0, the replay context
      is provably byte-identical to the live one for every row.
    * secondary pick: for non-OPS kinds the pipeline ALSO runs the ops gap-fill
      pick (plan_phase.py:175). It sets `ops_template_id`, never the page
      identity, so it is recorded per-request in the JSON but excluded from the
      headline HIT/MISS/WRONG-FAMILY counts.

CLASSIFICATION — hand-audited mapping, printed at runtime
    With only 12 distinct values, a hand-audited industry->acceptable-packs
    table (below, and printed in the output) is more honest than a token
    heuristic that would share failure modes with the very function under test.
      HIT          pick is in the acceptable set for that industry value
      MISS         pick is None (recipe-only; the designed outcome when no pack
                   covers the industry — 'logistics' has no real pack, its only
                   adjacent family is inventory-catalog-ops)
      WRONG-FAMILY pick is a pack outside the acceptable set
    Mapping judgment calls: 'Restaurants & Food Service — ERP SaaS' accepts both
    restaurant-family and ops/SaaS-family packs (the string names both);
    'Handmade ceramics studio and online shop' accepts pottery-craft-studio and
    retail-store-home (indie-retail family covers the online-shop half);
    'florist' is literally an industry_tag of retail-store-home.

    Two refinements the output carries as data, not prose:
    * WRONG-FAMILY rows are annotated `neutral_ops_pack` when the pack's
      industry_tags name a product shape, not an industry (hand list:
      owner-kpi-dashboard, leads-crm-list, account-tracking, checkout-cart,
      member-hub). A neutral pack on an ops surface is a soft wrong (industry-
      silent voice), a different defect class from a hard wrong (another
      industry's visual identity, e.g. fitness onto pottery).
    * MISS diagnosis, computed with the loader's own constants: for each
      industry value with misses, print the industry-only pick and, per
      surface-eligible pack, the non-weak declared-token overlap with its tags
      and whether every overlapping token is shorter than
      _MIN_DISTINCTIVE_TOKEN_LEN (the lone-hit suppression gate at
      loader.py:125-129).

RED-EXIT (a rerun must never silently measure the wrong thing)
    * corpus is not exactly 116 rows / 12 distinct values
    * the distinct value set differs from the 12 baked into ACCEPTABLE
    * `load_templates()` does not load exactly the 27 packs on disk today

OUTPUT
    Human table on stdout; machine JSON written to
    scripts/measure/.out/industry-replay-census.json (the bmv-api container
    bind-mounts only backend/, so docs/evidence is unreachable in-container —
    the runner copies both artifacts to docs/evidence/session25/).

Read-only against the DB.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, func  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.application.preview_app.industry_templates.loader import (  # noqa: E402
    _MIN_DISTINCTIVE_TOKEN_LEN,
    _WEAK_INDUSTRY_TOKENS,
    _claimed_tokens,
    _is_ops_skeleton,
    _is_public_marketing_skeleton,
    _tokenize,
    load_templates,
    pick_template_id,
)
from app.application.preview_app.product_kind import (  # noqa: E402
    OPS_KINDS,
    resolve_product_kind_contract,
)
from app.application.services.page_experience import gather_full_context  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.domain.models.request import Request  # noqa: E402

EXPECTED_ROWS = 116
EXPECTED_DISTINCT = 12
EXPECTED_PACKS = 27
OUT_JSON = BACKEND / "scripts/measure/.out/industry-replay-census.json"

#: Hand-audited: every pack id whose industry family plausibly matches the
#: stored industry string. Audited against the 27 packs' industry_tags on
#: 2026-08-07; printed at runtime so the judgment is in the archive.
ACCEPTABLE: dict[str, frozenset[str]] = {
    "Fine art gallery · original oil paintings · artist portfolio (gallery/portfolio)": frozenset(
        {"art-gallery-portfolio-home"}
    ),
    "Fine art gallery · original oil paintings · artist portfolio": frozenset(
        {"art-gallery-portfolio-home"}
    ),
    "fine art gallery": frozenset({"art-gallery-portfolio-home"}),
    "Art": frozenset({"art-gallery-portfolio-home"}),
    "restaurant": frozenset({"restaurant-cafe-home", "staff-floor-ops"}),
    "hotel": frozenset({"hotel-hospitality-home"}),
    "dental clinic": frozenset({"clinic-dental-home", "clinic-front-desk-ops"}),
    "logistics": frozenset({"inventory-catalog-ops"}),
    "fitness": frozenset({"fitness-studio-home"}),
    "florist": frozenset({"retail-store-home"}),
    "Restaurants & Food Service — ERP SaaS": frozenset(
        {"staff-floor-ops", "saas-accounting", "inventory-catalog-ops", "restaurant-cafe-home"}
    ),
    "Handmade ceramics studio and online shop": frozenset(
        {"pottery-craft-studio", "retail-store-home"}
    ),
}

#: Packs whose industry_tags name a product shape rather than any industry —
#: a WRONG-FAMILY pick from this set is industry-SILENT, not industry-wrong.
#: (booking-calendar-ops and inventory-catalog-ops are excluded: their tags
#: carry faint industry hints — spa/salon, warehouse.)
NEUTRAL_OPS_PACKS = frozenset(
    {"owner-kpi-dashboard", "leads-crm-list", "account-tracking", "checkout-cart", "member-hub"}
)


def red_exit(msg: str) -> None:
    print(f"\nRED-EXIT: {msg}", file=sys.stderr)
    print("RED-EXIT: a baked assumption drifted — this census would measure the wrong thing.", file=sys.stderr)
    sys.exit(2)


def build_context(req: Request, demo: dict | None) -> str:
    """plan_phase.py:61-73, byte for byte (same parts, same order, same join)."""
    full_context = gather_full_context(req, demo)
    industry = (req.industry or "").strip()
    return " ".join(
        part
        for part in (
            industry,
            getattr(req, "business_description", None) or "",
            getattr(req, "main_problem", None) or "",
            getattr(req, "desired_outcome", None) or "",
            getattr(req, "target_customers", None) or "",
            getattr(req, "business_name", None) or "",
            full_context[:800],
        )
        if str(part).strip()
    )


def main() -> None:
    templates = load_templates()
    if len(templates) != EXPECTED_PACKS:
        red_exit(f"load_templates() returned {len(templates)} packs, expected {EXPECTED_PACKS}")

    engine = create_engine(settings.DATABASE_URL)
    with Session(engine) as db:
        rows = (
            db.query(Request)
            .filter(Request.industry.isnot(None), func.trim(Request.industry) != "")
            .order_by(Request.id)
            .all()
        )
    if len(rows) != EXPECTED_ROWS:
        red_exit(f"corpus is {len(rows)} rows, expected {EXPECTED_ROWS}")
    distinct = {(r.industry or "").strip() for r in rows}
    if len(distinct) != EXPECTED_DISTINCT:
        red_exit(f"corpus has {len(distinct)} distinct industries, expected {EXPECTED_DISTINCT}")
    if distinct != set(ACCEPTABLE):
        drift = sorted(distinct ^ set(ACCEPTABLE))
        red_exit(f"distinct industry set drifted from the hand-audited mapping: {drift}")

    per_request: list[dict] = []
    demo_in_window = 0
    for req in rows:
        industry = (req.industry or "").strip()
        demo: dict | None = None
        if req.visual_demo_json:
            try:
                parsed = json.loads(req.visual_demo_json)
                demo = parsed if isinstance(parsed, dict) else None
            except (TypeError, ValueError):
                demo = None
        # Does skipping ensure_brand_brief matter? Only if demo text reaches
        # the 800-char context window at all — measure it, never assume it.
        if gather_full_context(req, demo)[:800] != gather_full_context(req, None)[:800]:
            demo_in_window += 1
        context = build_context(req, demo)
        kind = resolve_product_kind_contract(context).kind
        surface = "ops" if kind in OPS_KINDS else "public"
        pick = pick_template_id(
            industry=industry, surface=surface, seed=int(req.id), context=context
        )
        if pick is None:
            verdict = "MISS"
        elif pick in ACCEPTABLE[industry]:
            verdict = "HIT"
        else:
            verdict = "WRONG-FAMILY"
        # The pipeline's second, non-identity-bearing pick (plan_phase.py:175).
        ops_gapfill = (
            pick_template_id(industry=industry, surface="ops", seed=int(req.id), context=context)
            if surface == "public"
            else None
        )
        per_request.append(
            {
                "id": req.id,
                "industry": industry,
                "kind": kind,
                "surface": surface,
                "pick": pick,
                "verdict": verdict,
                "neutral_ops_pack": verdict == "WRONG-FAMILY" and pick in NEUTRAL_OPS_PACKS,
                "ops_gapfill_pick": ops_gapfill,
            }
        )

    totals = Counter(r["verdict"] for r in per_request)
    by_industry: dict[str, list[dict]] = {}
    for r in per_request:
        by_industry.setdefault(r["industry"], []).append(r)

    print("Census 0.1 — stored industry strings replayed through the REAL pick_template_id")
    print(f"corpus: {len(rows)} requests with non-empty industry, {len(distinct)} distinct values")
    print("        (a SMALL corpus — 4 of 12 values are fine-art variants of one business; read rates accordingly)")
    print(f"packs loaded: {len(templates)}")
    print(f"rows where demo text reaches context[:800] (replay fidelity check, expect 0): {demo_in_window}")
    print()
    print("HAND-AUDITED MAPPING (industry -> acceptable pack families):")
    for ind in sorted(ACCEPTABLE):
        print(f"  {ind!r} -> {sorted(ACCEPTABLE[ind])}")
    print()
    header = f"{'n':>3}  {'HIT':>3}  {'MISS':>4}  {'WRONG':>5}  industry / picks"
    print(header)
    print("-" * len(header))
    per_industry_json = []
    for ind, rs in sorted(by_industry.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        c = Counter(r["verdict"] for r in rs)
        picks = Counter(str(r["pick"]) for r in rs)
        surfaces = Counter(r["surface"] for r in rs)
        picks_s = ", ".join(f"{tid}:{n}" for tid, n in picks.most_common())
        print(f"{len(rs):>3}  {c['HIT']:>3}  {c['MISS']:>4}  {c['WRONG-FAMILY']:>5}  {ind!r}")
        print(f"{'':>21}  picks: {picks_s}  surfaces: {dict(surfaces)}")
        per_industry_json.append(
            {
                "industry": ind,
                "n": len(rs),
                "hit": c["HIT"],
                "miss": c["MISS"],
                "wrong_family": c["WRONG-FAMILY"],
                "picks": dict(picks),
                "surfaces": dict(surfaces),
            }
        )
    print("-" * len(header))
    n = len(per_request)
    neutral_wrong = sum(1 for r in per_request if r["neutral_ops_pack"])
    print(
        f"TOTALS: {n} requests — HIT {totals['HIT']} ({100 * totals['HIT'] // n}%), "
        f"MISS {totals['MISS']} ({100 * totals['MISS'] // n}%), "
        f"WRONG-FAMILY {totals['WRONG-FAMILY']} ({100 * totals['WRONG-FAMILY'] // n}%)"
    )
    print(
        f"of the WRONG-FAMILY picks, {neutral_wrong} are industry-NEUTRAL product-shape ops packs "
        f"(soft wrong: industry-silent voice); {totals['WRONG-FAMILY'] - neutral_wrong} carry a "
        f"DIFFERENT industry's identity (hard wrong)"
    )
    gapfill_picks = Counter(
        str(r["ops_gapfill_pick"]) for r in per_request if r["surface"] == "public"
    )
    print(f"secondary ops gap-fill picks (public-kind rows, informational): {dict(gapfill_picks)}")

    # ---- MISS diagnosis, from the loader's own constants ----------------------
    miss_industries = sorted(
        {r["industry"] for r in per_request if r["verdict"] == "MISS"}
    )
    diagnosis: list[dict] = []
    if miss_industries:
        print("\nMISS DIAGNOSIS (loader's own constants; overlap = non-weak declared-token hits):")
    for ind in miss_industries:
        surf = Counter(
            r["surface"] for r in per_request if r["industry"] == ind
        ).most_common(1)[0][0]
        industry_only = pick_template_id(industry=ind, surface=surf, seed=0, context="")
        declared = _claimed_tokens(ind)
        overlaps: list[dict] = []
        for tid, pack in templates.items():
            sk = str(pack.get("skeleton_id") or "")
            if surf == "ops" and not _is_ops_skeleton(sk):
                continue
            if surf == "public" and not _is_public_marketing_skeleton(sk):
                continue
            tag_tokens = _tokenize(" ".join(pack.get("industry_tags") or []))
            strong = (declared & tag_tokens) - _WEAK_INDUSTRY_TOKENS
            if strong:
                gated = all(len(t) < _MIN_DISTINCTIVE_TOKEN_LEN for t in strong)
                overlaps.append({"pack": tid, "overlap": sorted(strong), "all_below_len_gate": gated})
        print(f"  {ind!r} (surface={surf}): industry-only pick = {industry_only}")
        for o in overlaps:
            gate_note = (
                f"  <-- every hit shorter than _MIN_DISTINCTIVE_TOKEN_LEN={_MIN_DISTINCTIVE_TOKEN_LEN}; "
                "lone-hit gate (loader.py:125-129) suppresses this pack"
                if o["all_below_len_gate"]
                else ""
            )
            print(f"      shares tags with {o['pack']}: {o['overlap']}{gate_note}")
        if not overlaps:
            print("      no surface-eligible pack shares a non-weak tag token — no pack covers this industry")
        diagnosis.append(
            {"industry": ind, "surface": surf, "industry_only_pick": industry_only, "tag_overlaps": overlaps}
        )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "question": "Do stored industry strings resolve to the right pack family through the real pick_template_id?",
                "date": "2026-08-07",
                "corpus": {"rows": len(rows), "distinct_industries": len(distinct)},
                "packs_loaded": len(templates),
                "demo_in_context_window_rows": demo_in_window,
                "mapping": {k: sorted(v) for k, v in ACCEPTABLE.items()},
                "totals": {
                    "hit": totals["HIT"],
                    "miss": totals["MISS"],
                    "wrong_family": totals["WRONG-FAMILY"],
                    "wrong_family_neutral_ops": neutral_wrong,
                },
                "miss_diagnosis": diagnosis,
                "per_industry": per_industry_json,
                "per_request": per_request,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nJSON written: {OUT_JSON}")


if __name__ == "__main__":
    main()
