"""How many verdicts change if the classifier matched on word boundaries?

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api \
      -c 'python3 scripts/measure/boundary_variant_census.py'

No database, no network, no model. Runs the CURRENT resolver and two boundary
variants over the 20 synthetic briefs (docs/evidence/synthetic-briefs.json) and
the 47 stored kind_contexts (docs/evidence/preview-routes.json), and reports how
many verdicts change. It is a measurement for an owner ruling — it fixes nothing.

**The variant wraps the real function; it does not rewrite it.** Every
containment test in `classify_product_kind` and `resolve_product_kind_contract`
runs against the string `_blob()` returns, so patching `_blob` to return a str
subclass whose `__contains__` matches on boundaries changes the matching
primitive and nothing else. A re-implementation of the classifier here would
measure the re-implementation (blind spot 8).

**Two variants, because the hint table is not boundary-clean.** It holds
deliberate prefix stems — "reconcil", "bookkeep" — that a boundary on BOTH sides
kills silently ("reconcil" no longer matches "reconciliation"):

  word    boundary on both sides of the hint
  prefix  boundary on the left only — kills "oms"@Rooms and "spa"@workspace,
          keeps the stems

Hints carrying their own delimiter ("hr ") keep it: a boundary lookaround is
applied only where the hint's own edge is a word character.

**The prefix variant was ADOPTED (owner ruling, session 15)** — `_blob` now
returns a str subclass with exactly these semantics. The census's job since:
prove the shipped classifier still equals the measured prefix variant (any
per-row drift is a red exit) and keep the word variant measurable against it.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.application.preview_app import product_kind as pk  # noqa: E402
from app.application.preview_app.product_kind import (  # noqa: E402
    context_from_request,
    resolve_product_kind_contract,
)

MODES = ("current", "word", "prefix")


def _boundary_search(blob: str, hint: str, mode: str) -> bool:
    hint = str(hint)
    if not hint:
        return False
    lead = r"(?<!\w)" if hint[0].isalnum() else ""
    trail = (r"(?!\w)" if hint[-1].isalnum() else "") if mode == "word" else ""
    return re.search(f"{lead}{re.escape(hint)}{trail}", blob) is not None


class _WordBlob(str):
    mode = "word"

    def __contains__(self, item: object) -> bool:  # type: ignore[override]
        return _boundary_search(str(self), str(item), self.mode)


class _PrefixBlob(_WordBlob):
    mode = "prefix"


@contextlib.contextmanager
def _patched(mode: str):
    if mode == "current":
        yield
        return
    real = pk._blob
    cls = _WordBlob if mode == "word" else _PrefixBlob
    pk._blob = lambda *parts: cls(real(*parts))
    try:
        yield
    finally:
        pk._blob = real


def _resolve(blob: str, mode: str) -> tuple[str, str]:
    with _patched(mode):
        contract = resolve_product_kind_contract(blob)
    return contract.kind, contract.subtype


def _matched_hints(blob: str, mode: str) -> dict[str, list[str]]:
    """Which hints fire per table under a mode — for explaining changed rows."""
    tables = {
        "internal": pk._INTERNAL_OPS_HINTS,
        "saas": pk._SAAS_HINTS,
        "booking": pk._BOOKING_HINTS,
        "storefront": pk._STOREFRONT_HINTS,
    }
    out: dict[str, list[str]] = {}
    for name, hints in tables.items():
        if mode == "current":
            matched = [h for h in hints if h in blob]
        else:
            matched = [h for h in hints if _boundary_search(blob, h, mode)]
        if matched:
            out[name] = matched
    return out


def _self_check() -> None:
    """The patch must demonstrably reach the classifier before a number prints.

    A census whose wrap silently fails re-measures the current behaviour and
    reports zero changes — the most dangerous possible output.
    """
    # Containment semantics of the variant matcher.
    assert not _boundary_search("nine rooms", "oms", "word")
    assert not _boundary_search("nine rooms", "oms", "prefix")
    assert not _boundary_search("our workspace and dispatch", "spa", "word")
    assert not _boundary_search("our workspace and dispatch", "spa", "prefix")
    assert _boundary_search("a day spa retreat", "spa", "word")
    assert _boundary_search("bank reconciliation", "reconcil", "prefix")
    assert not _boundary_search("bank reconciliation", "reconcil", "word")
    assert _boundary_search("our hr team", "hr ", "word"), "hint-borne delimiter lost"
    # The SHIPPED classifier carries the prefix variant since the session-15
    # ruling: the blob itself must refuse a mid-word hint and keep a stem.
    assert "oms" not in pk._blob("institutional nine rooms available"), (
        "shipped _blob regressed to bare substring matching"
    )
    assert "reconcil" in pk._blob("bank reconciliation"), (
        "shipped _blob kills prefix stems — that is the word variant, not the ruling"
    )
    assert "hr " in pk._blob("our hr team"), "hint-borne delimiter lost in shipped _blob"
    # The word patch actually reaches the classifier: a stem-carried verdict
    # must flip when both sides are bounded (the old fixture rode "oms"@rooms,
    # which the adopted baseline no longer matches).
    probe = "bank reconciliation bookkeeping"
    assert _resolve(probe, "current")[0] == "saas_workspace", (
        "self-check fixture no longer reaches the stem-carried branch; "
        "re-anchor it before trusting any number below"
    )
    got = _resolve(probe, "word")[0]
    assert got != "saas_workspace", f"patch did not reach the classifier (word: {got})"


def main() -> int:
    parser = argparse.ArgumentParser()
    evidence = Path(__file__).resolve().parents[3] / "docs/evidence"
    parser.add_argument("--briefs", default=str(evidence / "synthetic-briefs.json"))
    parser.add_argument("--routes", default=str(evidence / "preview-routes.json"))
    parser.add_argument("--json", action="store_true", help="emit the rows as JSON")
    args = parser.parse_args()

    _self_check()

    # --- the 20 synthetic briefs -------------------------------------------
    payload = json.loads(Path(args.briefs).read_text(encoding="utf-8"))
    briefs = payload["briefs"] if isinstance(payload, dict) else payload
    synth_rows = []
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
        row = {
            "id": brief["id"],
            "business_name": brief["business_name"],
            "intended": f"{brief['intended_kind']}/{brief['intended_subtype']}",
        }
        for mode in MODES:
            row[mode] = "/".join(_resolve(blob, mode))
        row["blob"] = blob
        synth_rows.append(row)

    # --- the 47 stored kind_contexts ---------------------------------------
    stored = json.loads(Path(args.routes).read_text(encoding="utf-8"))
    stored_rows = []
    for run_id, entry in sorted(stored.items(), key=lambda kv: int(kv[0])):
        blob = str(entry.get("kind_context") or "")
        row = {"id": int(run_id), "business_name": entry.get("business_name")}
        for mode in MODES:
            row[mode] = "/".join(_resolve(blob, mode))
        row["blob"] = blob
        stored_rows.append(row)

    # Since the session-15 adoption the prefix column IS the shipped behaviour;
    # any per-row drift means the classifier diverged from what was measured.
    drift = [
        (label, r)
        for label, rows in (("synthetic", synth_rows), ("stored", stored_rows))
        for r in rows
        if r["prefix"] != r["current"]
    ]
    if drift:
        for label, r in drift:
            print(
                f"PREFIX DRIFT [{label}] {r['id']} {r['business_name']}: "
                f"current {r['current']} != prefix {r['prefix']}"
            )
        print("the shipped classifier no longer implements the measured prefix variant")
        return 1

    if args.json:
        strip = lambda rows: [{k: v for k, v in r.items() if k != "blob"} for r in rows]
        print(json.dumps({"synthetic": strip(synth_rows), "stored": strip(stored_rows)}, indent=2))
        return 0

    def _report(rows: list[dict], label: str, intended: bool) -> None:
        width = max(len(str(r["business_name"])) for r in rows)
        print(f"== {label} ==")
        head = f"{'id':<5}{'business':<{width + 2}}"
        if intended:
            head += f"{'intended':<26}"
        print(head + f"{'current':<26}{'word':<26}{'prefix':<26}")
        for r in rows:
            line = f"{r['id']:<5}{str(r['business_name']):<{width + 2}}"
            if intended:
                line += f"{r['intended']:<26}"
            line += f"{r['current']:<26}{r['word']:<26}{r['prefix']:<26}"
            flags = [m for m in ("word", "prefix") if r[m] != r["current"]]
            print(line + ("  <- " + ",".join(flags) if flags else ""))
        print()
        for mode in ("word", "prefix"):
            kind_changed = [
                r for r in rows
                if r[mode].split("/")[0] != r["current"].split("/")[0]
            ]
            subtype_only = [
                r for r in rows
                if r[mode] != r["current"]
                and r[mode].split("/")[0] == r["current"].split("/")[0]
            ]
            print(
                f"{label} / {mode}: kind changes {len(kind_changed)} of {len(rows)}, "
                f"subtype-only changes {len(subtype_only)}"
            )
            for r in kind_changed:
                print(f"    {r['id']} {r['business_name']}: {r['current']} -> {r[mode]}")
                before = _matched_hints(r["blob"], "current")
                after = _matched_hints(r["blob"], mode)
                for table in sorted(set(before) | set(after)):
                    lost = sorted(set(before.get(table, [])) - set(after.get(table, [])))
                    if lost:
                        print(f"        {table}: loses {', '.join(lost)}")
        if intended:
            for mode in MODES:
                ok = sum(1 for r in rows if r[mode].split("/")[0] == r["intended"].split("/")[0])
                both = sum(1 for r in rows if r[mode] == r["intended"])
                print(f"{label} / {mode}: intended kind {ok} of {len(rows)}, kind+subtype {both}")
        print()

    _report(synth_rows, "20 synthetic briefs", intended=True)
    _report(stored_rows, "47 stored kind_contexts", intended=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
