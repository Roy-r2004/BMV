#!/usr/bin/env python3
"""Mutation sweep for the three defects the 162-164 trio found."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

TARGETS = {
    "mock": Path("/repo/backend/app/application/preview_app/safety/mock_data.py"),
    "fb": Path("/repo/backend/app/application/preview_app/fallback.py"),
    "reg": Path("/repo/backend/preview-template/src/ui/registry.ts"),
    "mockmod": Path("/repo/backend/app/application/preview_app/codegen/mock.py"),
}
TESTS = [
    "tests/preview_app/test_trio_162_164_defects.py",
    "tests/preview_app/test_ui_catalogue_drift.py",
]
MUTATIONS = [
    ("mock", "t1 the guard invents placeholders again",
     "    borrowed = [t for t in catalogue_item_titles(mock) if t][:3]",
     "    borrowed = []"),
    ("mock", "t2 the brand fallback writes a gate-failing title",
     "f\"    {{ title: '{brand} selection', description: 'Chosen by the {brand} counter.' }},\\n\"",
     "\"    { title: 'Everyday essential', description: 'Built for daily use.' },\\n\""),
    ("mock", "t3 a borrowed apostrophe is not escaped",
     "    def _escape(text: str) -> str:", "    def _escape(text: str) -> str:\n        return text\n    def _unused(text: str) -> str:"),
    ("mock", "t4 more than three borrowed titles overrun the block",
     "if t][:3]", "if t][:99]"),
    ("fb", "t5 the stub raises on cosmetic errors again",
     "        errors = blocking_contract_errors(\n            validate_catalogue_page_content(content, route or {})\n        )",
     "        errors = validate_catalogue_page_content(content, route or {})"),
    ("reg", "t6 the registry denies a variant the component accepts",
     "'atelier', 'split', 'item']", "'atelier', 'split']"),
    ("mockmod", "t7 an ordinary import is waved through again",
     "        if token == \"import\":\n            return False",
     "        if token == \"import\" and False:\n            return False"),
    ("mockmod", "t8 re-exports are waved through",
     "    if _REEXPORT_RE.search(content):\n        return False",
     "    if False:\n        return False"),
]

def run_tests() -> bool:
    p = subprocess.run([sys.executable, "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
                       cwd="/repo/backend", capture_output=True, text=True)
    return p.returncode == 0

def main() -> None:
    originals = {k: p.read_text(encoding="utf-8") for k, p in TARGETS.items()}
    if not run_tests():
        print("baseline is RED"); raise SystemExit(2)
    print(f"baseline green; {len(MUTATIONS)} mutations\n")
    survivors = []
    try:
        for key, label, old, new in MUTATIONS:
            path, original = TARGETS[key], originals[key]
            if old not in original:
                print(f"  SKIP  {label} — anchor not found"); survivors.append(label); continue
            path.write_text(original.replace(old, new), encoding="utf-8")
            killed = not run_tests()
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed: survivors.append(label)
            path.write_text(original, encoding="utf-8")
    finally:
        for k, p in TARGETS.items(): p.write_text(originals[k], encoding="utf-8")
    print(f"\n{len(MUTATIONS) - len(survivors)} killed / {len(survivors)} survived")
    for s in survivors: print(f"  survivor: {s}")
    raise SystemExit(1 if survivors else 0)

if __name__ == "__main__":
    main()
