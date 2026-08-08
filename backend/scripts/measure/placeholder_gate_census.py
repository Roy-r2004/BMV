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

**A third family exists and neither predicate above can see it (added session 28).**
Session 27's fix D found that `"Business"` is a placeholder brand too — request
156 shipped *"Ready for Business?"*, *"Tell Business what you need"*,
*"Business — clear choices and real bookings."* Those are the scaffold's
brand-bound fallbacks handed a placeholder, and they reached customer-visible
copy. They live in **page TSX, not `mock.ts`**, so the shipped gate cannot see
them by construction and the SPECIFIED helpers do not name them either.

The BRAND predicate measures that class by running production's own
`scrub_placeholder_brand` over each page and counting what it would rewrite —
importing the function rather than restating its patterns, for the same reason
the other two are imported. A sentinel brand is passed in because the count is
the measurement; the real name only decides what the replacement text would be.

The `mock.ts`-only exclusion therefore now applies to the two original predicates
only, and it is stated rather than buried: the shipped gate reads one file, and
two of the three placeholder families this repo has found do not live in it.

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
from app.application.preview_app.safety.mock_data import (  # noqa: E402
    scrub_placeholder_brand,
)

#: Passed to `scrub_placeholder_brand` as the "real" name. Any string that is not
#: itself a placeholder works: the function returns a replacement *count*, and it
#: is the count this census reads, never the rewritten source.
_SENTINEL_BRAND = "Sentinel Brand Name"

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


def scan_brand(workspace: Path) -> tuple[dict[str, int], int]:
    """Fix D's family: the scaffold's brand fallbacks left holding a placeholder.

    Production's `scrub_placeholder_brand` decides what counts, so this cannot
    drift from it. Returns `({relative path: sites}, template_default_sites)`.

    **`src/pages/**` only, and the exclusion is the whole point of the split.**
    Scanning all of `src/` fires on 91 of 98 workspaces with an identical
    signature every time — `components/Nav.tsx x1`, `ui/public/AiFeatureDeck.tsx
    x1`, `AiFeaturePanel.tsx x1`, `AiFeatureStage.tsx x2`. Those are the
    **template's own default parameter values** (`function Nav({ brandName =
    'Brand' })`), copied verbatim into every workspace by the scaffolder. A
    default is not shipped copy: it renders only where a call site omits the
    prop, which is a different question and is measured separately. Counting
    them would have reproduced this script's original sin — the unguarded
    SPECIFIED set that fired on 87 of 87 and meant nothing.

    They are returned rather than dropped, so the number stays visible.
    """
    hits: dict[str, int] = {}
    for tsx in sorted((workspace / "src/pages").rglob("*.tsx")):
        _, sites = scrub_placeholder_brand(
            tsx.read_text(errors="replace"), _SENTINEL_BRAND
        )
        if sites:
            hits[str(tsx.relative_to(workspace))] = sites

    template_defaults = 0
    for tsx in sorted((workspace / "src").rglob("*.tsx")):
        if tsx.is_relative_to(workspace / "src/pages"):
            continue
        _, sites = scrub_placeholder_brand(
            tsx.read_text(errors="replace"), _SENTINEL_BRAND
        )
        template_defaults += sites
    return hits, template_defaults


def run_census(roots: list[Path]) -> dict:
    seen: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir(), key=lambda p: p.name):
            if d.is_dir() and d.name.isdigit() and (d / "src/data/mock.ts").is_file():
                # Last root wins: the live volume supersedes an archive.
                seen[d.name] = d

    runs: dict[str, dict] = {}
    brand_hits: dict[str, dict[str, int]] = {}
    template_default_runs = 0
    for name, workspace in sorted(seen.items(), key=lambda kv: int(kv[0])):
        runs[name] = scan((workspace / "src/data/mock.ts").read_text(errors="replace"))
        hits, template_defaults = scan_brand(workspace)
        if hits:
            brand_hits[name] = hits
        if template_defaults:
            template_default_runs += 1

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
        "brand_predicate": {
            "runs_firing": sorted(brand_hits, key=int),
            "run_count": len(brand_hits),
            "hits": brand_hits,
            "note": "fix D's family — the scaffold's brand-bound fallbacks left "
                    "holding a placeholder, measured with production's own "
                    "scrub_placeholder_brand over src/pages/** only. Lives in "
                    "page TSX, so the shipped gate cannot see it: that gate "
                    "reads src/data/mock.ts only",
            "template_default_runs": template_default_runs,
            "template_default_note": "workspaces whose copied-in template files "
                    "carry `brandName = 'Brand'` as a default parameter. NOT a "
                    "fire: a default renders only where a call site omits the "
                    "prop. Reported so the number is visible rather than dropped",
        },
        "runs_the_shipped_gate_would_miss": sorted(
            set(only_specified) | (set(brand_hits) - set(shipped_hits)), key=int
        ),
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
    br = result["brand_predicate"]
    print(f"  BRAND predicate (fix D's family, src/pages/** only, production's own "
          f"scrub_placeholder_brand): {br['run_count']} of {result['corpus_runs']} runs fire")
    for run in br["runs_firing"]:
        where = ", ".join(f"{f} x{n}" for f, n in sorted(br["hits"][run].items()))
        print(f"    request {run}: {where}")
    print(f"    [not a fire] {br['template_default_runs']} runs carry "
          f"`brandName = 'Brand'` as a template default parameter, which renders "
          f"only where a call site omits the prop")
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
