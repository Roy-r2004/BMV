"""Chat-message intent detection for refinement: full redesigns and file ranking."""
from __future__ import annotations

import re

_FULL_REDESIGN_RE = re.compile(
    r"\b("
    r"redesign\s+(everything|all|the\s+whole)|"
    r"change\s+all\s+(the\s+)?design|"
    r"completely\s+(new|different)\s+(look|design|ui)|"
    r"start\s+over|"
    r"rebuild\s+(everything|the\s+(whole\s+)?(app|preview))|"
    r"all\s+the\s+pages\s+exist|"
    r"ensure\s+all\s+(the\s+)?pages"
    r")\b",
    re.IGNORECASE,
)


def _is_full_redesign_request(message: str) -> bool:
    """Broad redesigns need a full pipeline regen, not a single chat JSON patch."""
    return bool(_FULL_REDESIGN_RE.search(message or ""))


def _rank_refinement_files(path: str) -> tuple:
    low = path.lower().replace("\\", "/")
    if "app.tsx" in low:
        return (0, path)
    if "/pages/" in low:
        return (1, path)
    if "mock.ts" in low:
        return (2, path)
    if "/layouts/" in low or "/components/" in low:
        return (3, path)
    return (4, path)
