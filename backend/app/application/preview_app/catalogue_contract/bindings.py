"""Catalogue import and JSX binding analysis."""
from __future__ import annotations

import re

def _ui_named_imports(tokens: list[str]) -> dict[str, str]:
    """Return local name -> exported name for named imports from the UI barrel."""
    imported: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        if tokens[index] != "import":
            index += 1
            continue
        try:
            from_index = tokens.index("from", index + 1)
        except ValueError:
            break
        if (
            from_index + 1 >= len(tokens)
            or tokens[from_index + 1] != "\0@/ui"
        ):
            index = from_index + 1
            continue
        clause = tokens[index + 1:from_index]
        if "{" not in clause or "}" not in clause:
            index = from_index + 2
            continue
        start = clause.index("{") + 1
        end = clause.index("}", start)
        cursor = start
        while cursor < end:
            if clause[cursor] == ",":
                cursor += 1
                continue
            # `import { type TableColumn }` is erased at runtime — exported
            # types are not components and must not hit the component checks.
            type_only = clause[cursor] == "type"
            if type_only:
                cursor += 1
                if cursor >= end:
                    break
            exported = clause[cursor]
            local = exported
            if cursor + 2 < end and clause[cursor + 1] == "as":
                local = clause[cursor + 2]
                cursor += 3
            else:
                cursor += 1
            if (
                not type_only
                and re.match(r"^[A-Za-z_$][\w$]*$", exported)
                and re.match(r"^[A-Za-z_$][\w$]*$", local)
            ):
                imported[local] = exported
        index = from_index + 2
    return imported


_ALLOWED_CATALOGUE_IMPORTS = {
    "@/ui",
    "react",
    "react-router-dom",
    "@/data/mock",
    "@/lib/app-nav",
}


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


def _runtime_import_bindings(
    tokens: list[str],
    allowed_sources: set[str],
) -> set[str]:
    """Collect value bindings from static imports whose source is allowed."""
    bindings: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != "import":
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and tokens[end] != ";":
            end += 1
        statement = tokens[index + 1:end]
        if not statement or statement[0].startswith("\0") or statement[0] == "(":
            index += 2
            continue
        try:
            from_index = statement.index("from")
        except ValueError:
            index += 1
            continue
        source_index = index + from_index + 2
        if (
            from_index + 1 >= len(statement)
            or not statement[from_index + 1].startswith("\0")
            or statement[from_index + 1][1:] not in allowed_sources
        ):
            index = source_index + 1
            continue

        clause = statement[:from_index]
        if not clause or clause[0] == "type":
            index = source_index + 1
            continue
        if _IDENTIFIER_RE.match(clause[0]):
            bindings.add(clause[0])
        for cursor, token in enumerate(clause):
            if token == "*" and cursor + 2 < len(clause) and clause[cursor + 1] == "as":
                local = clause[cursor + 2]
                if _IDENTIFIER_RE.match(local):
                    bindings.add(local)
            if token != "{":
                continue
            cursor += 1
            while cursor < len(clause) and clause[cursor] != "}":
                if clause[cursor] == ",":
                    cursor += 1
                    continue
                type_only = clause[cursor] == "type"
                if type_only:
                    cursor += 1
                if cursor >= len(clause) or not _IDENTIFIER_RE.match(clause[cursor]):
                    cursor += 1
                    continue
                local = clause[cursor]
                if (
                    cursor + 2 < len(clause)
                    and clause[cursor + 1] == "as"
                    and _IDENTIFIER_RE.match(clause[cursor + 2])
                ):
                    local = clause[cursor + 2]
                    cursor += 3
                else:
                    cursor += 1
                if not type_only:
                    bindings.add(local)
            break
        index = source_index + 1
    return bindings


def _local_component_bindings(tokens: list[str]) -> set[str]:
    """Collect simple function, class, const, interface, and type declarations.

    Interface/type names must be known so generics such as
    `useState<TradeInRequest[]>` are not misread as undefined JSX tags.
    """
    bindings: set[str] = set()
    for index, token in enumerate(tokens):
        if token in {"function", "class", "interface", "type"}:
            cursor = index + 1
            if token == "function" and cursor < len(tokens) and tokens[cursor] == "*":
                cursor += 1
            if cursor < len(tokens) and _IDENTIFIER_RE.match(tokens[cursor]):
                bindings.add(tokens[cursor])
        elif (
            token == "const"
            and index + 1 < len(tokens)
            and _IDENTIFIER_RE.match(tokens[index + 1])
        ):
            bindings.add(tokens[index + 1])
    return bindings


