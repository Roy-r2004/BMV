#!/usr/bin/env python3
"""Mutation sweep for the session 29 fixes.

Five fixes, sixteen mutations, each anchored on the source verbatim:

  A. AI-hub binder — hub adoption by route (request 136) and stranded
     requirement re-tracing (request 130), `ai_features.py`
  H. Assertion salvage extended to `visible_assertion_evidence_required`
     (request 138), `heal.py` + repair prompt
  F. Fragment-extraction guard (request 143), `authoring_parser.py`
  E. Synthetic surface evidence carries every page capability (request 129),
     `sanitize/evidence.py`
  I. Per-item photo queries (request 165), `industry_images.py` +
     `photo_binding.py`

Run inside the test container:
  docker run --rm -v "$PWD:/repo" -w /repo/backend \
    -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template \
    --entrypoint sh bmv-local-api -c \
    'pip install -q pytest; python /repo/docs/evidence/session29/mutate_session29_fixes.py'
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path("/repo")
AI = REPO / "backend/app/application/services/ai_features.py"
HEAL = REPO / "backend/app/domain/appspec/sanitize/heal.py"
PARSER = REPO / "backend/app/domain/appspec/authoring_parser.py"
EVID = REPO / "backend/app/domain/appspec/sanitize/evidence.py"
IMG = REPO / "backend/app/application/services/industry_images.py"
BIND = REPO / "backend/app/application/preview_app/catalogue_contract/photo_binding.py"
PROMPT = REPO / "backend/app/templates/prompts/app_spec_repair.j2"

T_BINDER = ["tests/appspec/test_ai_hub_binder_reconcile.py"]
T_SALVAGE = [
    "tests/appspec/test_visible_assertion_salvage.py",
    "tests/appspec/test_state_assertion_salvage.py",
]
T_FRAGMENT = ["tests/appspec/test_fragment_extraction_guard.py"]
T_EVID = ["tests/appspec/test_app_spec_sanitize.py", "tests/appspec/__init__.py"]
T_PHOTO = ["tests/preview_app/test_per_item_photo_binding.py"]

# (label, file, tests, count, old, new) — count is the number of anchored
# occurrences replace() must touch; a mismatch is a miscount, not a pass.
MUT: list[tuple[str, Path, list[str], int, str, str]] = [
    ("A1 hub adoption never matches a route", AI, T_BINDER, 1,
     "                == _normalized_route(PAGE_AI_HUB_ROUTE)",
     '                == "__never_a_route__"'),
    ("A2 adopted hub id ignored, literal minted", AI, T_BINDER, 1,
     '    hub_id = str(hub.get("id") or PAGE_AI_HUB_ID)',
     "    hub_id = PAGE_AI_HUB_ID"),
    ("A3 stranded reconcile loop skips everything", AI, T_BINDER, 1,
     "        if not rid or marker not in refs or rid.casefold() in traced_ids:",
     "        if True:"),
    ("A4 early return blind to stranded requirements", AI, T_BINDER, 1,
     "        and not _stranded_ai_requirement_ids(sanitized)",
     "        and True"),
    ("A5 traces minted without their page", AI, T_BINDER, 2,
     '                "page_ids": [hub_id],',
     '                "page_ids": [],'),
    ("H1 visible assertions no longer salvage material", HEAL, T_SALVAGE, 1,
     '        "visible_assertion_evidence_required": "drop_unprovable_visible_assertion",',
     ""),
    ("H2 salvage action mislabelled as state drop", HEAL, T_SALVAGE, 1,
     '        "visible_assertion_evidence_required": "drop_unprovable_visible_assertion",',
     '        "visible_assertion_evidence_required": "drop_unbindable_state_assertion",'),
    ("H3 the last assertion in a test is droppable", HEAL, T_SALVAGE, 1,
     "        if not isinstance(assertions, list) or len(assertions) <= 1:",
     "        if not isinstance(assertions, list):"),
    ("P1 repair prompt forgets the taught code", PROMPT, T_SALVAGE, 1,
     "visible_assertion_evidence_required",
     "some_forgotten_code"),
    ("F1 ratio floor drops to zero", PARSER, T_FRAGMENT, 1,
     "_FRAGMENT_GUARD_MIN_RATIO = 0.5",
     "_FRAGMENT_GUARD_MIN_RATIO = 0.0"),
    ("F2 raw floor so high the guard never fires", PARSER, T_FRAGMENT, 1,
     "_FRAGMENT_GUARD_MIN_RAW_CHARS = 2000",
     "_FRAGMENT_GUARD_MIN_RAW_CHARS = 10_000_000"),
    ("F3 repaired-path guard removed", PARSER, T_FRAGMENT, 1,
     "    if _is_fragment_extraction(len(text), len(extracted)):\n        return None\n",
     ""),
    ("F4 balanced-scan guard removed", PARSER, T_FRAGMENT, 1,
     "    if isinstance(loaded, dict) and _is_fragment_extraction(len(text), len(candidate)):",
     "    if False:"),
    ("E1 surface evidence back to one capability", EVID, T_EVID, 1,
     '            "capability_ids": capability_ids,',
     '            "capability_ids": capability_ids[:1],'),
    ("I1 per-item query regresses to business-only", IMG, T_PHOTO, 1,
     '            search_text = f"{query} {industry_head}".strip()',
     "            search_text = industry_head"),
    ("I2 query dedupe removed, one search per item", IMG, T_PHOTO, 1,
     "        if query not in results_by_query:",
     "        if True:"),
    ("B1 own-query dominance removed", BIND, T_PHOTO, 1,
     "                score = 2000 - rank + score_photo_for_title(titles[t_index], alts[url])",
     "                score = score_photo_for_title(titles[t_index], alts[url])"),
    ("B2 photo uniqueness dropped", BIND, T_PHOTO, 1,
     "        if t_index in taken_titles or u_index in taken_urls:",
     "        if t_index in taken_titles:"),
    ("B3 dispatcher never takes the per-item path", BIND, T_PHOTO, 1,
     "        if any(per_title):",
     "        if False:"),
]


def run(tests: list[str]) -> bool:
    tests = [t for t in tests if not t.endswith("__init__.py")]
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
