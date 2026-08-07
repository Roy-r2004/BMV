"""Mutation-test the blueprint transport ladder (owner-ruled, session 24).

    cd backend && python scripts/cli/mutate_blueprint_transport_ladder.py

The ask-site survey's second FILED row: blueprint was the only MANDATORY
naked ask — no retry, no floor, one transport cut = dead run. Five mutations
pin: the ladder actually wired into the stage, the refusal/transport
classification boundary, the empty-cut classification, the rung being
cross-provider, and the R7 sibling warning scanning TEXT_MODEL. Restores
from an in-memory backup. Exit code 0 only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

BLUEPRINT = BACKEND / "app/application/pipelines/blueprint.py"
CONFIG = BACKEND / "app/core/config.py"

SUITES = (
    "tests/pipelines/test_blueprint_transport_ladder.py "
    "tests/pipelines/test_early_stage_ai_call_scopes.py"
)

MUTATIONS = [
    (
        BLUEPRINT,
        "the ladder is unwired from the stage (a cut kills the run again)",
        "    result = _ask_blueprint_with_transport_ladder(ai_provider, prompt)\n"
        "    req.mvp_blueprint = result",
        '    with ai_call(stage="blueprint", writer="mvp_blueprint"):\n'
        "        result = ai_provider.ask_chat(\n"
        '            settings.TEXT_MODEL, [{"role": "user", "content": prompt}]\n'
        "        )\n"
        "    req.mvp_blueprint = result",
    ),
    (
        BLUEPRINT,
        "refusal-class raises join the retry (the classification boundary drops)",
        "    if error is not None:\n"
        "        return isinstance(error, ProviderGenerationError) and error.retryable",
        "    if error is not None:\n"
        "        return isinstance(error, ProviderGenerationError)",
    ),
    (
        BLUEPRINT,
        "the empty-cut body stops classifying as transport",
        '    return not (result or "").strip()',
        "    return False",
    ),
    (
        BLUEPRINT,
        "the rung re-asks the SAME model instead of the fallback slot",
        "        (3, settings.BLUEPRINT_TRANSPORT_FALLBACK_MODEL),",
        "        (3, settings.TEXT_MODEL),",
    ),
    (
        CONFIG,
        "the blueprint warning stops scanning TEXT_MODEL",
        "    offenders = [\n"
        "        slot\n"
        "        for slot in (\"TEXT_MODEL\",)\n"
        "        if _model_provider_prefix(getattr(config, slot)) == fallback_prefix\n"
        "    ]\n"
        "    if offenders:\n"
        "        from app.infrastructure.logging import get_logger\n"
        "\n"
        "        get_logger(\"Config\").warning(\n"
        "            \"BLUEPRINT_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — \"",
        "    offenders = []\n"
        "    if offenders:\n"
        "        from app.infrastructure.logging import get_logger\n"
        "\n"
        "        get_logger(\"Config\").warning(\n"
        "            \"BLUEPRINT_TRANSPORT_FALLBACK_MODEL=%s shares provider %r with %s — \"",
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