_JSX_PRECEDING_KEYWORDS = {
    "return",
    "default",
    "typeof",
    "in",
    "of",
    "case",
    "await",
    "yield",
    "do",
    "else",
    "void",
}


_GENERIC_FOLLOW_TOKENS = {"(", "[", ".", "?", ":", "=", ";", ",", ")", ">", "&", "|", "}"}


def _skips_generic_arguments(tokens: list[str], start: int) -> bool:
    """True when tokens[start] opens a TypeScript generic argument list.

    Handles nesting (`useState<Record<string, string>>`), unions
    (`useState<Date | null>`), and array suffixes (`useState<Item[]>`). JSX
    never survives the scan because props introduce strings, braces, or
    parens, which break plausibility.
    """
    depth = 1
    probe = start + 1
    while probe < len(tokens) and depth:
        current = tokens[probe]
        if current == "<":
            depth += 1
        elif current == ">":
            depth -= 1
        elif current in {"(", ")", "{", "}", ";", "="} or current.startswith("\0"):
            return False
        if probe - start > 60:
            return False
        probe += 1
    return (
        depth == 0
        and probe < len(tokens)
        and tokens[probe] in _GENERIC_FOLLOW_TOKENS
    )


def _uppercase_jsx_roots(tokens: list[str]) -> set[str]:
    """Return uppercase roots from JSX tag names, including member expressions."""
    roots: set[str] = set()
    for index, token in enumerate(tokens):
        if token != "<":
            continue
        cursor = index + 1
        closing = cursor < len(tokens) and tokens[cursor] == "/"
        if closing:
            cursor += 1
        if cursor >= len(tokens):
            continue
        root = tokens[cursor]
        if not _IDENTIFIER_RE.match(root) or not root[0].isupper():
            continue
        if (
            not closing
            and index > 0
            and _IDENTIFIER_RE.match(tokens[index - 1])
            and tokens[index - 1] not in _JSX_PRECEDING_KEYWORDS
            and _skips_generic_arguments(tokens, index)
        ):
            # Type arguments such as `useState<Record<string, string>>()` or
            # `React.ChangeEvent<HTMLInputElement>` are not JSX tags.
            continue
        roots.add(root)
    return roots


_REACT_GLOBAL_PROPS = {
    "key",
    "ref",
    "id",
    "style",
    "role",
    "title",
    "tabIndex",
    "hidden",
    "lang",
    "dir",
    "draggable",
    "slot",
    "suppressHydrationWarning",
    "dangerouslySetInnerHTML",
}


def _jsx_opening_props(
    tokens: list[str],
    component_locals: set[str],
) -> list[tuple[str, dict[str, str | None]]]:
    """Extract top-level JSX props; spread expressions remain intentionally opaque."""
    invocations: list[tuple[str, dict[str, str | None]]] = []
    index = 0
    while index + 1 < len(tokens):
        local = tokens[index + 1]
        if tokens[index] != "<" or local not in component_locals:
            index += 1
            continue
        cursor = index + 2
        curly = square = paren = 0
        props: dict[str, str | None] = {}
        while cursor < len(tokens):
            token = tokens[cursor]
            if token == ">" and not (curly or square or paren):
                break
            if not (curly or square or paren) and re.match(
                r"^[A-Za-z_$][A-Za-z0-9_$-]*$",
                token,
            ):
                value: str | None = None
                if cursor + 1 < len(tokens) and tokens[cursor + 1] == "=":
                    if cursor + 2 < len(tokens) and tokens[cursor + 2].startswith("\0"):
                        value = tokens[cursor + 2][1:]
                    elif (
                        cursor + 4 < len(tokens)
                        and tokens[cursor + 2] == "{"
                        and tokens[cursor + 3].startswith("\0")
                        and tokens[cursor + 4] == "}"
                    ):
                        value = tokens[cursor + 3][1:]
                props[token] = value
            if token == "{":
                curly += 1
            elif token == "}":
                curly = max(0, curly - 1)
            elif token == "[":
                square += 1
            elif token == "]":
                square = max(0, square - 1)
            elif token == "(":
                paren += 1
            elif token == ")":
                paren = max(0, paren - 1)
            cursor += 1
        invocations.append((local, props))
        index = cursor + 1
    return invocations

