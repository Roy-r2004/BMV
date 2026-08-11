#!/usr/bin/env python3
"""Roadmap 0.9's residue: the "3 script-style test files (2,061 lines)" row.

QUESTION. Phase 0 row 0.9 (`docs/PREVIEW_ROADMAP.md:1773`) asks whether "the 3
script-style test files (2,061 lines, not pytest-collected)" are run by CI.
Session 25 asks what REMAINS of that row after the 0.9 conversion pass
(roadmap ~line 903, commit `115375f`, 2026-08-02) converted eight
never-collected `test_*.py` files. Which three files did the row mean, are
they executed by anything, and is there any script-style residue left to
convert?

ANSWER THE CENSUS VERIFIES. The trio is a SUBSET of the eight already
converted. At the commit that wrote the row (`614c086`, 2026-08-01), the
never-collected `test_*.py` files and their `wc -l` were:

    tests/preview_app/test_catalogue_contract.py        1782
    tests/preview_app/test_brand_usage_contract.py       157
    tests/preview_app/test_safe_stub_braces.py           152
    tests/appspec/test_app_spec_persistence.py           139
    tests/preview_app/test_phase5_ui_alias_imports.py    127
    tests/infrastructure/test_logging.py                  18

Exactly ONE 3-subset sums to 2,061: {catalogue_contract 1782,
safe_stub_braces 152, phase5_ui_alias_imports 127}. Every other triple was
enumerated and none hits 2,061 (closest: 2,048 and 2,066). So the row's trio
is those three files — an early-audit sighting of what commit `115375f`
later converted in full. Residue to convert today: ZERO files.

METHOD. Two layers.
  1. Historical identification (NOT re-derivable in-container): the line
     counts above were taken on the host with
     `git show 614c086:<path> | wc -l` and are baked in as constants; this
     script re-runs only the subset-sum arithmetic over them.
  2. Current-tree verification (re-derivable, and what RED-EXIT guards):
     each of the three files exists, parses, defines >= 1 `test_` function
     (so pytest's `python_files = test_*.py` rule collects it), and has NO
     `if __name__ == "__main__"` block left; the collection guard
     `tests/test_every_test_file_is_collected.py` exists with an EMPTY
     `_EXEMPT`; the only non-`test_` `.py` files under `tests/` are the
     known imported helpers; and nothing under `.github/workflows/` or
     `scripts/`/`backend/scripts/` invokes the three files by name as
     scripts.

JUDGMENT CALLS.
  * "Script-style" at the audit commit meant `main()` under
    `if __name__ == "__main__"` — true of all six files, so structure does
    not select the trio; ONLY the exact 2,061 subset-sum does. Stated
    because a reader might expect the trio to be structurally distinct.
  * The pytest collect/run proof (51 collected, 51 passed, session 25) runs
    in docker and is archived beside this census's output in
    `docs/evidence/session25/script-style-tests-census.txt`, not re-run
    here: this script must stay runnable offline without pytest installed.
  * `tests/rollout/harness.py` and `tests/rollout/helpers.py` are NOT
    residue: they define no assertions-as-tests of their own and are
    imported by 10+ collected `tests/rollout/test_*.py` modules.
    `tests/conftest.py` is pytest plumbing. All three are allow-listed.

RED-EXIT when: a trio file is missing, defines no `test_` function, regrows
a `__main__` block, the guard file's `_EXEMPT` is non-empty, or a NEW
non-`test_` `.py` appears under `tests/` (that is exactly how new
script-style residue would enter). Read-only apart from an optional JSON
archive written when `docs/evidence/session25/` is reachable.
"""
from __future__ import annotations

import ast
import itertools
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TESTS = BACKEND / "tests"
REPO = BACKEND.parent

#: `wc -l` at commit 614c086 (2026-08-01), the commit that wrote roadmap row
#: 0.9. Taken on the host with `git show 614c086:<path> | wc -l`.
AUDIT_COUNTS: dict[str, int] = {
    "tests/preview_app/test_catalogue_contract.py": 1782,
    "tests/preview_app/test_brand_usage_contract.py": 157,
    "tests/preview_app/test_safe_stub_braces.py": 152,
    "tests/appspec/test_app_spec_persistence.py": 139,
    "tests/preview_app/test_phase5_ui_alias_imports.py": 127,
    "tests/infrastructure/test_logging.py": 18,
}
ROADMAP_TOTAL = 2061

#: Non-`test_` python files under tests/ that are legitimately there.
KNOWN_HELPERS = {
    "conftest.py",           # pytest plumbing
    "rollout/harness.py",    # imported by 10+ collected rollout tests
    "rollout/helpers.py",    # imported by 10+ collected rollout tests
}

GUARD = TESTS / "test_every_test_file_is_collected.py"


def red_exit(msg: str) -> None:
    print(f"\nRED-EXIT: {msg}", file=sys.stderr)
    sys.exit(2)


def the_unique_trio() -> tuple[str, ...]:
    hits = [
        combo
        for combo in itertools.combinations(sorted(AUDIT_COUNTS), 3)
        if sum(AUDIT_COUNTS[f] for f in combo) == ROADMAP_TOTAL
    ]
    if len(hits) != 1:
        red_exit(
            f"expected exactly one 3-subset of the audit counts summing to "
            f"{ROADMAP_TOTAL}, found {len(hits)} — the baked counts drifted"
        )
    return hits[0]


