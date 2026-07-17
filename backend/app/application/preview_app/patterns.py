"""Shared regex/constants for preview source analysis (leaf module)."""
from __future__ import annotations

import re

_MOCK_IMPORT_RE = re.compile(
    r"import\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['\"][^'\"]*data/mock['\"]"
)
_STRING_LINE_RE = re.compile(
    r"^(\s*(?:[\w.\[\]\"]+\s*:\s*)?)'(.*)'(\s*[,;]?\s*)$"
)

_SEEDED_STUB_DETAIL_MARKER = "record for demo lists"
_DATE_FIELD_KEYS = (
    "date",
    "dropOffDate",
    "startDate",
    "scheduledAt",
    "createdAt",
    "timestamp",
)
_LIST_EXPORT_RE = re.compile(
    r"export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*",
    re.MULTILINE,
)
_EMPTY_ARRAY_EXPORT_RE = re.compile(
    r"export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*\[\s*\]\s*;"
)
_TYPED_MOCK_EXPORT_RE = re.compile(
    r"export\s+const\s+(brand_name|brandName|owner_name|ownerName|design_system|designSystem|manifest|brandManifest|brand_manifest)\s*=\s*",
    re.MULTILINE,
)
_MOCK_SELF_IMPORT_RE = re.compile(
    r"^\s*import\s+[^;\n]*from\s*['\"][^'\"]*(?:/)?mock['\"]\s*;?\s*$",
    re.MULTILINE,
)
_EMPTY_ARRAY_STATE_RE = re.compile(
    r"const\s*\[\s*(\w+)\s*,\s*set\w+\s*\]\s*=\s*useState\s*(?:<[^(]*>)?\s*\(\s*\[\s*\]\s*\)"
)
_MOCK_IMPORT_ANY_RE = re.compile(
    r"^\s*import\s+[^;\n]*from\s*['\"][^'\"]*data/mock['\"]",
    re.MULTILINE,
)

_BRAND_EXPORT_RE = re.compile(r"export\s+const\s+brand\s*=\s*\{", re.MULTILINE)
MAX_BRAND_ARRAY_LEN = 12
DEFAULT_DYNAMIC_ARRAY_LEN = 3
_BRAND_ACCESS_RE = re.compile(
    r"""\bbrand(?P<chain>(?:(?:\s*\?\.\s*|\s*\.\s*)[A-Za-z_][A-Za-z0-9_]*|\s*\[\s*(?:\d+|[A-Za-z_][A-Za-z0-9_]*)\s*\])+)"""
)
_BRAND_CHAIN_PART_RE = re.compile(
    r"""(?:\?\.)\s*([A-Za-z_][A-Za-z0-9_]*)"""
    r"""|\.\s*([A-Za-z_][A-Za-z0-9_]*)"""
    r"""|\[\s*(\d+)\s*\]"""
    r"""|\[\s*([A-Za-z_][A-Za-z0-9_]*)\s*\]"""
)

_ALLOWED_NPM_IMPORTS = {
    "react",
    "react-dom",
    "react-router-dom",
    "react/jsx-runtime",
}
_CURATED_UI_NPM_IMPORTS = {
    "react",
    "react-dom",
    "react-router-dom",
    "clsx",
    "tailwind-merge",
    "class-variance-authority",
    "recharts",
    "@tanstack/react-table",
    "@radix-ui/react-dialog",
    "@radix-ui/react-select",
    "@radix-ui/react-tabs",
    "@radix-ui/react-tooltip",
    "motion",
    "lucide-react",
    "sonner",
    "date-fns",
}
_STUBBED_NPM_IMPORTS = {
    "@headlessui/react": "src/components/UiHeadless",
    "@headlessui/react/dist": "src/components/UiHeadless",
}
_IMPORT_FROM_RE = re.compile(
    r"""^\s*import\s+(?:type\s+)?(?:[\s\S]*?)\s+from\s+['"]([^'"]+)['"]\s*;?\s*(?://.*)?$""",
    re.MULTILINE,
)
_SIDE_EFFECT_IMPORT_RE = re.compile(
    r"""^\s*import\s+['"]([^'"]+)['"]\s*;?\s*(?://.*)?$""",
    re.MULTILINE,
)
_FORBIDDEN_RUNTIME_IMPORT_LINE_RE = re.compile(
    r"""^[^\S\r\n]*(?:[^\r\n]*\b(?:require|import)\s*\([^\r\n]*"""
    r"""|import\s+[A-Za-z_$][\w$]*\s*=[^\r\n]*)"""
    r"""[^\r\n]*(?:\r?\n|$)""",
    re.MULTILINE,
)
_HEADLESS_SYMBOLS = (
    "Transition",
    "Dialog",
    "Menu",
    "Disclosure",
    "Listbox",
    "Combobox",
    "Popover",
    "Tab",
    "Switch",
    "RadioGroup",
    "Portal",
)
_STATIC_UI_IMPORT_RE = re.compile(
    r"""^[ \t]*import[ \t]+(?P<clause>[^;'"`]+?)[ \t]+from[ \t]*"""
    r"""(?P<quote>['"])(?P<source>[^'"]+)(?P=quote)[ \t]*;?[ \t]*(?:\r?\n|$)""",
    re.MULTILINE,
)
_ROUTER_SYMBOLS = (
    "Link",
    "NavLink",
    "Outlet",
    "Navigate",
    "useNavigate",
    "useLocation",
    "useParams",
)

