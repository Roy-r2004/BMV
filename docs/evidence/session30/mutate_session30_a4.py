#!/usr/bin/env python3
"""Mutation sweep for Stage A / A4 — the provenance manifest guards.

Every policy rule's enforcement is mutated once; the guard suite must kill
each. Anchors verbatim, occurrence-counted.

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_a4.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
PROV = REPO / "backend/app/application/preview_app/provenance.py"

T = ["tests/preview_app/test_provenance_guards.py"]

MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("P1 allowlist quietly gains CC-BY", PROV, T, 1,
     '        "CC0-1.0",',
     '        "CC0-1.0",\n        "CC-BY-4.0",'),
    ("P2 sha pin relaxed to short hashes", PROV, T, 1,
     '_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")',
     '_FULL_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")'),
    ("P3 aceternity gate removed", PROV, T, 1,
     "        if _GATED_SOURCE_RE.search(source_repo):",
     "        if False:"),
    ("P4 react-bits bright line removed", PROV, T, 1,
     '        if _COMMONS_CLAUSE_SOURCE_RE.search(source_repo) and license_id != "MIT+Commons-Clause":',
     "        if False:"),
    ("P5 baseline tampered to smuggle a dep", PROV, T, 1,
     '        "vite",\n    }\n)',
     '        "vite",\n        "lenis",\n    }\n)'),
    ("P6 attributions ignore the manifest rows", PROV, T, 1,
     "    if not rows:",
     "    if True:"),
    ("P7 empty-state text drifts from the committed file", PROV, T, 1,
     '            "No third-party components are vendored in this template yet. Every",',
     '            "No third-party components are vendored here yet. Every",'),
    ("P8 broken manifest reads as empty", PROV, T, 1,
     "    if not isinstance(data, list):\n        raise ValueError",
     "    if not isinstance(data, list):\n        return []\n        raise ValueError"),
    ("P9 path containment check dropped", PROV, T, 1,
     '        if not path.startswith("src/ui/"):',
     "        if False:"),
    ("P10 existence check inverted", PROV, T, 1,
     "        elif not (base / path).is_file():",
     "        elif False:"),
]


def run(tests: list[str]) -> bool:
    return (
        subprocess.run(
            [sys.executable, "-m", "pytest", *tests, "-q", "-x", "--no-header"],
            cwd=str(REPO / "backend"),
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def main() -> None:
    all_tests = sorted({t for _, _, tests, _, _, _ in MUT for t in tests})
    if not run(all_tests):
        print("baseline RED — fix the tests before sweeping")
        raise SystemExit(2)
    print(f"baseline green; {len(MUT)} mutations\n")

    originals = {p: p.read_text(encoding="utf-8") for p in {m[1] for m in MUT}}
    survivors: list[str] = []
    try:
        for label, target, tests, count, old, new in MUT:
            source = originals[target]
            found = source.count(old)
            if found != count:
                print(f"  MISCOUNT  {label} — anchor x{found}, expected x{count}")
                survivors.append(label)
                continue
            target.write_text(source.replace(old, new), encoding="utf-8")
            killed = not run(tests)
            print(f"  {'kill' if killed else 'SURVIVED'}  {label}")
            if not killed:
                survivors.append(label)
            target.write_text(source, encoding="utf-8")
    finally:
        for path, text in originals.items():
            path.write_text(text, encoding="utf-8")

    print(f"\n{len(MUT) - len(survivors)} killed / {len(survivors)} survived")
    for label in survivors:
        print("  survivor:", label)
    raise SystemExit(1 if survivors else 0)


if __name__ == "__main__":
    main()
