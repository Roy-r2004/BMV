"""Mutation-test R6: self-describing early-stage rows + the errored-call refund.

    cd backend && python scripts/cli/mutate_r6_telemetry_budget.py

Telemetry census (requests >= 129): analyze, blueprint and demo were the only
stages whose EVERY row carried the `record_usage` fallback signature
(writer=NULL, attempt=1, stage=purpose) — no `ai_call` scope existed at their
ask sites. And an errored $0 appspec call (143's error-cut authoring attempt)
permanently consumed a unit of `APPSPEC_MAX_CALLS` — spend-before-ask with no
refund. Six mutations pin both halves: each stage's scope unwired, the refund
dropped, the refund firing on success too (the ceiling stops bounding), and
the deadline-tally half of the refund dropped. Restores from an in-memory
backup. Exit code 0 only when every mutation is caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

GENERATION = BACKEND / "app/application/appspec/generation.py"
DEADLINE = BACKEND / "app/application/services/request_deadline.py"
REFERENCE = BACKEND / "app/application/pipelines/reference_analysis.py"
BLUEPRINT = BACKEND / "app/application/pipelines/blueprint.py"
VISUAL_DEMO = BACKEND / "app/application/pipelines/visual_demo.py"

SUITES = (
    "tests/pipelines/test_early_stage_ai_call_scopes.py "
    "tests/appspec/test_appspec_request_budget.py"
)

MUTATIONS = [
    (
        REFERENCE,
        "the analyze scope is unwired (fallback rows return)",
        '    with ai_call(stage="analyze", writer="reference_url_analysis"):\n'
        "        result = ai_provider.ask_chat(\n"
        '            settings.TEXT_MODEL, [{"role": "user", "content": prompt}]\n'
        "        )",
        '    result = ai_provider.ask_chat(\n'
        '        settings.TEXT_MODEL, [{"role": "user", "content": prompt}]\n'
        "    )",
    ),
    (
        BLUEPRINT,
        "the blueprint scope is unwired",
        '        with ai_call(stage="blueprint", writer="mvp_blueprint", attempt=attempt):\n'
        "            try:\n"
        "                result = ai_provider.ask_chat(model, messages)\n"
        "            except Exception as exc:  # classified below; never silently eaten\n"
        "                error = exc",
        "        try:\n"
        "            result = ai_provider.ask_chat(model, messages)\n"
        "        except Exception as exc:  # classified below; never silently eaten\n"
        "            error = exc",
    ),
    (
        VISUAL_DEMO,
        "the demo scope is unwired",
        '        with ai_call(stage="demo", writer="visual_demo"):\n'
        "            response = ai_provider.ask_chat(\n"
        '                settings.CODER_MODEL, [{"role": "user", "content": prompt}]\n'
        "            )",
        '        response = ai_provider.ask_chat(\n'
        '            settings.CODER_MODEL, [{"role": "user", "content": prompt}]\n'
        "        )",
    ),
    (
        GENERATION,
        "the errored-call refund is dropped (a cut spends budget again)",
        "        self._acquire()\n"
        "        try:\n"
        "            return self.provider.ask_chat(model, messages, **kwargs)\n"
        "        except Exception:\n"
        "            self._refund()\n"
        "            raise",
        "        self._acquire()\n"
        "        return self.provider.ask_chat(model, messages, **kwargs)",
    ),
    (
        GENERATION,
        "the refund fires on success too (the ceiling stops bounding)",
        "        self._acquire()\n"
        "        try:\n"
        "            return self.provider.ask_chat(model, messages, **kwargs)\n"
        "        except Exception:\n"
        "            self._refund()\n"
        "            raise",
        "        self._acquire()\n"
        "        try:\n"
        "            result = self.provider.ask_chat(model, messages, **kwargs)\n"
        "            self._refund()\n"
        "            return result\n"
        "        except Exception:\n"
        "            self._refund()\n"
        "            raise",
    ),
    (
        DEADLINE,
        "the deadline-tally half of the refund is dropped",
        "        with self._lock:\n"
        "            used = self._stage_calls.get(stage, 0)\n"
        "            if used > 0:\n"
        "                self._stage_calls[stage] = used - 1",
        "        with self._lock:\n"
        "            pass",
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
