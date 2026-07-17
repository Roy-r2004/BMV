"""Catalogue import path normalization."""
from __future__ import annotations

import re

_IMPORT_SOURCE_REWRITES = (
    # Deep/relative kit imports → the @/ui barrel (it re-exports everything).
    (re.compile(r"(from\s*['\"])@/ui/[^'\"]+(['\"])"), r"\g<1>@/ui\g<2>"),
    (re.compile(r"(from\s*['\"])(?:\.{1,2}/)+ui(?:/[^'\"]*)?(['\"])"), r"\g<1>@/ui\g<2>"),
    (re.compile(r"(from\s*['\"])(?:\.{1,2}/)+data/mock(['\"])"), r"\g<1>@/data/mock\g<2>"),
    (re.compile(r"(from\s*['\"])@/src/lib/(app-nav['\"])"), r"\g<1>@/lib/\g<2>"),
    (re.compile(r"(from\s*['\"])(?:\.{1,2}/)+lib/app-nav(['\"])"), r"\g<1>@/lib/app-nav\g<2>"),
    # Legacy icon module → the barrel (which re-exports UiIcon).
    (
        re.compile(
            r"(import\s*\{[^}]*\}\s*from\s*['\"])(?:@/|(?:\.{1,2}/)+)components/UiIcons(['\"])"
        ),
        r"\g<1>@/ui\g<2>",
    ),
    (
        re.compile(
            r"import\s+([A-Za-z_$][\w$]*)\s+from\s*['\"](?:@/|(?:\.{1,2}/)+)components/UiIcons['\"];?"
        ),
        r"import { UiIcon as \g<1> } from '@/ui';",
    ),
)


def normalize_catalogue_page_imports(content: str, route: dict) -> str:
    """Rewrite spelling-level import mistakes the AI keeps making.

    Deep kit paths and relative mock/nav imports are semantically identical to
    the allowed sources — rejecting the whole page over them costs the user
    real content for no build-safety gain.
    """
    if not route.get("skeleton_id") or not content:
        return content
    for pattern, replacement in _IMPORT_SOURCE_REWRITES:
        content = pattern.sub(replacement, content)
    return content
