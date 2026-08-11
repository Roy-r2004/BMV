#!/usr/bin/env python3
"""Roadmap 3.7, baseline half: how many distinct page silhouettes does HEAD's
stored corpus actually hold, and what share does the top silhouette own?

QUESTION
    "Most generations are the same template" — quantify it. Per the owner's
    block prompt a silhouette is the per-page tuple
        (section sequence, skeleton, overlay, palette)
    over the two stored corpora:
      (a) the 58 archived workspaces in docs/evidence/preview-workspaces.tar.gz
      (b) the 47 kind_contexts in docs/evidence/preview-routes.json
    The distinct-silhouette count and the top-silhouette share become the
    baseline a later distinctness gate red-exits against, and an input to the
    owner's Phase-3 designer decision.

METHOD
    Extract the tarball to a temp dir. The tarball was REFRESHED 2026-08-05
    from 58 to 67 top-level dirs (docs/evidence/README.md: requests 1, 93-98,
    101-102 were added; 1 is empty, 93-98/101-102 are the catalogue-era octet).
    The 3.7 corpus is the ORIGINAL 58 = every dir except {1, 93..98, 101, 102}.
    Both facts are asserted (67 extracted, 58 after exclusion).

    Per workspace page (src/pages/**/*.tsx), the four components are realized
    from what the workspace actually stores:

      skeleton   the `SKELETON_ID = "..."` constant of catalogue-contract
                 scaffold pages; else a literal `data-skeleton="..."`
                 attribute; else "(none)".
      section    the RENDERED order, reproduced from SkeletonComposer's
      sequence   resolveOrder semantics (preview-template
                 src/ui/compose/SkeletonComposer.tsx): with RECIPE_ORDER the
                 order owns the face (filtered to declared slots, required
                 declared slots appended); without it the skeleton's
                 recommendedOrder filtered to declared slots, leftover declared
                 slots appended in declaration order. Slot names come from the
                 `const slots = {` object keys (line-anchored `key: (`,
                 minimum-indent level — validated 537/537 scaffold pages parse,
                 0 with zero keys). Each slot is mapped to the first
                 capitalized JSX component inside it so the sequence is
                 "top-level section components in order"; the slot-NAME
                 sequence is kept alongside because it is the vocabulary the
                 kind_context corpus stores. Non-scaffold ("freeform") pages
                 get the first-occurrence order of catalogue section
                 components (registry surfaces public+ops minus the chrome:
                 PublicShell/PublicNav/OpsShell); a freeform page using none
                 of them (the stock raw-div admin pages) gets the empty
                 sequence — honest: those pages are one hardcoded template.
      overlay    `design_overlay_id` inside the `export const brand`
                 design_system of src/data/mock.ts (the design_overlay.py
                 mood; quoted or unquoted key). Absent in pre-overlay
                 workspaces -> "(none)". The overlay-qualified RECIPE_ID
                 suffix (e.g. dense-ops-ledger) is reported in the breakdown.
      palette    `primary_color` of the same design_system block (quoted or
                 unquoted, first match after `export const brand` so the
                 secondary BRAND_MANIFEST copy cannot shadow it), lowercased.

    Per kind_context route (preview-routes.json .[].routes[]), the stored
    fields are `skeleton_id` and `section_slots` ONLY — no overlay, no palette
    is stored there. Its silhouette is therefore the 2-tuple
    (skeleton, section_slots); the corpora are NOT fully comparable and are
    never pretended to be. The cross-corpus comparable tuple is
    (skeleton, slot-name sequence), computed for both and combined, with the
    caveat printed that freeform workspace pages carry component-name
    vocabulary in that field.

    Page classes: home = skeleton public-home, or filename HomePage.tsx /
    route path "/" / page_id marketing-home where no skeleton is stored;
    catalogue = skeleton public-catalog, or (no skeleton stored) filename
    stem in Gallery/Collection/Catalog(ue)/Shop/Menu.

JUDGMENT CALLS
    1. The 58-corpus is derived by exclusion, not by trusting dir count:
       {1, 93-98, 101-102} are the documented 2026-08-05 additions. RED if
       either the 67 or the 58 drifts.
    2. Rendered order for no-RECIPE_ORDER scaffold pages uses HEAD's skeleton
       registry (preview-template src/ui/catalogue.json recommendedOrder /
       requiredSections). The 58 workspaces do not archive their own registry
       (only the excluded octet ships src/ui), so HEAD's stands in. RED if a
       scaffold page names a skeleton HEAD's registry lacks.
    3. RECIPE_ORDER entries naming never-declared slots (3 pages) drop out,
       exactly as the composer's `slots[section] != null` filter drops them.
    4. Palette is design_system.primary_color, not brand.accent: accent is
       absent from 34/58 while primary_color is present in 58/58; where both
       exist they agree with the palette-census field choice (README).
    5. A page-count cross-check is baked: content_census measured 753 page
       files over these same 58 workspaces. RED if that drifts — the tarball
       was swapped and this census would be measuring something else.
    6. Routes with skeleton_id ''/None -> "(none)"; section_slots None ->
       empty sequence. Counts of both are printed, not hidden.

RED-EXIT (loud, non-zero) when any baked assumption drifts:
    tarball / routes json / template catalogue.json missing; extracted dirs
    != 67; 58-corpus != 58; kind_contexts != 47 or any entry missing
    kind_context; corpus page files != 753; any workspace missing
    recipe-id.ts / mock.ts / RECIPE_ID / primary_color; a scaffold page whose
    slots object yields zero keys; a scaffold SKELETON_ID absent from HEAD's
    registry; registry entries missing recommendedOrder/requiredSections.

Read-only over the repo; writes its JSON archive to
docs/evidence/session25/silhouette-census.json. Run:

    docker run --rm -v "$REPO:/repo" -w /repo/backend \
      -e PREVIEW_TEMPLATE_DIR=/repo/backend/preview-template --entrypoint sh \
      bmv-local-api -c 'python3 scripts/measure/silhouette_census.py'
"""
from __future__ import annotations

