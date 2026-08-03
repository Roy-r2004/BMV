"""Mutation-test the DoD 7 route/page work.

    cd backend && python scripts/cli/mutate_route_bijection.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`,
which has discarded uncommitted work in this repo before.

Two blind spots this sweep is written against, both of which let six mutations
survive a first pass in session 7:

  - **asserting against the case that does not bind.** The cap only binds above 12
    routes and the alias tiers only matter *at* the cap, so the fixtures are sized
    to `_SMOKE_MAX_ROUTES`, not to a comfortable three-route app.
  - **driving the consumer and never the producer.** `_smoke_routes` is the
    producer; `render_pages_skipped` is only a measurement because
    `_render_smoke_check` publishes it, so the report mutations are aimed at the
    stage and the stage is what the tests call.

Exit code is 0 only when every mutation was caught. Requires the `api` service to
be up (`docker compose up -d api`); the repo is bind-mounted into it, so edits
here are visible there without a rebuild.

Note the shell: `sh -c`, never `sh -lc`. A login shell re-reads /etc/profile,
which drops /opt/node/bin from PATH, and `tsx_parse_error` fails open without
node — six unrelated tests go red and the mutation report becomes noise.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

#: `"failed" in summary` is wrong: "1 xfailed" contains it, so a green suite with
#: one xfail reads as red and the sweep refuses to start. Count instead.
_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

FINALIZE = BACKEND / "app/application/preview_app/pipeline/finalize.py"
ASSEMBLE = BACKEND / "app/application/preview_app/assemble.py"

SUITES = (
    "tests/preview_app/test_route_bijection.py "
    "tests/preview_app/test_request_40_defects.py"
)

MUTATIONS = [
    # --- _smoke_routes: which URLs get loaded --------------------------------
    (
        FINALIZE,
        "dedupe by component again (the defect: an alias URL is never loaded)",
        "        if url in urls:\n            continue\n        urls.add(url)",
        "        if component in seen:\n            continue\n        urls.add(url)",
    ),
    (
        FINALIZE,
        "aliases sort ahead of ops first sightings (cap displaces an unchecked page)",
        "    ordered = tiers[(0, 0)] + tiers[(0, 1)] + tiers[(1, 0)] + tiers[(1, 1)]",
        "    ordered = tiers[(0, 0)] + tiers[(1, 0)] + tiers[(0, 1)] + tiers[(1, 1)]",
    ),
    (
        FINALIZE,
        "ops routes sort ahead of public (reverts the surface order)",
        "    ordered = tiers[(0, 0)] + tiers[(0, 1)] + tiers[(1, 0)] + tiers[(1, 1)]",
        "    ordered = tiers[(0, 1)] + tiers[(0, 0)] + tiers[(1, 0)] + tiers[(1, 1)]",
    ),
    (
        FINALIZE,
        "the cap stops binding (smoke pass grows without bound in the reserve)",
        "    return ordered[:_SMOKE_MAX_ROUTES]",
        "    return ordered",
    ),
    # --- smoke_eligible_routes: the denominator itself -----------------------
    (
        FINALIZE,
        "wildcard routes counted as eligible pages",
        '        if not path or not component or "*" in path:\n            continue\n        out.append(route)',
        "        if not path or not component:\n            continue\n        out.append(route)",
    ),
    (
        FINALIZE,
        "routes with no page file counted as eligible pages",
        '        if not path or not component or "*" in path:\n            continue\n        out.append(route)',
        '        if not path or "*" in path:\n            continue\n        out.append(route)',
    ),
    # --- the published measurement -------------------------------------------
    (
        FINALIZE,
        "skipped hardcoded to zero after a successful probe",
        '        summary["skipped"] = max(0, eligible - len(routes))',
        '        summary["skipped"] = 0',
    ),
    (
        FINALIZE,
        "a smoke pass that never ran reports nothing skipped",
        '        "skipped": eligible,',
        '        "skipped": 0,',
    ),
    (
        FINALIZE,
        "eligible not published (checked keeps its missing denominator)",
        '        "eligible": eligible,',
        '        "eligible": 0,',
    ),
    (
        FINALIZE,
        "the crash map keeps the last URL rather than the first",
        '                errors.setdefault(component, f"{url}: {message}")',
        '                errors[component] = f"{url}: {message}"',
    ),
    (
        FINALIZE,
        "one file stubbed once per crashed URL",
        "        and not (component in _stub_seen or _stub_seen.add(component))",
        "        and True",
    ),
    # --- the orphan direction -------------------------------------------------
    (
        ASSEMBLE,
        "unrouted census ignores the architect (every page reads as orphaned)",
        "        if canonical_workspace_path(rel).lower() not in declared",
        "        if True",
    ),
    (
        ASSEMBLE,
        "unrouted census reports nothing (request 33's page reads as served)",
        "        if canonical_workspace_path(rel).lower() not in declared",
        "        if False",
    ),
    (
        ASSEMBLE,
        "unrouted census does not canonicalize the declared side",
        '        canonical_workspace_path(str(rt.get("component_file") or "")).lower()',
        '        str(rt.get("component_file") or "").lower()',
    ),
]

#: `docker run`, not `docker compose exec` — and unlike the older drivers here this
#: one has to be. The compose `api` service mounts only `backend/`, so
#: `test_request_40_defects.py`'s two kit-reading tests fail on a clean tree and the
#: baseline reads red before a single mutation is applied. Verified: compose gives
#: 2 failed / 134 passed on the same commit where `docker run` gives 136 passed.
REPO = BACKEND.parent
PYTEST = (
    f'docker run --rm -v "{REPO}:/repo" -w /repo/backend '
    "-e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh bmv-local-api "
    f"-c 'pip install -q pytest 2>/dev/null; python -m pytest {SUITES} "
    "-q --no-header -p no:cacheprovider'"
)


def run_suite() -> tuple[bool, str, list[str]]:
    proc = subprocess.run(
        PYTEST, shell=True, capture_output=True, text=True, timeout=900, cwd=BACKEND.parent
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
    originals = {path: path.read_text() for path in {FINALIZE, ASSEMBLE}}

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
            green, summary, failed = run_suite()
            print(f"\n[{'STILL GREEN <-- pins nothing' if green else 'RED'}] {label}")
            print(f"    {summary}")
            for name in failed:
                print(f"    caught by: {name}")
            if green:
                survivors.append(label)
            path.write_text(original)
    finally:
        restored = True
        for path, original in originals.items():
            path.write_text(original)
            if path.read_text() != original:
                print(f"RESTORE FAILED for {path}")
                restored = False
        if restored:
            print("\nsource restored and verified byte-identical")

    if not restored:
        return 2
    print(f"\nsurvivors: {survivors or 'none'}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
