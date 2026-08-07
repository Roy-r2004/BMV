"""Mutation-test the derived-palette threading into design_system fallbacks.

    cd backend && python scripts/cli/mutate_design_palette.py

The session-18 fix: `patterns.design_system_dict` gained a `design` parameter
carrying the run's real design system, so the derived palette (text / muted /
background / surface) rides through instead of hardcoded neutrals; the two
diverging copies of the function were unified (the font-name fix had landed in
only one); and `surface_color` — previously omitted — is always emitted. Each
mutation reverts one seam and expects `tests/preview_app/
test_design_system_palette.py` to go red. Restores from an **in-memory**
backup, never `git checkout`. One mutation at a time.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PATTERNS = BACKEND / "app/application/preview_app/patterns.py"
MOCK_DATA = BACKEND / "app/application/preview_app/safety/mock_data.py"
BRAND_CONTRACT = BACKEND / "app/application/preview_app/safety/brand_contract.py"

SUITES = "tests/preview_app/test_design_system_palette.py"

MUTATIONS = [
    (
        PATTERNS,
        "text_color discards the palette again",
        '        "text_color": design.get("text_color") or "#0f172a",',
        '        "text_color": "#0f172a",',
    ),
    (
        PATTERNS,
        "surface_color is omitted again (the original defect)",
        '        "surface_color": design.get("surface_color") or "#ffffff",\n',
        "",
    ),
    (
        PATTERNS,
        "font_family regresses to the squashed slug (the divergent-copy bug)",
        '        "font_family": font_token,',
        '        "font_family": re.sub(r"[^a-z0-9]+", "", font_token.lower()) or "sans",',
    ),
    (
        MOCK_DATA,
        "repair_typed_mock_exports stops passing the palette",
        '    ds_value = _default_export_value(\n'
        '        "design_system", {}, {}, {}, brand_name, primary, secondary, font, design\n'
        "    )",
        '    ds_value = _default_export_value(\n'
        '        "design_system", {}, {}, {}, brand_name, primary, secondary, font\n'
        "    )",
    ),
    (
        BRAND_CONTRACT,
        "the usage-driven injection stops passing the palette",
        "        base = (\n"
        "            _design_system_dict(primary, secondary, font, design)\n"
        '            if "design" in key.lower()\n'
        "            else {}\n"
        "        )",
        "        base = (\n"
        "            _design_system_dict(primary, secondary, font)\n"
        '            if "design" in key.lower()\n'
        "            else {}\n"
        "        )",
    ),
    (
        BRAND_CONTRACT,
        "the completeness patch stops passing the palette",
        "    design_system = _design_system_dict(primary, secondary, font, design)",
        "    design_system = _design_system_dict(primary, secondary, font)",
    ),
    (
        BRAND_CONTRACT,
        "ensure_brand_shape drops the palette on its way to the patch",
        "    full = _brand_completeness_patch(\n"
        "        brand_name, primary, secondary, font, client_names=names, design=design,\n"
        "    )",
        "    full = _brand_completeness_patch(\n"
        "        brand_name, primary, secondary, font, client_names=names,\n"
        "    )",
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
                survivors.append(label)
                continue
            path.write_text(original.replace(old, new))
            green, summary, failed = run_suite()
            path.write_text(original)
            if green:
                print(f"SURVIVED: {label} ({summary})")
                survivors.append(label)
            else:
                print(f"caught:   {label} ({summary}; {', '.join(failed[:4])})")
    finally:
        for path, original in originals.items():
            path.write_text(original)

    if survivors:
        print(f"\n{len(survivors)} SURVIVOR(S) — the tests do not pin the fix")
        return 1
    print(f"\nall {len(MUTATIONS)} mutations caught")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
