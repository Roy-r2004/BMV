"""Generic JSON extraction helpers shared across layers.

Model output is JSON *by convention*, not by construction. Three shapes broke the
old extractor, and all three were logged as `Provider output was truncated`:

1. **Prose before the fence.** The fence stripper only fired when the response
   *started* with ``` ``` ```, so an explanatory paragraph left it in place. The
   bracket matcher then latched onto the first ``{`` in the prose — request 68's
   was ``(event: { target: { value: string } })`` — and *stopped* at the first
   failure instead of trying the next candidate.
2. **The model drifts out of escaping mid-string.** Inside a long `content`
   value it starts correctly (``\\"``, ``\\n``) and then reverts to writing raw
   source: bare ``"`` where ``\\"`` was required. Requests 67 and 69 both did it.
3. **Shell-style line continuations.** Request 67 wrote ``\\`` + newline as its
   line separator inside a string, which is an invalid JSON escape.

Shapes 2 and 3 are *structurally* complete — brace-balanced, fenced, closing
``}`` present — which is why the truncation heuristics said `likely_truncated=
False` and the diagnosis went wrong for several sessions. They are not valid
JSON, and no amount of re-asking fixes a model's escaping habit. `repair_json_text`
recovers them; strict parsing is always attempted first, so a well-formed
response never takes the recovery path.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Matches every fenced block in the text, not only one anchored at position 0.
# The trailing fence is optional (`\Z`) so a response cut off before its closing
# fence still yields its body.
_FENCE_BLOCK_RE = re.compile(
    r"```[ \t]*[A-Za-z0-9_+.-]*[ \t]*\r?\n(.*?)(?:\r?\n[ \t]*```|\Z)",
    re.DOTALL,
)
_HEX4_RE = re.compile(r"[0-9a-fA-F]{4}")

#: Escapes JSON actually defines, minus `u` which needs its four hex digits.
_SIMPLE_ESCAPES = '"\\/bfnrt'
#: Characters that can legally begin a JSON value.
_VALUE_STARTS = '"[{-0123456789tfn'
_WS = " \t\r\n"
_CONTROL_ESCAPES = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}

#: How many `{` starts the span scanner will try before giving up.
_MAX_OBJECT_SPANS = 6


def _strip_markdown_fence_once(text: str) -> str:
    """Remove a single leading/trailing ``` fence without MULTILINE line damage."""
    text = text.strip()
    if not text.startswith("```"):
        return text
    text = re.sub(r"^```(?:json|tsx?|javascript|typescript)?\s*\n?", "", text, count=1)
    text = re.sub(r"\n?```\s*$", "", text, count=1)
    return text.strip()


def fenced_blocks(text: str) -> list[str]:
    """Every fenced block body in `text`, in order of appearance."""
    return [
        match.group(1).strip()
        for match in _FENCE_BLOCK_RE.finditer(text or "")
        if match.group(1).strip()
    ]


def balanced_object_spans(text: str, limit: int = _MAX_OBJECT_SPANS) -> list[str]:
    """Candidate ``{...}`` spans, outermost-first.

    The old implementation took the first ``{`` and gave up if the span it closed
    would not parse. A brace inside a prose sentence was therefore fatal.
    """
    spans: list[str] = []
    search_from = 0
    while len(spans) < limit:
        start = text.find("{", search_from)
        if start == -1:
            break
        end = _matching_brace(text, start)
        if end > start:
            span = text[start:end]
            if span not in spans:
                spans.append(span)
        search_from = start + 1
    # An unescaped quote inside a string desynchronises the matcher above, so
    # also offer the widest possible span for the repair pass to work on.
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last > first and text[first : last + 1] not in spans:
        spans.append(text[first : last + 1])
    return spans


def _matching_brace(text: str, start: int) -> int:
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return -1


def _skip_ws(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i] in _WS:
        i += 1
    return i


def _string_closes(text: str, after_quote: int, is_key: bool, container: str) -> bool:
    """Decide whether an unescaped ``"`` ends the string, from grammar position.

    A *key* is followed by ``:``; a *value* is followed by ``,``, ``}``, ``]`` or
    end of input, and a ``,`` must be followed by the next key (in an object) or
    the next value (in an array). Judging by grammar position rather than by a
    bare lookahead is what separates request 67's real terminator from the
    ``"item1": "https://…"`` the model left unescaped inside a `content` string.
    """
    k = _skip_ws(text, after_quote)
    n = len(text)
    if is_key:
        return k < n and text[k] == ":"
    if k >= n:
        return True
    ch = text[k]
    if ch in "}]":
        return True
    if ch == ",":
        m = _skip_ws(text, k + 1)
        if m >= n:
            return True
        if container == "{":
            return text[m] == '"'
        return text[m] in _VALUE_STARTS
    return False


