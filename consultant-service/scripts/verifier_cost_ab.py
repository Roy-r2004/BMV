"""What a verifier change costs, measured on the natural claim stream.

    python scripts/verifier_cost_ab.py --requests 104-108,119,120,128,129 \
        --baseline-template /tmp/verifier_v1.j2 \
        --out ../docs/evidence/session39/verifier-cost-ab.json

Session 38 changed the verifier (v1 -> v2) and measured it on a corpus
ENRICHED for duplication: 17 hand-labelled true claims, 5/17 confirmed
before and 12/17 after. That says the instrument got better at the thing it
was broken at. It does NOT say what the change costs, because a real run's
claim stream is not enriched — most claims a run raises are not duplication
claims at all, and a confirm only costs money when it turns the last
approvable candidate on a screen into a rejected one.

This measures the cost side, on the stream as it actually arrives. Every
image runs the inspector ONCE and both verifier arms score the SAME claims:
the inspector did not change, so re-running it per arm would only inject
its own sampling noise into a paired comparison. The arms differ solely in
which template image_defect_verifier.j2 resolves to.

The corpus is every image the pipeline actually produced for these
requests — shipped screens AND the candidates it discarded. Scoring only
shipped screens would measure a set already filtered for cleanliness and
under-report the confirm rate.

Cost model this feeds (pipeline/images.py): a confirmed defect sets
approved=False (qa.py), a screen with no approved candidate buys at most
one regeneration, and a regeneration is one image. So the money a verifier
change costs is (screens that newly lose every approvable candidate) x one
image, and the per-image confirm-rate delta measured here is the upper
bound on that rate.

Nothing here writes to the pipeline or the request ledger; it reads PNGs
already on disk and reports.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.pipeline import defect_check
from app.ui_spec import UIDemoSpec

SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(SERVICE_ROOT, "app", "prompts", "image_defect_verifier.j2")


def _cost(usage: dict | None) -> float:
    return float((usage or {}).get("cost") or 0.0)


def parse_requests(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            out.extend(range(int(lo), int(hi) + 1))
        elif part:
            out.append(int(part))
    return sorted(set(out))


def corpus(request_ids: list[int]) -> list[dict]:
    """Every image these requests produced: the shipped screen for each
    role, plus the candidates that lost. Candidates carry no spec of their
    own — they are another draw of the same screen, so they borrow the
    shipped row's spec, which is the spec they were drawn from."""
    from app.database import SessionLocal
    from app.models import GeneratedImage

    db = SessionLocal()
    try:
        rows = (
            db.query(GeneratedImage)
            .filter(GeneratedImage.request_id.in_(request_ids))
            .order_by(GeneratedImage.request_id, GeneratedImage.role_id)
            .all()
        )
        out, by_role = [], {}
        for row in rows:
            path = os.path.join(SERVICE_ROOT, row.file_path.lstrip("/"))
            if not os.path.exists(path):
                continue
            spec = (
                UIDemoSpec.model_validate(json.loads(row.spec_json)) if row.spec_json
                else UIDemoSpec.model_validate({"product": {"screen_type": row.screen_type or ""}})
            )
            by_role[(row.request_id, row.role_id)] = (spec, row.role_label)
            out.append({
                "key": f"{row.request_id}/{row.role_label}",
                "request_id": row.request_id,
                "role": row.role_id,
                "shipped": True,
                "qa_score": row.qa_score,
                "path": path,
                "spec": spec,
            })
        for rid in request_ids:
            cand_dir = os.path.join(SERVICE_ROOT, "uploads", "images", str(rid), "candidates")
            if not os.path.isdir(cand_dir):
                continue
            for name in sorted(os.listdir(cand_dir)):
                if not name.endswith(".png"):
                    continue
                role = name.rsplit("_cand", 1)[0]
                known = by_role.get((rid, role))
                if known is None:
                    print(f"  skipping {rid}/{name}: no shipped row for role {role!r}")
                    continue
                spec, label = known
                out.append({
                    "key": f"{rid}/{label}#{name.rsplit('_cand', 1)[1][:-4]}",
                    "request_id": rid,
                    "role": role,
                    "shipped": False,
                    "qa_score": None,
                    "path": os.path.join(cand_dir, name),
                    "spec": spec,
                })
        return out
    finally:
        db.close()