_MOCK_FORBIDDEN_STUB_NAMES = frozenset(
    {
        "SkeletonComposer",
        "getSkeleton",
        "PublicShell",
        "OpsShell",
        "PublicNav",
        "BrandFooter",
        "MarketingHero",
        "FeatureBento",
        "ProductShowcase",
        "ProcessSection",
        "TestimonialRail",
        "CTABand",
        "BookingPanel",
        "PageHeader",
        "StatCard",
        "ChartCard",
        "FilterBar",
        "DataTable",
        "ActivityFeed",
        "RiskQueue",
        "EmptyState",
        "Button",
        "Badge",
        "Input",
        "Select",
        "Dialog",
        "Tabs",
        "LogoMarquee",
        "CredentialStrip",
        "SpotlightCard",
        "ResultRail",
        "AccentBeam",
        "UiIcon",
        "AppLink",
        "toast",
    }
)

_NAV_IMPORT_RE = re.compile(
    r"^\s*import\s+Nav\s+from\s+['\"][^'\"]+['\"]\s*;?\s*\n",
    re.MULTILINE,
)
_NAV_JSX_RE = re.compile(r"<Nav\b[^>]*/>\s*", re.DOTALL)
_UI_ICON_USAGE_RE = re.compile(
    r"<UiIcon\b[^>]*\bname\s*=\s*(?:\{\s*)?['\"]([a-zA-Z0-9_-]+)['\"]"
)
_ICON_MAP_DECL_RE = re.compile(r"\bconst\s+(\w+)\s*(?::[^=]+)?=\s*\{")
_ICON_MAP_KEY_RE = re.compile(
    r"(?:^|[,{\n])\s*(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z_$][\w$-]*))\s*:"
)
_NAMED_UIICON_IMPORT_RE = re.compile(
    r"""import\s*\{\s*UiIcon\s*\}\s*from\s*(['"][^'"]*UiIcons['"])\s*;?""",
    re.MULTILINE,
)
_NAMED_ICONS_IMPORT_RE = re.compile(
    r"""import\s*\{([^}]+)\}\s*from\s*['"][^'"]*UiIcons['"]""",
    re.MULTILINE,
)


def design_system_dict(primary: str, secondary: str, font: str) -> dict:
    primary = primary or "#6366f1"
    secondary = secondary or primary
    font_token = (font or "Inter").split(",")[0].strip().strip('"').strip("'") or "Inter"
    font_class = re.sub(r"[^a-z0-9]+", "", font_token.lower()) or "sans"
    slug = re.sub(r"[^a-z0-9]+", "+", font_token.lower())
    return {
        "primary_color": primary,
        "secondary_color": secondary,
        "accent": primary,
        "text_color": "#0f172a",
        "muted_text_color": "#475569",
        "background_color": "#fafafa",
        "font_family": font_class,
        "font_import_url": f"https://fonts.googleapis.com/css2?family={slug}:wght@400;500;600;700&display=swap",
        "section_spacing": "4rem",
        "border_radius": "1rem",
        "card_style": "shadow (rgba(0,0,0,0.05))",
    }


def brand_object_span(mock: str) -> tuple[int, int] | None:
    match = _BRAND_EXPORT_RE.search(mock)
    if not match:
        return None
    start = match.end()
    depth = 1
    index = start
    while index < len(mock) and depth:
        if mock[index] == "{":
            depth += 1
        elif mock[index] == "}":
            depth -= 1
        index += 1
    return None if depth else (start, index - 1)


def strip_ts_comments_and_strings(src: str) -> str:
    out: list[str] = []
    index = 0
    while index < len(src):
        char = src[index]
        nxt = src[index + 1] if index + 1 < len(src) else ""
        if char == "/" and nxt == "/":
            while index < len(src) and src[index] != "\n":
                out.append(" ")
                index += 1
            continue
        if char == "/" and nxt == "*":
            out.extend((" ", " "))
            index += 2
            while index < len(src) - 1 and src[index : index + 2] != "*/":
                out.append("\n" if src[index] == "\n" else " ")
                index += 1
            if index < len(src) - 1:
                out.extend((" ", " "))
                index += 2
            continue
        if char in ("'", '"', "`"):
            quote = char
            out.append(" ")
            index += 1
            while index < len(src):
                current = src[index]
                if current == "\\" and index + 1 < len(src):
                    out.extend((" ", " "))
                    index += 2
                    continue
                out.append("\n" if current == "\n" else " ")
                index += 1
                if current == quote:
                    break
            continue
        out.append(char)
        index += 1
    return "".join(out)
