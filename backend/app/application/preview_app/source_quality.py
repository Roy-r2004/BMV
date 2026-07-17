"""Pure source-quality heuristics shared by codegen and safety.

Kept outside both packages so neither depends on the other.
"""
from __future__ import annotations

import re

from app.application.preview_app.patterns import _STRING_LINE_RE


def looks_truncated_source(content: str) -> bool:
    """Heuristic: reject AI file writes cut off mid-line (common token-limit failure)."""
    stripped = content.rstrip()
    if len(stripped) < 20:
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
