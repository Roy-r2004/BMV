"""Mutation-test the derived brand palette — no keyword table, no monoculture.

    cd backend && python scripts/cli/mutate_brand_palette.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

The blind spots this sweep is written against:

  - **the case that does not bind.** Restoring the industry table is not enough
    on its own: measured over the corpus it gives the *same* three colours. So
    the sweep also restores the precedence (`theme` first) and the demo-stage
    stamp separately, because any one of the three alone reproduces the defect
    and a test that only catches all three at once is catching nothing.
  - **driving the consumer, never the producer.** `derive_palette` is mutated,
    and so is `build_brand_brief`'s use of it, and so is the demo stage.
  - **never assert against the constant a mutation would change.** The identity
    space is shrunk to 1 and to 2; the tests write 48 out by hand, so shrinking
    it cannot pass.
  - **guards that cannot fail.** The contrast solver's targets are lowered below
    the WCAG floor; if the legibility test does not go red, no palette in the
    ring was ever near the boundary and the solver is decoration.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

PALETTE = BACKEND / "app/application/preview_app/brand_palette.py"
BRIEF = BACKEND / "app/application/preview_app/brand_brief.py"
ENRICH = BACKEND / "app/application/services/visual_demo_enrichment.py"

SUITES = (
    "tests/preview_app/test_brand_palette.py "
    "tests/preview_app/test_brand_brief.py "
    "tests/preview_app/test_design_brief.py "
    "tests/preview_app/test_design_overlay.py"
)

MUTATIONS = [
    # --- the monoculture comes back, one route at a time -----------------------
    (
        BRIEF,
        "the brief takes the demo theme's colour again (the original precedence)",
        """    palette = derive_palette(
        (business_name or demo.get("product_name") or "").strip(),
        business_description,
    )""",
        """    palette = derive_palette(
        (business_name or demo.get("product_name") or "").strip(),
        business_description,
    )
    if theme.get("primary_color"):
        palette = {**palette, "primary": str(theme["primary_color"])}""",
    ),
    (
        BRIEF,
        "the palette is keyed on the industry bucket again (one colour per bucket)",
        """    palette = derive_palette(
        (business_name or demo.get("product_name") or "").strip(),
        business_description,
    )""",
        "    palette = derive_palette(bucket, bucket)",
    ),
    (
        ENRICH,
        "the demo stage stamps a palette again, before the brief ever looks",
        '    demo.setdefault("visual_theme", {})',
        '    demo.setdefault("visual_theme", {})["primary_color"] = "#0f766e"',
    ),
    # --- what makes the derivation distinct ------------------------------------
    (
        PALETTE,
        "the identity space collapses to one palette (the monoculture, restored)",
        "_HUE_STOPS = 24",
        "_HUE_STOPS = 1",
    ),
    (
        PALETTE,
        "the tone axis is dropped, halving the identity space",
        """_TONES: tuple[tuple[str, float, float], ...] = (
    # label, primary saturation, background saturation
    ("vivid", 0.62, 0.34),
    ("slate", 0.34, 0.20),
)""",
        """_TONES: tuple[tuple[str, float, float], ...] = (
    ("vivid", 0.62, 0.34),
)""",
    ),
    (
        PALETTE,
        "every business hashes to the same index",
        '    digest = hashlib.blake2s(key.encode("utf-8"), digest_size=8).digest()\n'
        '    return int.from_bytes(digest, "big") % (_HUE_STOPS * len(_TONES))',
        "    return 0",
    ),
    # --- what makes it stable ---------------------------------------------------
    (
        PALETTE,
        "the description joins the key, so an edit rebrands the business",
        """    name = _PUNCT_RE.sub(" ", str(business_name or "").casefold()).strip()
    if name:
        return name
    return _PUNCT_RE.sub(" ", str(business_description or "").casefold()).strip()""",
        """    return _PUNCT_RE.sub(
        " ", f"{business_name or ''} {business_description or ''}".casefold()
    ).strip()""",
    ),
    # --- what makes it legible --------------------------------------------------
    (
        PALETTE,
        "the primary target drops below the WCAG floor",
        "_PRIMARY_ON_WHITE = 5.2",
        "_PRIMARY_ON_WHITE = 2.0",
    ),
    (
        PALETTE,
        "the muted target drops below the WCAG floor",
        "_MUTED_ON_BACKGROUND = 4.8",
        "_MUTED_ON_BACKGROUND = 2.0",
    ),
    (
        PALETTE,
        "the text target drops below the WCAG floor",
        "_TEXT_ON_BACKGROUND = 13.0",
        "_TEXT_ON_BACKGROUND = 2.0",
    ),
    (
        PALETTE,
        "the lightness bisection stops converging",
        "    for _ in range(32):",
        "    for _ in range(1):",
    ),
    (
        PALETTE,
        "the bisection picks the wrong side of the interval",
        """        if contrast_ratio(_hsl_to_rgb(hue, sat, mid), against) >= target:
            lo = mid
        else:
            hi = mid
    return lo""",
        """        if contrast_ratio(_hsl_to_rgb(hue, sat, mid), against) >= target:
            hi = mid
        else:
            lo = mid
    return lo""",
    ),
    # --- the seam ---------------------------------------------------------------
    (
        PALETTE,
        "`every_identity` grows its own copy of the derivation",
        "    for index in range(IDENTITY_COUNT):\n        yield index, palette_for_index(index)",
        '    for index in range(IDENTITY_COUNT):\n        yield index, {\n'
        '            "primary": "#0f766e", "secondary": "#134e4a", "background": "#f0fdfa",\n'
        '            "surface": "#ffffff", "text": "#042f2e", "muted": "#5f7a78",\n        }',
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
