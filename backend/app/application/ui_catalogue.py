"""Read and resolve the template-owned UI catalogue for preview generation."""
from __future__ import annotations

import json
import re
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from app.core.config import settings
from app.infrastructure.logging import get_logger


ui_log = get_logger("UiCatalogue")

_SKELETON_FIELDS = (
    "id",
    "surface",
    "shell",
    "purpose",
    "requiredSections",
    "optionalSections",
    "recommendedOrder",
    "supportedVariants",
)
_COMPONENT_FIELDS = ("name", "requiredProps", "optionalProps", "variants")
_SHELL_NAVIGATION_COMPONENTS = {
    "PublicShell": ("PublicNav",),
    "OpsShell": (),
}
_SLOT_COMPONENT_DEFAULTS = {
    "shell": None,
    "hero": "MarketingHero",
    "features": "FeatureBento",
    "showcase": "ProductShowcase",
    "inquire": "InquiryPanel",
    "process": "ProcessSection",
    "testimonials": "TestimonialRail",
    "cta": "CTABand",
    "footer": "BrandFooter",
    "trust": "LogoMarquee",
    "credentials": "CredentialStrip",
    "spotlight": "SpotlightCard",
    "results": "ResultRail",
    "booking": "BookingPanel",
    "workspace": "Card",
    "summary": "Card",
    "header": "PageHeader",
    "kpis": "StatCard",
    "chart": "ChartCard",
    "filters": "FilterBar",
    "table": "DataTable",
    "activity": "ActivityFeed",
    "risk": "RiskQueue",
    "empty": "EmptyState",
    # Signature product-face slots (accounting / trading)
    "pulse": "CashPulseBar",
    "board": "InvoiceBoard",
    "recon": "ReconSplit",
    "blotter": "BlotterTape",
    "ticker": "DeskTicker",
    "expenses": "ExpenseQueue",
}

_UI_SOURCE_SUFFIXES = (".ts", ".tsx")
_PROPS_SUFFIX = "Props"
_MAX_PROP_TYPE_CHARS = 160
_MAX_SHAPE_TYPE_CHARS = 60
_MAX_MEMBERS = 24
_MAX_REFERENCED_TYPES = 8
_MAX_ALIAS_CHARS = 140
_MAX_SHAPE_MEMBERS = 10
# Callers bound the serialized contract at 5000 chars (codegen/generate.py,
# codegen/critic.py, codegen/fix_agent.py). Overshooting makes bounded_json
# collapse the whole contract into a truncated preview, so shapes are fitted
# into the remaining headroom in priority order instead.
_CONTRACT_PROMPT_BUDGET = 4900
_TYPE_SHORTHAND = (
    (re.compile(r"React\.ReactNode"), "node"),
    (re.compile(r"\([^()]*\)\s*=>\s*[\w.\[\]<>, |]+"), "fn"),
    (re.compile(r"\(\s*fn\s*\)"), "fn"),
    (re.compile(r"(?:\bfn\b\s*\|\s*)+\bfn\b"), "fn"),
)
_EXPORTED_TYPE_RE = re.compile(r"\bexport\s+(interface|type)\s+([A-Za-z_$][\w$]*)")
_MEMBER_RE = re.compile(
    r"^(?:readonly\s+)?"
    r"(?:'(?P<quoted>[^']+)'|\"(?P<dquoted>[^\"]+)\"|(?P<plain>[A-Za-z_$][\w$]*))"
    r"(?P<optional>\?)?\s*:\s*(?P<type>.+)$",
    re.DOTALL,
)
_TYPE_REFERENCE_RE = re.compile(r"\b([A-Z][A-Za-z0-9_$]*)\b")


