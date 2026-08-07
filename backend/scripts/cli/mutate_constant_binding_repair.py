"""Mutation-test R3's constant-binding coercion (owner-ruled, session 24).

    cd backend && python scripts/cli/mutate_constant_binding_repair.py

The inquire-CTA code alone discarded two authored pages to scaffold; the
image-pool pair discarded a HomePage with no retry — constants coerced now by
`repair_constant_binding_defects`, gated (primary defect required, strict
codes refused) and backstopped (heal only on a re-validated-clean page). Four
mutations pin the load-bearing defenses: the enforce-chain wiring (which also
feeds the slot_fill judge's predicate), the re-validate backstop, the CTA
constant itself, and the region scoping that keeps legitimate hero bindings
untouched. (Gate-set mutations are deliberately absent: the backstop provably
absorbs them, so a sweep entry would be theater — the boundary behavior is
pinned by the mixed/derived-alone tests instead.) Restores from an in-memory backup. Exit code 0 only when
every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

REPAIR = BACKEND / "app/application/preview_app/catalogue_contract/repair.py"

SUITES = "tests/preview_app/test_constant_binding_repair.py"

MUTATIONS = [
    (
        REPAIR,
        "the heal is unwired from the enforce chain (pages die for a constant again)",
        "    repaired, healed = repair_constant_binding_defects(content, route)\n"
        "    if healed:\n"
        "        content = lock_recipe_section_order(repaired, route)\n"
        "        if not blocking_contract_errors(validate_catalogue_page_content(content, route)):\n"
        "            return content, False\n"
        "    repaired, healed = repair_missing_catalogue_slots(",
        "    repaired, healed = repair_missing_catalogue_slots(",
    ),
    (
        REPAIR,
        "the re-validate backstop drops (a partial fix ships as healed)",
        "    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):\n"
        "        return content, False\n"
        "    logger.info(\n"
        "        \"Catalogue page healed by constant-binding repair route=%s\",",
        "    logger.info(\n"
        "        \"Catalogue page healed by constant-binding repair route=%s\",",
    ),
    (
        REPAIR,
        "the CTA constant drifts (heals to the wrong anchor)",
        "        repaired = _INQUIRE_NEAR_MISS_HREF_RE.sub(\n"
        "            \"href: '#inquire'\", repaired, count=1\n"
        "        )",
        "        repaired = _INQUIRE_NEAR_MISS_HREF_RE.sub(\n"
        "            \"href: '#contact'\", repaired, count=1\n"
        "        )",
    ),
    (
        REPAIR,
        "the image rebind loses its region scoping (legit hero bindings rewritten)",
        "    return _IMAGE_POOL_REGION_RE.sub(_rebind_region, content)",
        "    return re.sub(\n"
        "        r\"images\\.(card|hero)(\\d*)\\b\",\n"
        "        lambda m: \"images.\"\n"
        "        + _LIFESTYLE_TO_ITEM.get(m.group(1) + m.group(2), \"item1\"),\n"
        "        content,\n"
        "    )",
    ),
]

REPO = BACKEND.parent
PYTEST = (
    f'docker run --rm -v "{REPO}:/repo" -w /repo/backend '
    "-e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api "
    f"-c 'pip install -q pytest 2>/dev/null; python -m pytest {SUITES} "
    "-q --no-header -p no:cacheprovider'"
)


def run_suite() -> tuple[bool, str, list[str]]:
    proc = subprocess.run(
        PYTEST, shell=True, capture_output=True, text=True, timeout=900, cwd=REPO
    )
    out = proc.stdout + proc.stderr
    summary = ""
    for line in reversed(out.strip().splitlines()):
        if "passed" in line or "failed" in line or "error" in line.lower():
            summary = line.strip()
            break
    failed = sorted(
        {
            line.split("::")[-1].split()[0]
            for line in out.splitlines()
            if line.startswith("FAILED")
        }
    )
    green = "passed" in summary and not _FAILED_RE.search(summary)
    return green, summary, failed


def main() -> int:
    paths = {path for path, *_ in MUTATIONS}
    originals = {path: path.read_text() for path in paths}

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for path, label, old, new in MUTATIONS:
            original = originals[path]
            if original.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {original.count(old)} times "
                    "— NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"{label} (anchor drift)")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                print(f"!! {label}: replacement is a no-op — NOT APPLIED")
                survivors.append(f"{label} (no-op)")
                continue

            path.write_text(mutated)
            try:
                caught_green, caught_summary, failed = run_suite()
            finally:
                path.write_text(original)

            if caught_green:
                print(f"SURVIVED  {label}  [{caught_summary}]")
                survivors.append(label)
            else:
                names = ", ".join(failed[:3]) or caught_summary
                print(f"caught    {label}  <- {names}")
    finally:
        for path, text in originals.items():
            path.write_text(text)

    print()
    if survivors:
        print(f"{len(survivors)} SURVIVED of {len(MUTATIONS)}:")
        for entry in survivors:
            print(f"  - {entry}")
        return 1
    print(f"all {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
