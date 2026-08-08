#!/usr/bin/env python3
"""Mutation sweep for the pack_copy_shipped gate (session 28)."""
from __future__ import annotations
import subprocess, sys
from pathlib import Path

TARGETS = {
    "loader": Path("/repo/backend/app/application/preview_app/industry_templates/loader.py"),
    "gate": Path("/repo/backend/app/application/preview_app/quality_gate.py"),
}
TESTS = ["tests/preview_app/test_pack_copy_shipped.py"]

MUTATIONS = [
    ("loader", "q1 short structural leaves counted as copy",
     "_PACK_SENTENCE_MIN_CHARS = 16", "_PACK_SENTENCE_MIN_CHARS = 1"),
    ("loader", "q2 single words counted as sentences",
     '                and " " in text\n', ""),
    ("loader", "q3 route literals counted as copy",
     '                and not text.startswith(("/", "#", "http"))\n', ""),
    ("loader", "q4 the set is empty, so the gate is green forever",
     "    for pack in load_templates().values():\n        _walk(pack.get(\"mock_seed\"), sentences)",
     "    for pack in []:\n        _walk(pack.get(\"mock_seed\"), sentences)"),
    ("loader", "q5 only the first pack contributes",
     "    for pack in load_templates().values():",
     "    for pack in list(load_templates().values())[:1]:"),
    ("loader", "q6 nested structures are not walked",
     "        if isinstance(node, dict):\n            for value in node.values():\n                _walk(value, out)",
     "        if isinstance(node, dict):\n            for value in []:\n                _walk(value, out)"),
    ("gate", "q7 the gate no longer fails on pack copy",
     "    for leaked in sorted(leaves & pack_literal_sentences()):",
     "    for leaked in sorted(set() & pack_literal_sentences()):"),
    ("gate", "q8 substring matching instead of exact leaf",
     "    for leaked in sorted(leaves & pack_literal_sentences()):",
     "    for leaked in sorted(s for s in pack_literal_sentences() if any(s in l for l in leaves)):"),
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
            path.write_text(original.replace(old, new, 1), encoding="utf-8")
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
