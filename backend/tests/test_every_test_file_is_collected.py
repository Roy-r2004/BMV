"""A file named `test_*.py` that yields no tests is 0 % coverage wearing a badge.

Roadmap 0.9. Six files under `tests/` matched `test_*.py` and pytest collected
**nothing** from them — 2,375 lines of assertions that had never run in CI:

    tests/preview_app/test_catalogue_contract.py        1782
    tests/preview_app/test_brand_usage_contract.py       157
    tests/preview_app/test_safe_stub_braces.py           152
    tests/appspec/test_app_spec_persistence.py           139
    tests/preview_app/test_phase5_ui_alias_imports.py    127
    tests/infrastructure/test_logging.py                  18

They were script-style: logic under `if __name__ == "__main__"`, or at module
level, or in functions not named `test_*`. Every one of them passed review, sat
in the tree for months, and asserted nothing. Converting them was the task; this
is what stops it happening again.

Static rather than a nested pytest run, deliberately. Invoking pytest inside
pytest to ask "what would you collect" is slow, recursive, and answers a
slightly different question than the one that matters. The failure mode here is
structural — a file with no `test_*` function and no `Test*` class — and the AST
answers that exactly. A file whose tests exist but fail to *import* already
fails the suite loudly as a collection error, so that case needs no guard.

Mirrors the collection-time guard in
`tests/preview_app/test_quality_gate_fail_codes.py`, which does the same job for
quality-gate fail codes that no test names.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parent

#: Files that match `test_*.py` but are deliberately not test modules. Empty,
#: and it should stay that way — an entry here is a file nobody runs. Add one
#: only with a comment saying what runs its assertions instead.
_EXEMPT: frozenset[str] = frozenset()


def _test_files() -> list[Path]:
    return sorted(
        path
        for path in TESTS_ROOT.rglob("test_*.py")
        if "__pycache__" not in path.parts
    )


def _defines_a_test(tree: ast.Module) -> bool:
    """True when pytest's default naming rules would collect something."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                return True
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("test"):
                        return True
    return False


def test_the_tests_directory_is_not_empty() -> None:
    """Guard the guard: a glob that matches nothing would pass everything."""
    assert len(_test_files()) > 100, (
        f"only {len(_test_files())} test files found under {TESTS_ROOT} — "
        "this guard is not looking where it thinks it is"
    )


@pytest.mark.parametrize(
    "path", _test_files(), ids=lambda p: str(p.relative_to(TESTS_ROOT))
)
def test_a_test_file_collects_at_least_one_test(path: Path) -> None:
    relative = str(path.relative_to(TESTS_ROOT))
    if relative in _EXEMPT:
        pytest.skip(f"{relative} is exempt")

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assert _defines_a_test(tree), (
        f"{relative} is named test_*.py but defines no test pytest would "
        "collect — no `test_*` function and no `Test*` class with one. If its "
        "assertions live under `if __name__ == '__main__'` or at module level, "
        "they have never run in CI. Convert them into real tests; do not add "
        "the file to _EXEMPT to silence this."
    )
