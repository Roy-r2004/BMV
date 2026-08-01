"""One catalogue for the whole app.

`seed.items` is the only list the detail route resolves against. When a listing
page hands `CatalogGrid` (or the home page hands `ProductShowcase`) its own
literal array, three things go wrong at once and none of them are visible to a
compiler or a route table:

* **Identity.** Request 40's `/gallery` numbered its cards `id: '1'…'6'` while
  `seed.items` are slugs, so all six cards linked to `/artwork/1…6` and every one
  of them rendered *"We could not find that one."* The journey walk still passed:
  it checks that the detail page reads a route param, not that the ids the browse
  page emits exist in the data the detail page reads.
* **Truth.** The home page invented three more works (`Whispers of the Horizon`,
  `Beneath the Surface`, `Echoes in Blue`) that appear in no data file, and the
  owner dashboard invented a fourth set. Four disjoint catalogues, one business.
* **Count.** The grid header said "8 paintings" over 6 tiles.

So the array is rewritten to derive from `seed.items`. Headings, descriptions and
layout stay exactly as authored — only the item source changes.
"""
from __future__ import annotations

import re

from app.application.services.industry_images import item_slot_names

_ITEMS_PROP_RE = re.compile(r"\bitems=\{\s*\[")
_LISTING_COMPONENTS = ("CatalogGrid", "ProductShowcase")

# One photograph per catalogue position. `normalize_image_slot_map` guarantees
# `item1..item8` exist, so this never reads an undefined key, and the pool is as
# long as the grid — request 40 showed `card1` for both "Whispering Winds" and
# "Desert Bloom" because its pool was three deep.
#
# Derived from the imagery service rather than restated, so the pool the pages
# read and the pool the fetcher fills cannot drift apart.
_IMAGE_POOL_SLOTS = item_slot_names()
_IMAGE_POOL_SIZE = len(_IMAGE_POOL_SLOTS)
_IMAGE_POOL = "[" + ", ".join(f"images.{s}" for s in _IMAGE_POOL_SLOTS) + "]"


def _matching_bracket(src: str, open_idx: int) -> int:
    """Index just past the `]` that closes the `[` at `open_idx`, or -1.

    String- *and* comment-aware. Both matter, and the second one bit hard: the
    model writes explanatory `//` comments inside its arrays, request 41's home
    page had one reading "rely on component's internal design", and treating that
    apostrophe as a string opener desynchronised the scan for the rest of the
    file. A codemod that cannot be certain where the literal ends must do nothing.
    """
    depth = 0
    i = open_idx
    quote = ""
    while i < len(src):
        ch = src[i]
        pair = src[i : i + 2]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if pair == "//":
            newline = src.find("\n", i)
            if newline == -1:
                return -1
            i = newline + 1
            continue
        if pair == "/*":
            close = src.find("*/", i + 2)
            if close == -1:
                return -1
            i = close + 2
            continue
        if ch in "\"'`":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _element_name_before(src: str, idx: int) -> str:
    """Name of the JSX element whose attribute list contains `idx`."""
    open_idx = src.rfind("<", 0, idx)
    while open_idx != -1:
        m = re.match(r"<\s*([A-Za-z_][\w.]*)", src[open_idx:])
        if m:
            close = src.find(">", open_idx)
            if close == -1 or close > idx:
                return m.group(1)
        open_idx = src.rfind("<", 0, open_idx)
    return ""


def _catalog_items_expr(detail_base: str) -> str:
    href = (
        f"    href: `{detail_base}/${{String(it.slug ?? it.id ?? i + 1)}}`,\n"
        if detail_base
        else ""
    )
    return (
        "{(seed.items ?? []).map((it: any, i: number) => ({\n"
        "    id: String(it.slug ?? it.id ?? i + 1),\n"
        "    title: String(it.title ?? it.name ?? ''),\n"
        "    description: String(it.description ?? ''),\n"
        f"    imageSrc: String(it.image ?? {_IMAGE_POOL}[i % {_IMAGE_POOL_SIZE}]),\n"
        "    imageAlt: String(it.title ?? it.name ?? ''),\n"
        "    meta: it.medium ? String(it.medium) : (it.price ? String(it.price) : undefined),\n"
        "    category: it.category ? String(it.category) : undefined,\n"
        "    status: it.status ? String(it.status) : undefined,\n"
        "    badge: it.badge ? String(it.badge) : undefined,\n"
        f"{href}"
        "  }))}"
    )


