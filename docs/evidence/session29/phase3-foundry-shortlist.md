# Phase 3 Stage B — Free-Component Foundry: Mining Shortlist

Date: 2026-08-09. Ruling in force: third-party UI is **free-license only — MIT-verified**, copied and
rewritten onto design tokens as house primitives, never installed as packages. Candidate sources named
by the owner: Aceternity UI, Magic UI, React Bits. Allowed new runtime deps: Lenis, possibly dotLottie.

Kit facts checked before mining (`backend/preview-template/package.json`): `motion@^12` (Framer Motion
successor) and `animejs@^4` are already in the kit; **three.js, GSAP, ogl, cobe, tsparticles are NOT**.
Tailwind v4, React 19, `cn()` util exists at `src/ui/lib/cn.ts` (shadcn-style components port cleanly).

---

## 0. Existing kit inventory (do not duplicate)

`backend/preview-template/src/ui/`:

- **core/**: Badge, Button, Card, Dialog, Input, Select, Table, Tabs, Toast, Tooltip
- **public/**: AccentBeam, AiFeatureDeck, AiFeaturePanel, AiFeatureStage, BookingPanel, BrandFooter,
  CTABand, CatalogGrid, ConfirmStage, CredentialStrip, FeatureBento, InquiryPanel, LogoMarquee,
  MarketingHero, ProcessSection, ProductShowcase, PublicNav, PublicShell, ResultRail, ScheduleRail,
  SpotlightCard, TestimonialRail
- **ops/**: ActivityFeed, BlotterTape, CashPulseBar, ChartCard, DataTable, DeskTicker, EmptyState,
  ExpenseQueue, FilterBar, InvoiceBoard, OpsShell, PageHeader, ReconSplit, RiskQueue, StatCard
- **motion/**: AnimeChrome, anime presets; **compose/**: SkeletonComposer; **lib/**: AppLink, KitImage, cn, format

Already covered concepts: bento grid, logo marquee, marketing hero, spotlight card, testimonial rail,
CTA band. Candidates below that overlap these are marked **(upgrade)** — mine only the effect, graft it
onto the existing house component.

---

## 1. License verification (as of 2026-08-09)

### VERIFIED MIT — clear to mine

| Source | License | Evidence URL | Notes |
|---|---|---|---|
| **Magic UI** (magicui.design) | **MIT** | LICENSE.md in official repo: <https://github.com/magicuidesign/magicui/blob/main/LICENSE.md> | Every component in the repo/docs is free and MIT. README states "Free. Open Source." A separate **Magic UI Pro** sells *templates/blocks* — those live outside this repo; anything reachable under `magicui.design/docs/components` is the free MIT set. |
| **Lenis** (smooth scroll) | **MIT** © darkroom.engineering | Repo: <https://github.com/darkroomengineering/lenis> — LICENSE: <https://github.com/darkroomengineering/lenis/blob/main/LICENSE> | Correct package is `lenis` (NOT the deprecated `@studio-freight/lenis`). The React wrapper `lenis/react` ships from the same repo under the same MIT license. Approved as a runtime dep. |
| **dotLottie** (`@lottiefiles/dotlottie-react`) | **MIT** © LottieFiles | Monorepo: <https://github.com/LottieFiles/dotlottie-web> — LICENSE: <https://github.com/LottieFiles/dotlottie-web/blob/main/LICENSE> | `packages/react` in that monorepo is the React player. Note: the player loads a WASM renderer at runtime — verify it can be bundled/self-hosted (no CDN fetch) before approving, since generated previews should be self-contained. |

**MIT attribution requirement**: MIT requires preserving the copyright + permission notice in
"substantial portions" you copy. Since Stage B rewrites sources onto tokens, satisfy it once with an
`ATTRIBUTIONS.md` (or header comments) in the template crediting each upstream (e.g. "Portions adapted
from Magic UI, MIT, © magicuidesign"). Cheap, unambiguous, do it.

### NOT plain MIT / NEEDS HUMAN LICENSE CHECK

| Source | Finding | Evidence URL |
|---|---|---|
| **React Bits** (reactbits.dev) | **MIT + Commons Clause — FAILS the "MIT-verified" ruling as written.** License file: <https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md>. The Commons Clause rider forbids to "sell, sublicense, or redistribute the components themselves — whether alone, in a bundle, or as a ported version," while allowing commercial use "as part of an application, website, or product." | BMV's foundry *rewrites (ports) components and redistributes them inside generated apps delivered to paying customers*. That is arguably "part of a website," but the "ported version" language sits close enough to what the foundry does that this is an **owner/legal call, not an engineering call**. Until cleared: do not mine React Bits. |
| **Aceternity UI** (ui.aceternity.com) | **MIT claim is unverifiable at the source.** There is **no official public repo containing the free components** — the official GitHub org (<https://github.com/aceternity>) has only two boilerplate repos, no component library, no LICENSE file covering the components. The site's licence page (<https://ui.aceternity.com/licence>) covers **Pro** items only (no MIT mention; forbids redistributing "the Item... or its source files"). "MIT License for personal or commercial use" appears only in SEO/marketing copy on some listing pages, and I could not reproduce that sentence on the components index (<https://ui.aceternity.com/components>) or category pages (<https://ui.aceternity.com/categories/cards>) today. | Free tier (105 components on /components) vs paid: **Aceternity UI Pro / All-Access** (<https://pro.aceternity.com/licence>, <https://ui.aceternity.com/pricing>) sells premium blocks/templates. The 105 items on /components are the "free" set, but **their license text is nowhere authoritative**. Needs a human check — e.g. email the author (Manu Arora) or find an explicit per-component license statement — before any Aceternity code is copied. |

---

## 2. Candidate list

Legend — recipes: **CIN** cinematic/editorial luxury · **ART** warm artisan/craft · **RET** bold retail ·
**GAL** minimal gallery · **PRO** professional services · **PLA** playful/vibrant.
Deps: "motion" = framer-motion/motion, already in kit. Anything else is called out.

### Tier A — Magic UI (verified MIT, clear to mine) — 16 candidates

| # | Component | What it does | Recipes | Implementation notes |
|---|---|---|---|---|
| A1 | Blur Fade | Staggered blur+fade entrance for text/sections/grids | all six | motion only; the house "reveal on scroll" primitive |
| A2 | Text Reveal | Scroll-driven word-by-word text reveal (sticky section) | CIN, PRO | motion; pairs perfectly with Lenis |
| A3 | Number Ticker | Count-up stat number on scroll into view | PRO, RET | motion; upgrade for ops/StatCard-style public stats |
| A4 | Word Rotate | Vertically rotating word in a headline | PLA, RET | motion; hero headline garnish |
| A5 | Animated Shiny Text | Shimmer sweep across a text badge/eyebrow | CIN, RET | CSS only; announcement pills |
| A6 | Scroll Based Velocity | Marquee text whose speed/skew follows scroll velocity | RET, PLA | motion; big-type section divider |
| A7 | Aurora Text | Animated aurora gradient inside headline text | PLA | CSS only |
| A8 | Border Beam | Animated beam of light tracing a card border | PRO, CIN | CSS/motion; token-friendly card accent |
| A9 | Shine Border | Animated shine sweep on card border | CIN (luxury cards) | CSS only |
| A10 | Magic Card **(upgrade)** | Mouse-tracking radial-gradient spotlight card | PRO, RET | motion; graft onto existing `SpotlightCard` rather than adding a twin |
| A11 | Particles | Dependency-free canvas particle background | CIN, PLA | plain canvas, no deps — the safe "sparkle" background |
| A12 | Ripple | Concentric soft ripple background behind hero/CTA | PRO, GAL | CSS only |
| A13 | Flickering Grid | Flickering pixel-grid canvas background | RET, PLA | plain canvas |
| A14 | Animated Grid Pattern / Dot Pattern | Subtle animated SVG grid/dot backgrounds | PRO, GAL, ART | SVG only; quiet texture for services/gallery |
| A15 | Shimmer Button + Interactive Hover Button | CTA buttons: shimmer sweep; arrow slide-in hover | RET, PLA (shimmer) / all (hover) | CSS only; fold into `core/Button` as variants, not new components |
| A16 | Hero Video Dialog | Hero thumbnail that opens video in animated lightbox | RET, PRO | motion; kit has Radix Dialog to back it |
| A17 | Avatar Circles | Overlapping avatar stack + "+N" social-proof chip | ART, PRO, RET | static; testimonial/booking garnish |
| A18 | Animated List | Auto-cycling vertical list of notification-style cards | PRO, PLA | motion; "what our system does" storytelling |
| A19 | Lens | Magnifying-lens zoom over an image on hover | GAL, RET | motion; product/gallery detail |
| A20 | Progressive Blur | Gradient edge-blur overlay for image/marquee edges | GAL, CIN | CSS only; classy fade for `LogoMarquee` edges |

(A15 counts as two button variants; net new-component count stays ~16 since A10/A20 are grafts.)

### Tier B — Aceternity UI (HOLD until license is human-verified) — 12 candidates

Mine these **only after** the Aceternity license check clears. All are on the free /components index.

| # | Component | What it does | Recipes | Implementation notes |
|---|---|---|---|---|
| B1 | Hero Parallax | Multi-row product-image parallax hero on scroll | RET, CIN | motion; flagship hero, wants Lenis |
| B2 | Aurora Background | Soft animated aurora gradient section background | CIN, PLA | CSS keyframes only |
| B3 | Lamp Section Header | Conic-gradient "lamp" glow section header | CIN | motion; signature luxury look |
| B4 | Spotlight (New) | Animated spotlight sweep over dark hero | CIN, PRO | CSS/SVG |
| B5 | Timeline | Scroll-progress-drawn vertical timeline | PRO, ART | motion; company story / process (upgrade for `ProcessSection`) |
| B6 | Sticky Scroll Reveal | Sticky text panel with content swapping per scroll step | PRO, CIN | motion; services walkthrough |
| B7 | Container Scroll Animation | Screenshot/card tilts from 3D to flat as you scroll | RET, PRO | motion; product-shot hero |
| B8 | Animated Testimonials **(upgrade)** | Photo + quote crossfade with word stagger | ART, PRO | motion; graft onto `TestimonialRail` |
| B9 | 3D Card Effect | Perspective tilt-on-hover card with popping layers | RET, PLA | motion + mouse tracking; product cards |
| B10 | Direction Aware Hover | Overlay slides in from the edge the cursor entered | GAL, ART | motion; gallery/portfolio grids |
| B11 | Focus Cards | Grid where hovered card focuses, siblings blur/dim | GAL | CSS/motion; minimal gallery hero grid |
| B12 | Compare | Draggable before/after image slider | PRO, ART | motion; renovation/beauty/craft businesses |
| B13 | Flip Words | Headline word flips through alternatives | PLA, RET | motion |
| B14 | Text Generate Effect | Words materialize one-by-one with blur | CIN | motion; editorial intros |
| B15 | Moving Border / Hover Border Gradient | Animated running border for CTA buttons | RET, PLA | motion/CSS; `core/Button` variants |
| B16 | Wobble Card | Cursor-following wobble/parallax feature card | PLA | motion; playful bento cells (upgrade for `FeatureBento`) |

### Tier C — React Bits (BLOCKED: MIT + Commons Clause; owner/legal decision required)

Listed only so the owner knows what's being left on the table if the license verdict is "no":
Split Text, Blur Text, Scroll Float / Scroll Reveal, Tilted Card, Masonry, Rolling Gallery, Bounce
Cards, Click Spark, Dot Grid / Squares backgrounds. All the pretty React Bits backgrounds (Aurora,
Beams, Silk, Hyperspeed, Threads, Iridescence, Orb, Liquid Chrome) additionally require **ogl or
three.js — not in the kit** — so most of the source is doubly disqualified. Magic UI + Aceternity
cover every category React Bits would have contributed.

**Count: 20 clear-to-mine (Tier A) + 16 license-gated (Tier B) = 36 candidates, ~30 net new after upgrades/variants fold in.**

---

## 3. Red flags

1. **React Bits is not MIT.** MIT + Commons Clause (<https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md>): no selling, sublicensing, or redistributing the components "alone, in a bundle, or as a ported version." The foundry model (rewrite + ship in paid customer apps) needs an explicit owner/legal ruling. Default: **exclude**.
2. **Aceternity's MIT claim has no authoritative source.** No public component repo, no LICENSE file; the org at <https://github.com/aceternity> contains only boilerplates; <https://ui.aceternity.com/licence> covers Pro and forbids source redistribution. "MIT" appears only in marketing copy. **All of Tier B is gated on a human check.**
3. **Aceternity free/pro adjacency.** The site interleaves free components with Pro blocks/templates (pro.aceternity.com, /pricing). Anything under "Blocks", "Templates", or "All-Access" is paid — mine only from the /components index, and only post-clearance.
4. **three.js / WebGL components — do not mine** (three.js is not in the kit): Aceternity *Canvas Reveal Effect*, *GitHub Globe*, *3D Globe*, *Dither Shader*, *Vortex Background* (heavy canvas + simplex-noise); React Bits WebGL backgrounds (ogl/three). Magic UI *Globe* needs the `cobe` dep — skip.
5. **Hidden small deps to inline or avoid**: Aceternity *Sparkles* pulls `@tsparticles/*` (heavy — use Magic UI *Particles* instead, zero-dep); Aceternity *Wavy Background* needs `simplex-noise` (tiny, could be inlined, but Aurora Background covers the niche); Magic UI *Confetti* needs `canvas-confetti`; Magic UI/Aceternity *Dotted Map / World Map* need `dotted-map`. None of these justify a new package under the "no new deps" rule.
6. **Magic UI "Light Rays" and some community components** may use WebGL/heavier canvas — verify each file's imports at copy time; the rule is: if the component imports anything beyond react/motion/clsx/tailwind, it must be inlined or rejected.
7. **Lenis package identity**: use `lenis` from darkroomengineering; the old `@studio-freight/lenis` is the same code but deprecated — don't let the LLM or a copied snippet import the dead package name.
8. **dotLottie WASM**: `@lottiefiles/dotlottie-react` fetches a WASM renderer; confirm it bundles/self-hosts offline before adding, or generated previews gain a runtime CDN dependency.
9. **Attribution**: even for verified-MIT mining, add `ATTRIBUTIONS.md` to the preview template (Magic UI © magicuidesign, MIT; Lenis © darkroom.engineering, MIT; dotLottie © LottieFiles, MIT) to satisfy MIT's notice-preservation clause.

## Sources

- Magic UI repo + LICENSE: <https://github.com/magicuidesign/magicui>, <https://github.com/magicuidesign/magicui/blob/main/LICENSE.md>
- Magic UI component index: <https://magicui.design/docs/components>
- React Bits repo + LICENSE: <https://github.com/DavidHDev/react-bits>, <https://github.com/DavidHDev/react-bits/blob/main/LICENSE.md>
- Aceternity free component index: <https://ui.aceternity.com/components>; licence page: <https://ui.aceternity.com/licence>; Pro: <https://pro.aceternity.com/licence>; official GitHub org: <https://github.com/aceternity>
- Lenis: <https://github.com/darkroomengineering/lenis> (LICENSE: <https://github.com/darkroomengineering/lenis/blob/main/LICENSE>)
- dotLottie: <https://github.com/LottieFiles/dotlottie-web> (LICENSE: <https://github.com/LottieFiles/dotlottie-web/blob/main/LICENSE>)
