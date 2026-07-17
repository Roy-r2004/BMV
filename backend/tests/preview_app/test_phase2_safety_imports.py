from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
# Shared constants live in patterns.py (leaf module outside the safety package).
SAFETY_FILE = (
    REPO_ROOT
    / "backend"
    / "app"
    / "application"
    / "preview_app"
    / "patterns.py"
)


def headless_symbols() -> tuple[str, ...]:
    tree = ast.parse(SAFETY_FILE.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "_HEADLESS_SYMBOLS" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Tuple):
            raise AssertionError("_HEADLESS_SYMBOLS must stay a tuple literal")
        values: list[str] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                raise AssertionError("_HEADLESS_SYMBOLS must contain only string literals")
            values.append(element.value)
        return tuple(values)
    raise AssertionError("Could not find _HEADLESS_SYMBOLS in safety.py")


def main() -> None:
    symbols = headless_symbols()

    for required in ("Transition", "Dialog", "Menu"):
        if required not in symbols:
            raise AssertionError(f"Missing expected compatibility symbol: {required}")

    for forbidden in ("AnimatePresence", "motion", "useAnimation"):
        if forbidden in symbols:
            raise AssertionError(f"Unexpected framer-motion stub symbol still present: {forbidden}")


def test_headless_symbols_contract() -> None:
    main()


if __name__ == "__main__":
    main()
