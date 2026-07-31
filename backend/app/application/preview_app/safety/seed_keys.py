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


def _sub_value(sub: str, key: str, brand: str) -> str:
    lowered = sub.lower()
    if lowered in {"id", "slug", "key"}:
        # A detail route resolves by this. "Id — Brand" is not a URL segment.
        return "1"
    if lowered in {"href", "path", "url", "link", "to"}:
        return "#"
    if lowered in {"image", "imagesrc", "img", "photo", "src", "avatar", "logo"}:
        return ""
    if lowered in {"count", "total", "value", "amount", "price", "number"}:
        return "0"
    if lowered in {"title", "heading", "headline", "name", "label"}:
        return f"{_humanize(key)} — {brand}"
    if lowered in {"description", "subcopy", "body", "text", "detail", "summary", "copy"}:
        return f"{brand}: {_humanize(key).lower()} content is being prepared."
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
            f"{sub}: {json.dumps(_sub_value(sub, leaf, brand), ensure_ascii=False)}"
            for sub in subs
        )
        return f"{{ {inner} }}"
    return json.dumps(f"{_humanize(leaf)} — {brand}", ensure_ascii=False)


def _default_for(key: str, sources: str, brand: str) -> str:
    """TS literal for a missing seed key, inferred from how pages use it."""
    return _default_for_path(key, sources, brand)


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
    missing = sorted(referenced - existing - _NEVER_INJECT)
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
