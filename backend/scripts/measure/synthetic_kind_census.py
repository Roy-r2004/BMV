"""Does the classifier land the 20 synthetic briefs on the kinds they intend?

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/synthetic_kind_census.py --briefs ../docs/evidence/synthetic-briefs.json'

No database, no network, no model. `resolve_product_kind_contract` is a pure
function of one string, which is the whole reason this is answerable offline.

**Scope, stated so it cannot be overclaimed.** This measures CLASSIFICATION and
nothing else. It does not say the resulting preview is good, or fast, or that it
ships — those need funded runs. What it does say is whether the five never-selected
skeletons and the nine never-imported catalogue components are *reachable at all*,
which no measurement over the archived corpus could answer: that corpus holds 18
distinct briefs and 15 of them classify `storefront`.

The call shape is load-bearing. `context_from_request(req)` returns **one string**;
session 12 wrote `resolve_product_kind_contract(*context_from_request(req))`, which
splatted it one character per argument, matched no keyword, and silently forced
every run in a published census to `storefront`. Pass the string.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app.product_kind import (  # noqa: E402
    context_from_request,
    resolve_product_kind_contract,
)


def _explain(blob: str) -> dict[str, list[str]]:
    """Which hint strings matched, and the word each one matched *inside*.

    The classifier tests bare substrings, so the interesting part of a hit is
    not that it fired but what it fired on. Reported as `hint@word` — this is
    how "a nine-bedroom guest house is a trading desk" became legible.
    """
    from app.application.preview_app import product_kind as pk

    tables = {
        "internal": pk._INTERNAL_OPS_HINTS,
        "saas": pk._SAAS_HINTS,
        "booking": pk._BOOKING_HINTS,
        "storefront": pk._STOREFRONT_HINTS,
    }
    words = [w.strip(".,;:()") for w in blob.split()]
    out: dict[str, list[str]] = {}
    for name, hints in tables.items():
        matched = []
        for hint in hints:
            if hint in blob:
                host = next((w for w in words if hint in w and w != hint), None)
                matched.append(f"{hint}@{host}" if host else hint)
        if matched:
            out[name] = matched
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--briefs",
        default=str(Path(__file__).resolve().parents[3] / "docs/evidence/synthetic-briefs.json"),
    )
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="show which hint strings matched, and where in the text",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.briefs).read_text(encoding="utf-8"))
    briefs = payload["briefs"] if isinstance(payload, dict) else payload

    rows = []
    for brief in briefs:
        req = SimpleNamespace(
            industry=brief.get("industry"),
            business_name=brief.get("business_name"),
            business_description=brief.get("business_description"),
            description=None,
            main_problem=None,
            desired_outcome=None,
            target_customers=None,
            what_you_like=None,
        )
        blob = context_from_request(req)
        contract = resolve_product_kind_contract(blob)
        want = (brief["intended_kind"], brief["intended_subtype"])
        got = (contract.kind, contract.subtype)
        rows.append(
            {
                "id": brief["id"],
                "business_name": brief["business_name"],
                "intended": "/".join(want),
                "resolved": "/".join(got),
                "kind_ok": want[0] == got[0],
                "subtype_ok": want == got,
                "pages": [p.path for p in contract.pages],
                "hits": _explain(blob),
            }
        )

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    width = max(len(r["business_name"]) for r in rows)
    print(f"{'id':<6}{'business':<{width + 2}}{'intended':<28}{'resolved':<28}verdict")
    print("-" * (6 + width + 2 + 28 + 28 + 10))
    for row in rows:
        if row["subtype_ok"]:
            verdict = "ok"
        elif row["kind_ok"]:
            verdict = "SUBTYPE"
        else:
            verdict = "KIND"
        print(
            f"{row['id']:<6}{row['business_name']:<{width + 2}}"
            f"{row['intended']:<28}{row['resolved']:<28}{verdict}"
        )
        if args.explain:
            for table, matched in row["hits"].items():
                print(f"        {table:<11}{', '.join(matched)}")

    kind_ok = sum(1 for r in rows if r["kind_ok"])
    subtype_ok = sum(1 for r in rows if r["subtype_ok"])
    print()
    print(f"kind correct:    {kind_ok} of {len(rows)}")
    print(f"subtype correct: {subtype_ok} of {len(rows)}")

    reached = sorted({r["resolved"] for r in rows})
    print(f"distinct contracts reached: {len(reached)} — {', '.join(reached)}")

    misses = [r for r in rows if not r["subtype_ok"]]
    if misses:
        print()
        print("misclassified — findings, not tuning targets:")
        for row in misses:
            print(
                f"  {row['id']} {row['business_name']}: wanted {row['intended']}, "
                f"got {row['resolved']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
