"""Pure source-quality heuristics shared by codegen and safety.

Kept outside both packages so neither depends on the other.
"""
from __future__ import annotations

import re

from app.application.preview_app.patterns import _STRING_LINE_RE


def _brace_imbalanced(content: str) -> bool:
    """True when `{` / `}` counts differ outside strings and comments."""
    depth = 0
    in_str: str | None = None
    in_line_comment = False
    in_block_comment = False
    escape = False
    i = 0
    n = len(content)
    while i < n:
        ch = content[i]
        nxt = content[i + 1] if i + 1 < n else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch in {'"', "'", "`"}:
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return True
        i += 1
    return depth != 0


def looks_truncated_source(content: str) -> bool:
    """Heuristic: reject AI file writes cut off mid-line (common token-limit failure)."""
    stripped = content.rstrip()
    if len(stripped) < 20:
        return True
    # Mid-component cuts often end on a complete JSX tag (`>`) while braces
    # remain open — treat imbalance as truncation so slot-fill / codegen retry.
    if _brace_imbalanced(stripped):
        return True
    last = stripped.splitlines()[-1].rstrip()
    if not last:
        return False
    if stripped.endswith(("}", ");", "};", "/>", ">", '"""', "'''")):
        return False
    if last.count('"') % 2 == 1 or last.count("'") % 2 == 1:
        return True
    if re.search(r'className="[^"]*$', last):
        return True
    if re.search(r"<\w+[^>]*$", last):
        return True
    return False


def fix_unescaped_apostrophes(content: str) -> tuple[str, bool]:
    """Escape stray apostrophes inside single-quoted string literals."""
    changed = False
    out_lines = []
    for line in content.splitlines():
        m = _STRING_LINE_RE.match(line)
        if m:
            prefix, body, suffix = m.group(1), m.group(2), m.group(3)
            if re.search(r"(?<!\\)'", body):
                fixed_body = re.sub(r"(?<!\\)'", r"\\'", body)
                line = f"{prefix}'{fixed_body}'{suffix}"
                changed = True
        out_lines.append(line)
    return ("\n".join(out_lines), changed)