def repair_json_text(text: str) -> str | None:
    """Re-escape a model's under-escaped JSON. Returns None if nothing changed.

    Single pass, no backtracking: the JSON *skeleton* is tracked exactly, and the
    only judgement call is whether an unescaped ``"`` inside a string terminates
    it — decided by grammar position (see `_string_closes`). The result is still
    handed to `json.loads`, so a wrong call fails closed rather than inventing a
    document.
    """
    out: list[str] = []
    changed = False
    i = 0
    n = len(text)
    stack: list[str] = []
    expect_key = False
    in_str = False
    str_is_key = False

    while i < n:
        ch = text[i]

        if not in_str:
            if ch == '"':
                str_is_key = bool(stack) and stack[-1] == "{" and expect_key
                in_str = True
            elif ch in "{[":
                stack.append(ch)
                expect_key = ch == "{"
            elif ch in "}]":
                if stack:
                    stack.pop()
                expect_key = False
            elif ch == ":":
                expect_key = False
            elif ch == ",":
                expect_key = bool(stack) and stack[-1] == "{"
            out.append(ch)
            i += 1
            continue

        if ch == "\\":
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt and nxt in _SIMPLE_ESCAPES:
                out.append(ch)
                out.append(nxt)
                i += 2
                continue
            if nxt == "u" and _HEX4_RE.match(text, i + 2):
                out.append(text[i : i + 6])
                i += 6
                continue
            changed = True
            if nxt in ("\r", "\n"):
                # Shell-style line continuation where the grammar wanted `\n`.
                out.append("\\n")
                i += 2
                if nxt == "\r" and i < n and text[i] == "\n":
                    i += 1
                continue
            if nxt in (" ", "\t"):
                # The same continuation with its newline collapsed to spaces.
                # Keeping the backslash would ship source that cannot parse.
                i += 1
                continue
            # Anything else — `\d` in a regex, say — is preserved, not guessed at.
            out.append("\\\\")
            i += 1
            continue

        if ch == '"':
            container = stack[-1] if stack else ""
            if _string_closes(text, i + 1, str_is_key, container):
                out.append('"')
                in_str = False
                if str_is_key:
                    expect_key = False
            else:
                out.append('\\"')
                changed = True
            i += 1
            continue

        if ch in _CONTROL_ESCAPES or ord(ch) < 0x20:
            changed = True
            out.append(_CONTROL_ESCAPES.get(ch) or "\\u%04x" % ord(ch))
            i += 1
            continue

        out.append(ch)
        i += 1

    if in_str or stack:
        # Genuinely unterminated. Say so instead of inventing a closing brace.
        return None
    return "".join(out) if changed else None


def extract_json_with_meta(text: str) -> tuple[Any, dict[str, Any]]:
    """Extract the first valid JSON value, with the method that found it.

    `meta["method"]` is one of `direct`, `fence`, `fenced-block`, `repaired`,
    `span`, `span-repaired`. Anything other than `direct`/`fence` is worth
    logging: it says the model's output needed work, and which kind.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty model output")

    sources: list[tuple[str, str]] = [("direct", text)]
    fence_once = _strip_markdown_fence_once(text)
    if fence_once and fence_once != text:
        sources.append(("fence", fence_once))
    seen = {value for _, value in sources}
    for block in fenced_blocks(text):
        if block not in seen:
            seen.add(block)
            sources.append(("fenced-block", block))

    last_error: Exception | None = None

    # 1. Strict, in order of decreasing confidence. Unchanged behaviour for any
    #    response that is already valid JSON.
    for method, source in sources:
        try:
            return json.loads(source), {"method": method, "repaired": False}
        except Exception as exc:  # noqa: BLE001 - candidate rejected, keep going
            last_error = exc

    # 2. Re-escape, still on whole sources: the common failure is one bad quote
    #    in a 30 KB file body, not a missing document.
    for method, source in sources:
        repaired = repair_json_text(source)
        if repaired is None:
            continue
        try:
            value = json.loads(repaired)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        if isinstance(value, (dict, list)):
            return value, {"method": "repaired", "repaired": True, "source": method}

    if "{" not in text:
        raise ValueError("No JSON object found in model output")

    # 3. Fall back to substring spans — prose on both sides of a bare object.
    for method, source in sources:
        for span in balanced_object_spans(source):
            try:
                return json.loads(span), {"method": "span", "repaired": False, "source": method}
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            repaired = repair_json_text(span)
            if repaired is None:
                continue
            try:
                value = json.loads(repaired)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                continue
            if isinstance(value, dict):
                return value, {"method": "span-repaired", "repaired": True, "source": method}

    raise ValueError(
        "No valid JSON object found in model output"
        + (f" (last decode error: {last_error})" if last_error else "")
    )


def extract_json_from_text(text: str):
    """Robustly extract the first valid JSON object from any model output."""
    return extract_json_with_meta(text)[0]
