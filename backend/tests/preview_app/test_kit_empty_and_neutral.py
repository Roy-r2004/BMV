"""Shared kit components must be industry-neutral and must not render empty shells.

Both defects were found only by rendering a generated app and looking at it:

- `CredentialStrip`'s default heading was the literal `'Clinical trust'`, so a
  fine-art gallery page displayed "CLINICAL TRUST" as a section eyebrow whenever
  the generator did not pass its own heading.
- `CredentialStrip`, `FeatureBento` and `TestimonialRail` each rendered their
  heading (and, for the bento, a "01 / 00" carousel counter) with an empty body
  when handed `items=[]`, which reads as an unfinished page rather than an absent
  section.
"""
from __future__ import annotations

import re

from app.core.config import settings

_KIT = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui" / "public"

# Vocabulary that silently brands a generic kit component for one industry.
_INDUSTRY_WORDS = (
    "clinical",
    "clinic",
    "dental",
    "dentist",
    "patient",
    "treatment",
    "appointment",
    "orthodont",
)

_DEFAULT_STRING_PROP_RE = re.compile(
    r"^\s*(?:heading|title|label|eyebrow|description)\s*=\s*(['\"])(.+?)\1\s*,?\s*$",
    re.M,
)


def _source(name: str) -> str:
    return (_KIT / f"{name}.tsx").read_text(encoding="utf-8")


def test_no_kit_component_defaults_to_industry_specific_copy() -> None:
    offenders: list[str] = []
    for path in sorted(_KIT.glob("*.tsx")):
        source = path.read_text(encoding="utf-8")
        for _quote, value in _DEFAULT_STRING_PROP_RE.findall(source):
            low = value.lower()
            if any(word in low for word in _INDUSTRY_WORDS):
                offenders.append(f"{path.name}: {value!r}")
    assert not offenders, (
        "shared kit components must not default to one industry's vocabulary — a "
        f"generic default leaks onto every business that does not override it: {offenders}"
    )


def test_credential_strip_default_heading_is_neutral() -> None:
    source = _source("CredentialStrip")
    assert "'Clinical trust'" not in source
    assert re.search(r"heading\s*=\s*'[^']+'", source), "expected a default heading to remain"


def test_empty_items_render_nothing_rather_than_a_bare_heading() -> None:
    """Each of these must bail out before rendering its section wrapper."""
    for name in ("CredentialStrip", "FeatureBento", "TestimonialRail"):
        source = _source(name)
        assert re.search(r"if \(!?\s*(?:is[A-Za-z]*Empty|items\.length)", source), (
            f"{name} has no empty-items guard, so it renders a heading over an empty body"
        )


def test_feature_bento_counter_carries_no_placeholder_jargon() -> None:
    source = _source("FeatureBento")
    assert "Guest path" not in source, (
        "'Guest path · 01 / 03' shipped as visible customer-facing copy"
    )


def test_guard_precedes_the_rendered_section() -> None:
    """The bail-out must come before the JSX, or it does not prevent the shell."""
    for name in ("CredentialStrip", "TestimonialRail"):
        source = _source(name)
        guard = source.index("items.length")
        section = source.index("<section")
        assert guard < section, f"{name} guard must precede its <section>"


def test_feature_bento_guard_runs_after_hooks() -> None:
    """React forbids an early return before hooks; the guard must sit after them."""
    source = _source("FeatureBento")
    early_return = source.index("if (isEmpty) return null;")
    last_hook = max(
        source.rindex("React.useEffect"),
        source.rindex("React.useCallback"),
        source.rindex("React.useState"),
        source.rindex("React.useRef"),
    )
    assert last_hook < early_return, (
        "the empty guard must come after every hook call, or renders break "
        "with 'rendered fewer hooks than expected'"
    )
