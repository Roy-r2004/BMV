"""Mutation-test the derived scaffold CTA — no literal, no industry key.

    cd backend && python scripts/cli/mutate_scaffold_hero_cta.py

Reverts each half of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

The blind spots this sweep is written against:

  - **asserting against the case that does not bind.** Every rule is driven
    through *two* businesses with disjoint route tables plus an ops-only app
    with no public destination at all. A single-business fixture cannot tell a
    derived CTA from a lucky literal.
  - **driving the consumer, never the producer.** `scaffold_hero_ctas` is
    mutated and so is the block `ensure_seed_scaffold_fields` writes — a fix in
    the helper that the emitter ignores is exactly how this defect survives.
  - **guards that cannot fail.** The parameterized-route filter and the neutral
    fallback are each mutated away; if neither goes red, no fixture reaches
    them and they are decoration.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

MOCK_DATA = BACKEND / "app/application/preview_app/safety/mock_data.py"

SUITES = (
    "tests/preview_app/test_scaffold_hero_cta.py "
    "tests/preview_app/test_fallback_accounting.py"
)

MUTATIONS = [
    # --- the literal comes back ----------------------------------------------
    (
        MOCK_DATA,
        "the hero CTA is a literal again (the trattoria's collection)",
        '            f"    primaryCta: {_ts_cta(primary_cta)},\\n"',
        '            "    primaryCta: { label: \'Explore the collection\', href: \'/gallery\' },\\n"',
    ),
    (
        MOCK_DATA,
        "the secondary CTA is a literal again (a dead /contact#inquire)",
        '            f"    secondaryCta: {_ts_cta(secondary_cta)},\\n"',
        '            "    secondaryCta: { label: \'Talk to us\', href: \'/contact#inquire\' },\\n"',
    ),
    (
        MOCK_DATA,
        "the `cta` block keeps its dead href",
        "            f\"    primaryHref: '{_ts_label(primary_cta, key='href')}',\\n\"",
        '            "    primaryHref: \'/contact#inquire\',\\n"',
    ),
    # --- what makes it general ------------------------------------------------
    (
        MOCK_DATA,
        "the destination is picked alphabetically, ignoring nav rank",
        "    ranked.sort(key=lambda entry: (entry[0], entry[1]))",
        "    ranked.sort(key=lambda entry: entry[1])",
    ),
    (
        MOCK_DATA,
        "ops routes become CTA destinations (a hero linking /admin)",
        "        if not _is_public_marketing_nav_path(normalized):\n            continue",
        "        if False:\n            continue",
    ),
    (
        MOCK_DATA,
        "parameterized routes become CTA destinations (/gallery/:id)",
        # Two call sites share this line; the route-normalizer below has the
        # same guard, so the anchor needs the line after it to be unique.
        '        if not path.startswith("/") or ":" in path:\n            continue\n        normalized = path.rstrip("/") or "/"',
        '        if not path.startswith("/"):\n            continue\n        normalized = path.rstrip("/") or "/"',
    ),
    (
        MOCK_DATA,
        "the home page is offered as its own CTA destination",
        "        if normalized in _NAV_HOME_PATHS:\n            continue",
        "        if False:\n            continue",
    ),
    # --- the fallback ---------------------------------------------------------
    (
        MOCK_DATA,
        "an app with no public route gets a guessed destination",
        '_NEUTRAL_CTA = {"label": "See what we offer", "href": "/"}',
        '_NEUTRAL_CTA = {"label": "Explore the collection", "href": "/gallery"}',
    ),
    (
        MOCK_DATA,
        "both CTAs collapse onto one destination",
        '        {"label": ranked[1][2], "href": ranked[1][1]} if len(ranked) > 1 else dict(_NEUTRAL_CTA)',
        "        dict(primary)",
    ),
    # --- the escaping ---------------------------------------------------------
    (
        MOCK_DATA,
        "a quote in a page title is no longer escaped (breaks the module)",
        '    return str(cta.get(key) or ("/" if key == "href" else "")).replace(\n        "\\\\", "\\\\\\\\"\n    ).replace("\'", "\\\\\'")',
        '    return str(cta.get(key) or ("/" if key == "href" else ""))',
    ),
    # --- the seam -------------------------------------------------------------
    (
        MOCK_DATA,
        "the emitter stops receiving the architect (helper right, output wrong)",
        "    seeded = ensure_seed_scaffold_fields(mock, brand_name=brand_name, architect=architect)",
        "    seeded = ensure_seed_scaffold_fields(mock, brand_name=brand_name)",
    ),
    # --- the hero's supporting line -------------------------------------------
    # The gate is right not to fire on this: `placeholder_content_shipped` looks
    # for unfilled tokens like `[Artist Name]` and the prose was a *filled* one.
    (
        MOCK_DATA,
        "the invented warmth comes back as the hero subcopy",
        "            f\"    subcopy: '{subcopy}',\\n\"",
        '            f"    subcopy: \'A clear next step from {brand} — warm, specific, '
        'and ready when you are.\',\\n"',
    ),
    (
        MOCK_DATA,
        "the subcopy names destinations the app does not serve",
        "    for _, _, label in _ranked_public_destinations(architect, brand_name):",
        '    for _, _, label in [(0, "/gallery", "Collection"), (1, "/x", "Studio")]:',
    ),
    (
        MOCK_DATA,
        "the subcopy is unescaped, so a quoted page title breaks the module",
        '    subcopy = _ts_label({"label": scaffold_hero_subcopy(architect, brand_name)})',
        "    subcopy = scaffold_hero_subcopy(architect, brand_name)",
    ),
    (
        MOCK_DATA,
        "an app with no public destination gets a promise anyway",
        "    if not labels:\n        return f\"{brand_name or 'Brand'}.\"",
        "    if not labels:\n        return f\"A clear next step from {brand_name}.\"",
    ),
    (
        MOCK_DATA,
        "the buttons and the supporting line stop reading one list",
        "    ranked = _ranked_public_destinations(architect, brand_name)\n\n    if not ranked:",
        "    ranked = sorted(_ranked_public_destinations(architect, brand_name), reverse=True)\n\n    if not ranked:",
    ),
    # --- the font's second spelling -------------------------------------------
    (
        MOCK_DATA,
        "the design-system repair squashes the font name again (`sourcesans3`)",
        '        "font_family": font_token,',
        '        "font_family": re.sub(r"[^a-z0-9]+", "", font_token.lower()) or "sans",',
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
