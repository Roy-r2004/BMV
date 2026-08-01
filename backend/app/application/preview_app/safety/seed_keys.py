"""Every `seed.<key>` a page reads must exist.

`seed` is a plain object literal, so a page that reads a key the synthesizer never
wrote gets `undefined` — and one property access later the page throws and the
error boundary replaces it. Request 42's `AdminAboutEditPage` read
`seed.aboutPage.title` five times; `tsc` reported all five as TS2339 and the page
would have rendered a stack trace.

`ensure_seed_scaffold_fields` covers the *known* scaffold keys. This covers the
ones the model invents, which cannot be enumerated in advance: the shape is
inferred from how the page uses the key, and the content is brand-flavoured filler
rather than a guess at meaning. Filler that renders beats a crash, and the visual
critic can still see that a section is generic.
"""
from __future__ import annotations

import json
import re

from app.application.preview_app.workspace import list_source_files, read_file, write_file
from app.infrastructure.logging import get_logger

log = get_logger("SafetyGuards")

#: `seed.aboutPage`, `seed?.aboutPage`, `(seed as any).aboutPage`
_SEED_READ_RE = re.compile(r"\bseed\s*(?:as\s+any\s*\)?\s*)?\??\.\s*([A-Za-z_][A-Za-z0-9_]*)")
#: The sub-keys a page reads off that value, e.g. `seed.aboutPage.title`
_SUB_READ_RE_TMPL = r"\bseed\s*\??\.\s*{key}\s*\??\.\s*([A-Za-z_][A-Za-z0-9_]*)"
#: Array usage: `?? []` or any array method. Request 45's edit page did
#: `seed.artworks.find((art) => …)` — `find` was not in this list, so the key was
#: defaulted to a string and `.find` became "Type 'String' has no call signatures".
_ARRAY_METHODS = (
    "map|filter|slice|forEach|length|find|findIndex|findLast|some|every|reduce"
    "|flatMap|flat|sort|concat|includes|indexOf|join|at|reverse|keys|entries"
)
_ARRAY_USE_RE_TMPL = (
    r"\bseed\s*\??\.\s*{key}\s*(?:\?\?\s*\[\]|\)?\s*\??\.\s*(?:" + _ARRAY_METHODS + r")\b)"
)

#: Reading past a value is not reading the value. Every array method is also a
#: property name, so these can never be mistaken for a sub-key of their own.
_ARRAY_METHOD_NAMES = frozenset(_ARRAY_METHODS.split("|"))

#: How deep the shape inference walks. `seed.ops.kpis.availableWorks` is depth 3,
#: which is as deep as a generated page has ever read.
_MAX_SHAPE_DEPTH = 3

#: Names that mean "a collection" even with no observed array usage. Request 46's
#: dashboard did `const chartData = seed.ops.chartData` and handed it to a chart —
#: the read itself proves nothing, and a string there draws no chart.
_COLLECTION_NAMES = frozenset(
    {
        "chartdata",
        "chart",
        "series",
        "datapoints",
        "points",
        "rows",
        "items",
        "list",
        "entries",
        "records",
        "columns",
        "options",
        "tags",
        "steps",
    }
)

_NEVER_INJECT = frozenset({"items", "hero", "cta", "footer", "map", "length", "filter"})


def _path_read_re(path: str) -> str:
    """Regex matching a dotted read like `seed.ops.items`, `?.` tolerated between."""
    parts = [re.escape(part) for part in path.split(".")]
    head = r"\bseed\s*(?:as\s+any\s*\)?\s*)?\??\.\s*"
    return head + r"\s*\??\.\s*".join(parts)


def _path_used_as_array(path: str, sources: str) -> bool:
    pattern = (
        _path_read_re(path)
        + r"\s*(?:\?\?\s*\[\]|\)?\s*\??\.\s*(?:"
        + _ARRAY_METHODS
        + r")\b)"
    )
    return re.search(pattern, sources) is not None


