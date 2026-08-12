"""What a rendered screen is, in words — for the result page and the deck.

Both surfaces caption the same screenshot, so both read it from here. When
this lived in two places they drifted within a session: the page listed
panels the deck did not mention, and a client comparing the two would have
been right to ask which one was describing their software.

The description is COMPOSED, never written. Every noun in it is a string
the image model was handed to render — the screen's own subheading, its KPI
labels, its panel titles, the AI module's headline. The sentence adds
grammar and nothing else, which is what lets a client check the caption
against the picture above it. A stage that summarised the screen instead
would be prose ABOUT the image, indistinguishable from prose that is wrong.

Returns None when the spec is unavailable or unparseable. None means "we
cannot say" — the caller renders no caption rather than a confident blank.
"""

import json
import logging

logger = logging.getLogger("consultant.screen_story")

_MAX_TRACKS = 4
_MAX_SECTIONS = 3


def _join(items: list[str]) -> str:
    """Oxford-free list: 'a', 'a and b', 'a, b and c'."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _describe(screen_title: str, tracks: list[str], sections: list[str], ai: dict | None) -> str:
    parts: list[str] = []
    if tracks:
        parts.append(f"Tracks {_join(tracks)}")
        if sections:
            parts.append(f"across {_join(sections)}")
    elif sections:
        parts.append(f"Shows {_join(sections)}")
    elif screen_title:
        parts.append(f"The {screen_title.lower()} view of the product")

    sentence = " ".join(parts).strip()
    sentence = (sentence + ".") if sentence else ""

    if ai:
        # Named, not paraphrased — the panel's own label and its own line.
        label = ai["title"] or "The AI panel"
        sentence = f"{sentence} {label} reads: “{ai['headline']}”.".strip()
    return sentence


def from_spec_json(spec_json: str | None, screen_title: str = "") -> dict | None:
    """The caption slice of a screen's spec, or None if we cannot say."""
    if not spec_json:
        return None
    try:
        spec = json.loads(spec_json)
    except (TypeError, ValueError):
        logger.warning("unparseable spec_json; screen is captioned with nothing")
        return None
    if not isinstance(spec, dict):
        return None

    tracks = [
        str(k.get("label") or "").strip()
        for k in (spec.get("kpis") or []) if str(k.get("label") or "").strip()
    ][:_MAX_TRACKS]

    sections: list[str] = []
    for panel in (spec.get("primary_panel"), spec.get("secondary_panel"), spec.get("chart")):
        title = str((panel or {}).get("title") or "").strip()
        if title and title not in sections:
            sections.append(title)
    sections = sections[:_MAX_SECTIONS]

    raw_ai = spec.get("ai") or {}
    headline = str(raw_ai.get("headline") or "").strip()
    # The spec's own rule for whether the module was drawn at all. An AI
    # panel with no headline is not on the screen, and describing one that
    # is not there advertises AI in a demo that does not show it.
    ai = {
        "title": str(raw_ai.get("title") or "").strip(),
        "headline": headline,
        "rationale": str(raw_ai.get("rationale") or "").strip(),
        "confidence": str(raw_ai.get("confidence") or "").strip(),
        "chips": [str(c).strip() for c in (raw_ai.get("chips") or []) if str(c).strip()][:4],
    } if headline else None

    subheading = str(spec.get("subheading") or "").strip()
    return {
        "subheading": subheading or None,
        "tracks": tracks,
        "sections": sections,
        "description": _describe(screen_title, tracks, sections, ai),
        "ai": ai,
    }
