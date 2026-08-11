"""Mutation-test the repair collapse guard (owner-ruled, session 24).

    cd backend && python scripts/cli/mutate_repair_collapse_guard.py

Request 143 rev 1: ai_appspec_repair replaced a 6-page spec with a 503-byte
fragment and three revisions died reconciling nothing. The guard rejects a
repair output that empties `pages`/`states` its parent populated — parent
kept, fail closed, distinct reason. Six mutations pin: the predicate firing
at all, each of the three wired AI-repair sites (validation, coverage,
schema), the populated-shrink boundary (repairs legitimately drop faulted
objects), and the reason staying distinct. Restores from an in-memory
backup. Exit code 0 only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATION = BACKEND / "app/application/appspec/generation.py"

SUITES = "tests/appspec/test_repair_collapse_guard.py"

MUTATIONS = [
    (
        GENERATION,
        "the predicate never fires (fragments spiral again)",
        "    for key in (\"pages\", \"states\"):\n"
        "        parent_items = parent_payload.get(key)\n"
        "        if (\n"
        "            isinstance(parent_items, (list, tuple))\n"
        "            and parent_items\n"
        "            and not child_payload.get(key)\n"
        "        ):\n"
        "            return True\n"
        "    return False",
        "    return False",
    ),
    (
        GENERATION,
        "the guard over-fires on any shrink (legitimate repairs punished)",
        "            isinstance(parent_items, (list, tuple))\n"
        "            and parent_items\n"
        "            and not child_payload.get(key)",
        "            isinstance(parent_items, (list, tuple))\n"
        "            and parent_items\n"
        "            and len(child_payload.get(key) or []) < len(parent_items)",
    ),
    (
        GENERATION,
        "the validation-repair site is unwired",
        "                    if _repair_collapsed_spec(\n"
        "                        parent_payload_before_repair,\n"
        "                        repaired_candidate.payload if repaired_candidate else None,\n"
        "                    ):\n"
        "                        log.info(\n"
        "                            \"AppSpec repair collapsed the spec for request %s \"\n"
        "                            \"(pages/states emptied) — keeping the parent and \"\n"
        "                            \"failing closed\",\n"
        "                            request_id,\n"
        "                        )\n"
        "                        return _fallback(\"repair_collapsed_parent_spec\")\n"
        "                    candidate = repaired_candidate",
        "                    candidate = repaired_candidate",
    ),
    (
        GENERATION,
        "the coverage-repair site is unwired",
        "                if _repair_collapsed_spec(\n"
        "                    parent_payload_before_repair,\n"
        "                    repaired_candidate.payload if repaired_candidate else None,\n"
        "                ):\n"
        "                    log.info(\n"
        "                        \"AppSpec coverage repair collapsed the spec for \"\n"
        "                        \"request %s (pages/states emptied) — keeping the \"\n"
        "                        \"parent and failing closed\",\n"
        "                        request_id,\n"
        "                    )\n"
        "                    return _fallback(\"repair_collapsed_parent_spec\")\n"
        "                candidate = repaired_candidate",
        "                candidate = repaired_candidate",
    ),
    (
        GENERATION,
        "the schema-repair site is unwired",
        "                    repaired_candidate = _sanitize_tracked(repaired, source_snapshot)\n"
        "                    if _repair_collapsed_spec(\n"
        "                        candidate.payload,\n"
        "                        repaired_candidate.payload if repaired_candidate else None,\n"
        "                    ):\n"
        "                        log.info(\n"
        "                            \"AppSpec schema repair collapsed the spec for \"\n"
        "                            \"request %s (pages/states emptied) — keeping the \"\n"
        "                            \"parent and failing closed\",\n"
        "                            request_id,\n"
        "                        )\n"
        "                        return _fallback(\"repair_collapsed_parent_spec\")\n"
        "                    candidate = repaired_candidate",
        "                    repaired_candidate = _sanitize_tracked(repaired, source_snapshot)\n"
        "                    candidate = repaired_candidate",
    ),
    (
        GENERATION,
        "the collapse hides behind the generic terminal reason",
        "                        return _fallback(\"repair_collapsed_parent_spec\")\n"
        "                    candidate = repaired_candidate\n"
        "                    _record_lineage(",
        "                        return _fallback(\"deterministic_validation_failed\")\n"
        "                    candidate = repaired_candidate\n"
        "                    _record_lineage(",
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
