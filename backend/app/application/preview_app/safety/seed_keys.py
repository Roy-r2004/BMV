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
#: Array usage: `.map(`, `.length`, `?? []`, `.filter(`, `.slice(`
_ARRAY_USE_RE_TMPL = (
    r"\bseed\s*\??\.\s*{key}\s*(?:\?\?\s*\[\]|\)?\s*\.\s*(?:map|filter|slice|forEach|length)\b)"
)

_NEVER_INJECT = frozenset({"items", "hero", "cta", "footer", "map", "length", "filter"})


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


def _default_for(key: str, sources: str, brand: str) -> str:
    """TS literal for a missing seed key, inferred from how pages use it."""
    if re.search(_ARRAY_USE_RE_TMPL.format(key=re.escape(key)), sources):
        fields = {"title": f"{_humanize(key)} — {brand}", "description": f"Prepared by {brand}."}
        # `(seed.exhibitions ?? []).map((e) => e.venue)` — the callback parameter is
        # a few tokens past the key, not adjacent to it, so look ahead rather than
        # anchoring. The fields the row is destructured or dotted for must exist or
        # the map body throws on the first row.
        for match in re.finditer(rf"\b{re.escape(key)}\b", sources):
            window = sources[match.end() : match.end() + 400]
            callback = re.search(
                r"\.\s*(?:map|forEach|filter)\s*\(\s*\(?\s*(?:\{\s*(?P<destructured>[^}]*)\}"
                r"|(?P<alias>[A-Za-z_][A-Za-z0-9_]*))",
                window,
            )
            if not callback:
                continue
            if callback.group("destructured"):
                for sub in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", callback.group("destructured")):
                    fields.setdefault(sub, _sub_value(sub, key, brand))
                break
            alias = callback.group("alias")
            for sub in sorted(
                set(
                    re.findall(
                        rf"\b{re.escape(alias)}\s*\??\.\s*([A-Za-z_][A-Za-z0-9_]*)", window
                    )
                )
            ):
                fields.setdefault(sub, _sub_value(sub, key, brand))
            break
        one = ", ".join(
            f"{name}: {json.dumps(value, ensure_ascii=False)}" for name, value in fields.items()
        )
        return f"[{{ {one} }}]"

    subs = sorted(
        set(re.findall(_SUB_READ_RE_TMPL.format(key=re.escape(key)), sources))
    )
    subs = [s for s in subs if s not in {"map", "filter", "slice", "length", "forEach"}]
    if subs:
        inner = ", ".join(
            f"{sub}: {json.dumps(_sub_value(sub, key, brand), ensure_ascii=False)}"
            for sub in subs
        )
        return f"{{ {inner} }}"
    return json.dumps(f"{_humanize(key)} — {brand}", ensure_ascii=False)


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
