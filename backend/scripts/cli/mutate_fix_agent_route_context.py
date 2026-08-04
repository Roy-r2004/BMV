"""Mutation-test the fix agent's route block — allow-list once, degrade by dropping.

    cd backend && python scripts/cli/mutate_fix_agent_route_context.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

The blind spots this sweep is written against:

  - **fixtures too small to reach the rule.** The budget only binds past two
    catalogue routes. Every assertion runs over the archived corpus (10-19
    routes per run), and one test guards the fixture's own size so a smaller
    corpus cannot silently make the rest vacuous.
  - **asserting against the case that does not bind.** Removing a *rung* only
    shows up on runs that reach it, so `skeleton_ids_only` is mutated away and
    caught by the 18- and 19-route runs, not by request 93's nine.
  - **guards that cannot fail.** The final route-clipping loop is mutated to a
    no-op; if nothing goes red, no archived run ever reaches it and the loop is
    speculative code rather than a fallback.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

ARCHITECT = BACKEND / "app/application/preview_app/codegen/architect.py"

SUITES = (
    "tests/preview_app/test_fix_agent_route_context.py "
    "tests/preview_app/test_catalogue_contract.py"
)

MUTATIONS = [
    # --- the allow-list bound -------------------------------------------------
    (
        ARCHITECT,
        "each route restates every component definition (the defect)",
        '        for component in contract.pop("components", None) or []:',
        '        for component in contract.get("components", None) or []:',
    ),
    (
        ARCHITECT,
        "routes stop naming their allowed components",
        '        contract["allowed_components"] = allowed',
        '        contract["allowed_components"] = []',
    ),
    (
        ARCHITECT,
        "the library is keyed per route, so a shared component lands twice",
        "            library.setdefault(name, component)",
        "            library[name + str(len(routes))] = component",
    ),
    (
        ARCHITECT,
        "prop shapes are restated per route instead of hoisted",
        '        for key, members in (contract.pop(_PROP_SHAPES_KEY, None) or {}).items():',
        '        for key, members in (contract.get(_PROP_SHAPES_KEY, None) or {}).items():',
    ),
    # --- degrade by dropping, not collapsing ---------------------------------
    (
        ARCHITECT,
        "the ladder is removed and the whole block collapses again",
        "    for level in _DETAIL_LEVELS:",
        "    for level in _DETAIL_LEVELS[:1]:",
    ),
    (
        ARCHITECT,
        "only the full level is ever emitted (the pre-fix behaviour exactly)",
        "        payload = _routes_context_payload(routes, library, prop_shapes, level)\n        rendered = json.dumps(payload, ensure_ascii=False, separators=(\",\", \":\"))\n        if len(rendered) <= _ROUTES_CONTEXT_BUDGET:\n            return rendered",
        "        payload = _routes_context_payload(routes, library, prop_shapes, level)\n        return json.dumps(payload, ensure_ascii=False, separators=(\",\", \":\"))",
    ),
    (
        ARCHITECT,
        "the last rung is dropped (18- and 19-route runs lose their block)",
        "    _DETAIL_NAMES_ONLY,\n    _DETAIL_SKELETON_IDS_ONLY,\n)",
        "    _DETAIL_NAMES_ONLY,\n)",
    ),
    (
        ARCHITECT,
        "the rungs are ordered most-degraded first (every run loses its library)",
        "_DETAIL_LEVELS = (\n    _DETAIL_FULL,\n    _DETAIL_NO_PROP_SHAPES,\n    _DETAIL_NAMES_ONLY,\n    _DETAIL_SKELETON_IDS_ONLY,\n)",
        "_DETAIL_LEVELS = (\n    _DETAIL_SKELETON_IDS_ONLY,\n    _DETAIL_NAMES_ONLY,\n    _DETAIL_NO_PROP_SHAPES,\n    _DETAIL_FULL,\n)",
    ),
    # --- what no rung may drop ------------------------------------------------
    (
        ARCHITECT,
        "the most degraded rung loses the route's own file",
        '                **{k: v for k, v in route.items() if k != "contract"},\n                "section_slots": contract.get("section_slots") or [],\n                "shell_component": contract.get("shell_component"),\n            })\n        return {"detail_level": level, "routes": trimmed}',
        '                "path": route.get("path"),\n                "skeleton_id": route.get("skeleton_id"),\n            })\n        return {"detail_level": level, "routes": trimmed}',
    ),
    (
        ARCHITECT,
        "the degradation is silent (no `detail_level` on the block)",
        '    payload: dict = {\n        "detail_level": level,',
        "    payload: dict = {",
    ),
    # --- the empty case -------------------------------------------------------
    (
        ARCHITECT,
        "a run with no catalogue routes now sends a ladder payload",
        "    if not routes:\n        # `[]` and `{\"routes\": []}` read the same to a model, and the empty\n        # case is what a run with no catalogue routes has always sent.\n        return _bounded_json([], _ROUTES_CONTEXT_BUDGET)",
        "    if False:\n        return _bounded_json([], _ROUTES_CONTEXT_BUDGET)",
    ),
    # --- the budget itself ----------------------------------------------------
    (
        ARCHITECT,
        "the budget is raised instead of the block being made to fit",
        "_ROUTES_CONTEXT_BUDGET = 10000",
        "_ROUTES_CONTEXT_BUDGET = 100000",
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