def current_state(rel: str) -> dict:
    path = TESTS / Path(rel).relative_to("tests")
    if not path.is_file():
        red_exit(f"{rel} is missing from the current tree")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    test_funcs = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name.startswith("test_")
    ]
    has_main = any(
        isinstance(n, ast.If)
        and isinstance(n.test, ast.Compare)
        and isinstance(n.test.left, ast.Name)
        and n.test.left.id == "__name__"
        for n in tree.body
    )
    if not test_funcs:
        red_exit(f"{rel} defines no test_ function — it regressed to a script")
    if has_main:
        red_exit(f"{rel} has grown an `if __name__` block back")
    with path.open("rb") as fh:
        lines = sum(1 for _ in fh)
    return {"file": rel, "lines_now": lines, "test_functions": len(test_funcs)}


def guard_is_armed() -> None:
    if not GUARD.is_file():
        red_exit(f"collection guard {GUARD.name} is missing")
    tree = ast.parse(GUARD.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_EXEMPT":
            call = node.value
            if isinstance(call, ast.Call) and call.args:
                arg = call.args[0]
                if not (isinstance(arg, (ast.List, ast.Tuple, ast.Set)) and not arg.elts):
                    red_exit("_EXEMPT in the collection guard is non-empty")
            return
    red_exit("could not find _EXEMPT in the collection guard")


def no_new_helpers() -> list[str]:
    found = sorted(
        str(p.relative_to(TESTS))
        for p in TESTS.rglob("*.py")
        if "__pycache__" not in p.parts
        and not p.name.startswith("test_")
        and p.name != "__init__.py"
    )
    unexpected = [f for f in found if f not in KNOWN_HELPERS]
    if unexpected:
        red_exit(
            "non-test_ python files under tests/ beyond the known helpers "
            f"(possible NEW script-style residue): {unexpected}"
        )
    return found


def executed_by_sweep(trio: tuple[str, ...]) -> dict[str, list[str]]:
    """Split references to the trio into script-execution vs pytest-target.

    A line like `python tests/preview_app/test_x.py` would mean the __main__
    era is back — RED-EXIT. A filename inside a pytest target list (the
    scripts/cli/mutate_* harnesses keep the trio in their SUITES constants)
    is the healthy post-conversion state and is reported, not flagged.
    """
    names = [Path(f).name for f in trio]
    script_exec: list[str] = []
    pytest_target: list[str] = []
    self_path = Path(__file__).resolve()
    sweep_roots = [REPO / ".github", REPO / "scripts", BACKEND / "scripts"]
    exts = {".yml", ".yaml", ".sh", ".json", ".toml", ".cfg", ".ini", ".py"}
    for root in sweep_roots:
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if not p.is_file() or p.suffix not in exts or "__pycache__" in p.parts:
                continue
            if p.resolve() == self_path:
                continue  # the census names its own subjects
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for name in names:
                    if name not in line:
                        continue
                    where = f"{p.relative_to(REPO)}:{lineno}: {name}"
                    if "pytest" in line or "SUITES" in line or line.lstrip().startswith('"tests/'):
                        pytest_target.append(where)
                    elif "python" in line:
                        script_exec.append(where)
                    else:
                        pytest_target.append(where + " (bare mention)")
    if script_exec:
        red_exit(f"the trio is executed as scripts again: {script_exec}")
    return {"script_exec": script_exec, "pytest_target": pytest_target}


def main() -> None:
    trio = the_unique_trio()
    print("script-style-tests census — roadmap 0.9 residue (session 25)")
    print(f"roadmap row total: {ROADMAP_TOTAL} lines over 3 files")
    print("\nunique 3-subset of the audit-commit (614c086) counts:")
    per_file = []
    for rel in trio:
        state = current_state(rel)
        state["lines_at_614c086"] = AUDIT_COUNTS[rel]
        per_file.append(state)
        print(
            f"  {rel}: {AUDIT_COUNTS[rel]} lines then, "
            f"{state['lines_now']} now, {state['test_functions']} test_ functions, "
            "no __main__ block"
        )
    print(f"  sum then: {sum(AUDIT_COUNTS[f] for f in trio)}")

    guard_is_armed()
    print("\ncollection guard: present, _EXEMPT empty")
    helpers = no_new_helpers()
    print(f"non-test_ files under tests/ (all known imported helpers): {helpers}")
    refs = executed_by_sweep(trio)
    print("\nexecuted-by sweep over .github/, scripts/, backend/scripts/:")
    print(f"  as a script (python <file>): {len(refs['script_exec'])} — must be 0")
    print(f"  as a pytest target (mutation harness SUITES): {len(refs['pytest_target'])}")
    for line in refs["pytest_target"]:
        print(f"    {line}")

    verdict = (
        "RESIDUE IS ZERO: the row's trio is a subset of the eight files commit "
        "115375f already converted; all three are collected pytest modules today"
    )
    print(f"\nverdict: {verdict}")

    evidence_dir = REPO / "docs" / "evidence" / "session25"
    if evidence_dir.is_dir():
        payload = {
            "question": "roadmap 0.9: 3 script-style test files, 2061 lines — what remains?",
            "audit_commit": "614c086",
            "conversion_commit": "115375f",
            "trio": per_file,
            "trio_lines_at_audit": sum(AUDIT_COUNTS[f] for f in trio),
            "roadmap_total": ROADMAP_TOTAL,
            "collection_guard": "tests/test_every_test_file_is_collected.py, _EXEMPT empty",
            "non_test_files_under_tests": helpers,
            "executed_by": {
                "as_script": refs["script_exec"],
                "as_pytest_target": refs["pytest_target"],
                "ci_note": "sole workflow is preview-template-tests.yml (vitest); backend pytest has no CI workflow",
            },
            "verdict": verdict,
        }
        out = evidence_dir / "script-style-tests-census.json"
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"json archived: {out}")


if __name__ == "__main__":
    main()