def _showcase_items_expr(detail_base: str) -> str:
    href = (
        f"    href: `{detail_base}/${{String(it.slug ?? it.id ?? i + 1)}}`,\n"
        if detail_base
        else ""
    )
    # ProductShowcase is an editorial mosaic capped at three; slicing here keeps
    # the "and a fourth image is half-cropped" layout bug from coming back.
    return (
        "{(seed.items ?? []).slice(0, 3).map((it: any, i: number) => ({\n"
        "    title: String(it.title ?? it.name ?? ''),\n"
        "    description: String(it.description ?? ''),\n"
        f"    imageSrc: String(it.image ?? {_IMAGE_POOL}[i % {_IMAGE_POOL_SIZE}]),\n"
        "    imageAlt: String(it.title ?? it.name ?? ''),\n"
        "    badge: it.badge ? String(it.badge) : (it.status ? String(it.status) : undefined),\n"
        f"{href}"
        "  }))}"
    )


def _has_object_items(literal: str) -> bool:
    """True when the literal is a list of objects, i.e. an inlined catalogue."""
    return "{" in literal and re.search(r"\b(title|name)\s*:", literal) is not None


def unify_catalogue_item_source(content: str, *, detail_base: str = "") -> tuple[str, list[str]]:
    """Point every listing component at `seed.items`. Returns (content, changed).

    Idempotent: the scaffolds already derive from `seed`, and a derived expression
    is not a literal, so it is skipped. Leaves the file untouched on anything it
    cannot parse with certainty.
    """
    if not content or "seed.items" not in content and "seed" not in content:
        # Still fine to rewrite — the import guard adds `seed` — but a file with
        # no mock import at all is not a page this codemod understands.
        if "@/data/mock" not in content:
            return content, []
    changed: list[str] = []
    out = content
    searched_from = 0
    while True:
        m = _ITEMS_PROP_RE.search(out, searched_from)
        if not m:
            break
        open_idx = out.index("[", m.start())
        end = _matching_bracket(out, open_idx)
        if end == -1:
            # One unreadable array must not cost the file its other listings.
            searched_from = open_idx + 1
            continue
        # `items={[...]}` — the `}` that closes the expression container.
        brace_end = out.find("}", end)
        if brace_end == -1 or out[end:brace_end].strip():
            searched_from = end
            continue
        element = _element_name_before(out, m.start())
        literal = out[open_idx:end]
        if element not in _LISTING_COMPONENTS or not _has_object_items(literal):
            searched_from = brace_end
            continue
        replacement = (
            _showcase_items_expr(detail_base)
            if element == "ProductShowcase"
            else _catalog_items_expr(detail_base)
        )
        out = out[: m.start()] + "items=" + replacement + out[brace_end + 1 :]
        changed.append(element)
        searched_from = m.start() + len("items=") + len(replacement)
    if not changed:
        return content, []
    if not re.search(r"import\s*\{[^}]*\bseed\b[^}]*\}\s*from\s*['\"]@/data/mock['\"]", out):
        out = _ensure_mock_named_import(out, "seed")
    if "images." in out and not re.search(
        r"import\s*\{[^}]*\bimages\b[^}]*\}\s*from\s*['\"]@/data/mock['\"]", out
    ):
        out = _ensure_mock_named_import(out, "images")
    return out, changed


_ITEMS_KEY_RE = re.compile(r"(?<![A-Za-z0-9_$.])['\"]?items['\"]?\s*:\s*\[")
_ITEM_IMAGE_BINDING_RE = re.compile(
    r"\b(?:image|imageSrc|imageUrl|thumbnail|photo)\s*:\s*images\s*\.\s*"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)