def _path_sub_keys(path: str, sources: str) -> list[str]:
    found = set(re.findall(_path_read_re(path) + r"\s*\??\.\s*([A-Za-z_][A-Za-z0-9_]*)", sources))
    return sorted(found - _ARRAY_METHOD_NAMES)


def _seed_span(mock: str) -> tuple[int, int] | None:
    """(body_start, closing_brace_index) of `export const seed = { ... }`."""
    m = re.search(r"export\s+const\s+seed\s*(?::[^=]+)?=\s*\{", mock)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    quote = ""
    while i < len(mock) and depth:
        ch = mock[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    if depth:
        return None
    return start, i - 1


def _top_level_keys(body: str) -> set[str]:
    keys: set[str] = set()
    depth = 0
    i = 0
    quote = ""
    line_start = True
    while i < len(body):
        ch = body[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            i += 1
            continue
        if ch in "{[(":
            depth += 1
        elif ch in "}])":
            depth -= 1
        elif depth == 0 and (line_start or ch == ","):
            m = re.match(r"[,\s]*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\s*:", body[i:])
            if m:
                keys.add(m.group(1))
        line_start = ch == "\n"
        i += 1
    return keys


def _humanize(key: str) -> str:
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("_", " ")
    return spaced.strip().capitalize()


#: Substrings that say what a field is *for*. Matched inside the name, not against
#: it: request 47 read `seed.ctaHeading` and `seed.ctaDescription`, neither of which
#: equals "heading" or "description", so both fell through to the identifier echo
#: and the home page's closing band read "Cta heading — Jeanne Kassab Art".
_HEADLINE_HINTS = ("heading", "headline", "title", "eyebrow", "kicker")
_BODY_HINTS = ("description", "subcopy", "body", "detail", "summary", "copy", "blurb")


def _tokens(name: str) -> frozenset[str]:
    """`imageUrl` → {image, url}; `card1` → {card1}. Words, never substrings.

    Substring matching reads `logout` as a logo and `linkedin` as a link. Exact
    matching — what this used to do — misses `imageUrl`, `heroImage`,
    `thumbnailUrl` and `photoUrl`, every one of which is a URL.
    """
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", name or "").replace("_", " ").replace("-", " ")
    return frozenset(token.lower() for token in spaced.split() if token)


#: The four classes whose wrong value is *destructive* rather than merely
#: generic. A sentence in any of these slots is worse than no value at all: an
#: `<img src>` shows the broken-image glyph, an `<a href>` goes nowhere, a detail
#: route stops resolving, and a stat tile reads as prose.
#:
#: Only these are widened to word matching. `name`/`label` and the copy hints
#: below stay exactly as they were — a merely generic string is not worth the
#: blast radius of matching `className` as a name.
_ID_WORDS = frozenset({"id", "slug", "key"})
_IMAGE_WORDS = frozenset(
    {
        "image",
        "imagesrc",
        "imageurl",
        "img",
        "photo",
        "src",
        "avatar",
        "logo",
        "thumbnail",
        "thumb",
        "picture",
        "headshot",
        "poster",
    }
)
_LINK_WORDS = frozenset({"href", "path", "url", "link", "to"})
_NUMBER_WORDS = frozenset(
    {"count", "total", "value", "amount", "price", "number", "qty", "quantity"}
)

#: The same four classes, said by the *container* instead of the leaf. Request
#: 71's `images: { card1: … }` names nothing at the leaf and everything at the
#: container, so leaf-only matching produced the caption
#: `"Card1 — Atelier Vaugirard"` where `OwnerPaintingEditPage.tsx:20` reads an
#: `imageUrl`. A container is only consulted when the leaf classifies as nothing,
#: so `images.title` is still a heading and `images.alt` is still copy.
_IMAGE_CONTAINERS = frozenset(
    {
        "images",
        "imagery",
        "imgs",
        "photos",
        "pictures",
        "pics",
        "thumbnails",
        "thumbs",
        "avatars",
        "logos",
        "media",
        "headshots",
        "screenshots",
    }
)
_LINK_CONTAINERS = frozenset({"links", "urls", "hrefs", "routes", "social", "socials"})
_NUMBER_CONTAINERS = frozenset(
    {"counts", "totals", "metrics", "kpis", "stats", "numbers", "figures", "prices"}
)

#: `imageUrl: seed.images.card1`, `src={seed.images.card1}` — the identifier a
#: value is assigned to, immediately before the read.
_ASSIGNMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*\{?\s*$")
#: `style={{ backgroundImage: `url(${seed.images.card1})` }}`
_CSS_URL_RE = re.compile(r"url\(\s*['\"]?\s*(?:\$\{)?\s*$")


def _usage_class(path: str, sources: str) -> str:
    """What the *pages* do with this value, which outranks both names.

    A name is a guess about intent; the prop a value is handed to is the DOM's
    own statement of its type. This is the signal that catches the case both
    names miss — a leaf and a container that are each uninformative, read into
    an `<img src>` two files away.
    """
    for match in re.finditer(_path_read_re(path), sources):
        before = sources[max(0, match.start() - 80) : match.start()]
        if _CSS_URL_RE.search(before):
            return "image"
        assigned = _ASSIGNMENT_RE.search(before)
        if not assigned:
            continue
        words = _tokens(assigned.group(1))
        if words & _IMAGE_WORDS:
            return "image"
        if words & _LINK_WORDS:
            return "href"
    return ""


def _leaf_is_copy(sub: str) -> bool:
    """True when the leaf's own name already says "this is prose"."""
    lowered = sub.lower()
    return (
        lowered in {"name", "label", "text"}
        or any(hint in lowered for hint in _HEADLINE_HINTS)
        or any(hint in lowered for hint in _BODY_HINTS)
    )


def _value_class(sub: str, container: str, usage: str = "") -> str:
    """`id` | `image` | `href` | `number`, or `""` — strongest signal first.

    Usage site, then leaf, then container. `image` is tested before `href`
    because `imageUrl` is both, and `"#"` in an `<img src>` is a broken image
    while an image URL in an `<a href>` still navigates.
    """
    if usage:
        return usage
    words = _tokens(sub)
    for name, vocabulary in (
        ("id", _ID_WORDS),
        ("image", _IMAGE_WORDS),
        ("href", _LINK_WORDS),
        ("number", _NUMBER_WORDS),
    ):
        if words & vocabulary:
            return name
    if _leaf_is_copy(sub):
        # The leaf classified itself as prose, so the container has no gap to
        # fill: `images.title` is a caption, not a second URL.
        return ""
    lowered_container = (container or "").lower()
    for name, vocabulary in (
        ("image", _IMAGE_CONTAINERS),
        ("href", _LINK_CONTAINERS),
        ("number", _NUMBER_CONTAINERS),
    ):
        if lowered_container in vocabulary:
            return name
    return ""


def _sub_value(sub: str, container: str, brand: str, usage: str = "") -> str:
    """Filler for one leaf. `container` is the key this leaf hangs off."""
    value_class = _value_class(sub, container, usage)
    if value_class == "id":
        # A detail route resolves by this. "Id — Brand" is not a URL segment.
        return "1"
    if value_class == "image":
        # `KitImage` degrades an empty src to a brand-tinted placeholder. It
        # cannot degrade a sentence — that renders the broken-image glyph.
        return ""
    if value_class == "href":
        return "#"
    if value_class == "number":
        return "0"
    lowered = sub.lower()
    if lowered in {"name", "label"}:
        return brand
    if any(hint in lowered for hint in _HEADLINE_HINTS):
        return f"Discover {brand}"
    if any(hint in lowered for hint in _BODY_HINTS) or lowered == "text":
        return f"See what {brand} offers, and get in touch about anything you like."
    # Unknown field: brand it rather than echoing the identifier, so a form input
    # or a caption reads as content instead of as a variable name.
    return f"{_humanize(sub)} — {brand}"


def _array_default_for(path: str, sources: str, brand: str) -> str:
    """A one-row array literal carrying the fields the map body reads off a row."""
    leaf = path.rsplit(".", 1)[-1]
    if leaf.lower() in {"chartdata", "chart", "series", "datapoints", "points"}:
        # A chart row is `{ label, value }` in every kit component that draws one;
        # `{ title, description }` renders an empty plot.
        fields: dict[str, object] = {"label": "Jan", "value": 12}
    else:
        fields = {"title": f"{_humanize(leaf)} — {brand}", "description": f"Prepared by {brand}."}
    # `(seed.exhibitions ?? []).map((e) => e.venue)` — the callback parameter is
    # a few tokens past the key, not adjacent to it, so look ahead rather than
    # anchoring. The fields the row is destructured or dotted for must exist or
    # the map body throws on the first row.
    # Anchor on the arrow, not on the method name: `slice(0, 4).map(item => …)`
    # puts two calls and a pair of numbers between the key and the parameter, and
    # only `=>` distinguishes a callback parameter from an argument.
    callback_re = re.compile(
        r"\(?\s*(?:\{\s*(?P<destructured>[^}]*)\}|(?P<alias>[A-Za-z_][A-Za-z0-9_]*))"
        r"\s*(?::[^)=]+)?\s*\)?\s*=>"
    )
    for match in re.finditer(_path_read_re(path), sources):
        window = sources[match.end() : match.end() + 400]
        callback = callback_re.search(window)
        if not callback:
            continue
        destructured = callback.group("destructured")
        alias = callback.group("alias")
        if destructured:
            for sub in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", destructured):
                fields.setdefault(sub, _sub_value(sub, leaf, brand))
            break
        if alias and alias not in _ARRAY_METHOD_NAMES:
            for sub in sorted(
                set(
                    re.findall(
                        rf"\b{re.escape(alias)}\s*\??\.\s*([A-Za-z_][A-Za-z0-9_]*)", window
                    )
                )
            ):
                fields.setdefault(sub, _sub_value(sub, leaf, brand))
            break
    one = ", ".join(
        f"{name}: {json.dumps(value, ensure_ascii=False)}" for name, value in fields.items()
    )
    return f"[{{ {one} }}]"


def _default_for_path(path: str, sources: str, brand: str, depth: int = 1) -> str:
    """TS literal for a seed path, inferred from how the pages use *that path*.

    Recursive, because the shape rule is the same at every level and applying it
    only at the top produced request 46's crash: `seed.ops` was injected as four
    strings while the dashboard read `seed.ops.items.slice(0, 4).map(…)`,
    `seed.ops.activity.map(…)` and `seed.ops.kpis.availableWorks`. The page loaded
    the error boundary with "items.slice(...).map is not a function".
    """
    if _path_used_as_array(path, sources):
        return _array_default_for(path, sources, brand)
    subs = _path_sub_keys(path, sources)
    leaf = path.rsplit(".", 1)[-1]
    if not subs and depth > 1 and leaf.lower() in _COLLECTION_NAMES:
        return _array_default_for(path, sources, brand)
    if subs and depth < _MAX_SHAPE_DEPTH:
        inner = ", ".join(
            f"{sub}: {_default_for_path(f'{path}.{sub}', sources, brand, depth + 1)}"
            for sub in subs
        )
        return f"{{ {inner} }}"
    if subs:
        inner = ", ".join(
            f"{sub}: "
            f"{json.dumps(_sub_value(sub, leaf, brand, _usage_class(f'{path}.{sub}', sources)), ensure_ascii=False)}"
            for sub in subs
        )
        return f"{{ {inner} }}"
    # Route the terminal string through the same vocabulary: this value goes on the
    # page verbatim, so it has to read as copy rather than as the key's name.
    #
    # The container comes from the path, not from the leaf. Passing `leaf` twice
    # is what shipped request 71's `images: { card1: "Card1 — Atelier Vaugirard" }`:
    # the one signal that said "URL" was the segment this branch threw away.
    parts = path.split(".")
    container = parts[-2] if len(parts) > 1 else leaf
    return json.dumps(
        _sub_value(leaf, container, brand, _usage_class(path, sources)), ensure_ascii=False
    )


def _default_for(key: str, sources: str, brand: str) -> str:
    """TS literal for a missing seed key, inferred from how pages use it."""
    return _default_for_path(key, sources, brand)


#: A guard that hands the read off to a fallback: `?? …`, `|| …`, or the
#: `seed.x?.length ? seed.x : …` idiom.
_PAGE_FALLBACK_RE = re.compile(
    r"""^\s*(?:\?\s*\.\s*length\s*\?[^:]{0,80}:|(?:\?\?|\|\|))\s*"""
)
#: `[]`, `{}`, `''` — a fallback that supplies nothing.
_EMPTY_LITERAL_RE = re.compile(r"""^(?:\[\s*\]|\{\s*\}|["'`]\s*["'`])""")


def _page_supplies_its_own(key: str, sources: str) -> bool:
    """True when a read of `seed.<key>` falls back to a literal that has content.

    Then the key's absence breaks nothing *and* the page already has something
    better to show, so injecting a stub is not a repair — it is a regression.
    Request 47's home page read
    `seed.showcase?.length ? seed.showcase : [three real paintings]`; this guard
    invented a one-row `seed.showcase`, which made `?.length` truthy and displaced
    all three. The page shipped a heading over an empty band.

    An *empty* fallback — `?? []`, `?? {}`, `?? ''` — supplies nothing, so the key
    is still worth filling: that is content where the page had none.
    """
    for match in re.finditer(_path_read_re(key), sources):
        window = sources[match.end() : match.end() + 400]
        guard = _PAGE_FALLBACK_RE.match(window)
        if not guard:
            continue
        if not _EMPTY_LITERAL_RE.match(window[guard.end() :]):
            return True
    return False


def ensure_seed_keys_pages_read(workspace, brand_name: str = "Brand") -> list[str]:
    """Add every `seed.<key>` the pages read and the seed does not define.

    Returns the keys added. Conservative by construction: known scaffold keys are
    left to `ensure_seed_scaffold_fields`, and a seed object this cannot span is
    left untouched.
    """
    mock_path = "src/data/mock.ts"
    try:
        mock = read_file(workspace, mock_path)
    except Exception:
        return []
    if not mock or "export const seed" not in mock:
        return []
    span = _seed_span(mock)
    if not span:
        return []
    body_start, close_at = span
    existing = _top_level_keys(mock[body_start:close_at])

    sources: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".ts")) or rel.endswith("mock.ts"):
            continue
        try:
            sources.append(read_file(workspace, rel) or "")
        except Exception:
            continue
    blob = "\n".join(sources)
    if not blob:
        return []

    referenced = {k for k in _SEED_READ_RE.findall(blob) if k}
    candidates = sorted(referenced - existing - _NEVER_INJECT)
    missing = [k for k in candidates if not _page_supplies_its_own(k, blob)]
    deferred = [k for k in candidates if k not in missing]
    if deferred:
        log.info(
            "seed keys left to the page's own fallback: %s", ", ".join(deferred)
        )
    if not missing:
        return []

    brand = brand_name or "Brand"
    additions = "".join(
        f"\n  {key}: {_default_for(key, blob, brand)}," for key in missing
    )
    before = mock[:close_at].rstrip()
    joiner = "" if before.endswith(("{", ",")) else ","
    updated = mock[:close_at] + joiner + additions + "\n" + mock[close_at:]
    try:
        write_file(workspace, mock_path, updated)
    except Exception as e:
        log.warning("seed key guard could not write mock.ts: %s", e)
        return []
    log.info("seed keys added for pages that read them: %s", ", ".join(missing))
    return missing