import json
import os
import re
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TARBALL = REPO / "docs" / "evidence" / "preview-workspaces.tar.gz"
ROUTES_JSON = REPO / "docs" / "evidence" / "preview-routes.json"
TEMPLATE_DIR = Path(os.environ.get("PREVIEW_TEMPLATE_DIR", str(REPO / "backend" / "preview-template")))
CATALOGUE_JSON = TEMPLATE_DIR / "src" / "ui" / "catalogue.json"
OUT_JSON = REPO / "docs" / "evidence" / "session25" / "silhouette-census.json"

EXPECTED_TARBALL_DIRS = 67
ADDED_2026_08_05 = {"1", "93", "94", "95", "96", "97", "98", "101", "102"}
EXPECTED_CORPUS = 58
EXPECTED_KIND_CONTEXTS = 47
EXPECTED_PAGE_FILES = 753  # content_census.py cross-check, same 58 workspaces

SKEL_RE = re.compile(r'SKELETON_ID\s*=\s*"([^"]+)"')
ORDER_RE = re.compile(r"RECIPE_ORDER\s*=\s*\[([^\]]*)\]")
SLOTS_OPEN_RE = re.compile(r"^\s*const slots(?:\s*:\s*\w+)?\s*=\s*\{\s*$", re.M)
SLOT_KEY_RE = re.compile(r"^([ \t]+)(\w+):[ \t]*\([ \t]*$", re.M)
SLOTS_CLOSE_RE = re.compile(r"^\s*\};\s*$", re.M)
DATA_SKEL_RE = re.compile(r'data-skeleton="([^"]+)"')
BRAND_RE = re.compile(r"export const brand\b")
PRIMARY_RE = re.compile(r"""["']?primary_color["']?\s*:\s*["'](#[0-9a-fA-F]{3,8})["']""")
OVERLAY_RE = re.compile(r"""["']?design_overlay_id["']?\s*:\s*["']([a-z_]+)["']""")
RECIPE_ID_RE = re.compile(r'RECIPE_ID\s*=\s*"([^"]+)"')
FIRST_COMPONENT_RE = re.compile(r"<([A-Z][A-Za-z0-9]*)")

