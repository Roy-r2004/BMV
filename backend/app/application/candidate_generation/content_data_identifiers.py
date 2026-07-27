"""Shared naming and seed-shaping primitives for generated content data.

These helpers are used both by the deterministic ``content-data.ts`` emitter
and by the canonical generated-data API manifest, so they live in one place to
keep the emitted module and its declared contract in lockstep.
"""
from __future__ import annotations

import re


UNCOUNTABLE_ALIASES = frozenset({"availability"})
TYPESCRIPT_RESERVED_IDENTIFIERS = frozenset(
    {
        "abstract",
        "any",
        "as",
        "asserts",
        "async",
        "await",
        "bigint",
        "boolean",
        "break",
        "case",
        "catch",
        "class",
        "const",
        "constructor",
        "continue",
        "debugger",
        "declare",
        "default",
        "delete",
        "do",
        "else",
        "enum",
        "export",
        "extends",
        "false",
        "finally",
        "for",
        "from",
        "function",
        "get",
        "if",
        "implements",
        "import",
        "in",
        "infer",
        "instanceof",
        "interface",
        "is",
        "keyof",
        "let",
        "module",
        "namespace",
        "never",
        "new",
        "null",
        "number",
        "object",
        "of",
        "override",
        "package",
        "private",
        "protected",
        "public",
        "readonly",
        "require",
        "return",
        "satisfies",
        "set",
        "static",
        "string",
        "super",
        "switch",
        "symbol",
        "this",
        "throw",
        "true",
        "try",
        "type",
        "typeof",
        "undefined",
        "unique",
        "unknown",
        "var",
        "void",
        "while",
        "with",
        "yield",
    }
)


def identifier_words(identifier: str) -> list[str]:
    parts = [part.lower() for part in re.findall(r"[A-Za-z0-9]+", identifier)]
    filtered = [
        part
        for part in parts
        if part not in {"entity", "collection", "field", "record"}
    ]
    return filtered or ["data"]


def lower_camel(words: list[str]) -> str:
    if not words:
        return "data"
    head, *tail = words
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


def upper_camel(words: list[str]) -> str:
    if not words:
        return "Data"
    return "".join(part[:1].upper() + part[1:] for part in words)


def typescript_prefix(name: str) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if not candidate:
        return "tsData"
    return f"ts{candidate[:1].upper()}{candidate[1:]}"


def needs_typescript_prefix(name: str) -> bool:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if not candidate:
        return True
    if not re.match(r"^[A-Za-z_$]", candidate):
        return True
    return candidate in TYPESCRIPT_RESERVED_IDENTIFIERS


def valid_typescript_identifier(
    name: str,
    *,
    force_prefix: bool = False,
) -> str:
    candidate = re.sub(r"[^A-Za-z0-9_$]", "", name)
    if force_prefix or needs_typescript_prefix(candidate):
        return typescript_prefix(candidate)
    return candidate


def singularize(words: list[str]) -> list[str]:
    if not words:
        return ["data"]
    last = words[-1]
    if last in UNCOUNTABLE_ALIASES:
        return words
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith("ses") and len(last) > 3:
        last = last[:-2]
    elif last.endswith("s") and len(last) > 1 and not last.endswith("ss"):
        last = last[:-1]
    return [*words[:-1], last]


def pluralize(words: list[str]) -> list[str]:
    if not words:
        return ["data"]
    last = words[-1]
    if last in UNCOUNTABLE_ALIASES:
        return words
    if last.endswith("y") and len(last) > 1 and last[-2] not in "aeiou":
        last = last[:-1] + "ies"
    elif last.endswith(("s", "x", "z", "ch", "sh")):
        last = last + "es"
    else:
        last = last + "s"
    return [*words[:-1], last]


def unique_alias(base: str, used: set[str]) -> str:
    stem = valid_typescript_identifier(base or "data")
    candidate = stem
    suffix = 1
    while candidate in used:
        suffix += 1
        candidate = valid_typescript_identifier(f"{stem}{suffix}")
    used.add(candidate)
    return candidate


def collection_seed_records(collection: object) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    entity_words = identifier_words(str(getattr(collection, "entity_id", "")))
    for seed_record in getattr(collection, "seed_records", ()):
        payload: dict[str, object] = {}
        for item in getattr(seed_record, "values", ()):
            field_words = identifier_words(str(getattr(item, "field_id", "")))
            value = getattr(item, "value", None)
            full_key = lower_camel(field_words)
            payload[full_key] = value
            if (
                len(field_words) > len(entity_words)
                and field_words[: len(entity_words)] == entity_words
            ):
                short_key = lower_camel(field_words[len(entity_words) :])
                payload.setdefault(short_key, value)
        records.append(payload)
    return records


def seed_record_property_keys(collection: object) -> list[tuple[str, str, str]]:
    """Return ``(field_id, property_name, alias_of)`` for one collection.

    ``alias_of`` is empty for the canonical (fully qualified) property name and
    names the canonical property for the entity-prefix-stripped alias.
    """

    entity_words = identifier_words(str(getattr(collection, "entity_id", "")))
    seen: set[str] = set()
    keys: list[tuple[str, str, str]] = []
    for seed_record in getattr(collection, "seed_records", ()):
        for item in getattr(seed_record, "values", ()):
            field_id = str(getattr(item, "field_id", "") or "")
            field_words = identifier_words(field_id)
            full_key = lower_camel(field_words)
            if full_key not in seen:
                seen.add(full_key)
                keys.append((field_id, full_key, ""))
            if (
                len(field_words) > len(entity_words)
                and field_words[: len(entity_words)] == entity_words
            ):
                short_key = lower_camel(field_words[len(entity_words) :])
                if short_key not in seen:
                    seen.add(short_key)
                    keys.append((field_id, short_key, full_key))
    return keys


__all__ = [
    "TYPESCRIPT_RESERVED_IDENTIFIERS",
    "UNCOUNTABLE_ALIASES",
    "collection_seed_records",
    "identifier_words",
    "lower_camel",
    "needs_typescript_prefix",
    "pluralize",
    "seed_record_property_keys",
    "singularize",
    "typescript_prefix",
    "unique_alias",
    "upper_camel",
    "valid_typescript_identifier",
]