def inspect_all(images: list[dict]) -> tuple[list[dict], float]:
    """One inspector pass, shared by both arms."""
    spend = 0.0
    stream = []
    for i, img in enumerate(images, start=1):
        with open(img["path"], "rb") as f:
            image_bytes = f.read()
        inspected = defect_check.inspect_call(image_bytes, img["spec"])
        spend += _cost(inspected["usage"])
        claims = inspected["claims"]
        stream.append({**img, "bytes": image_bytes, "claims": claims})
        print(f'  [inspect] {i:>2}/{len(images)} {img["key"]:<26} claims={len(claims)}  ${spend:.4f}')
    return stream, spend


def verify_arm(stream: list[dict], label: str) -> tuple[dict, float]:
    """Verify every cached claim under whichever template is live now."""
    spend, verdicts = 0.0, {}
    for i, img in enumerate(stream, start=1):
        results = []
        for claim in img["claims"]:
            verdict = defect_check.verify_call(img["bytes"], claim, img["spec"])
            spend += _cost(verdict["usage"])
            results.append({
                "kind": claim["kind"],
                "what": claim.get("what", "")[:160],
                "confirmed": bool(verdict["confirmed"]),
                "reason": (verdict.get("reason") or "")[:200],
            })
        verdicts[img["key"]] = results
        n = sum(1 for r in results if r["confirmed"])
        print(f'  [{label}] {i:>2}/{len(stream)} {img["key"]:<26} confirmed={n}/{len(results)}  ${spend:.4f}')
    return verdicts, spend


def tally(verdicts: dict, stream: list[dict]) -> dict:
    """Per-claim and per-image confirm rates, and the per-image rate split
    by kind — the kind split is what says whether a change aimed at
    duplication leaked into the rest of the stream."""
    claims = confirmed = 0
    images_with = 0
    by_kind = Counter()
    for img in stream:
        rows = verdicts[img["key"]]
        claims += len(rows)
        hits = [r for r in rows if r["confirmed"]]
        confirmed += len(hits)
        if hits:
            images_with += 1
        for r in hits:
            by_kind[r["kind"]] += 1
    return {
        "images": len(stream),
        "claims": claims,
        "confirmed_claims": confirmed,
        "images_with_confirmed": images_with,
        "image_confirm_rate": round(images_with / len(stream), 4) if stream else 0.0,
        "confirmed_by_kind": dict(by_kind),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", required=True, help="e.g. 104-108,119,128")
    parser.add_argument("--baseline-template", required=True, help="the OLD verifier template")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    request_ids = parse_requests(args.requests)
    images = corpus(request_ids)
    print(f"{len(images)} images over requests {request_ids}, model={settings.DEFECT_MODEL}\n")

    stream, spend_inspect = inspect_all(images)
    raised = sum(len(s["claims"]) for s in stream)
    print(f"\n{raised} claims raised, ${spend_inspect:.4f}. Both arms score these same claims.\n")

    live = open(TEMPLATE, encoding="utf-8").read()
    baseline = open(args.baseline_template, encoding="utf-8").read()
    backup = tempfile.mktemp(suffix=".j2")
    shutil.copy(TEMPLATE, backup)
    try:
        open(TEMPLATE, "w", encoding="utf-8").write(baseline)
        v1, spend_v1 = verify_arm(stream, "v1")
        open(TEMPLATE, "w", encoding="utf-8").write(live)
        v2, spend_v2 = verify_arm(stream, "v2")
    finally:
        shutil.copy(backup, TEMPLATE)
        os.unlink(backup)

    report = {
        "requests": request_ids,
        "model": settings.DEFECT_MODEL,
        "cost_usd": round(spend_inspect + spend_v1 + spend_v2, 5),
        "inspector_cost_usd": round(spend_inspect, 5),
        "v1": {**tally(v1, stream), "cost_usd": round(spend_v1, 5)},
        "v2": {**tally(v2, stream), "cost_usd": round(spend_v2, 5)},
        "per_image": [
            {
                "key": img["key"],
                "shipped": img["shipped"],
                "qa_score": img["qa_score"],
                "claims": len(img["claims"]),
                "v1": v1[img["key"]],
                "v2": v2[img["key"]],
            }
            for img in stream
        ],
    }
    print("\nv1:", {k: v for k, v in report["v1"].items() if k != "cost_usd"})
    print("v2:", {k: v for k, v in report["v2"].items() if k != "cost_usd"})
    print(f'\ntotal ${report["cost_usd"]:.4f}')

    if args.out:
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        json.dump(report, open(args.out, "w"), indent=2)
        print(f"-> {args.out}")


if __name__ == "__main__":
    main()
