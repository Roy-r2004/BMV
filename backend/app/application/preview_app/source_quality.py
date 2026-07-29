"""Source-quality checks shared by codegen and safety.

Kept outside both packages so neither depends on the other. The heuristics are
pure; `tsx_parse_error` additionally shells out to the preview template's own
TypeScript compiler when one is reachable.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from app.application.preview_app.patterns import _STRING_LINE_RE
from app.core.config import settings


def _code_positions(content: str) -> Iterator[tuple[int, str]]:
    """Yield `(index, char)` for characters outside strings and comments."""
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
        yield i, ch
        i += 1


def _brace_imbalanced(content: str) -> bool:
    """True when `{` / `}` counts differ outside strings and comments."""
    depth = 0
    for _, ch in _code_positions(content):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return True
    return depth != 0


def _matching_brace_end(content: str, open_index: int) -> int | None:
    """Index of the `}` matching the `{` at open_index, ignoring strings/comments."""
    if open_index < 0 or open_index >= len(content) or content[open_index] != "{":
        return None
    depth = 0
    for index, ch in _code_positions(content):
        if index < open_index:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


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


# Content density of a catalogue page, measured from the source alone: a slot
# counts as substantive when it renders real markup rather than the shared
# "nothing here yet" placeholder. Two substantive slots is the floor for a page
# that may ship as a scaffold without being reported as a fallback.
_MIN_SUBSTANTIVE_SLOTS = 2
_MIN_SLOT_BODY_CHARS = 60
_PLACEHOLDER_SLOT_ELEMENTS = frozenset({"EmptyState"})

_SLOT_OBJECT_RE = re.compile(r"\bslots\s*=\s*\{")
_SLOT_ENTRY_RE = re.compile(r"(?m)^[ \t]+([A-Za-z_]\w*)\s*:\s*\(")
_JSX_ELEMENT_RE = re.compile(r"<([A-Za-z][\w.]*)")


def catalogue_slot_bodies(source: str) -> dict[str, str]:
    """JSX body of every `slots = { name: ( … ) }` entry in a catalogue page."""
    match = _SLOT_OBJECT_RE.search(source or "")
    if not match:
        return {}
    open_index = match.end() - 1
    close_index = _matching_brace_end(source, open_index)
    if close_index is None:
        return {}
    block = source[open_index + 1 : close_index]
    entries = list(_SLOT_ENTRY_RE.finditer(block))
    bodies: dict[str, str] = {}
    for index, entry in enumerate(entries):
        stop = entries[index + 1].start() if index + 1 < len(entries) else len(block)
        bodies[entry.group(1)] = block[entry.end() : stop].strip()
    return bodies


def _slot_body_is_substantive(body: str) -> bool:
    elements = set(_JSX_ELEMENT_RE.findall(body))
    if not elements or elements <= _PLACEHOLDER_SLOT_ELEMENTS:
        return False
    return len(" ".join(body.split())) >= _MIN_SLOT_BODY_CHARS


def substantive_slot_count(source: str) -> int:
    """Number of slots rendering markup beyond the shared empty-state placeholder."""
    return sum(
        1 for body in catalogue_slot_bodies(source).values() if _slot_body_is_substantive(body)
    )


def catalogue_page_is_thin(source: str) -> bool:
    """True when a catalogue page carries too little rendered content to ship."""
    return substantive_slot_count(source) < _MIN_SUBSTANTIVE_SLOTS


_MAX_PARSED_SOURCE_BYTES = 256_000
_TSX_PARSE_TIMEOUT_SECONDS = 10

_TYPESCRIPT_TSX_PARSER = r"""
const ts = require(process.argv[1]);
let source = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { source += chunk; });
process.stdin.on("end", () => {
  const file = ts.createSourceFile(
    "page.tsx",
    source,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  const first = (file.parseDiagnostics || [])[0];
  if (!first) {
    process.stdout.write("ok");
    return;
  }
  const at = file.getLineAndCharacterOfPosition(first.start || 0);
  process.stdout.write(
    "line " + (at.line + 1) + ": " + ts.flattenDiagnosticMessageText(first.messageText, " ")
  );
});
"""


def _typescript_compiler() -> Path | None:
    compiler = (
        Path(settings.PREVIEW_TEMPLATE_DIR)
        / "node_modules"
        / "typescript"
        / "lib"
        / "typescript.js"
    )
    return compiler if compiler.is_file() else None


def tsx_parse_error(content: str) -> str:
    """First TypeScript/JSX syntax error in `content`, else an empty string.

    Fails open: an unreachable compiler returns "" so a missing toolchain never
    demotes every generated page to a deterministic scaffold.
    """
    if not (content or "").strip():
        return ""
    try:
        encoded = content.encode("utf-8", errors="strict")
    except UnicodeError:
        return ""
    if len(encoded) > _MAX_PARSED_SOURCE_BYTES:
        return ""
    node = shutil.which("node")
    compiler = _typescript_compiler()
    if not node or compiler is None:
        return ""
    try:
        result = subprocess.run(
            [node, "-e", _TYPESCRIPT_TSX_PARSER, str(compiler.resolve())],
            input=content,
            capture_output=True,
            text=True,
            timeout=_TSX_PARSE_TIMEOUT_SECONDS,
            check=False,
            cwd=Path(settings.PREVIEW_TEMPLATE_DIR),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return ""
    if result.returncode != 0:
        return ""
    output = (result.stdout or "").strip()
    return "" if output in ("", "ok") else output[:200]


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
