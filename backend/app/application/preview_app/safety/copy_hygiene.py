"""Preview safety — visible-copy hygiene (undecoded escapes, template jargon)."""
from __future__ import annotations

import re

from app.application.preview_app.workspace import (
    list_source_files,
    read_file,
    write_file,
)
from app.infrastructure.logging import get_logger

guard_log = get_logger("SafetyGuards")

# C0/C1 control code points stay escaped — decoding one would corrupt a regex
# character class or inject a raw control byte into source.
_ESCAPE_RE = re.compile(r"\\+u(?P<hex>[0-9a-fA-F]{4})")

# JSX attribute string literals and JSX text nodes are the two places where a
# `\uXXXX` sequence is never processed and therefore always renders literally.
_JSX_ATTR_RE = re.compile(
    r"""(?P<head>\b[A-Za-z_][\w:.\-]*=(?P<quote>["']))"""
    r"""(?P<value>(?:(?!(?P=quote))[^\n])*\\u[0-9a-fA-F]{4}(?:(?!(?P=quote))[^\n])*)"""
    r"""(?P=quote)""",
)
_JSX_TEXT_RE = re.compile(
    r"(?<=>)(?P<text>[^<>{}\"'`\n]*\\u[0-9a-fA-F]{4}[^<>{}\"'`\n]*)(?=<)"
)


def _decode_escapes(text: str) -> str:
    def _one(match: re.Match) -> str:
        code = int(match.group("hex"), 16)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            return match.group(0)
        return chr(code)

    return _ESCAPE_RE.sub(_one, text)


def decode_literal_unicode_escapes(workspace) -> list[str]:
    """Decode `\\uXXXX` that reached rendered copy instead of a JS string literal.

    JSX attribute values and JSX text are handed to the DOM verbatim, so an
    escape that survives into either ships as visible backslash-u-x-x-x-x.
    Escapes inside real JS/TS string literals are left alone — the engine
    decodes those, and rewriting them could corrupt a regex or data payload.
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".jsx")):
            continue
        raw = read_file(workspace, rel)
        if "\\u" not in raw:
            continue
        updated = _JSX_ATTR_RE.sub(
            lambda m: f"{m.group('head')}{_decode_escapes(m.group('value'))}{m.group('quote')}",
            raw,
        )
        updated = _JSX_TEXT_RE.sub(lambda m: _decode_escapes(m.group("text")), updated)
        if updated != raw:
            write_file(workspace, rel, updated)
            fixed.append(rel)
            guard_log.info("decoded literal unicode escapes in %s", rel)
    return fixed


#: Named HTML entities React never decodes — it escapes text, so `&copy;` reaches
#: the DOM as five visible characters. Request 47's home page footer read
#: "&copy; 2024 Jeanne Kassab Art".
#:
#: Deliberately excludes `&lt;`, `&gt;`, `&quot;` and `&apos;`: their replacements
#: are JSX and string-literal syntax, so decoding them would break the file rather
#: than the copy.
_HTML_ENTITIES: tuple[tuple[str, str], ...] = (
    ("&copy;", "©"),
    ("&reg;", "®"),
    ("&trade;", "™"),
    ("&nbsp;", " "),
    ("&mdash;", "—"),
    ("&ndash;", "–"),
    ("&hellip;", "…"),
    ("&middot;", "·"),
    ("&bull;", "•"),
    ("&lsquo;", "‘"),
    ("&rsquo;", "’"),
    ("&ldquo;", "“"),
    ("&rdquo;", "”"),
    ("&times;", "×"),
    ("&deg;", "°"),
    ("&euro;", "€"),
    ("&pound;", "£"),
    ("&amp;", "&"),
)


def decode_html_entities(workspace) -> list[str]:
    """Decode named HTML entities that reached rendered copy.

    React escapes the text it renders, so an entity in a string literal or a JSX
    text node ships verbatim: `&copy; 2024` is five characters and a year. Files
    using `dangerouslySetInnerHTML` are skipped — there the entity is doing its job.

    `&amp;` is decoded last so `&amp;copy;` does not become `©`.
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".jsx")):
            continue
        raw = read_file(workspace, rel)
        if "&" not in raw or "dangerouslySetInnerHTML" in raw:
            continue
        updated = raw
        for entity, char in _HTML_ENTITIES:
            updated = updated.replace(entity, char)
        if updated != raw:
            write_file(workspace, rel, updated)
            fixed.append(rel)
            guard_log.info("decoded literal html entities in %s", rel)
    return fixed


# Mirrors the meta-demo ban in templates/prompts/preview_app_slot_fill.j2 so it
# holds when the model ignores the prompt, plus the catalogue template's own
# placeholder eyebrows.
_BANNED_COPY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"designed to feel alive", re.I), "Built for real use"),
    (re.compile(r"make it unforgettable", re.I), "Made to last"),
    (
        re.compile(r"premium presence from first glance", re.I),
        "A clear first impression",
    ),
    (re.compile(r"cinematic first impression", re.I), "A clear first impression"),
    (re.compile(r"book the next chapter", re.I), "Get in touch"),
    (re.compile(r"signature craft", re.I), "Our work"),
    (re.compile(r"on-time delivery", re.I), "Delivered on schedule"),
    (re.compile(r"lead drop", re.I), "Featured"),
    (re.compile(r"next move", re.I), "What comes next"),
    (re.compile(r"guest path", re.I), "Chapter"),
)


def strip_template_jargon_copy(workspace) -> list[str]:
    """Replace internal/meta-demo phrasing with plain business language.

    Every banned phrase contains a space, so it can only occur inside a string
    literal, JSX text, or a comment — never an identifier or import path.
    """
    fixed: list[str] = []
    for rel in list_source_files(workspace):
        if not rel.endswith((".tsx", ".jsx", ".ts")):
            continue
        raw = read_file(workspace, rel)
        updated = raw
        for pattern, replacement in _BANNED_COPY:
            updated = pattern.sub(replacement, updated)
        if updated != raw:
            write_file(workspace, rel, updated)
            fixed.append(rel)
            guard_log.info("replaced template jargon copy in %s", rel)
    return fixed