RECIPE_FAMILIES = ("editorial", "dense-ops", "warm-service", "bold-retail", "nocturne", "craft")

CATALOG_STEMS = {"GalleryPage", "CollectionPage", "CatalogPage", "CataloguePage", "ShopPage", "MenuPage"}

NONE = "(none)"


def red(msg: str) -> None:
    print(f"\nRED-EXIT: {msg}", file=sys.stderr)
    print("RED-EXIT: a baked assumption drifted; this census refuses to measure the wrong thing.", file=sys.stderr)
    sys.exit(2)


def load_registry() -> dict[str, dict]:
    if not CATALOGUE_JSON.exists():
        red(f"template catalogue missing: {CATALOGUE_JSON}")
    cat = json.loads(CATALOGUE_JSON.read_text())
    reg: dict[str, dict] = {}
    for sk in cat.get("skeletons", []):
        if "recommendedOrder" not in sk or "requiredSections" not in sk:
            red(f"skeleton {sk.get('id')!r} lacks recommendedOrder/requiredSections — registry schema drifted")
        reg[sk["id"]] = sk
    if not reg:
        red("template catalogue.json holds zero skeletons")
    section_vocab = {
        c["name"]
        for c in cat.get("components", [])
        if c.get("surface") in ("public", "ops") and c["name"] not in ("PublicShell", "PublicNav", "OpsShell")
    }
    if not section_vocab:
        red("template catalogue.json yields an empty section-component vocabulary")
    reg["__section_vocab__"] = section_vocab  # type: ignore[assignment]
    return reg


def resolve_order(skeleton: dict, declared: list[str], order: list[str] | None) -> list[str]:
    """Port of SkeletonComposer.resolveOrder — the rendered section order."""
    base = order if order else [s for s in skeleton["recommendedOrder"]]
    seq = [s for s in base if s != "shell" and s in declared]
    if order:
        for s in skeleton["requiredSections"]:
            if s != "shell" and s in declared and s not in seq:
                seq.append(s)
        return seq
    for s in declared:
        if s != "shell" and s not in seq:
            seq.append(s)
    return seq


def parse_workspace_page(text: str, registry: dict) -> dict | None:
    """Returns skeleton, slot sequence, component sequence, style flags."""
    vocab = registry["__section_vocab__"]
    m = SKEL_RE.search(text)
    if m:
        skeleton = m.group(1)
        if skeleton not in registry:
            return {"error": f"scaffold skeleton {skeleton!r} not in HEAD registry"}
        om = SLOTS_OPEN_RE.search(text)
        if not om:
            return {"error": "scaffold page without a `const slots = {` object"}
        cm = SLOTS_CLOSE_RE.search(text, om.end())
        body = text[om.end() : cm.start() if cm else len(text)]
        hits = list(SLOT_KEY_RE.finditer(body))
        if not hits:
            return {"error": "scaffold slots object yields zero keys"}
        min_indent = min(len(h.group(1)) for h in hits)
        top = [h for h in hits if len(h.group(1)) == min_indent]
        declared = [h.group(2) for h in top]
        slot_component: dict[str, str] = {}
        for i, h in enumerate(top):
            span = body[h.end() : top[i + 1].start() if i + 1 < len(top) else len(body)]
            fc = FIRST_COMPONENT_RE.search(span)
            slot_component[h.group(2)] = fc.group(1) if fc else f"({h.group(2)})"
        order_m = ORDER_RE.search(text)
        order = None
        if order_m:
            order = [s.strip().strip("\"'") for s in order_m.group(1).split(",") if s.strip()]
        slot_seq = resolve_order(registry[skeleton], declared, order)
        comp_seq = [slot_component[s] for s in slot_seq]
        return {"style": "scaffold", "skeleton": skeleton, "slot_seq": slot_seq, "comp_seq": comp_seq}
    # freeform: literal data-skeleton attr if present; section components in
    # first-occurrence order from the JSX region.
    dm = DATA_SKEL_RE.search(text)
    skeleton = dm.group(1) if dm else NONE
    ret = text.find("return (")
    region = text[ret:] if ret >= 0 else text
    seen: list[str] = []
    for cm2 in FIRST_COMPONENT_RE.finditer(region):
        name = cm2.group(1)
        if name in vocab and name not in seen:
            seen.append(name)
    return {"style": "freeform", "skeleton": skeleton, "slot_seq": seen, "comp_seq": seen}


