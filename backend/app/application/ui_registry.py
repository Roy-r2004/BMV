"""Derive `catalogue.json` from `registry.ts`, its declared source of truth.

`registry.ts` says at the top:

    catalogue.json is generated from this file via `npm run sync:ui`.
    Do not hand-edit catalogue.json.

That script no longer exists — it was deliberately removed when the template was
slimmed, and `sync-ui-catalogue` is in `test_scaffold_pruned.py`'s forbidden
substrings, so restoring it in the template would fail that test on purpose. The
two files were left hand-synced with nothing to notice a divergence, and the
consequence is silent: `ui_catalogue.load_catalogue()` reads the JSON, so a
component added to `registry.ts` alone is invisible to every prompt, validator
and skeleton contract, while a component present only in the JSON is offered to
the model and then fails to import.

So the generator lives here, on the side that consumes the artifact, in the
language that reads it. Regenerate with:

    python -m app.application.ui_registry --write

`test_ui_catalogue_drift.py` fails when the checked-in JSON stops matching, which
is the part that actually keeps them together.

The parsing is deliberately narrow — it understands exactly the subset of
TypeScript `registry.ts` uses (string literals, string arrays, object literals of
string arrays, and `...SPREAD` of a module-level string array) and raises on
anything else rather than guessing. A silent partial parse would reintroduce the
drift it exists to prevent.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.application.ui_catalogue import (
    _object_body,
    _split_top_level,
    _string_end,
    _strip_ts_comments,
)
from app.core.config import settings

# Fixed preamble of the generated file. These four keys are not derivable from
# `registry.ts`; they are the contract the JSON adds around it.
CATALOGUE_PREAMBLE: dict[str, Any] = {
    "version": 1,
    "import": "@/ui",
    "generatedFrom": "src/ui/registry.ts",
    "rule": (
        "Generated pages must import UI only from @/ui. Do not invent props or "
        "import Radix/Recharts/TanStack directly."
    ),
}

# Order matters: the generated arrays follow the declaration order in the source,
# so a reordered `registry.ts` is a real diff and shows up as one.
_COMPONENTS_EXPORT = "CATALOGUE_COMPONENTS"
_SKELETONS_EXPORT = "SKELETONS"

_ARRAY_CONST_RE = re.compile(r"(?:export\s+)?const\s+([A-Z][A-Z0-9_]*)\s*=\s*\[")
_STRING_LITERAL_RE = re.compile(r"^(['\"])(.*)\1$", re.DOTALL)
_SPREAD_RE = re.compile(r"^\.\.\.\s*([A-Za-z_$][\w$]*)$")
_KEY_RE = re.compile(r"^(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z_$][\w$]*))\s*:\s*(.+)$", re.DOTALL)


class RegistryParseError(ValueError):
    """`registry.ts` used a construct this parser will not guess at."""


def registry_path() -> Path:
    return Path(settings.PREVIEW_TEMPLATE_DIR) / "src" / "ui" / "registry.ts"


def catalogue_path() -> Path:
    return Path(settings.PREVIEW_TEMPLATE_DIR) / "src" / "ui" / "catalogue.json"


def _unquote(text: str) -> str | None:
    """The value of a TS string literal, or None if `text` is not one.

    Handles the implicit concatenation TS allows across a line break inside a
    single quoted string only by rejecting it — `purpose:` values in
    `registry.ts` are single literals, possibly on their own line.
    """
    match = _STRING_LITERAL_RE.match(text.strip())
    if not match:
        return None
    raw = match.group(2)
    # Only the escapes the source actually contains. json.loads would also
    # re-interpret \\u sequences, which is wanted, but it rejects single quotes.
    return json.loads('"' + raw.replace('\\"', '"').replace('"', '\\"') + '"')


def _array_bounds(source: str, open_index: int) -> int:
    """Index of the `]` matching the `[` at `open_index`."""
    depth = 0
    index = open_index
    while index < len(source):
        char = source[index]
        if char in "'\"`":
            index = _string_end(source, index)
            continue
        if char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise RegistryParseError(f"unbalanced array starting at offset {open_index}")


def _string_arrays(source: str) -> dict[str, list[str]]:
    """Module-level `const NAME = ['a', 'b'] as const;` arrays, for spreads."""
    found: dict[str, list[str]] = {}
    for match in _ARRAY_CONST_RE.finditer(source):
        name = match.group(1)
        open_index = match.end() - 1
        body = source[open_index + 1 : _array_bounds(source, open_index)]
        items = [_unquote(part) for part in _split_top_level(body, ",")]
        if items and all(item is not None for item in items):
            found[name] = [item for item in items if item is not None]
    return found


def _parse_value(text: str, arrays: dict[str, list[str]]) -> Any:
    text = text.strip().rstrip(",")
    literal = _unquote(text)
    if literal is not None:
        return literal
    if text.startswith("["):
        body = text[1 : _array_bounds(text, 0)]
        out: list[Any] = []
        for part in _split_top_level(body, ","):
            spread = _SPREAD_RE.match(part.strip())
            if spread:
                name = spread.group(1)
                if name not in arrays:
                    raise RegistryParseError(f"spread of unknown array {name!r}")
                out.extend(arrays[name])
                continue
            out.append(_parse_value(part, arrays))
        return out
    if text.startswith("{"):
        body = _object_body(text, 0)
        if body is None:
            raise RegistryParseError(f"unbalanced object literal: {text[:60]!r}")
        return _parse_object(body, arrays)
    raise RegistryParseError(f"unsupported value: {text[:80]!r}")


def _parse_object(body: str, arrays: dict[str, list[str]]) -> dict[str, Any]:
    """Object-literal members, split on top-level commas only.

    Not on newlines: `registry.ts` wraps long values onto the next line
    (`purpose:` does it for six skeletons), and splitting there silently dropped
    the key — a parser that quietly loses a field is worse than no parser, because
    it reports the field as drift and then "fixes" it by deleting it.
    """
    out: dict[str, Any] = {}
    for entry in _split_top_level(body, ","):
        entry = entry.strip()
        if not entry:
            continue
        match = _KEY_RE.match(entry)
        if not match:
            raise RegistryParseError(f"unparsed object member: {entry[:80]!r}")
        key = match.group(1) or match.group(2) or match.group(3)
        out[key] = _parse_value(match.group(4), arrays)
    return out


def _parse_object_array(source: str, export_name: str, arrays: dict[str, list[str]]) -> list[dict]:
    marker = re.search(
        r"export\s+const\s+" + re.escape(export_name) + r"\s*(?::[^=]+)?=\s*\[",
        source,
    )
    if not marker:
        raise RegistryParseError(f"{export_name} not found in registry.ts")
    open_index = marker.end() - 1
    body = source[open_index + 1 : _array_bounds(source, open_index)]
    entries: list[dict] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "{":
            inner = _object_body(body, index)
            if inner is None:
                raise RegistryParseError(f"unbalanced entry in {export_name}")
            entries.append(_parse_object(inner, arrays))
            index += len(inner) + 2
            continue
        index += 1
    if not entries:
        raise RegistryParseError(f"{export_name} parsed to zero entries")
    return entries


def build_catalogue_from_registry(source: str | None = None) -> dict[str, Any]:
    """The `catalogue.json` content that `registry.ts` currently implies."""
    if source is None:
        source = registry_path().read_text(encoding="utf-8")
    stripped = _strip_ts_comments(source)
    arrays = _string_arrays(stripped)
    return {
        **CATALOGUE_PREAMBLE,
        "components": _parse_object_array(stripped, _COMPONENTS_EXPORT, arrays),
        "skeletons": _parse_object_array(stripped, _SKELETONS_EXPORT, arrays),
    }


def serialize_catalogue(catalogue: dict[str, Any]) -> str:
    """Byte-for-byte the format the checked-in file uses."""
    return json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n"


def catalogue_drift() -> list[str]:
    """Human-readable differences between the checked-in JSON and registry.ts.

    Empty when they agree. Reports the *content* difference rather than a text
    diff, so reformatting the JSON is not reported as drift but a renamed prop is.
    """
    expected = build_catalogue_from_registry()
    try:
        actual = json.loads(catalogue_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"catalogue.json is unreadable: {e}"]

    problems: list[str] = []
    for key, value in CATALOGUE_PREAMBLE.items():
        if actual.get(key) != value:
            problems.append(f"{key}: {actual.get(key)!r} != {value!r}")

    for section, id_key in (("components", "name"), ("skeletons", "id")):
        want = {str(item.get(id_key)): item for item in expected[section]}
        have = {str(item.get(id_key)): item for item in (actual.get(section) or [])}
        for missing in sorted(set(want) - set(have)):
            problems.append(f"{section}: {missing} is in registry.ts but not catalogue.json")
        for extra in sorted(set(have) - set(want)):
            problems.append(f"{section}: {extra} is in catalogue.json but not registry.ts")
        for name in sorted(set(want) & set(have)):
            for field in sorted(set(want[name]) | set(have[name])):
                if want[name].get(field) != have[name].get(field):
                    problems.append(
                        f"{section}.{name}.{field}: "
                        f"catalogue.json has {have[name].get(field)!r}, "
                        f"registry.ts implies {want[name].get(field)!r}"
                    )
        want_order = [str(item.get(id_key)) for item in expected[section]]
        have_order = [str(item.get(id_key)) for item in (actual.get(section) or [])]
        if want_order != have_order and set(want_order) == set(have_order):
            problems.append(f"{section}: declaration order differs from registry.ts")
    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--write",
        action="store_true",
        help="rewrite catalogue.json from registry.ts (default: report drift only)",
    )
    args = parser.parse_args(argv)

    if args.write:
        target = catalogue_path()
        target.write_text(serialize_catalogue(build_catalogue_from_registry()), encoding="utf-8")
        print(f"wrote {target}")
        return 0

    problems = catalogue_drift()
    if not problems:
        print("catalogue.json matches registry.ts")
        return 0
    print(f"{len(problems)} drift(s) between registry.ts and catalogue.json:")
    for problem in problems:
        print(f"  {problem}")
    print("\nregenerate with: python -m app.application.ui_registry --write")
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
