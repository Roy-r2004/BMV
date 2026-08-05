"""Mutation-test the generator half of request 95's menu defect.

    cd backend && python scripts/cli/mutate_nav_label_collision.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

Request 95's public nav labelled `/my-reservations` "Reservations" and omitted
the declared public `/reservations` entirely. The roadmap attributed that to the
template's `shortLabel`; measured, the *shipped* `mock.ts` already carried the
label "Reservations" on the member route, so the whole visible defect is this
file's — `_normalize_nav_section` deduped on the label key and dropped the route
that lost. The template half is real too and is swept separately by
`preview-template-tests/tools/mutate.py`.

The blind spots this sweep is written against:

  - **the case that does not bind.** The two collision guards overlap on the
    obvious fixture, so the suite carries a fixture for each: two prefixes
    reducing to one word, and a shortened form equal to a sibling's full label.
    The vitest sweep of the same rule left both green until those were added.
  - **guards that cannot fail.** The path-derived fallback is removed; if
    nothing goes red, no fixture ever exhausts the candidates and it is
    decoration.
  - **the boundary in the other direction.** Keeping label collisions must not
    stop duplicate *destinations* collapsing, so path dedupe is mutated too.

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
    "tests/preview_app/test_routes_and_nav_dedup.py "
    "tests/preview_app/test_chrome_nav_strip.py "
    "tests/preview_app/test_scaffold_hero_cta.py"
)

MUTATIONS = [
    # --- the defect itself ----------------------------------------------------
    (
        MOCK_DATA,
        "a label collision deletes the route again (request 95's missing /reservations)",
        """    labels = _nav_labels_for_section([(raw, path) for _, path, raw in kept], brand_name)
    cleaned: list[dict] = [
        {"id": entry_id, "path": path, "href": path, "label": labels[index]}
        for index, (entry_id, path, _) in enumerate(kept)
    ]""",
        """    labels = _nav_labels_for_section([(raw, path) for _, path, raw in kept], brand_name)
    cleaned: list[dict] = []
    _seen_labels: set[str] = set()
    for index, (entry_id, path, raw) in enumerate(kept):
        _label = _nav_label(raw, path, brand_name)
        if _nav_key(_label) in _seen_labels:
            continue
        _seen_labels.add(_nav_key(_label))
        cleaned.append({"id": entry_id, "path": path, "href": path, "label": _label})""",
    ),
    (
        MOCK_DATA,
        "labels are decided one entry at a time instead of across the section",
        "    labels = _nav_labels_for_section([(raw, path) for _, path, raw in kept], brand_name)",
        "    labels = [_nav_labels_for_section([(raw, path)], brand_name)[0]"
        " for _, path, raw in kept]",
    ),
    # --- the two collision guards, which overlap on the obvious fixture -------
    (
        MOCK_DATA,
        "collisions between two shortened labels stop counting",
        "        if short_counts.get(_nav_key(short[index]), 0) > 1 or any(",
        "        if False or any(",
    ),
    (
        MOCK_DATA,
        "collisions against a sibling's FULL label stop counting",
        "            key == _nav_key(short[index]) for j, key in enumerate(full_keys) if j != index\n        ):",
        "            False for j, key in enumerate(full_keys) if j != index\n        ):",
    ),
    (
        MOCK_DATA,
        "the shortened form is preferred even when it was ruled out",
        "            candidates = [full[index], short[index]]",
        "            candidates = [short[index], full[index]]",
    ),
    # --- what makes the rule terminate ---------------------------------------
    (
        MOCK_DATA,
        "the path-derived fallback is removed, so candidates can run out",
        """        segments = [s for s in path.strip("/").split("/") if s]
        candidates.append(
            " ".join(s.replace("-", " ").replace("_", " ").title() for s in segments) or "Home"
        )
""",
        "",
    ),
    (
        MOCK_DATA,
        "the label key stops normalising, so 'My Orders' never matches 'my orders'",
        '    return re.sub(r"[^a-z0-9]+", "", label.lower())',
        "    return label",
    ),
    # --- the boundary in the other direction ---------------------------------
    (
        MOCK_DATA,
        "duplicate destinations stop collapsing (the redundancy the dedupe exists for)",
        "        if path in seen_paths:\n            continue\n        seen_paths.add(path)",
        "        seen_paths.add(path)",
    ),
    # --- the unshortened form -------------------------------------------------
    (
        MOCK_DATA,
        "the unshortened label is shortened too, so there is nothing to fall back to",
        "    text = re.sub(r\"\\s+\", \" \", str(raw_label or \"\")).strip()\n"
        "    for variant in _brand_label_variants(brand_name):",
        "    text = _NAV_LABEL_NOISE_RE.sub(\"\", re.sub(r\"\\s+\", \" \", str(raw_label or \"\")).strip())\n"
        "    for variant in _brand_label_variants(brand_name):",
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
