# Phase 3 license policy — free-license-only, rewritten onto tokens, provenance-manifested

Owner-ruled 2026-08-08 (session 26), operationalized 2026-08-09 (session 29).
This document is the policy Stage A lands and every later stage obeys.

## The three rules

1. **MIT-verified or nothing.** A component may be mined only when the exact
   file being copied is under MIT (or a strictly more permissive license:
   ISC, BSD-2/3, 0BSD, Unlicense/CC0). "The project is mostly MIT" is not
   verification — pro/paid tiers inside otherwise-MIT projects are the known
   trap. License is verified **per file at the source commit**, not per
   project.
2. **Copied and rewritten onto tokens, never installed.** Mined code lands as
   house primitives under `backend/preview-template/src/ui/**`, restyled to
   consume the recipe token pipe (`design_recipes.py` → `index_css.j2` →
   tokens). Raw copy-paste kits re-import sameness — every raw-Aceternity
   site looks like Aceternity — so the rewrite is the point, not overhead.
   No new package.json dependency may enter via mining. The only permitted
   new runtime deps in all of Phase 3: **Lenis**, plus **dotLottie** if and
   only if the Stage-C pilot adopts it (each verified MIT before install,
   and each is a *global* decision — one fingerprint-keyed lockfile serves
   every generated site).
3. **Every borrowed file is manifested.** No provenance row, no merge.

## The provenance manifest

`backend/preview-template/PROVENANCE.json` — one array, one object per
borrowed file, append-only:

```json
{
  "path": "src/ui/effects/Marquee.tsx",
  "source_repo": "https://github.com/magicuidesign/magicui",
  "source_path": "registry/magicui/marquee.tsx",
  "source_commit": "<full sha at time of copy>",
  "license": "MIT",
  "license_url": "https://github.com/magicuidesign/magicui/blob/<sha>/LICENSE",
  "retrieved": "2026-08-09",
  "rewritten": true,
  "rewrite_notes": "restyled onto --recipe tokens; framer-motion -> motion; removed cn() dep",
  "recipe_personalities": ["bold-retail", "playful"]
}
```

Rules the manifest enforces (a pytest guards each once Stage A lands):
- every file under a `src/ui/**` path listed in the manifest exists;
- every manifest row's `license` is in the allowlist;
- `source_commit` and `license_url` are non-empty (a claim without a pin is
  not provenance);
- no `package.json` dependency delta without a manifest row of kind
  `"dependency"` (Lenis/dotLottie get one each).

## What is NOT acceptable, with the reason recorded

- **GSAP plugins beyond the free core** — GSAP core is free since 2025-04
  (Webflow) and stays the *fallback* engine; premium plugins (SplitText et
  al.) historically carried non-MIT terms and are out regardless of current
  status unless re-verified per file.
- **Tailwind UI / shadcn "blocks" from paid drops, Aceternity Pro, Magic UI
  Pro** — paid tiers, categorically out.
- **CC-BY components** — attribution in a generated customer site is a
  branding defect; skip rather than attribute.
- **Anything requiring three.js** — not in the kit, and a renderer is a
  global dependency decision this policy does not grant.

## Source verdicts (verified 2026-08-09 — see `evidence/session29/phase3-foundry-shortlist.md` for URLs)

| source | verdict | consequence |
|---|---|---|
| **Magic UI** | **verified MIT** (LICENSE.md in the official repo; only its Pro *templates* are paid, and they live outside the repo) | clear to mine — Tier A, 20 candidates |
| **React Bits** | MIT + Commons Clause — the license *explicitly permits* "use, copy, modify, merge, publish, and distribute the Software **as part of an application, website, or product**"; it forbids selling/redistributing *the components themselves* (alone, bundled, or ported) | **ADMITTED — owner ruling 2026-08-09.** Generated customer sites are the explicitly-permitted case. **Bright line recorded:** the preview-template's mined components must never be published as a standalone kit/library (including open-sourcing the template as a component collection) — that is the act the clause forbids. Manifest rows carry `"license": "MIT+Commons-Clause"`, never plain "MIT" |
| **Aceternity UI** | **MIT claim unverifiable** — no public component repo, no LICENSE file; the official org hosts only boilerplates and the site's licence page covers Pro | all 16 Aceternity candidates gated on a **human license check** before any file is copied |
| **Lenis** | verified MIT (`darkroomengineering/lenis` — use the `lenis` package, NOT the deprecated `@studio-freight` one) | admissible when Stage B lands it |
| **dotLottie** | verified MIT (`LottieFiles/dotlottie-web`) | admissible if Stage C adopts it — confirm the WASM renderer self-hosts (no CDN fetch at runtime) |

**Stage B mining set, as ruled:** Magic UI's 20 + React Bits' admitted picks
(~26-30 total — the roadmap's target met from verified sources). Aceternity's
16 stay gated: its defect is *no findable license text at all*, which no
ruling can cure; re-admit only if a human check finds actual text. MIT
attribution is satisfied by an `ATTRIBUTIONS.md` in the preview template
(notice preservation), generated from the provenance manifest; the allowlist
gains exactly one non-plain-MIT entry, `MIT+Commons-Clause (React Bits form,
end-product embedding only)`.

## Process per mined component (the foundry loop)

1. Verify license per file at commit → record row.
2. Copy at pinned commit → rewrite onto tokens (no `cn()`/`clsx` imports the
   kit lacks; `motion` is the animation dep, already shipped).
3. Tag with `recipe_personalities` — a primitive with no personality tag is
   a sameness generator and gets rejected in review.
4. Register in `registry.ts` + `catalogue.json` so codegen may emit it.
5. Manifest row + the pytest suite green.
