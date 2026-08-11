#!/usr/bin/env python3
"""Mutation sweep for Stage A / A1 — the single SiteSpec.design resolution.

Targets the load-bearing behaviors of `site_design.resolve_site_design`, the
thin `write_index_css` renderer, and the overlay's post-deletion contract.
Anchors verbatim, occurrence-counted (MISCOUNT is a failure, never a skip).

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session30/mutate_session30_a1.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
SITE = REPO / "backend/app/application/preview_app/site_design.py"
ASSEMBLE = REPO / "backend/app/application/preview_app/assemble.py"
OVERLAY = REPO / "backend/app/application/preview_app/design_overlay.py"

T_SITE = ["tests/preview_app/test_site_design.py"]
T_OVERLAY = ["tests/preview_app/test_design_overlay.py"]
T_SECURITY = ["tests/preview_app/test_task3_security.py"]

# (label, file, tests, count, old, new)
MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("S1 overlay overrides no longer replace recipe tokens", SITE, T_SITE, 1,
     "        tokens.update({k: v for k, v in overrides.items() if v is not None})",
     "        tokens.update({})"),
    ("S2 None-valued override erases the recipe token", SITE, T_SITE, 1,
     "        tokens.update({k: v for k, v in overrides.items() if v is not None})",
     "        tokens.update(dict(overrides))"),
    ("S3 brief fonts ignored, recipe pair ships", SITE, T_SITE, 1,
     '    if ds.get("font_sans"):\n        fonts["sans"] = ds["font_sans"]',
     '    if False:\n        fonts["sans"] = ds["font_sans"]'),
    ("S4 brand lock ignored, caller colors ship", SITE, T_SITE, 1,
     '    if ds.get("brand_locked"):',
     "    if False:"),
    ("S5 lock always on, unlocked palette hijacked", SITE, T_SITE, 1,
     '    if ds.get("brand_locked"):',
     "    if True:"),
    ("S6 renderer default drifts (radius)", SITE, T_SITE, 1,
     '    "radius_ui": "0.75rem",',
     '    "radius_ui": "0.5rem",'),
    ("S7 variant loses its recipe fallback", SITE, T_SITE, 1,
     '            "hero": ds.get("hero_variant") or resolved.get("hero_variant") or None,',
     '            "hero": ds.get("hero_variant") or None,'),
    ("S8 placeholder axis drifts (container)", SITE, T_SITE, 1,
     '    "container": {"max": "92rem"},',
     '    "container": {"max": "80rem"},'),
    ("S9 emitted module loses its export", SITE, T_SITE, 1,
     '        "export const SITE_DESIGN: SiteDesign = "',
     '        "const SITE_DESIGN: SiteDesign = "'),
    ("S10 sanitize dropped, hostile theme inputs pass through", SITE, T_SECURITY, 1,
     "    primary, secondary, font_family = sanitize_theme_inputs(primary, secondary, font)",
     '    font_family = str(font or "")'),
    ("C1 glow renders from the wrong token", SITE, T_SITE, 1,
     '        "glow": tokens["glow"],',
     '        "glow": tokens["shadow_alpha"],'),
    ("A1 workspace stops receiving site-design.ts", ASSEMBLE, T_SITE, 1,
     "    write_recipe_id(workspace, {\"id\": design[\"recipe_id\"]})\n    write_site_design(workspace, design)",
     "    write_recipe_id(workspace, {\"id\": design[\"recipe_id\"]})"),
    ("A2 recipe-id.ts loses the resolved id", ASSEMBLE, T_SITE, 1,
     "    write_recipe_id(workspace, {\"id\": design[\"recipe_id\"]})",
     "    write_recipe_id(workspace, None)"),
    ("O1 overlay stops stamping its radius", OVERLAY, T_OVERLAY, 1,
     '    design["border_radius"] = tokens["radius_ui"]',
     '    design.setdefault("border_radius", tokens["radius_ui"])'),
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
