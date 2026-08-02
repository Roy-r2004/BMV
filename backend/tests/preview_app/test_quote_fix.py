"""An unescaped apostrophe inside a single-quoted TS string breaks the build.

Converted from a six-line print-probe that pytest never collected (roadmap 0.9).
The probe printed `changed:` and the fixed line and left a human to decide
whether it was right; these assert it.

Not in the brief's list of six — `tests/test_every_test_file_is_collected.py`
found this one and the empty `test_qa_probe.py` the moment it was added.
"""
from __future__ import annotations

from app.application.preview_app.source_quality import fix_unescaped_apostrophes

#: The line from the original probe, verbatim: mock copy for a restaurant
#: preview, where `station's` closes the string early and everything after it
#: becomes syntax errors.
_SAMPLE = (
    "  text: 'Fixing just one station's over-portioning saved us "
    "$1,200/month in ingredient costs.',"
)


def test_an_apostrophe_inside_a_single_quoted_string_is_escaped() -> None:
    fixed, changed = fix_unescaped_apostrophes(_SAMPLE)

    assert changed is True
    assert "station\\'s" in fixed, f"apostrophe left unescaped: {fixed!r}"
    # The delimiters and the rest of the content must survive untouched — a
    # fixer that escapes the apostrophe by mangling the quoting trades one
    # build break for another.
    assert fixed.startswith("  text: '")
    assert fixed.endswith("',")
    assert "$1,200/month in ingredient costs." in fixed


def test_a_line_with_nothing_to_fix_is_returned_unchanged() -> None:
    """`changed` is the signal callers use to decide whether to rewrite a file."""
    clean = "  text: 'No apostrophes here at all.',"
    fixed, changed = fix_unescaped_apostrophes(clean)

    assert changed is False
    assert fixed == clean


def test_an_already_escaped_apostrophe_is_not_double_escaped() -> None:
    """Running the fixer twice must be a no-op on its own output."""
    once, _ = fix_unescaped_apostrophes(_SAMPLE)
    twice, changed_again = fix_unescaped_apostrophes(once)

    assert twice == once, f"second pass changed the line again: {twice!r}"
    assert changed_again is False
