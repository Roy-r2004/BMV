"""Mutation-test route alias inflation — the scaffold end and the router end.

    cd backend && python scripts/cli/mutate_route_alias_inflation.py

Reverts each part of the fix in turn, runs the suites that pin it, reports which
tests caught it, and restores from an **in-memory** backup — never `git checkout`.

Two ends of one defect. The scaffolded detail page read `params.id ??
params.slug`, so `assemble.py` minted a `:id`/`:slug` pair for every listing to
make sure one of them matched. Request 69 shipped three routes to the same page
and the one React Router binds carries `:paintingId`, which the page did not
read.

The blind spots this sweep is written against:

  - **a fix that changes no outcome.** The census is the guard against that
    (36 of 47 stored runs change, 800 -> 727 routes); here, each half is
    reverted alone so neither can be carried by the other.
  - **the boundary in the other direction.** The alias exists to stop a dead
    link, so "mint nothing at all" is mutated in and must be caught — reducing
    two aliases to none would be a regression wearing the fix's clothes.
  - **guards that cannot fail.** `_has_param_child` must say no to a
    grandchild (`/gallery/:id/edit`) and to a literal child; both directions
    are mutated.
  - **anchors that match twice.** Counted before applying, and a multiple match
    is reported as a survivor rather than skipped.

Exit code is 0 only when every mutation was caught.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_FAILED_RE = re.compile(r"\b(\d+) (?:failed|error|errors)\b")

BACKEND = Path(__file__).resolve().parents[2]

ASSEMBLE = BACKEND / "app/application/preview_app/assemble.py"
SCAFFOLD = BACKEND / "app/application/preview_app/catalogue_contract/scaffold.py"

SUITES = (
    "tests/preview_app/test_route_alias_inflation.py "
    "tests/preview_app/test_router_alias_params.py "
    "tests/preview_app/test_journey_contract.py "
    "tests/preview_app/test_route_bijection.py "
    "tests/preview_app/test_dead_link_repair.py"
)

MUTATIONS = [
    # --- the scaffold end -----------------------------------------------------
    (
        SCAFFOLD,
        "the detail page reads the two hardcoded names again",
        "        \"  const itemKey = String(Object.values(params)[0] ?? '').trim();\\n\"",
        "        \"  const itemKey = String(params.id ?? params.slug ?? '').trim();\\n\"",
    ),
    (
        SCAFFOLD,
        "the detail page reads a param that is never the declared one",
        "String(Object.values(params)[0] ?? '')",
        "String(params.nonexistent ?? '')",
    ),
    (
        SCAFFOLD,
        "the item key stops being trimmed, so ` 3` matches nothing",
        "String(Object.values(params)[0] ?? '').trim();",
        "String(Object.values(params)[0] ?? '');",
    ),
    # --- the router end: one alias, not two -----------------------------------
    (
        ASSEMBLE,
        "the listing site mints the `:slug` twin again",
        '                alias = f"{base}/:id"\n'
        "                if alias not in registered:",
        '                for alias in (f"{base}/:id", f"{base}/:slug"):\n'
        "                 if alias not in registered:",
    ),
    (
        ASSEMBLE,
        "the sibling site mints the `:slug` twin again",
        '                    alias = f"{parent}/:id"\n'
        "                    priority = 2 if _is_record_component(leaf, comp) else 1",
        '                    alias = f"{parent}/:slug"\n'
        "                    priority = 2 if _is_record_component(leaf, comp) else 1",
    ),
    # --- the router end: no alias when one is declared -------------------------
    (
        ASSEMBLE,
        "the listing site aliases over a declared param child again",
        "                if _has_param_child(base, all_paths):\n                    continue",
        "                if False:\n                    continue",
    ),
    (
        ASSEMBLE,
        "the sibling site aliases over a declared param child again",
        "                if _has_param_child(parent_key, all_paths):\n"
        "                    detailish = False",
        "                if False:\n                    detailish = False",
    ),
    # --- the boundary: the alias must not disappear altogether ------------------
    (
        ASSEMBLE,
        "no listing alias is minted at all, so seed cards dead-end again",
        '                alias = f"{base}/:id"\n'
        "                if alias not in registered:",
        '                alias = f"{base}/:id"\n'
        "                if False:",
    ),
    # --- the predicate ---------------------------------------------------------
    (
        ASSEMBLE,
        "a grandchild counts as a param child, so a real listing loses its alias",
        '        p.startswith(prefix) and p[len(prefix) :].startswith(":") '
        'and "/" not in p[len(prefix) :]',
        '        p.startswith(prefix) and p[len(prefix) :].startswith(":")',
    ),
    (
        ASSEMBLE,
        "any child counts, so a literal `/gallery/coastal` suppresses the alias",
        '        p.startswith(prefix) and p[len(prefix) :].startswith(":") '
        'and "/" not in p[len(prefix) :]',
        '        p.startswith(prefix) and "/" not in p[len(prefix) :]',
    ),
    (
        ASSEMBLE,
        "the base's trailing slash is not normalized, so `/gallery/` never matches",
        '    prefix = (base.rstrip("/") or "") + "/"',
        '    prefix = base + "/"',
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
        PYTEST, shell=True, capture_output=True, text=True, timeout=1800, cwd=REPO
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