@lru_cache(maxsize=1)
def load_catalogue() -> dict[str, Any]:
    """Load the generated catalogue from the configured preview template."""
    path = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui" / "catalogue.json"
    try:
        with path.open(encoding="utf-8") as handle:
            catalogue = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid UI catalogue JSON at {path}: {exc.msg}") from exc
    if not isinstance(catalogue, dict):
        raise ValueError(f"Invalid UI catalogue at {path}: root must be a JSON object")
    if not isinstance(catalogue.get("components"), list):
        raise ValueError(f"Invalid UI catalogue at {path}: components must be an array")
    if not isinstance(catalogue.get("skeletons"), list):
        raise ValueError(f"Invalid UI catalogue at {path}: skeletons must be an array")
    if not all(isinstance(item, dict) and item.get("name") for item in catalogue["components"]):
        raise ValueError(f"Invalid UI catalogue at {path}: every component must be an object with a name")
    if not all(isinstance(item, dict) and item.get("id") for item in catalogue["skeletons"]):
        raise ValueError(f"Invalid UI catalogue at {path}: every skeleton must be an object with an id")
    return catalogue


def _string_end(source: str, start: int) -> int:
    """Index just past the string literal opened at `start`."""
    quote = source[start]
    index = start + 1
    while index < len(source):
        char = source[index]
        if char == "\\":
            index += 2
            continue
        if char == quote:
            return index + 1
        index += 1
    return len(source)


def _strip_ts_comments(source: str) -> str:
    chunks: list[str] = []
    index = 0
    length = len(source)
    while index < length:
        char = source[index]
        if char in "'\"`":
            end = _string_end(source, index)
            chunks.append(source[index:end])
            index = end
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end < 0 else end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            chunks.append(" ")
            continue
        chunks.append(char)
        index += 1
    return "".join(chunks)