def classify(skeleton: str, stem: str) -> str:
    if skeleton == "public-home" or (skeleton == NONE and stem == "HomePage"):
        return "home"
    if skeleton == "public-catalog" or (skeleton == NONE and stem in CATALOG_STEMS):
        return "catalogue"
    return "other"


def recipe_overlay_suffix(recipe_id: str) -> str:
    for fam in sorted(RECIPE_FAMILIES, key=len, reverse=True):
        if recipe_id == fam:
            return NONE
        if recipe_id.startswith(fam + "-"):
            return recipe_id[len(fam) + 1 :]
    return NONE


def share(counter: Counter, total: int) -> dict:
    if total == 0:
        return {"distinct": 0, "top": None, "top_count": 0, "top_share": None, "total": 0}
    top, top_count = counter.most_common(1)[0]
    return {
        "distinct": len(counter),
        "top": list(top) if isinstance(top, tuple) else top,
        "top_count": top_count,
        "top_share": round(top_count / total, 4),
        "total": total,
    }


def fmt_share(label: str, s: dict) -> str:
    if s["total"] == 0:
        return f"  {label:<18} (no pages in class)"
    return (
        f"  {label:<18} {s['distinct']:>4} distinct over {s['total']:>4} pages | "
        f"top holds {s['top_count']} = {s['top_share'] * 100:.1f}%"
    )


