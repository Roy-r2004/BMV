#!/usr/bin/env python3
"""Phase 1 DoD: `placeholder_content_shipped` fires zero times over 20 businesses.

    python3 backend/scripts/measure/placeholder_gate_census.py \
        --workspaces /app/data/preview-apps [--json OUT] [--check ARCHIVED.json]

The row had stood open on *"inverted so far — the gate exists and fires correctly;
the DoD wants zero fires, which means the writers still emit placeholders"*, with
two data points (2 leaks on request 73, 2 on 68) and a note that it needed a
20-business run. **It never needed a run.** The gate's predicate is a regex over
`src/data/mock.ts` (`quality_gate.py:293`), and 89 workspaces are sitting on the
volume. This scores the row offline, for $0.

**Both predicates are measured, and that is the point of the script.**

- **SHIPPED** — `_BRACKETED_PLACEHOLDER_RE`, imported from `quality_gate` rather
  than restated, so the census cannot drift from the gate the way two earlier
  censuses in this repo drifted from the code they claimed to measure.
- **SPECIFIED** — `early_brand_placeholder_strings()` and
  `early_brand_placeholder_item_titles()`. **Item 1.8 said to build the gate on
  these two and the shipped gate does not call either.** They are still consumed
  only by `product_face.py`, exactly as 1.8 described them *before* the work. So
  the DoD row has been scored against a narrower detector than the item that
  created it asked for, and nobody recorded the substitution.

If SPECIFIED fires where SHIPPED does not, "fires zero times" is a statement
about the regex, not about whether placeholders shipped — which is the failure
mode this repo keeps rediscovering: a gate that measures whether we updated our
own pattern.

**The SPECIFIED predicate reproduces `product_face`'s guard, and the first cut of
this script did not.** `early_brand_placeholder_strings()` is every string leaf of
the Brand-default seed, which includes `/gallery`, `60 min`, `Get started`,
`On schedule` — routes, durations and CTAs that any genuine site legitimately
ships. Matched bare, it fired on **87 of 87 workspaces** and meant nothing.
Production never uses it bare: `product_face.py:90` requires
`text in early_brand_placeholder_strings() and "Brand" in text`, and
`:117` requires a default item title to be Brand-bearing or one of two named
exceptions. The census now applies the same co-occurrence guard, because a census
that paraphrases the code it measures is the exact defect this repo has shipped
twice (see the traps section of the roadmap). The bare-match number is retained
as `specified_predicate_unguarded` so the difference is visible rather than
quietly dropped.

One exclusion, stated rather than buried: **only `src/data/mock.ts` is read**,
because that is the only file the shipped gate reads. A placeholder baked into a
page TSX is out of scope for this row.

Read-only. Reads no database and makes no network call.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_REPO_BACKEND = Path(__file__).resolve().parents[2]
if str(_REPO_BACKEND) not in sys.path:
    sys.path.insert(0, str(_REPO_BACKEND))

from app.application.preview_app.industry_templates.seed import (  # noqa: E402
    early_brand_placeholder_item_titles,
    early_brand_placeholder_strings,
)
from app.application.preview_app.quality_gate import (  # noqa: E402
    _BRACKETED_PLACEHOLDER_RE,
)

#: The two titles `product_face.py:118` treats as early-placeholder even without
#: a "Brand" token in them. Restated here because they are literals there too.
_NAMED_EARLY_TITLES = {"Everyday essential", "Guest favorite"}

#: A quoted string leaf in `mock.ts`. The SPECIFIED sets hold exact leaf values,
#: so matching them means comparing against whole string literals, never a
#: substring of the file: `"Brand Story"` must not hit on a page describing "the
#: brand story behind every plate".
_STRING_LEAF = re.compile(r"""(['"])((?:\\.|(?!\1)[^\\\n])*)\1""")


def _string_leaves(source: str) -> list[str]:
    return [m.group(2).strip() for m in _STRING_LEAF.finditer(source)]


def _specified_set() -> set[str]:
    """1.8's helpers as `product_face` actually applies them.

    The `"Brand" in s` half is the guard at `product_face.py:90`; without it the
    set is every string leaf of the Brand-default seed and matches real copy.
    """
    strings = {s for s in early_brand_placeholder_strings() if s and "Brand" in s}
    titles = {
        t for t in early_brand_placeholder_item_titles()
        if t and ("Brand" in t or t in _NAMED_EARLY_TITLES)
    }
    return strings | titles


def _specified_set_unguarded() -> set[str]:
    """The same helpers matched bare — retained to show what the guard removes."""
    return {
        s for s in (early_brand_placeholder_strings() | early_brand_placeholder_item_titles())
        if s and s != "Brand"
    }


def scan(source: str) -> dict:
    """Every predicate over one `mock.ts`."""
    shipped = sorted(dict.fromkeys(_BRACKETED_PLACEHOLDER_RE.findall(source)))
    leaves = set(_string_leaves(source))
    return {
        "shipped": shipped,
        "specified": sorted(leaves & _specified_set()),
        "specified_unguarded": sorted(leaves & _specified_set_unguarded()),
    }


def run_census(roots: list[Path]) -> dict:
    seen: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            if d.is_dir() and d.name.isdigit() and (d / "src/data/mock.ts").is_file():
                # Last root wins: the live volume supersedes an archive.
                seen[d.name] = d / "src/data/mock.ts"

    runs: dict[str, dict] = {}
    for name, mock in sorted(seen.items(), key=lambda kv: int(kv[0])):
        runs[name] = scan(mock.read_text(errors="replace"))

    shipped_hits = {r: v["shipped"] for r, v in runs.items() if v["shipped"]}
    specified_hits = {r: v["specified"] for r, v in runs.items() if v["specified"]}
    unguarded_hits = {
        r: v["specified_unguarded"] for r, v in runs.items() if v["specified_unguarded"]
    }
    only_specified = sorted(
        (r for r in specified_hits if r not in shipped_hits), key=int
    )

    return {
        "corpus_runs": len(runs),
        "shipped_predicate": {
            "runs_firing": sorted(shipped_hits, key=int),
            "run_count": len(shipped_hits),
            "hits": shipped_hits,
        },
        "specified_predicate": {
            "runs_firing": sorted(specified_hits, key=int),
            "run_count": len(specified_hits),
            "hits": specified_hits,
        },
        "specified_predicate_unguarded": {
            "run_count": len(unguarded_hits),
            "note": "bare match, no `Brand` co-occurrence guard — matches routes and "
                    "generic CTAs, retained only to show what the guard removes",
        },
        "runs_the_shipped_gate_would_miss": only_specified,
        "verdict": "MET" if not shipped_hits else "FAILED",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--workspaces", type=Path, action="append", required=True)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--check", type=Path,
                    help="archived census JSON; red-exit on any drift")
    args = ap.parse_args()

    result = run_census(args.workspaces)
    sh = result["shipped_predicate"]
    sp = result["specified_predicate"]

    print("Phase 1 DoD — placeholder_content_shipped fires zero times")
    print(f"  corpus: {result['corpus_runs']} workspaces with a src/data/mock.ts")
    print()
    print(f"  SHIPPED predicate (_BRACKETED_PLACEHOLDER_RE, the gate's own): "
          f"{sh['run_count']} of {result['corpus_runs']} runs fire")
    for run in sh["runs_firing"]:
        print(f"    request {run}: {', '.join(sh['hits'][run])}")
    print()
    print(f"  SPECIFIED predicate (1.8's early_brand_* helpers, NOT wired to the gate, "
          f"guarded as product_face applies them): "
          f"{sp['run_count']} of {result['corpus_runs']} runs fire")
    for run in sp["runs_firing"]:
        print(f"    request {run}: {', '.join(sp['hits'][run])}")
    print(f"    [unguarded, for contrast] bare match fires on "
          f"{result['specified_predicate_unguarded']['run_count']} runs — routes, "
          f"durations and CTAs; not a placeholder signal")
    print()
    print(f"  runs the shipped gate would MISS: "
          f"{result['runs_the_shipped_gate_would_miss'] or 'none'}")
    print(f"  VERDICT (row is scored on the shipped predicate): {result['verdict']}")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"wrote {args.json}")

    if args.check:
        archived = json.loads(args.check.read_text(encoding="utf-8"))
        drift = [k for k in archived if archived.get(k) != result.get(k)]
        if drift:
            print(f"DRIFT against {args.check}: {', '.join(drift)} — the corpus or a "
                  "predicate changed; re-derive before citing the archived numbers",
                  file=sys.stderr)
            raise SystemExit(1)
        print(f"check OK — matches {args.check}")


if __name__ == "__main__":
    main()
