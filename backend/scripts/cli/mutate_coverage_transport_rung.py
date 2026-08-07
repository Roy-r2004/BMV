"""Mutation-test R1 at coverage_review: the correlated-transport rung.

    cd backend && python scripts/cli/mutate_coverage_transport_rung.py

The last appspec ask site without a cross-provider rung. The design mirrors
the authoring ladder: classify first (AppSpecCoverageTransportError vs
malformation), the existing varied attempt-2 retry is the bounded same-model
re-ask, and ONLY two cuts in a row (correlated weather) buy ONE ask on
`APPSPEC_TRANSPORT_FALLBACK_MODEL` at telemetry attempt 3 — malformation
never reaches the rung, a mixed sequence fails closed, and the terminal
reasons stay honest (`coverage_review_transport` vs
`coverage_review_malformed`). Seven mutations pin: both transport raise
sites keeping their class, the rung firing at all, the correlation
requirement, the fallback model actually used, the attempt actually bumped,
and the transport reason kept distinct. Restores from an in-memory backup.
Exit code 0 only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

COVERAGE = BACKEND / "app/application/appspec/coverage.py"
GENERATION = BACKEND / "app/application/appspec/generation.py"

SUITES = "tests/appspec/test_coverage_retry_variation.py"

MUTATIONS = [
    (
        COVERAGE,
        "the stream-cut raise loses its transport class (finish=error site)",
        "    if str(provider_diag.get(\"finish_reason\") or \"\").lower() == \"error\":\n"
        "        raise AppSpecCoverageTransportError(",
        "    if str(provider_diag.get(\"finish_reason\") or \"\").lower() == \"error\":\n"
        "        raise AppSpecCoverageError(",
    ),
    (
        COVERAGE,
        "the in-transit raise loses its transport class (retryable site)",
        "            raise AppSpecCoverageTransportError(\n"
        "                f\"AppSpec coverage review stream failed in transit: {exc}\"\n"
        "            ) from exc",
        "            raise AppSpecCoverageError(\n"
        "                f\"AppSpec coverage review stream failed in transit: {exc}\"\n"
        "            ) from exc",
    ),
    (
        GENERATION,
        "the rung is unwired (a second cut fails closed with no fallback ask)",
        "                except AppSpecCoverageTransportError as second_cut:\n"
        "                    if not first_was_transport:\n"
        "                        return _fallback(\"coverage_review_transport\")",
        "                except AppSpecCoverageTransportError as second_cut:\n"
        "                    if True:\n"
        "                        return _fallback(\"coverage_review_transport\")",
    ),
    (
        GENERATION,
        "the correlation requirement drops (a mixed sequence reaches the rung)",
        "                    if not first_was_transport:\n"
        "                        return _fallback(\"coverage_review_transport\")",
        "                    if False:\n"
        "                        return _fallback(\"coverage_review_transport\")",
    ),
    (
        GENERATION,
        "the rung re-asks the SAME model instead of the fallback slot",
        "                            model=settings.APPSPEC_TRANSPORT_FALLBACK_MODEL,\n"
        "                            attempt=3,",
        "                            model=runtime_policy.coverage_model,\n"
        "                            attempt=3,",
    ),
    (
        GENERATION,
        "the rung's telemetry attempt is not bumped",
        "                            model=settings.APPSPEC_TRANSPORT_FALLBACK_MODEL,\n"
        "                            attempt=3,\n"
        "                            corrective_instruction=coverage_retry_instruction(\n"
        "                                second_cut\n"
        "                            ),",
        "                            model=settings.APPSPEC_TRANSPORT_FALLBACK_MODEL,\n"
        "                            attempt=2,\n"
        "                            corrective_instruction=coverage_retry_instruction(\n"
        "                                second_cut\n"
        "                            ),",
    ),
    (
        GENERATION,
        "the transport reason collapses into the malformed reason",
        "                    except AppSpecCoverageError:\n"
        "                        return _fallback(\"coverage_review_transport\")",
        "                    except AppSpecCoverageError:\n"
        "                        return _fallback(\"coverage_review_malformed\")",
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