def main() -> int:
    print("silhouette_census — roadmap 3.7 baseline: distinct page silhouettes on HEAD's stored corpus")
    print(f"tuple: (section sequence, skeleton, overlay, palette) | date 2026-08-07\n")

    for p in (TARBALL, ROUTES_JSON):
        if not p.exists():
            red(f"corpus file missing: {p}")
    registry = load_registry()

    # ---- corpus (a): the 58 archived workspaces --------------------------
    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(TARBALL) as tf:
            tf.extractall(td, filter="data")
        root = Path(td)
        dirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda p: int(p.name))
        if len(dirs) != EXPECTED_TARBALL_DIRS:
            red(
                f"tarball holds {len(dirs)} top-level dirs, expected {EXPECTED_TARBALL_DIRS} "
                f"(the 2026-08-05 refresh state). The archive changed; re-derive the 58-corpus rule."
            )
        corpus = [d for d in dirs if d.name not in ADDED_2026_08_05]
        if len(corpus) != EXPECTED_CORPUS:
            red(f"58-corpus rule yields {len(corpus)} workspaces, expected {EXPECTED_CORPUS}")

        pages: list[dict] = []
        ws_meta: dict[str, dict] = {}
        parse_errors: list[str] = []
        for d in corpus:
            mock = d / "src" / "data" / "mock.ts"
            rid_f = d / "src" / "lib" / "recipe-id.ts"
            if not mock.exists():
                red(f"workspace {d.name} has no src/data/mock.ts")
            if not rid_f.exists():
                red(f"workspace {d.name} has no src/lib/recipe-id.ts")
            mt = mock.read_text()
            bm = BRAND_RE.search(mt)
            start = bm.end() if bm else 0
            pm = PRIMARY_RE.search(mt, start)
            if not pm:
                red(f"workspace {d.name} mock.ts has no design_system primary_color")
            ovm = OVERLAY_RE.search(mt, start)
            rm = RECIPE_ID_RE.search(rid_f.read_text())
            if not rm:
                red(f"workspace {d.name} recipe-id.ts has no RECIPE_ID")
            recipe_id = rm.group(1)
            ws_meta[d.name] = {
                "palette": pm.group(1).lower(),
                "overlay": ovm.group(1) if ovm else NONE,
                "recipe_id": recipe_id,
                "recipe_overlay_suffix": recipe_overlay_suffix(recipe_id),
            }
            for f in sorted((d / "src" / "pages").rglob("*.tsx")):
                if f.name.startswith("._"):
                    # macOS AppleDouble resource forks ride along in the tarball;
                    # on Linux they extract as real files. Not pages — skip.
                    continue
                parsed = parse_workspace_page(f.read_text(errors="replace"), registry)
                if parsed is None or "error" in (parsed or {}):
                    parse_errors.append(f"{d.name}/{f.relative_to(d).as_posix()}: {parsed['error']}")
                    continue
                meta = ws_meta[d.name]
                pages.append(
                    {
                        "workspace": d.name,
                        "file": f.relative_to(d).as_posix(),
                        "style": parsed["style"],
                        "skeleton": parsed["skeleton"],
                        "slot_seq": parsed["slot_seq"],
                        "comp_seq": parsed["comp_seq"],
                        "overlay": meta["overlay"],
                        "palette": meta["palette"],
                        "recipe_id": meta["recipe_id"],
                        "page_class": classify(parsed["skeleton"], f.stem),
                    }
                )
        if parse_errors:
            red("page parse assumptions broke:\n  " + "\n  ".join(parse_errors[:10]))
        if len(pages) != EXPECTED_PAGE_FILES:
            red(f"58-corpus page files = {len(pages)}, expected {EXPECTED_PAGE_FILES} (content_census cross-check)")

    def sil(p: dict) -> tuple:
        return (tuple(p["comp_seq"]), p["skeleton"], p["overlay"], p["palette"])

    def sil_slots(p: dict) -> tuple:
        return (tuple(p["slot_seq"]), p["skeleton"], p["overlay"], p["palette"])

    full = Counter(sil(p) for p in pages)
    full_slots = Counter(sil_slots(p) for p in pages)
    by_class = {
        c: Counter(sil(p) for p in pages if p["page_class"] == c) for c in ("home", "catalogue")
    }
    n_home = sum(by_class["home"].values())
    n_cat = sum(by_class["catalogue"].values())

    comp_values = {
        "section_sequence": Counter(tuple(p["comp_seq"]) for p in pages),
        "skeleton": Counter(p["skeleton"] for p in pages),
        "overlay": Counter(p["overlay"] for p in pages),
        "palette": Counter(p["palette"] for p in pages),
    }
    drop_idx = {"section_sequence": 0, "skeleton": 1, "overlay": 2, "palette": 3}
    leave_one_out = {
        name: len(Counter(tuple(v for j, v in enumerate(sil(p)) if j != i) for p in pages))
        for name, i in drop_idx.items()
    }

    sites = Counter(
        tuple(sorted((p["file"], *map(str, sil(p))) for p in pages if p["workspace"] == w))
        for w in ws_meta
    )

    print("corpus (a): 58 archived workspaces — verified 67 tarball dirs, minus the documented")
    print(f"2026-08-05 additions {sorted(ADDED_2026_08_05, key=int)} -> {len(ws_meta)} workspaces, {len(pages)} pages")
    n_scaffold = sum(1 for p in pages if p["style"] == "scaffold")
    print(f"  page styles: {n_scaffold} catalogue-contract scaffold / {len(pages) - n_scaffold} freeform")
    print(f"  page classes: {n_home} home, {n_cat} catalogue, {len(pages) - n_home - n_cat} other\n")

    print("A. WORKSPACE SILHOUETTES — (section-component sequence, skeleton, overlay, palette)")
    a_all = share(full, len(pages))
    print(fmt_share("all pages", a_all))
    a_home = share(by_class["home"], n_home)
    a_cat = share(by_class["catalogue"], n_cat)
    print(fmt_share("home pages", a_home))
    print(fmt_share("catalogue pages", a_cat))
    a_slots = share(full_slots, len(pages))
    print(f"  (slot-name realization of the same tuple: {a_slots['distinct']} distinct, top {a_slots['top_share']*100:.1f}%)")
    a_sites = share(sites, len(ws_meta))
    print(f"  whole-site silhouettes: {a_sites['distinct']} distinct over {len(ws_meta)} sites | top holds {a_sites['top_count']} = {a_sites['top_share']*100:.1f}%\n")

    print("  top 5 page silhouettes:")
    for t, c in full.most_common(5):
        seq, sk, ov, pal = t
        print(f"    {c:>3}x  skeleton={sk} overlay={ov} palette={pal}")
        print(f"          sections: {' > '.join(seq) if seq else '(no catalogue sections)'}")

    print("\n  per-component contribution (distinct values alone | tuple distinct without it, of {}):".format(a_all["distinct"]))
    for name in drop_idx:
        print(
            f"    {name:<17} {len(comp_values[name]):>4} distinct alone | drop it -> {leave_one_out[name]:>4} "
            f"(carries +{a_all['distinct'] - leave_one_out[name]})"
        )
    print(f"    overlay values   : {dict(comp_values['overlay'].most_common())}")
    print(f"    palette values   : {dict(comp_values['palette'].most_common())}")
    print(f"    skeleton values  : {dict(comp_values['skeleton'].most_common())}")
    print(f"    recipe ids (context, not in tuple): {dict(Counter(m['recipe_id'] for m in ws_meta.values()))}")

    # ---- corpus (b): the 47 kind_contexts --------------------------------
    routes_doc = json.loads(ROUTES_JSON.read_text())
    if len(routes_doc) != EXPECTED_KIND_CONTEXTS:
        red(f"preview-routes.json holds {len(routes_doc)} entries, expected {EXPECTED_KIND_CONTEXTS}")
    for k, v in routes_doc.items():
        if not str(v.get("kind_context", "")).strip():
            red(f"preview-routes.json entry {k} has no kind_context")

    routes: list[dict] = []
    for k, v in routes_doc.items():
        for r in v.get("routes", []):
            sk = r.get("skeleton_id") or NONE
            ss = r.get("section_slots")
            seq = tuple(ss) if isinstance(ss, list) else tuple()
            pid = r.get("page_id") or ""
            path = r.get("path") or ""
            cls = "home" if (sk == "public-home" or (sk == NONE and (pid == "marketing-home" or path == "/"))) else (
                "catalogue" if sk == "public-catalog" else "other"
            )
            routes.append({"request": k, "path": path, "skeleton": sk, "slot_seq": list(seq), "page_class": cls})

    r_sil = Counter((tuple(r["slot_seq"]), r["skeleton"]) for r in routes)
    r_by_class = {
        c: Counter((tuple(r["slot_seq"]), r["skeleton"]) for r in routes if r["page_class"] == c)
        for c in ("home", "catalogue")
    }
    rn_home = sum(r_by_class["home"].values())
    rn_cat = sum(r_by_class["catalogue"].values())
    r_no_sk = sum(1 for r in routes if r["skeleton"] == NONE)
    r_no_ss = sum(1 for r in routes if not r["slot_seq"])
    r_sites = Counter(
        tuple(sorted((r["path"], r["skeleton"], ">".join(r["slot_seq"])) for r in routes if r["request"] == k))
        for k in routes_doc
    )

    print(f"\ncorpus (b): 47 kind_contexts, {len(routes)} routes — stored fields are skeleton_id +")
    print("section_slots ONLY (no overlay, no palette is stored per route); the corpora are not")
    print("fully comparable and this census does not pretend they are.")
    print(f"  routes without skeleton_id: {r_no_sk}; without section_slots: {r_no_ss}\n")
    print("B. KIND_CONTEXT SILHOUETTES — (section_slots, skeleton) [2-tuple, all the corpus stores]")
    b_all = share(r_sil, len(routes))
    print(fmt_share("all routes", b_all))
    b_home = share(r_by_class["home"], rn_home)
    b_cat = share(r_by_class["catalogue"], rn_cat)
    print(fmt_share("home routes", b_home))
    print(fmt_share("catalogue routes", b_cat))
    b_sites = share(r_sites, len(routes_doc))
    print(f"  whole-site (per kind_context): {b_sites['distinct']} distinct over {len(routes_doc)} | top holds {b_sites['top_count']} = {b_sites['top_share']*100:.1f}%")
    print("  top 5 route silhouettes:")
    for (seq, sk), c in r_sil.most_common(5):
        print(f"    {c:>3}x  skeleton={sk} sections: {' > '.join(seq) if seq else '(none stored)'}")
    r_comp = {
        "section_sequence": Counter(tuple(r["slot_seq"]) for r in routes),
        "skeleton": Counter(r["skeleton"] for r in routes),
    }
    print("  per-component: "
          f"section_sequence {len(r_comp['section_sequence'])} distinct alone, "
          f"skeleton {len(r_comp['skeleton'])} distinct alone")

    # ---- combined on the comparable subset -------------------------------
    ws_pairs = Counter((tuple(p["slot_seq"]), p["skeleton"]) for p in pages)
    combined = ws_pairs + r_sil
    total_comb = len(pages) + len(routes)
    c_all = share(combined, total_comb)
    overlap = sorted(set(routes_doc) & set(ws_meta), key=int)
    print("\nC. COMBINED on the comparable 2-tuple (section sequence, skeleton) — workspace pages")
    print("use slot names where scaffolded and catalogue component names where freeform (stated,")
    print("not hidden); kind_context routes use their stored section_slots.")
    print(fmt_share("all pages+routes", c_all))
    ws_only = set(ws_pairs) - set(r_sil)
    r_only = set(r_sil) - set(ws_pairs)
    print(f"  tuples seen only in workspaces: {len(ws_only)}; only in kind_contexts: {len(r_only)}; shared: {len(set(ws_pairs) & set(r_sil))}")
    print(f"  request-id overlap between corpora: {len(overlap)} of 47 kind_contexts also have an archived workspace: {overlap}")

    # ---- archive ---------------------------------------------------------
    out = {
        "question": "roadmap 3.7 baseline: distinct page silhouettes on HEAD's stored corpus",
        "date": "2026-08-07",
        "tuple": ["section_sequence", "skeleton", "overlay", "palette"],
        "corpus_a": {
            "workspaces": len(ws_meta),
            "pages": len(pages),
            "scaffold_pages": n_scaffold,
            "freeform_pages": len(pages) - n_scaffold,
            "silhouettes": {
                "all": a_all,
                "home": a_home,
                "catalogue": a_cat,
                "slot_name_realization": a_slots,
                "whole_site": a_sites,
            },
            "component_distinct_alone": {k: len(v) for k, v in comp_values.items()},
            "component_leave_one_out": leave_one_out,
            "overlay_distribution": dict(comp_values["overlay"].most_common()),
            "palette_distribution": dict(comp_values["palette"].most_common()),
            "skeleton_distribution": dict(comp_values["skeleton"].most_common()),
            "recipe_id_distribution": dict(Counter(m["recipe_id"] for m in ws_meta.values())),
            "top10": [
                {"count": c, "sections": list(t[0]), "skeleton": t[1], "overlay": t[2], "palette": t[3]}
                for t, c in full.most_common(10)
            ],
            "pages_detail": pages,
        },
        "corpus_b": {
            "kind_contexts": len(routes_doc),
            "routes": len(routes),
            "fields_stored": ["skeleton_id", "section_slots"],
            "comparability": "no overlay/palette stored — 2-tuple only, never merged with the 4-tuple",
            "routes_without_skeleton": r_no_sk,
            "routes_without_section_slots": r_no_ss,
            "silhouettes": {"all": b_all, "home": b_home, "catalogue": b_cat, "whole_site": b_sites},
            "component_distinct_alone": {k: len(v) for k, v in r_comp.items()},
            "top10": [
                {"count": c, "sections": list(t[0]), "skeleton": t[1]} for t, c in r_sil.most_common(10)
            ],
            "routes_detail": routes,
        },
        "combined_comparable_2tuple": {
            "all": c_all,
            "workspace_only_tuples": len(ws_only),
            "kind_context_only_tuples": len(r_only),
            "shared_tuples": len(set(ws_pairs) & set(r_sil)),
            "request_id_overlap": overlap,
            "caveat": "freeform workspace pages carry component-name vocabulary in the sequence field",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=1))
    print(f"\narchived: {OUT_JSON}")
    print("silhouette_census: GREEN (all baked assumptions held)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
