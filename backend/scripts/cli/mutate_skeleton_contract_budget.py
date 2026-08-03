"""Mutation-test the skeleton/slot contract prompt budget.

    cd backend && python scripts/cli/mutate_skeleton_contract_budget.py

Retires the xfail that pinned a 4,000-char bound with no derivation, and closes
the defect that bound was hiding: above 5,000 chars `bounded_json` stops being a
bound and starts clipping every list to 12 items, so `public-catalog` shipped a
codegen prompt whose allow-list was missing 18 of its 30 components — including
the `MarketingHero` and `ProductShowcase` that the same contract had just
assigned to that page's hero and showcase slots.

That is this repo's recurring defect shape: a guard whose success is
indistinguishable from its failure. Nothing logged, nothing raised, and the
prompt still looked like a well-formed contract. So the tests get mutated.

Unlike the other drivers here this one uses **`docker run`, not
`docker compose exec`**. The compose `api` service mounts only `backend/`, and a
login shell there drops `/opt/node/bin` so `tsx_parse_error` fails open — both
turn into failures that read as application defects. See HANDOFF.md.

Exit code is 0 only when every mutation was caught. Restores from an in-memory
backup, never `git checkout`, which has eaten uncommitted work in this repo.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: `"failed" in summary` is wrong: "2 xfailed" contains it, so a green suite
#: reads as red and the sweep refuses to start. Both existing drivers shipped
#: with that bug. Count instead.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

CATALOGUE = BACKEND / "app/application/ui_catalogue.py"
ATTACH = BACKEND / "app/application/preview_app/pipeline/architect_normalize.py"

SUITES = (
    "tests/preview_app/test_catalogue_contract.py "
    "tests/preview_app/test_propshape_contract.py "
    "tests/preview_app/test_task4_prompt_contract.py "
    "tests/preview_app/test_ui_catalogue_drift.py"
)

MUTATIONS: list[tuple[str, Path, str, str]] = [
    # --- the fitting itself --------------------------------------------------
    (
        "no fitting at all — prompts get the validator's full contract",
        CATALOGUE,
        "    contract = compact_skeleton_contract(skeleton_id, section_slots)\n"
        "    if _serialized_len(contract) <= max_chars:\n"
        "        return contract",
        "    contract = compact_skeleton_contract(skeleton_id, section_slots)\n"
        "    if True:\n"
        "        return contract",
    ),
    (
        "drops prop_shapes but never components (the half-fix)",
        CATALOGUE,
        "    components = list(without_shapes.get(\"components\") or [])",
        "    return without_shapes\n"
        "    components = list(without_shapes.get(\"components\") or [])",
    ),
    (
        "budget raised past the caller bound instead of the contract fitted",
        CATALOGUE,
        "_CONTRACT_PROMPT_BUDGET = 4900",
        "_CONTRACT_PROMPT_BUDGET = 6000",
    ),
    # --- what the fitting may not sacrifice ---------------------------------
    (
        "nothing is protected — slot components droppable like any other",
        CATALOGUE,
        "    protected = {\n        name\n        for name in (",
        "    protected = set()\n    _unused = {\n        name\n        for name in (",
    ),
    # --- the priority order the tail-drop depends on ------------------------
    (
        "slot components appended after the alphabetical bulk (the old order)",
        CATALOGUE,
        "            for name in (shell_component, *navigation_components, *slot_components.values())",
        "            for name in (shell_component, *navigation_components)",
    ),
    # --- the validator's view stays complete --------------------------------
    (
        "validator's allow-list shrunk to shell/nav/slot defaults",
        CATALOGUE,
        "    for name in sorted(allowed):\n        if name and name not in selected_names:\n            selected_names.append(name)",
        "    for name in sorted(allowed):\n        if False:\n            selected_names.append(name)",
    ),
    # --- the attach site, which had no bound at all -------------------------
    (
        "attach site back to the unfitted contract",
        ATTACH,
        "            skeleton_contract = skeleton_contract_for_prompt(skeleton_id, section_slots)",
        "            from app.application.ui_catalogue import compact_skeleton_contract\n"
        "            skeleton_contract = compact_skeleton_contract(skeleton_id, section_slots)",
    ),
    (
        "attach site back to spaced separators (~350 uncounted chars a file)",
        ATTACH,
        '                separators=(",", ":"),\n            )\n            app_spec_contract',
        '                separators=(", ", ": "),\n            )\n            app_spec_contract',
    ),
]

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
    # Read the SUMMARY LINE, never the exit code.
    green = "passed" in summary and not _FAILED_RE.search(summary)
    return green, summary, failed


def main() -> int:
    originals = {path: path.read_text() for path in {CATALOGUE, ATTACH}}

    green, summary, _ = run_suite()
    print(f"baseline: {summary}")
    if not green:
        print("BASELINE IS RED — fix before mutating")
        return 1

    survivors: list[str] = []
    try:
        for label, path, old, new in MUTATIONS:
            source = originals[path]
            if source.count(old) != 1:
                print(
                    f"!! {label}: anchor matched {source.count(old)} times in "
                    f"{path.name} — NOT APPLIED, this mutation tests nothing"
                )
                survivors.append(f"{label} (anchor drift)")
                continue
            path.write_text(source.replace(old, new, 1))
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            path.write_text(source)
    finally:
        for path, source in originals.items():
            path.write_text(source)
            if path.read_text() != source:
                print(f"RESTORE FAILED for {path}")
                return 2
        print("\nsources restored and verified byte-identical")

    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
