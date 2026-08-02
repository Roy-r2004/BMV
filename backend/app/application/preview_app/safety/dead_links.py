"""Deterministic repair for links pointing at routes the app does not serve.

Dead links are **37 of the 49 blocking quality-gate issues** across requests
77-85, and **5 of those 9 gate failures were dead links and nothing else** — the
single largest reason a finished preview is withheld.

Measured on those runs they are neither typos nor routes that assembly dropped
(`declared - rendered` is empty on every one of 78/81/82/84/85). The writers
link to pages that were never planned: `/about`, `/restaurant`, `/dining`,
`/experiences`, `/plan-your-stay`.

That rules out retargeting as the whole answer. Of the 31 distinct dead hrefs,
**22 have no plausible target**, and sending those to `/` wholesale is precisely
the catch-all disguise `rendered_route_paths` refuses to accept — a link that
looks live and goes somewhere else. So the guard is graded:

1. **Retarget** where a real destination exists — a served parent
   (`/patient/messages/new` -> `/patient/messages`, 6 of 31) or a served
   dash-prefix (`/book-canoe-trip` -> `/book`, 3 of 31).
2. **Unlink** where none does and the href is a JSX attribute we can prove is
   optional. `Button` declares `href?: string` and only renders an anchor
   `if (href)`; an `<a>` without one is inert. Dropping the attribute keeps the
   text and the layout and removes the lie.
3. **Drop the whole entry** where the href sits in an object inside an array — a
   footer item, a quick-link tile. Removing one element cannot change the
   array's type, and it is the only honest repair: request 88 shipped a footer
   whose Activities, Contact and Privacy Policy links all landed on the home
   page, which reads as navigable and is not. Never the last element; an empty
   footer is a different defect.
4. **Home, recorded** for a standalone object value (`primaryCta={{…}}`),
   because deleting a key can break a required prop type and a guard that
   breaks the build is worse than the dead link it set out to fix.

Note the asymmetry in 2 vs 3: *replacing* an href value cannot change a prop's
type, so it is safe on any tag; *removing* the key can, so it is confined to the
tags whose contract we own. Only `href` and `defaultPath` string values are
rewritten at all — `<Link to=…>` is not matched here, or by the sweep that
reports these, so it is nobody's business but the gate's.

Every repair is counted, returned as a guard action and logged per file. The
gate stops blocking on these, so that count becomes the only remaining signal
that the writers invent pages that were never planned — a guard that repaired
them silently would hide the defect it is compensating for.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator, Mapping

from app.application.preview_app.capabilities.journey import (
    _norm,
    _route_matches,
    served_route_paths,
)
from app.infrastructure.logging import get_logger

log = get_logger("SafetyGuards")

#: JSX tags whose `href` is optional, so removing it cannot fail typecheck.
#: `Button` is the template's own (`ui/core/Button.tsx:34`, `href?: string`),
#: and a bare `<a>` is valid HTML. Anything else keeps its href and stays the
#: gate's problem — guessing at a third-party prop contract is how a guard turns
#: a dead link into a red build.
_UNLINKABLE_TAGS = frozenset({"a", "Button", "NavLink"})

#: `href="/x"`, `href={"/x"}`, `href={`/x/${id}`}`, `"href": "/x"`, `href: '/x'`.
_HREF_RE = re.compile(
    r"""(?P<key>(?<![\w-])["']?(?:href|defaultPath)["']?)"""
    r"""(?P<mid>\s*[:=]\s*\{?\s*)"""
    r"""(?P<quote>["'`])(?P<value>/[^"'`]*)(?P=quote)"""
    r"""(?P<close>\s*\}?)"""
)


def _parents(path: str) -> Iterator[str]:
    parts = path.strip("/").split("/")
    for cut in range(len(parts) - 1, 0, -1):
        yield "/" + "/".join(parts[:cut])


def _dash_shortenings(path: str) -> Iterator[str]:
    parts = path.strip("/").split("/")
    last = parts[-1]
    while "-" in last:
        last = last.rsplit("-", 1)[0]
        yield "/" + "/".join(parts[:-1] + [last])


def resolve_dead_href(href: str, served: set[str]) -> str | None:
    """The nearest destination the router actually serves, or None.

    `/` is never returned: "no real target" and "send them home" are different
    answers and the caller has to choose between them knowingly.
    """
    for candidate in (*_parents(href), *_dash_shortenings(href)):
        if candidate != "/" and _route_matches(candidate, served):
            return candidate
    return None


def _path_of(value: str) -> str:
    """The route part of an href — `/contact#inquire` is a link to `/contact`."""
    return value.split("#", 1)[0].split("?", 1)[0] or "/"


def _shape_of(value: str) -> str:
    """The path a template literal resolves to: `/gallery/${id}` -> `/gallery/:_`."""
    return re.sub(r"\$\{[^}]*\}", ":_", value)


def _bracket_spans(source: str) -> list[tuple[int, int, str]]:
    """Every `{...}` and `[...]` span, ignoring brackets inside strings.

    A backward scan cannot tell `}` in code from `}` in a template literal, and
    the writers emit plenty of both. One forward pass with a stack can.
    """
    spans: list[tuple[int, int, str]] = []
    stack: list[tuple[int, str]] = []
    quote: str | None = None
    i = 0
    while i < len(source):
        ch = source[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            elif quote == "`" and ch == "$" and source[i : i + 2] == "${":
                # `${` re-enters code inside a template literal.
                stack.append((i + 1, "{"))
                quote = None
                i += 2
                continue
        elif ch in "\"'`":
            quote = ch
        elif ch in "{[":
            stack.append((i, ch))
        elif ch in "}]":
            if stack:
                start, opener = stack.pop()
                if (opener, ch) in (("{", "}"), ("[", "]")):
                    spans.append((start, i, opener))
        i += 1
    return spans


def _array_element_span(
    source: str, at: int, spans: list[tuple[int, int, str]]
) -> tuple[int, int] | None:
    """The `{...}` element to delete when `at` sits in an object inside an array.

    Deleting a whole entry is type-safe — the array's element type is unchanged
    and it simply has one fewer — and it is the only honest repair for a footer
    item whose page was never built. Grounding it instead produces three links
    labelled Activities, Contact and Privacy Policy that all land on the home
    page, which reads as navigable and is not.
    """
    enclosing = [s for s in spans if s[0] < at < s[1] and s[2] == "{"]
    if not enclosing:
        return None
    start, end, _ = max(enclosing, key=lambda s: s[0])
    if not source[:start].rstrip().endswith(("[", ",")):
        return None
    if not [s for s in spans if s[0] < start and s[1] > end and s[2] == "["]:
        return None
    after = source[end + 1 :]
    trailing = after.lstrip()
    # Only ever take the comma *after* the entry. The final entry's only comma
    # is the one in front of it, which the previous entry's deletion has already
    # claimed — two edits over one character, and the collision resolver drops
    # one of them silently, leaving the link dead. Request 82's `nextSteps` had
    # four dead entries and shipped with the fourth still pointing at
    # `/plan-your-stay`.
    #
    # It also means an all-dead list keeps its last entry, grounded. An empty
    # footer is a different defect, not a fix for this one.
    if not trailing.startswith(","):
        return None
    return start, end + 1 + (len(after) - len(trailing)) + 1


def _owning_tag(source: str, at: int) -> str | None:
    """The JSX tag an attribute at `at` belongs to, or None if it is not one."""
    open_at = source.rfind("<", 0, at)
    if open_at < 0:
        return None
    # An intervening `>` means the `<` belongs to an earlier, already-closed tag,
    # so this href is object data rather than an attribute.
    if ">" in source[open_at:at]:
        return None
    match = re.match(r"<\s*([A-Za-z][\w.]*)", source[open_at:])
    return match.group(1) if match else None


def repair_file_dead_links(source: str, served: set[str]) -> tuple[str, dict[str, int]]:
    """Repair every dead href in one file. Pure — no IO, so it is testable."""
    counts = {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 0}
    edits: list[tuple[int, int, str]] = []
    spans = _bracket_spans(source)

    for match in _HREF_RE.finditer(source):
        raw = match.group("value")
        # `/owner/...` is a literal ellipsis in template prose, not a route.
        if "..." in raw:
            continue
        probe = _shape_of(_path_of(raw)) if "${" in raw else _path_of(raw)
        if _route_matches(probe, served):
            continue

        target = resolve_dead_href(_norm(probe), served)
        if target is not None:
            start, end = match.span("value")
            edits.append((start, end, target))
            counts["retargeted"] += 1
            continue

        tag = _owning_tag(source, match.start())
        if tag in _UNLINKABLE_TAGS:
            edits.append((match.start(), match.end(), ""))
            counts["unlinked"] += 1
            continue

        element = _array_element_span(source, match.start(), spans)
        if element is not None:
            edits.append((element[0], element[1], ""))
            counts["dropped"] += 1
            continue

        start, end = match.span("value")
        edits.append((start, end, "/"))
        counts["homed"] += 1

    if not edits:
        return source, counts
    # A dropped array element can swallow a later href match inside the same
    # object. Applying both would splice into text that no longer exists.
    kept: list[tuple[int, int, str]] = []
    for edit in sorted(edits):
        if kept and edit[0] < kept[-1][1]:
            continue
        kept.append(edit)
    out = source
    for start, end, replacement in reversed(kept):
        out = out[:start] + replacement + out[end:]
    return out, counts


def repair_dead_links(
    workspace: Path | str, architect: Mapping[str, Any]
) -> list[str]:
    """Retarget, unlink or ground every dead href in the workspace.

    Returns one action string per file changed, in the shape
    `apply_workspace_guards` collects. Fails open: with no router on disk there
    is no route table to judge against, and inventing one would neutralise every
    link in the app.
    """
    root = Path(workspace)
    served = served_route_paths(root, architect)
    if not served:
        return []

    from app.application.preview_app.protected_paths import is_template_owned_path

    actions: list[str] = []
    totals = {"retargeted": 0, "unlinked": 0, "dropped": 0, "homed": 0}
    for path in sorted((root / "src").rglob("*.ts*")):
        rel = path.relative_to(root).as_posix()
        # `apply_workspace_guards` restores template-owned files on its way out,
        # so repairing one here is undone before the build and redone on the next
        # attempt. A template component that hardcodes a route it cannot
        # guarantee is a defect in the template and is fixed there —
        # `MarketingHero`'s default CTA was `/gallery`.
        if is_template_owned_path(rel, architect):
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        repaired, counts = repair_file_dead_links(source, served)
        if repaired == source:
            continue
        try:
            path.write_text(repaired, encoding="utf-8")
        except OSError as e:  # a read-only or vanished file is not worth a crash
            log.warning("dead-link repair could not write %s: %s", path, e)
            continue
        for key in totals:
            totals[key] += counts[key]
        actions.append(
            f"dead-links:{rel} ("
            + ", ".join(f"{k}={v}" for k, v in counts.items() if v)
            + ")"
        )
    if actions:
        log.info(
            "dead links repaired across %s file(s): %s",
            len(actions),
            ", ".join(f"{k}={v}" for k, v in totals.items() if v),
        )
    return actions


__all__ = ["repair_dead_links", "repair_file_dead_links", "resolve_dead_href"]
