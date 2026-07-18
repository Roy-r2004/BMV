"""Catalogue slot helpers and route lookup."""
from __future__ import annotations

import re

from app.application.preview_app.protected_paths import canonical_workspace_path
from app.application.ui_catalogue import get_skeleton

def catalogue_route_for_file(file_path: str, architect: dict | None) -> dict:
    target = canonical_workspace_path(file_path).lower()
    for route in (architect or {}).get("routes") or []:
        component_file = canonical_workspace_path(route.get("component_file", "")).lower()
        if component_file and component_file == target:
            return route
    return {}


def required_non_shell_slots(route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return []
    return [
        str(section)
        for section in get_skeleton(skeleton_id).get("requiredSections") or []
        if section != "shell"
    ]


def assigned_non_shell_slots(route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return []
    skeleton = get_skeleton(skeleton_id)
    required = [
        str(section)
        for section in skeleton.get("requiredSections") or []
        if section != "shell"
    ]
    assigned = [
        str(section)
        for section in route.get("section_slots") or []
        if section != "shell"
    ]
    selected = set(required + assigned)
    # Prefer the route's recipe/template order when present.
    if assigned:
        ordered = [section for section in assigned if section in selected]
        for section in required:
            if section not in ordered:
                ordered.append(section)
        for section in skeleton.get("recommendedOrder") or []:
            name = str(section)
            if name != "shell" and name in selected and name not in ordered:
                ordered.append(name)
        return ordered
    order = [
        str(section)
        for section in skeleton.get("recommendedOrder") or []
        if section != "shell"
    ]
    return [section for section in order if section in selected]


def expected_shell(route: dict) -> str:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return ""
    skeleton = get_skeleton(skeleton_id)
    return str(
        skeleton.get("shell")
        or ("OpsShell" if skeleton.get("surface") == "ops" else "PublicShell")
    )


def _declared_slot_values(tokens: list[str]) -> dict[str, list[str]]:
    """Return top-level slot properties and their value tokens."""
    start = -1
    prefix = ["const", "slots", "=", "{"]
    for index in range(len(tokens) - len(prefix) + 1):
        if tokens[index:index + len(prefix)] == prefix:
            start = index + len(prefix)
            break
    if start < 0:
        return {}

    values: dict[str, list[str]] = {}
    cursor = start
    while cursor < len(tokens):
        while cursor < len(tokens) and tokens[cursor] == ",":
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor] == "}":
            break

        key_token = tokens[cursor]
        if key_token.startswith("\0"):
            key = key_token[1:]
        elif re.match(r"^[A-Za-z_$][A-Za-z0-9_$-]*$", key_token):
            key = key_token
        else:
            key = ""

        if key and cursor + 1 < len(tokens) and tokens[cursor + 1] == ":":
            value_start = cursor + 2
            value_end = value_start
            nesting: list[str] = []
            pairs = {"(": ")", "[": "]", "{": "}"}
            while value_end < len(tokens):
                token = tokens[value_end]
                if token in pairs:
                    nesting.append(pairs[token])
                elif nesting and token == nesting[-1]:
                    nesting.pop()
                elif not nesting and token in {",", "}"}:
                    break
                value_end += 1
            values[key] = tokens[value_start:value_end]
            cursor = value_end
            continue

        if key and (
            cursor + 1 >= len(tokens)
            or tokens[cursor + 1] in {",", "}"}
        ):
            # Object shorthand is an identifier-valued property.
            values[key] = [key_token]
            cursor += 1
            continue

        # Skip unsupported property forms without treating nested keys as slots.
        nesting = []
        cursor += 1
        while cursor < len(tokens):
            token = tokens[cursor]
            if token in {"(", "[", "{"}:
                nesting.append({"(": ")", "[": "]", "{": "}"}[token])
            elif nesting and token == nesting[-1]:
                nesting.pop()
            elif not nesting and token in {",", "}"}:
                break
            cursor += 1
    return values


def _slot_value_is_present(value_tokens: list[str]) -> bool:
    tokens = list(value_tokens)
    while len(tokens) >= 2 and tokens[0] == "(" and tokens[-1] == ")":
        depth = 0
        wraps_all = True
        for index, token in enumerate(tokens):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0 and index != len(tokens) - 1:
                    wraps_all = False
                    break
        if not wraps_all or depth:
            break
        tokens = tokens[1:-1]
    return bool(tokens) and tokens not in (
        ["null"],
        ["undefined"],
        ["false"],
        ["{", "}"],
    )

