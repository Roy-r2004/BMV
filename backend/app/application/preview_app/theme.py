"""Validated theme values safe for interpolation into generated CSS."""
from __future__ import annotations

import re


_SAFE_FONTS = {
    name.lower(): name
    for name in (
        "Inter",
        "Arial",
        "Atkinson",
        "Atkinson Hyperlegible",
        "Roboto",
        "Poppins",
        "Montserrat",
        "Open Sans",
        "Lato",
        "Nunito",
        "Nunito Sans",
        "DM Sans",
        "IBM Plex Sans",
        "Instrument Sans",
        "Instrument Serif",
        "Manrope",
        "Merriweather",
        "Playfair Display",
        "Source Sans 3",
        "Work Sans",
    )
}
_HEX_COLOR_RE = re.compile(
    r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$"
)


def safe_css_color(value: str | None, fallback: str) -> str:
    candidate = str(value or "").strip()
    return candidate if _HEX_COLOR_RE.fullmatch(candidate) else fallback


def safe_font_name(value: str | None, fallback: str = "Inter") -> str:
    candidate = str(value or "").split(",", 1)[0].strip().strip("\"'")
    return _SAFE_FONTS.get(candidate.lower(), fallback)


def safe_font_family(value: str | None, fallback: str = "Inter") -> str:
    return f'"{safe_font_name(value, fallback)}", system-ui, sans-serif'


def sanitize_theme_inputs(
    primary: str | None,
    secondary: str | None,
    font: str | None,
) -> tuple[str, str, str]:
    safe_primary = safe_css_color(primary, "#6366f1")
    safe_secondary = safe_css_color(secondary, safe_primary)
    return safe_primary, safe_secondary, safe_font_family(font)