def rebind_catalogue_item_images(source: str) -> tuple[str, int]:
    """Force every catalogue photo onto the ``item*`` pool. Returns (source, rebound).

    The imagery service supplies a fixed number of `item*` slots; the mock writer
    is asked for "10–20 items for catalogs" and is handed the *whole* slot map, so
    on request 70 it wrote eleven artworks, ran out at `images.item8`, and
    continued into `images.card1`, `card2`, `card3` (`src/data/mock.ts:459,471,483`).
    `card2` and `card3` are the "customer experience" and "team service" role
    slots — the two the item ranker pushes to the back *precisely because their
    photographs show people* — so "Still Life with Pears · Oil on Panel" and
    "Forest Edge Path · Oil on Linen" shipped as photographs of a person at an easel.

    Capping the item count would have fixed the photograph by deleting three real
    artworks, and extending the pool cannot hold: the pool is sized during planning
    and the item count is chosen later by the model, so any fixed size is a bound
    the model can exceed. Cycling within `item*` is the only form of the fix that
    makes the defect unrepresentable at any item count.

    Positions are counted over image *bindings* in source order, which is the
    catalogue order whenever items bind their photos the same way — and an item
    that carries a literal URL instead of a slot is left alone, so it neither
    shifts the ring nor gets overwritten.

    Idempotent, and a no-op on any array whose end this cannot locate with
    certainty.
    """
    if not source or "images." not in source:
        return source, 0
    pool = _IMAGE_POOL_SLOTS
    if not pool:
        return source, 0
    allowed = set(pool)
    edits: list[tuple[int, int, str]] = []
    searched_from = 0
    while True:
        key = _ITEMS_KEY_RE.search(source, searched_from)
        if not key:
            break
        open_idx = source.index("[", key.start())
        end = _matching_bracket(source, open_idx)
        if end == -1:
            searched_from = open_idx + 1
            continue
        searched_from = end
        for position, match in enumerate(
            _ITEM_IMAGE_BINDING_RE.finditer(source, open_idx, end)
        ):
            if match.group(1) in allowed:
                continue
            edits.append((match.start(1), match.end(1), pool[position % len(pool)]))
    if not edits:
        return source, 0
    out: list[str] = []
    cursor = 0
    for start, stop, slot in edits:
        out.append(source[cursor:start])
        out.append(slot)
        cursor = stop
    out.append(source[cursor:])
    return "".join(out), len(edits)


_MOCK_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*(['\"])@/data/mock\2\s*;?")


def _ensure_mock_named_import(content: str, name: str) -> str:
    m = _MOCK_IMPORT_RE.search(content)
    if m:
        names = [n.strip() for n in m.group(1).split(",") if n.strip()]
        if name in names:
            return content
        names.append(name)
        return (
            content[: m.start()]
            + "import { " + ", ".join(sorted(set(names))) + " } from '@/data/mock';"
            + content[m.end() :]
        )
    return f"import {{ {name} }} from '@/data/mock';\n" + content


def catalogue_detail_base(architect: dict | None) -> str:
    """The route base a card should link into, e.g. `/artwork` or `/gallery`.

    Prefers a param route whose static base is *also* a declared route, so the
    "back to the collection" link and the card link agree and neither 404s.
    """
    routes = list((architect or {}).get("routes") or [])
    declared = {str(r.get("path") or "").rstrip("/") for r in routes}
    bases: list[str] = []
    for route in routes:
        path = str(route.get("path") or "")
        if "/:" not in path:
            continue
        surface = str(route.get("surface") or "").lower()
        if surface == "ops" or path.startswith(("/admin", "/owner", "/ops", "/staff")):
            continue
        base = path.split("/:", 1)[0].rstrip("/")
        if base:
            bases.append(base)
    for base in bases:
        if base in declared:
            return base
    return bases[0] if bases else ""
