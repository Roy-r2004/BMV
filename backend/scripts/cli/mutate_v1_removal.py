"""Mutation-test the v1 role-pages removal.

    cd backend && python scripts/cli/mutate_v1_removal.py

Session 17: the legacy HTML fallback was removed by owner ruling. Four
mutations: each `raise` in the orchestrator's codegen failure path softened to
`pass` (the run would emit `done` over a failed preview), the legacy
generate-pages route re-added, and the HTML_PAGE prompt enum re-added without
a caller. Restores from an in-memory backup.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

ORCHESTRATOR = BACKEND / "app/application/pipelines/orchestrator.py"
REQUESTS_ROUTER = BACKEND / "app/api/v1/routers/requests.py"
PROMPTS = BACKEND / "app/application/prompts.py"

SUITES = "tests/application/test_v1_fallback_removed.py"

MUTATIONS = [
    (
        ORCHESTRATOR,
        "the no-runway raise becomes pass: a failed run would emit done anyway",
        """                raise
            _emit(db, request_id, "build", "Retrying preview generation...", 86,""",
        """                pass
            _emit(db, request_id, "build", "Retrying preview generation...", 86,""",
    ),
    (
        ORCHESTRATOR,
        "the retry-failure raise becomes pass: a twice-failed run would emit done",
        """                except Exception:
                    pass
                raise""",
        """                except Exception:
                    pass""",
    ),
    (
        REQUESTS_ROUTER,
        "the legacy generate-pages route is re-added",
        '@router.post("/{request_id}/generate-build-plans")',
        '@router.post("/{request_id}/generate-pages")\n'
        "def trigger_generate_pages(request_id: int):\n"
        '    return {"ok": True}\n\n'
        '@router.post("/{request_id}/generate-build-plans")',
    ),
    (
        PROMPTS,
        "the HTML_PAGE prompt enum is re-added without a caller",
        '    UI_EXPERIENCE_PLAN = "prompts/ui_experience_plan.j2"',
        '    HTML_PAGE = "prompts/html_page.j2"\n'
        '    UI_EXPERIENCE_PLAN = "prompts/ui_experience_plan.j2"',
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
