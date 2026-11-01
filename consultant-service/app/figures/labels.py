"""Words that label a numbered thing ("Phase 2", "Exhibit 2.1", "page 7").

A digit right after one of these words is a label, not a quantity, so the
number reader does not count it. The list is closed and holds only the words
our own renderers number. A word is added here only together with a renderer
that numbers it, because every word on the list is a place for a stray digit
to hide: "Option 3" passes the law only because we draw "Option 3" ourselves.
"""
from __future__ import annotations

LABEL_WORDS: tuple[str, ...] = (
    "phase", "step", "section", "exhibit", "volume", "page", "module", "screen",
    "part", "appendix", "table", "slide", "footnote", "option",
    # the structure words the roadmap prompts name (Task 9 names them in the prompts)
    "tier", "stage", "level", "gate", "wave", "sprint", "round", "milestone",
)