def _object_body(source: str, open_index: int) -> str | None:
    """Body between the brace at `open_index` and its match, or None if unbalanced."""
    depth = 0
    index = open_index
    while index < len(source):
        char = source[index]
        if char in "'\"`":
            index = _string_end(source, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[open_index + 1 : index]
        index += 1
    return None


def _split_top_level(text: str, separators: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "'\"`":
            end = _string_end(text, index)
            current.append(text[index:end])
            index = end
            continue
        if text.startswith("=>", index):
            current.append("=>")
            index += 2
            continue
        if char in "{([<":
            depth += 1
        elif char in "})]>":
            depth = max(0, depth - 1)
        if depth == 0 and char in separators:
            parts.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().rstrip(",;")


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _parse_members(body: str) -> tuple[dict[str, str], tuple[str, ...]]:
    members: dict[str, str] = {}
    optional: list[str] = []
    for raw in _split_top_level(body, ";\n,"):
        match = _MEMBER_RE.match(raw)
        if not match:
            continue
        name = match.group("quoted") or match.group("dquoted") or match.group("plain")
        type_text = _collapse(match.group("type"))
        if not name or not type_text or name in members:
            continue
        members[name] = _clip(type_text, _MAX_PROP_TYPE_CHARS)
        if match.group("optional"):
            optional.append(name)
        if len(members) >= _MAX_MEMBERS:
            break
    return members, tuple(optional)


def _dedupe(names: tuple[str, ...]) -> list[str]:
    ordered: list[str] = []
    for name in names:
        if name and name not in ordered:
            ordered.append(name)
    return ordered


def _type_references(text: str) -> list[str]:
    seen: list[str] = []
    for name in _TYPE_REFERENCE_RE.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def _parse_declarations(source: str) -> Iterator[tuple[str, dict[str, Any]]]:
    for match in _EXPORTED_TYPE_RE.finditer(source):
        kind, name = match.group(1), match.group(2)
        cursor = match.end()
        if kind == "interface":
            open_index = source.find("{", cursor)
            if open_index < 0:
                continue
            body = _object_body(source, open_index)
            if body is None:
                continue
            members, optional = _parse_members(body)
            extends = tuple(_type_references(source[cursor:open_index]))
            yield name, {
                "members": members,
                "optional": optional,
                "alias": "",
                "extends": extends,
            }
            continue
        equals = source.find("=", cursor)
        if equals < 0:
            continue
        remainder = source[equals + 1 :]
        stripped = remainder.lstrip()
        if stripped.startswith("{"):
            open_index = equals + 1 + (len(remainder) - len(stripped))
            body = _object_body(source, open_index)
            if body is None:
                continue
            members, optional = _parse_members(body)
            yield name, {
                "members": members,
                "optional": optional,
                "alias": "",
                "extends": (),
            }
            continue
        statement = _split_top_level(stripped, ";")[0] if stripped else ""
        alias = _clip(_collapse(statement), _MAX_ALIAS_CHARS)
        if alias:
            yield name, {
                "members": {},
                "optional": (),
                "alias": alias,
                "extends": (),
            }


@lru_cache(maxsize=1)
def load_ui_type_declarations() -> dict[str, dict[str, Any]]:
    """Exported TS interfaces/aliases under the template's src/ui, by type name.

    Best effort by design: unreadable or unparseable sources are skipped so
    prompt construction degrades to catalogue prop names instead of failing.
    """
    declarations: dict[str, dict[str, Any]] = {}
    try:
        root = settings.PREVIEW_TEMPLATE_DIR / "src" / "ui"
        paths = sorted(root.rglob("*"))
    except Exception:  # noqa: BLE001 - never break prompt construction
        return declarations
    for path in paths:
        try:
            if path.suffix not in _UI_SOURCE_SUFFIXES or not path.is_file():
                continue
            source = _strip_ts_comments(path.read_text(encoding="utf-8"))
            for name, shape in _parse_declarations(source):
                declarations.setdefault(name, shape)
        except Exception:  # noqa: BLE001 - one bad file must not lose the rest
            continue
    return declarations


@lru_cache(maxsize=256)
def ui_type_shape(type_name: str) -> dict[str, Any] | None:
    """Resolved shape of one exported template type, or None when unknown."""
    declarations = load_ui_type_declarations()
    shape = declarations.get(type_name)
    if not shape:
        return None
    members: dict[str, str] = {}
    optional: list[str] = []
    for parent in shape["extends"]:
        inherited = declarations.get(parent)
        if not inherited:
            continue
        members.update(inherited["members"])
        optional.extend(inherited["optional"])
    members.update(shape["members"])
    optional.extend(name for name in shape["optional"] if name not in optional)
    return {
        "members": members,
        "optional": tuple(name for name in optional if name in members),
        "alias": shape["alias"],
    }


def _render_shape(shape: dict[str, Any]) -> str:
    if shape["alias"]:
        return shape["alias"]
    optional = set(shape["optional"])
    return "; ".join(
        f"{name}{'?' if name in optional else ''}: {type_text}"
        for name, type_text in shape["members"].items()
    )


@lru_cache(maxsize=256)
def component_prop_shape(component_name: str) -> dict[str, Any] | None:
    """Compact prop contract for one catalogue component, derived from its source.

    Returns `{"props": "<name?: type; …>", "types": {"<Referenced>": "<shape>"}}`
    or None when the component's `…Props` interface cannot be resolved. One hop
    only: props members resolve the named types they reference, and those types
    are rendered inline rather than expanded again.
    """
    shape = ui_type_shape(f"{component_name}{_PROPS_SUFFIX}")
    if not shape or not shape["members"]:
        return None
    declarations = load_ui_type_declarations()
    referenced: dict[str, str] = {}
    for type_text in shape["members"].values():
        for name in _type_references(type_text):
            if len(referenced) >= _MAX_REFERENCED_TYPES:
                break
            if name in referenced or name not in declarations:
                continue
            nested = ui_type_shape(name)
            rendered = _render_shape(nested) if nested else ""
            if not rendered:
                continue
            referenced[name] = rendered if nested["alias"] else f"{{ {rendered} }}"
    return {"props": _render_shape(shape), "types": referenced}


def _simplify_type(type_text: str) -> str:
    simplified = type_text
    for pattern, replacement in _TYPE_SHORTHAND:
        simplified = pattern.sub(replacement, simplified)
    # Literal-union aliases are one hop deeper than the member shape but cost a
    # few characters, and unknown allowed values are their own defect class.
    declarations = load_ui_type_declarations()
    for name in _type_references(simplified):
        alias = (declarations.get(name) or {}).get("alias")
        if alias and "{" not in alias:
            simplified = simplified.replace(name, alias)
    return _clip(_collapse(simplified), _MAX_SHAPE_TYPE_CHARS)


def _compact_member_list(rendered: str) -> str:
    """`"{ title: string; detail?: string }"` -> `"title, detail?"`."""
    body = rendered.strip()
    if body.startswith("{"):
        body = body[1:-1]
    parts: list[str] = []
    for member in _split_top_level(body, ";")[:_MAX_SHAPE_MEMBERS]:
        name, _, type_text = member.partition(": ")
        simple = _simplify_type(type_text)
        # A clipped literal union reads as an allowed value; the name alone is safer.
        if simple == "string" or simple.endswith("…"):
            parts.append(name)
        else:
            parts.append(f"{name}:{simple}")
    return ", ".join(parts)


def prop_shape_entries(component_name: str) -> list[tuple[str, str]]:
    """`("<Component>.<prop>[]", "<member, member?, …>")` for object-shaped props.

    Array props come first: those element shapes are what generated pages get
    wrong (CredentialStrip items as `{label, value}` instead of `{title, detail}`).
    """
    shape = component_prop_shape(component_name)
    if not shape:
        return []
    arrays: list[tuple[str, str]] = []
    scalars: list[tuple[str, str]] = []
    for member in shape["props"].split("; "):
        prop, _, type_text = member.partition(": ")
        prop = prop.rstrip("?")
        references = _type_references(type_text)
        for type_name, rendered in shape["types"].items():
            if type_name not in references or not rendered.startswith("{"):
                continue
            members = _compact_member_list(rendered)
            if not members:
                continue
            if f"{type_name}[]" in type_text or "Array<" in type_text:
                arrays.append((f"{component_name}.{prop}[]", members))
            else:
                scalars.append((f"{component_name}.{prop}", members))
            break
    return arrays + scalars


@lru_cache(maxsize=1)
def catalogue_prop_shape_block() -> str:
    """Every catalogue component's object-prop member names, one per line.

    For prompts that have no skeleton (mock.ts synthesis feeds every page).
    """
    lines: list[str] = []
    try:
        for component in load_catalogue()["components"]:
            for key, members in prop_shape_entries(str(component.get("name") or "")):
                lines.append(f"{key} = {{ {members} }}")
    except Exception:  # noqa: BLE001 - a missing block beats a failed prompt
        return ""
    return "\n".join(lines)


def _budgeted_prop_shapes(contract: dict[str, Any], components: tuple[str, ...]) -> dict[str, str]:
    """Fit `Component.prop -> members` entries into the callers' JSON budget.

    Array element shapes go in first, then single-object props; within each group
    the page's own slot/shell/nav components lead. A shape that does not fit is
    dropped, never truncated — a partial map still reads as valid guidance.
    """
    try:
        entries: list[tuple[str, str]] = []
        for name in _dedupe(components):
            entries.extend(prop_shape_entries(name))
        used = len(json.dumps(contract, ensure_ascii=False, separators=(",", ":")))
        used += len('"prop_shapes":{},')
        shapes: dict[str, str] = {}
        for key, members in sorted(entries, key=lambda entry: not entry[0].endswith("[]")):
            if key in shapes:
                continue
            cost = (
                len(json.dumps(key, ensure_ascii=False))
                + len(json.dumps(members, ensure_ascii=False))
                + 2
            )
            if used + cost > _CONTRACT_PROMPT_BUDGET:
                continue
            shapes[key] = members
            used += cost
        return shapes
    except Exception:  # noqa: BLE001 - a missing shape beats a failed generation
        return {}


def get_skeleton(skeleton_id: str) -> dict[str, Any]:
    """Return one skeleton by its catalogue ID."""
    for skeleton in load_catalogue()["skeletons"]:
        if skeleton.get("id") == skeleton_id:
            return skeleton
    raise ValueError(f"Unknown UI skeleton: {skeleton_id}")


def _search_text(page: dict[str, Any]) -> str:
    values = (
        page.get("id"),
        page.get("title"),
        page.get("page_type"),
        page.get("purpose"),
        page.get("layout"),
        page.get("path"),
        page.get("role_id"),
        page.get("role_label"),
    )
    return " ".join(str(value).lower() for value in values if value)


def _infer_surface(page: dict[str, Any]) -> str:
    explicit = str(page.get("surface") or "").lower()
    if explicit in {"public", "ops"}:
        return explicit

    skeleton_id = str(page.get("skeleton_id") or "")
    if skeleton_id.startswith("ops-"):
        return "ops"
    if skeleton_id.startswith("public-"):
        return "public"

    layout = str(page.get("layout") or "").lower()
    path = str(page.get("path") or "").lower()
    page_type = str(page.get("page_type") or "").lower()
    role = " ".join(
        str(page.get(key) or "").lower() for key in ("role_id", "role_label")
    )
    text = _search_text(page)
    if layout in {"admin", "ops", "dashboard"}:
        return "ops"
    if re.search(r"(^|/)(admin|owner|ops)(/|$)", path):
        return "ops"
    role_tokens = set(re.findall(r"[a-z]+", role))
    if role_tokens & {"public", "customer", "client", "guest", "patient"}:
        return "public"
    if role_tokens & {
        "owner",
        "admin",
        "administrator",
        "ops",
        "operator",
        "operations",
        "staff",
        "manager",
        "trader",
        "portfolio",
        "execution",
        "risk",
        "pm",
    }:
        return "ops"
    if any(
        word in page_type
        for word in (
            "dashboard",
            "operational",
            "record detail",
            "settings",
            "configuration",
            "trading",
            "blotter",
            "desk",
        )
    ):
        return "ops"
    if any(
        word in text
        for word in (
            "dashboard",
            "back office",
            "operations",
            "admin portal",
            "blotter",
            "trading desk",
            "order ticket",
            "hedge fund",
            "invoice",
            "bookkeep",
            "reconcil",
            "workspace",
            "work queue",
        )
    ):
        return "ops"
    # Explicit product-kind lock from planner / product_kind module
    product_kind = str(page.get("product_kind") or "").lower()
    if product_kind in {"saas_workspace", "internal_ops"}:
        return "ops"
    return "public"


_DETAIL_ID_SEGMENT = re.compile(r"(?:^|[^a-z0-9])detail(?:[^a-z0-9]|$)")


def _explicit_detail_is_anchored(page: dict[str, Any]) -> bool:
    """Whether a planner-assigned `public-detail` carries item evidence.

    `0e678fa` made the INFERENCE route-anchored — a detail page shows ONE item,
    which is a fact about the route — but the explicit-skeleton escape hatch
    below returned a planner-assigned `public-detail` unchanged, and plan pages
    carry no path, so the fixed rule could never fire on them. Measured over
    the 60 stored plans (session 20): ~30 About/Contact/Our-Story/Private-Dining
    pages carry explicit `public-detail` with no anchor — request 124's
    PrivateDiningPage fill was rejected for the painting-first hero and
    itemSpecs that contract demands, and session 18's AboutPage the same way.

    Evidence that keeps the label: an item path (same end-anchored rule the
    inference uses), or a `detail` segment in the page ID — planner slugs like
    `painting-detail` / `room-detail-king` NAME the page an item detail. IDs
    only, never titles: "lodge contact details." in a title is the exact bare
    substring 0e678fa removed. A page with neither falls through to inference,
    so prose that independently resolves detail (run 88's sauna page via its
    "Amenity Detail Page" type) keeps it anyway.
    """
    path = str(page.get("path") or "").strip().lower().rstrip("/")
    if not path:
        contract_block = page.get("app_spec_contract")
        if isinstance(contract_block, dict):
            path = str(contract_block.get("route") or "").strip().lower().rstrip("/")
    if path and re.search(r"/(?::[^/]+|\[[^\]]+\])$", path):
        return True
    page_id = str(page.get("id") or page.get("page_id") or "").casefold()
    return bool(_DETAIL_ID_SEGMENT.search(page_id))


def _infer_skeleton_id(page: dict[str, Any], surface: str) -> str:
    explicit = str(page.get("skeleton_id") or "")
    if explicit:
        try:
            skeleton = get_skeleton(explicit)
        except ValueError:
            pass
        else:
            if skeleton.get("surface") == surface and not (
                explicit == "public-detail" and not _explicit_detail_is_anchored(page)
            ):
                return explicit

    path = str(page.get("path") or "").lower().rstrip("/")
    text = _search_text(page)
    if surface == "ops":
        if any(word in text for word in ("setting", "configuration", "preferences")):
            return "ops-settings"
        if any(word in text for word in ("dashboard", "overview", "analytics", "insights")):
            return "ops-dashboard"
        if any(word in text for word in ("detail", "profile", "record")) or (
            path and re.search(r"/(?:\d+|:[^/]+|\[[^\]]+\])$", path)
        ):
            return "ops-detail"
        return "ops-list"

    # Transactional flows first: judged as marketing pages they would be
    # rejected for missing hero/testimonials and fall back to scaffolds.
    if any(
        word in text
        for word in (
            "cart",
            "checkout",
            "order status",
            "track order",
            "order tracking",
            "tracking",
            "wishlist",
            "my orders",
            "order history",
            "account",
            "login",
            "sign in",
            "sign up",
            "register",
        )
    ):
        return "public-utility"
    if any(word in text for word in ("book", "appointment", "reserve", "intake", "schedule")):
        return "public-booking"
    if path == "/" or any(word in text for word in ("home", "landing", "homepage")):
        return "public-home"
    # A detail page shows ONE item, which is a fact about the route rather than a
    # word in prose. Matching the bare substring "detail" put About, Contact,
    # booking-confirmation and treatment-plan pages under the `public-detail`
    # contract on ordinary English — "contact details.", "a page detailing our
    # story", "detailed room information" — and that contract
    # (`catalogue_contract/validate.py:227-244`, written against request 50, a
    # fine-art gallery) *requires* a painting-first hero, an `itemSpecs` binding
    # and an `#inquire` CTA, so those pages had their fills discarded for a
    # deterministic scaffold. Measured over the 399 stored public routes: 95
    # reached this branch, **94 of them on the bare word alone**, and 35 of those
    # named no item in their path at all.
    if path and re.search(r"/(?::[^/]+|\[[^\]]+\])$", path):
        return "public-detail"
    if any(
        word in text
        for word in (
            "single product",
            "single service",
            "treatment detail",
            "item detail",
            "product detail",
            "service detail",
            "detail page",
        )
    ):
        return "public-detail"
    if path and re.search(r"/(?:services?|products?|treatments?)/[^/]+$", path):
        return "public-detail"
    if any(
        word in text
        for word in ("catalog", "catalogue", "shop", "store", "browse", "collection", "compare")
    ) or (path and re.search(r"/(?:shop|store|products|catalog)$", path)):
        return "public-catalog"
    return "public-service"


def infer_page_contract(page: dict[str, Any]) -> dict[str, str]:
    """Infer additive catalogue fields for a legacy plan page or route."""
    surface = _infer_surface(page)
    return {
        "surface": surface,
        "skeleton_id": _infer_skeleton_id(page, surface),
    }


def infer_section_slots(page: dict[str, Any], skeleton_id: str) -> list[str]:
    """Return valid slots in skeleton order, completing required content slots."""
    skeleton = get_skeleton(skeleton_id)
    recommended = list(skeleton.get("recommendedOrder") or [])
    required = list(skeleton.get("requiredSections") or [])
    optional = list(skeleton.get("optionalSections") or [])
    allowed_slots = set(required) | set(optional)
    allowed_slots.discard("shell")
    slot_order = recommended + [
        slot for slot in (*required, *optional) if slot not in recommended
    ]
    allowed_components = set(skeleton.get("allowedComponents") or [])
    source = page.get("section_slots")
    if not isinstance(source, list) or not source:
        source = page.get("sections")

    requested: set[str] = set()
    if isinstance(source, list):
        for item in source:
            if isinstance(item, str):
                name = item
            elif isinstance(item, dict):
                name = item.get("slot") or item.get("name") or item.get("id") or ""
            else:
                name = ""
            normalized = str(name).strip()
            if normalized in allowed_slots:
                requested.add(normalized)

    if not requested:
        requested.update(slot for slot in required if slot != "shell")
    else:
        requested.update(slot for slot in required if slot != "shell")

    selected = requested | {slot for slot in required if slot != "shell"}
    for slot in selected:
        component = skeleton.get("shell") if slot == "shell" else _SLOT_COMPONENT_DEFAULTS.get(slot)
        if not component or component not in allowed_components:
            raise ValueError(
                f"Skeleton {skeleton_id} has no valid allowed component default for slot {slot}"
            )
    return [slot for slot in slot_order if slot in selected]


def compact_skeleton_contract(
    skeleton_id: str,
    section_slots: list[str] | None = None,
) -> dict[str, Any]:
    """Return only the chosen skeleton and metadata for its allowed components.

    This is the **complete** view and the one validators must use:
    `catalogue_contract.validate` builds `allowed_ui_names` out of
    `contract["components"]`, so dropping an entry here turns a legitimate
    component into a `forbidden @/ui component` error. Prompts want the
    opposite — something that fits a character budget — and get it from
    `skeleton_contract_for_prompt`. Do not merge the two.
    """
    catalogue = load_catalogue()
    skeleton = get_skeleton(skeleton_id)
    allowed = set(skeleton.get("allowedComponents") or [])
    slots = infer_section_slots({"section_slots": section_slots or []}, skeleton_id)
    shell_component = str(skeleton.get("shell") or "")
    navigation_components = [
        name
        for name in _SHELL_NAVIGATION_COMPONENTS.get(shell_component, ())
        if name in allowed
    ]
    slot_components: dict[str, str] = {}
    for slot in slots:
        name = skeleton.get("shell") if slot == "shell" else _SLOT_COMPONENT_DEFAULTS.get(slot)
        if not name or name not in allowed:
            continue
        slot_components[slot] = name
    # Priority order, and it is load-bearing: `skeleton_contract_for_prompt`
    # drops from the tail, so the page's own shell/nav/slot components must
    # lead. They used to be appended *after* the alphabetical bulk, which put
    # MarketingHero and ProductShowcase at positions 15 and 22 of
    # public-catalog's 30 — past the point anything downstream kept.
    selected_names: list[str] = _dedupe(
        tuple(
            name
            for name in (shell_component, *navigation_components, *slot_components.values())
            if name and name in allowed
        )
    )
    # Then every remaining skeleton-allowed component, so validators/prompts
    # accept Button, Badge, Input, DataTable, etc. — not only shell/slot defaults.
    for name in sorted(allowed):
        if name and name not in selected_names:
            selected_names.append(name)
    components_by_name = {
        component["name"]: component for component in catalogue["components"]
    }
    components = [
        {
            key: components_by_name[name][key]
            for key in _COMPONENT_FIELDS
            if key in components_by_name[name]
        }
        for name in selected_names
        if name in components_by_name
    ]
    skeleton_contract = {
        key: skeleton[key] for key in _SKELETON_FIELDS if key in skeleton
    }
    supported = skeleton_contract.get("supportedVariants")
    if isinstance(supported, dict):
        skeleton_contract["supportedVariants"] = {
            name: variants for name, variants in supported.items() if name in selected_names
        }
    contract: dict[str, Any] = {
        "skeleton": skeleton_contract,
        "shell_component": shell_component,
        "navigation_components": navigation_components,
        "section_slots": slots,
        "slot_components": slot_components,
        "components": components,
    }
    prop_shapes = _budgeted_prop_shapes(
        contract,
        (*slot_components.values(), shell_component, *navigation_components, *selected_names),
    )
    if prop_shapes:
        contract["prop_shapes"] = prop_shapes
    return contract


def skeleton_contract_for_prompt(
    skeleton_id: str,
    section_slots: list[str] | None = None,
    max_chars: int = _CONTRACT_PROMPT_BUDGET,
) -> dict[str, Any]:
    """Return the contract fitted into a prompt's character budget, deliberately.

    Every prompt caller wraps the contract in `bounded_json(contract, 5000)`.
    Above that limit `bounded_json` stops being a bound and becomes a mutation:
    it clips *every* list to 12 items and truncates strings to 500 chars
    (`text_utils.bounded_json`). For `public-catalog` — 5,296 chars, 30
    components — that silently discarded 18 of them, including the
    `MarketingHero` and `ProductShowcase` that the contract's own
    `slot_components` assigned to that page's hero and showcase slots. So the
    prompt got "use only these catalogue components" over a list missing the
    ones it had just required, chosen by alphabetical position.

    Fitting happens here instead, cheapest sacrifice first:

    1. `prop_shapes`, which `_budgeted_prop_shapes` already fits and which is
       guidance rather than vocabulary — a partial map still reads as valid.
    2. `components`, from the tail of the priority order established in
       `compact_skeleton_contract`, so the shell, nav and slot components a
       page cannot render without are the last things to go.

    Anything dropped is logged. A silently smaller vocabulary looks exactly
    like a model that chose not to use a component.
    """
    contract = compact_skeleton_contract(skeleton_id, section_slots)
    if _serialized_len(contract) <= max_chars:
        return contract

    without_shapes = {key: value for key, value in contract.items() if key != "prop_shapes"}
    if _serialized_len(without_shapes) <= max_chars:
        ui_log.info(
            "catalogue_contract_prop_shapes_dropped skeleton=%s dropped=%d",
            skeleton_id,
            len(contract.get("prop_shapes") or {}),
        )
        return without_shapes

    protected = {
        name
        for name in (
            without_shapes.get("shell_component"),
            *(without_shapes.get("navigation_components") or []),
            *(without_shapes.get("slot_components") or {}).values(),
        )
        if name
    }
    components = list(without_shapes.get("components") or [])
    fitted = dict(without_shapes)
    dropped: list[str] = []
    while len(components) > len(protected) and _serialized_len(fitted) > max_chars:
        for index in range(len(components) - 1, -1, -1):
            if str(components[index].get("name") or "") not in protected:
                dropped.append(str(components[index].get("name") or ""))
                del components[index]
                break
        else:  # pragma: no cover - loop guard; every survivor is protected
            break
        fitted["components"] = components
    fitted["components"] = components
    ui_log.warning(
        "catalogue_contract_components_dropped skeleton=%s kept=%d dropped=%s chars=%d budget=%d",
        skeleton_id,
        len(components),
        ",".join(dropped) or "-",
        _serialized_len(fitted),
        max_chars,
    )
    return fitted


def _serialized_len(contract: dict[str, Any]) -> int:
    """Length as the prompt callers serialize it — `bounded_json`'s separators."""
    return len(json.dumps(contract, ensure_ascii=False, separators=(",", ":")))


def compact_catalogue_plan_contract() -> dict[str, Any]:
    """Return skeleton choices and slot rules without injecting the component catalogue."""
    skeleton_fields = (
        "id",
        "surface",
        "shell",
        "purpose",
        "requiredSections",
        "optionalSections",
        "recommendedOrder",
    )
    return {
        "skeletons": [
            {
                key: skeleton[key]
                for key in skeleton_fields
                if key in skeleton
            }
            for skeleton in load_catalogue()["skeletons"]
        ]
    }
