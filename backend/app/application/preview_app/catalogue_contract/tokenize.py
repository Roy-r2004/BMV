"""Catalogue source tokenization helpers."""
from __future__ import annotations

import re

def _scrub_comments_and_strings(content: str, *, strings: bool) -> str:
    chars = list(content or "")
    output = list(chars)
    index = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(chars):
        char = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            else:
                output[index] = " "
            index += 1
            continue
        if block_comment:
            output[index] = "\n" if char == "\n" else " "
            if char == "*" and nxt == "/":
                output[index + 1] = " "
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if strings:
                output[index] = "\n" if char == "\n" else " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char == "/" and nxt == "/":
            output[index] = output[index + 1] = " "
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            output[index] = output[index + 1] = " "
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            if strings:
                output[index] = " "
        index += 1
    return "".join(output)


def _source_tokens(content: str) -> list[str]:
    source = _scrub_comments_and_strings(content, strings=False)
    tokens: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            value: list[str] = []
            escaped = False
            while index < len(source):
                current = source[index]
                if escaped:
                    value.append(current)
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    index += 1
                    break
                else:
                    value.append(current)
                index += 1
            tokens.append("\0" + "".join(value))
            continue
        identifier = re.match(r"[A-Za-z_$][A-Za-z0-9_$-]*", source[index:])
        if identifier:
            tokens.append(identifier.group(0))
            index += identifier.end()
            continue
        tokens.append(char)
        index += 1
    return tokens


def _has_token_sequence(tokens: list[str], sequence: list[str]) -> bool:
    size = len(sequence)
    return any(tokens[index:index + size] == sequence for index in range(len(tokens) - size + 1))

