"""Mutation-test R7: the same-provider transport-fallback warning.

    cd backend && python scripts/cli/mutate_transport_fallback_provider_warning.py

The transport fallback's value is provider independence (runs 136/137: the
storm cuts primary and re-ask alike). The invariant was a `.env` comment;
`assert_safe_runtime_configuration` now WARNS — never crashes — when
`APPSPEC_TRANSPORT_FALLBACK_MODEL` shares a provider prefix with
`APPSPEC_MODEL`/`APPSPEC_REPAIR_MODEL`/`APPSPEC_COVERAGE_MODEL` (the coverage
slot joined when its rung landed, session 24). Eight mutations pin: the prefix
parse (no-slash ids stay unclassifiable, matching is case-insensitive), all
three primary slots scanned, the equality direction, the offenders actually
returned, the warning being a warning (not a crash), and startup actually
calling the check. Anchors re-scoped to the appspec warn function after the
preview sibling landed (session 22) made the shared lines ambiguous.
Restores from an in-memory backup. Exit code 0 only when every mutation is
caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

CONFIG = BACKEND / "app/core/config.py"

SUITES = "tests/appspec/test_transport_fallback_provider_warning.py"

MUTATIONS = [
    (
        CONFIG,
        "a no-slash model id becomes classifiable: bare names start matching",
        "    head, sep, _ = (model or \"\").strip().partition(\"/\")\n"
        "    if not sep or not head:\n"
        "        return None",
        "    head, sep, _ = (model or \"\").strip().partition(\"/\")\n"
        "    if not sep or not head:\n"
        "        return (model or \"\").strip().lower() or None",
    ),
    (
        CONFIG,
        "the prefix match turns case-sensitive",
        "    return head.lower()",
        "    return head",
    ),
    (
        CONFIG,
        "the repair slot drops out of the scan",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_REPAIR_MODEL\", \"APPSPEC_COVERAGE_MODEL\")",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_COVERAGE_MODEL\")",
    ),
    (
        CONFIG,
        "the coverage slot drops out of the scan (session 24's rider unpinned)",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_REPAIR_MODEL\", \"APPSPEC_COVERAGE_MODEL\")",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_REPAIR_MODEL\")",
    ),
    (
        CONFIG,
        "the provider comparison inverts: cross-provider configs warn",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_REPAIR_MODEL\", \"APPSPEC_COVERAGE_MODEL\")\n"
        "        if _model_provider_prefix(getattr(config, slot)) == fallback_prefix",
        "        for slot in (\"APPSPEC_MODEL\", \"APPSPEC_REPAIR_MODEL\", \"APPSPEC_COVERAGE_MODEL\")\n"
        "        if _model_provider_prefix(getattr(config, slot)) != fallback_prefix",
    ),
    (
        CONFIG,
        "the warning becomes a startup crash",
        "    if offenders:\n"
        "        from app.infrastructure.logging import get_logger\n"
        "\n"
        "        get_logger(\"Config\").warning(\n"
        "            \"APPSPEC_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — \"",
        "    if offenders:\n"
        "        raise RuntimeConfigurationError(\"same_provider_transport_fallback\")\n"
        "        from app.infrastructure.logging import get_logger\n"
        "\n"
        "        get_logger(\"Config\").warning(\n"
        "            \"APPSPEC_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — \"",
    ),
    (
        CONFIG,
        "the offender list is swallowed",
        "            config.APPSPEC_TRANSPORT_FALLBACK_MODEL,\n"
        "            fallback_prefix,\n"
        "            \" and \".join(offenders),\n"
        "        )\n"
        "    return offenders",
        "            config.APPSPEC_TRANSPORT_FALLBACK_MODEL,\n"
        "            fallback_prefix,\n"
        "            \" and \".join(offenders),\n"
        "        )\n"
        "    return []",
    ),
    (
        CONFIG,
        "startup never calls the check",
        "        raise RuntimeConfigurationError(code)\n"
        "    warn_same_provider_transport_fallback(config)",
        "        raise RuntimeConfigurationError(code)",
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
