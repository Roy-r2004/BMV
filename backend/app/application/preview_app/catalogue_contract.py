"""Deterministic validation and minimal scaffolds for catalogue-owned pages."""
from __future__ import annotations

import json
import re

from app.application.preview_app.protected_paths import canonical_workspace_path
from app.application.ui_catalogue import compact_skeleton_contract, get_skeleton


def catalogue_route_for_file(file_path: str, architect: dict | None) -> dict:
    target = canonical_workspace_path(file_path).lower()
    for route in (architect or {}).get("routes") or []:
        component_file = canonical_workspace_path(route.get("component_file", "")).lower()
        if component_file and component_file == target:
            return route
    return {}


def required_non_shell_slots(route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return []
    return [
        str(section)
        for section in get_skeleton(skeleton_id).get("requiredSections") or []
        if section != "shell"
    ]


def assigned_non_shell_slots(route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return []
    skeleton = get_skeleton(skeleton_id)
    required = [
        str(section)
        for section in skeleton.get("requiredSections") or []
        if section != "shell"
    ]
    assigned = [
        str(section)
        for section in route.get("section_slots") or []
        if section != "shell"
    ]
    selected = set(required + assigned)
    order = [
        str(section)
        for section in skeleton.get("recommendedOrder") or []
        if section != "shell"
    ]
    return [section for section in order if section in selected]


def expected_shell(route: dict) -> str:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return ""
    skeleton = get_skeleton(skeleton_id)
    return str(
        skeleton.get("shell")
        or ("OpsShell" if skeleton.get("surface") == "ops" else "PublicShell")
    )


def _scrub_comments_and_strings(content: str, *, strings: bool) -> str:
    chars = list(content or "")
    output = list(chars)
    index = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    while index < len(chars):
        char = chars[index]
        nxt = chars[index + 1] if index + 1 < len(chars) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            else:
                output[index] = " "
            index += 1
            continue
        if block_comment:
            output[index] = "\n" if char == "\n" else " "
            if char == "*" and nxt == "/":
                output[index + 1] = " "
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if strings:
                output[index] = "\n" if char == "\n" else " "
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char == "/" and nxt == "/":
            output[index] = output[index + 1] = " "
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            output[index] = output[index + 1] = " "
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            if strings:
                output[index] = " "
        index += 1
    return "".join(output)


def _source_tokens(content: str) -> list[str]:
    source = _scrub_comments_and_strings(content, strings=False)
    tokens: list[str] = []
    index = 0
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            value: list[str] = []
            escaped = False
            while index < len(source):
                current = source[index]
                if escaped:
                    value.append(current)
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == quote:
                    index += 1
                    break
                else:
                    value.append(current)
                index += 1
            tokens.append("\0" + "".join(value))
            continue
        identifier = re.match(r"[A-Za-z_$][A-Za-z0-9_$-]*", source[index:])
        if identifier:
            tokens.append(identifier.group(0))
            index += identifier.end()
            continue
        tokens.append(char)
        index += 1
    return tokens


def _has_token_sequence(tokens: list[str], sequence: list[str]) -> bool:
    size = len(sequence)
    return any(tokens[index:index + size] == sequence for index in range(len(tokens) - size + 1))


def _declared_slot_values(tokens: list[str]) -> dict[str, list[str]]:
    """Return top-level slot properties and their value tokens."""
    start = -1
    prefix = ["const", "slots", "=", "{"]
    for index in range(len(tokens) - len(prefix) + 1):
        if tokens[index:index + len(prefix)] == prefix:
            start = index + len(prefix)
            break
    if start < 0:
        return {}

    values: dict[str, list[str]] = {}
    cursor = start
    while cursor < len(tokens):
        while cursor < len(tokens) and tokens[cursor] == ",":
            cursor += 1
        if cursor >= len(tokens) or tokens[cursor] == "}":
            break

        key_token = tokens[cursor]
        if key_token.startswith("\0"):
            key = key_token[1:]
        elif re.match(r"^[A-Za-z_$][A-Za-z0-9_$-]*$", key_token):
            key = key_token
        else:
            key = ""

        if key and cursor + 1 < len(tokens) and tokens[cursor + 1] == ":":
            value_start = cursor + 2
            value_end = value_start
            nesting: list[str] = []
            pairs = {"(": ")", "[": "]", "{": "}"}
            while value_end < len(tokens):
                token = tokens[value_end]
                if token in pairs:
                    nesting.append(pairs[token])
                elif nesting and token == nesting[-1]:
                    nesting.pop()
                elif not nesting and token in {",", "}"}:
                    break
                value_end += 1
            values[key] = tokens[value_start:value_end]
            cursor = value_end
            continue

        if key and (
            cursor + 1 >= len(tokens)
            or tokens[cursor + 1] in {",", "}"}
        ):
            # Object shorthand is an identifier-valued property.
            values[key] = [key_token]
            cursor += 1
            continue

        # Skip unsupported property forms without treating nested keys as slots.
        nesting = []
        cursor += 1
        while cursor < len(tokens):
            token = tokens[cursor]
            if token in {"(", "[", "{"}:
                nesting.append({"(": ")", "[": "]", "{": "}"}[token])
            elif nesting and token == nesting[-1]:
                nesting.pop()
            elif not nesting and token in {",", "}"}:
                break
            cursor += 1
    return values


def _slot_value_is_present(value_tokens: list[str]) -> bool:
    tokens = list(value_tokens)
    while len(tokens) >= 2 and tokens[0] == "(" and tokens[-1] == ")":
        depth = 0
        wraps_all = True
        for index, token in enumerate(tokens):
            if token == "(":
                depth += 1
            elif token == ")":
                depth -= 1
                if depth == 0 and index != len(tokens) - 1:
                    wraps_all = False
                    break
        if not wraps_all or depth:
            break
        tokens = tokens[1:-1]
    return bool(tokens) and tokens not in (
        ["null"],
        ["undefined"],
        ["false"],
        ["{", "}"],
    )


def _ui_named_imports(tokens: list[str]) -> dict[str, str]:
    """Return local name -> exported name for named imports from the UI barrel."""
    imported: dict[str, str] = {}
    index = 0
    while index < len(tokens):
        if tokens[index] != "import":
            index += 1
            continue
        try:
            from_index = tokens.index("from", index + 1)
        except ValueError:
            break
        if (
            from_index + 1 >= len(tokens)
            or tokens[from_index + 1] != "\0@/ui"
        ):
            index = from_index + 1
            continue
        clause = tokens[index + 1:from_index]
        if "{" not in clause or "}" not in clause:
            index = from_index + 2
            continue
        start = clause.index("{") + 1
        end = clause.index("}", start)
        cursor = start
        while cursor < end:
            if clause[cursor] in {",", "type"}:
                cursor += 1
                continue
            exported = clause[cursor]
            local = exported
            if cursor + 2 < end and clause[cursor + 1] == "as":
                local = clause[cursor + 2]
                cursor += 3
            else:
                cursor += 1
            if re.match(r"^[A-Za-z_$][\w$]*$", exported) and re.match(
                r"^[A-Za-z_$][\w$]*$",
                local,
            ):
                imported[local] = exported
        index = from_index + 2
    return imported


_ALLOWED_CATALOGUE_IMPORTS = {
    "@/ui",
    "react",
    "react-router-dom",
    "@/data/mock",
    "@/lib/app-nav",
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_$][\w$]*$")


def _runtime_import_bindings(
    tokens: list[str],
    allowed_sources: set[str],
) -> set[str]:
    """Collect value bindings from static imports whose source is allowed."""
    bindings: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] != "import":
            index += 1
            continue
        end = index + 1
        while end < len(tokens) and tokens[end] != ";":
            end += 1
        statement = tokens[index + 1:end]
        if not statement or statement[0].startswith("\0") or statement[0] == "(":
            index += 2
            continue
        try:
            from_index = statement.index("from")
        except ValueError:
            index += 1
            continue
        source_index = index + from_index + 2
        if (
            from_index + 1 >= len(statement)
            or not statement[from_index + 1].startswith("\0")
            or statement[from_index + 1][1:] not in allowed_sources
        ):
            index = source_index + 1
            continue

        clause = statement[:from_index]
        if not clause or clause[0] == "type":
            index = source_index + 1
            continue
        if _IDENTIFIER_RE.match(clause[0]):
            bindings.add(clause[0])
        for cursor, token in enumerate(clause):
            if token == "*" and cursor + 2 < len(clause) and clause[cursor + 1] == "as":
                local = clause[cursor + 2]
                if _IDENTIFIER_RE.match(local):
                    bindings.add(local)
            if token != "{":
                continue
            cursor += 1
            while cursor < len(clause) and clause[cursor] != "}":
                if clause[cursor] == ",":
                    cursor += 1
                    continue
                type_only = clause[cursor] == "type"
                if type_only:
                    cursor += 1
                if cursor >= len(clause) or not _IDENTIFIER_RE.match(clause[cursor]):
                    cursor += 1
                    continue
                local = clause[cursor]
                if (
                    cursor + 2 < len(clause)
                    and clause[cursor + 1] == "as"
                    and _IDENTIFIER_RE.match(clause[cursor + 2])
                ):
                    local = clause[cursor + 2]
                    cursor += 3
                else:
                    cursor += 1
                if not type_only:
                    bindings.add(local)
            break
        index = source_index + 1
    return bindings


def _local_component_bindings(tokens: list[str]) -> set[str]:
    """Collect simple function, class, and const declarations."""
    bindings: set[str] = set()
    for index, token in enumerate(tokens):
        if token in {"function", "class"}:
            cursor = index + 1
            if token == "function" and cursor < len(tokens) and tokens[cursor] == "*":
                cursor += 1
            if cursor < len(tokens) and _IDENTIFIER_RE.match(tokens[cursor]):
                bindings.add(tokens[cursor])
        elif (
            token == "const"
            and index + 1 < len(tokens)
            and _IDENTIFIER_RE.match(tokens[index + 1])
        ):
            bindings.add(tokens[index + 1])
    return bindings


def _uppercase_jsx_roots(tokens: list[str]) -> set[str]:
    """Return uppercase roots from JSX tag names, including member expressions."""
    roots: set[str] = set()
    for index, token in enumerate(tokens):
        if token != "<":
            continue
        cursor = index + 1
        closing = cursor < len(tokens) and tokens[cursor] == "/"
        if closing:
            cursor += 1
        if cursor >= len(tokens):
            continue
        root = tokens[cursor]
        if not _IDENTIFIER_RE.match(root) or not root[0].isupper():
            continue
        if (
            not closing
            and index > 0
            and _IDENTIFIER_RE.match(tokens[index - 1])
            and cursor + 1 < len(tokens)
            and tokens[cursor + 1] == ">"
            and cursor + 2 < len(tokens)
            and tokens[cursor + 2] in {"(", "[", ".", "?", ":", "=", ";", ",", ")"}
        ):
            # Type arguments such as `factory<Component>()` are not JSX tags.
            continue
        roots.add(root)
    return roots


_REACT_GLOBAL_PROPS = {
    "key",
    "ref",
    "id",
    "style",
    "role",
    "title",
    "tabIndex",
    "hidden",
    "lang",
    "dir",
    "draggable",
    "slot",
    "suppressHydrationWarning",
    "dangerouslySetInnerHTML",
}


def _jsx_opening_props(
    tokens: list[str],
    component_locals: set[str],
) -> list[tuple[str, dict[str, str | None]]]:
    """Extract top-level JSX props; spread expressions remain intentionally opaque."""
    invocations: list[tuple[str, dict[str, str | None]]] = []
    index = 0
    while index + 1 < len(tokens):
        local = tokens[index + 1]
        if tokens[index] != "<" or local not in component_locals:
            index += 1
            continue
        cursor = index + 2
        curly = square = paren = 0
        props: dict[str, str | None] = {}
        while cursor < len(tokens):
            token = tokens[cursor]
            if token == ">" and not (curly or square or paren):
                break
            if not (curly or square or paren) and re.match(
                r"^[A-Za-z_$][A-Za-z0-9_$-]*$",
                token,
            ):
                value: str | None = None
                if cursor + 1 < len(tokens) and tokens[cursor + 1] == "=":
                    if cursor + 2 < len(tokens) and tokens[cursor + 2].startswith("\0"):
                        value = tokens[cursor + 2][1:]
                    elif (
                        cursor + 4 < len(tokens)
                        and tokens[cursor + 2] == "{"
                        and tokens[cursor + 3].startswith("\0")
                        and tokens[cursor + 4] == "}"
                    ):
                        value = tokens[cursor + 3][1:]
                props[token] = value
            if token == "{":
                curly += 1
            elif token == "}":
                curly = max(0, curly - 1)
            elif token == "[":
                square += 1
            elif token == "]":
                square = max(0, square - 1)
            elif token == "(":
                paren += 1
            elif token == ")":
                paren = max(0, paren - 1)
            cursor += 1
        invocations.append((local, props))
        index = cursor + 1
    return invocations


def validate_catalogue_page_content(content: str, route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    if not skeleton_id:
        return []
    errors: list[str] = []
    tokens = _source_tokens(content or "")
    if not _has_token_sequence(
        tokens,
        ["const", "SKELETON_ID", "=", "\0" + skeleton_id, "as", "const"],
    ):
        errors.append("assigned skeleton literal")
    if not _has_token_sequence(tokens, ["getSkeleton", "(", "SKELETON_ID", ")"]):
        errors.append("getSkeleton")
    composer_valid = False
    for index in range(len(tokens) - 1):
        if tokens[index:index + 2] != ["<", "SkeletonComposer"]:
            continue
        try:
            end = tokens.index(">", index + 2)
        except ValueError:
            continue
        invocation = tokens[index:end + 1]
        if (
            _has_token_sequence(invocation, ["skeletonId", "=", "{", "SKELETON_ID", "}"])
            and _has_token_sequence(invocation, ["slots", "=", "{", "slots", "}"])
        ):
            composer_valid = True
            break
    if not composer_valid:
        errors.append("SkeletonComposer invocation")
    shell = expected_shell(route)
    if shell and not _has_token_sequence(tokens, ["<", shell]):
        errors.append(shell)
    assigned_slots = assigned_non_shell_slots(route)
    slot_values = _declared_slot_values(tokens)
    actual_slots = set(slot_values)
    for slot in assigned_slots:
        if slot not in actual_slots or not _slot_value_is_present(slot_values[slot]):
            errors.append(f"slot:{slot}")
    for slot in sorted(actual_slots - set(assigned_slots)):
        errors.append(f"extra slot:{slot}")
    import_sources: list[str] = []
    forbidden_import_syntax = False
    for index, token in enumerate(tokens):
        if token == "require":
            forbidden_import_syntax = True
        if token == "import" and index + 1 < len(tokens) and tokens[index + 1] == "(":
            forbidden_import_syntax = True
        if (
            token == "import"
            and index + 2 < len(tokens)
            and re.match(r"^[A-Za-z_$][\w$]*$", tokens[index + 1])
            and tokens[index + 2] == "="
        ):
            forbidden_import_syntax = True
        if token == "from" and index + 1 < len(tokens):
            source = tokens[index + 1]
            if source.startswith("\0"):
                import_sources.append(source[1:])
        elif token == "import" and index + 1 < len(tokens):
            if tokens[index + 1] == "(" and index + 2 < len(tokens):
                source = tokens[index + 2]
                if source.startswith("\0"):
                    import_sources.append(source[1:])
            elif tokens[index + 1].startswith("\0"):
                import_sources.append(tokens[index + 1][1:])
    if forbidden_import_syntax:
        errors.append("forbidden import syntax")
    if any(source not in _ALLOWED_CATALOGUE_IMPORTS for source in import_sources):
        errors.append("forbidden import")
    if "@/ui" not in import_sources:
        errors.append("missing @/ui import")
    bound_jsx_roots = _runtime_import_bindings(
        tokens,
        _ALLOWED_CATALOGUE_IMPORTS,
    ) | _local_component_bindings(tokens)
    for root in sorted(_uppercase_jsx_roots(tokens) - bound_jsx_roots):
        errors.append(f"undefined JSX component:{root}")
    contract = compact_skeleton_contract(
        skeleton_id,
        [str(slot) for slot in route.get("section_slots") or []],
    )
    component_metadata = {
        str(component["name"]): component
        for component in contract.get("components") or []
        if component.get("name")
    }
    allowed_ui_names = set(component_metadata) | {"SkeletonComposer", "getSkeleton"}
    ui_imports = _ui_named_imports(tokens)
    for exported in sorted(set(ui_imports.values()) - allowed_ui_names):
        errors.append(f"forbidden @/ui component:{exported}")
    for local, props in _jsx_opening_props(tokens, set(ui_imports)):
        exported = ui_imports[local]
        metadata = component_metadata.get(exported)
        if not metadata:
            continue
        allowed_props = set(metadata.get("requiredProps") or []) | set(
            metadata.get("optionalProps") or []
        )
        variants = metadata.get("variants") or {}
        for prop, literal in props.items():
            if (
                prop not in allowed_props
                and prop not in _REACT_GLOBAL_PROPS
                and not prop.startswith(("aria-", "data-"))
            ):
                errors.append(f"invalid prop:{exported}.{prop}")
                continue
            allowed_values = variants.get(prop)
            if (
                literal is not None
                and isinstance(allowed_values, list)
                and literal not in allowed_values
            ):
                errors.append(f"invalid variant:{exported}.{prop}={literal}")
    return errors


_SLOT_COMPONENT = {
    "hero": "MarketingHero",
    "features": "FeatureBento",
    "showcase": "ProductShowcase",
    "process": "ProcessSection",
    "testimonials": "TestimonialRail",
    "cta": "CTABand",
    "footer": "BrandFooter",
    "trust": "LogoMarquee",
    "credentials": "CredentialStrip",
    "spotlight": "SpotlightCard",
    "results": "ResultRail",
    "booking": "BookingPanel",
    "header": "PageHeader",
    "kpis": "StatCard",
    "chart": "ChartCard",
    "filters": "FilterBar",
    "table": "DataTable",
    "activity": "ActivityFeed",
    "risk": "RiskQueue",
    "empty": "EmptyState",
}


def _safe_slot_jsx(slot: str, brand: str, title: str) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    samples = {
        "hero": (
            f'<MarketingHero brandName={{{brand_js}}} headline={{{title_js}}} '
            'subcopy="A clear, considered experience built around your next step." '
            'primaryCta={{ label: "Get started", href: "#details" }} '
            'imageSrc="catalogue-hero.jpg" imageAlt="" />'
        ),
        "features": (
            '<FeatureBento heading="What you can expect" items={['
            '{ title: "Simple planning", description: "Everything needed to make a confident choice." }, '
            '{ title: "Thoughtful service", description: "A consistent experience from first visit to follow-up." }'
            ']} />'
        ),
        "showcase": (
            '<ProductShowcase heading="Featured experiences" items={['
            '{ title: "Signature service", description: "A dependable starting point.", imageSrc: "catalogue-product.svg", imageAlt: "" }'
            ']} />'
        ),
        "process": (
            '<ProcessSection heading="How it works" steps={['
            '{ title: "Choose", description: "Find the right option." }, '
            '{ title: "Confirm", description: "Select a convenient time." }, '
            '{ title: "Enjoy", description: "We take care of the details." }'
            ']} />'
        ),
        "testimonials": (
            '<TestimonialRail heading="What clients say" items={['
            '{ quote: "Clear, warm, and easy from start to finish.", author: "A returning client", role: "Verified guest" }'
            ']} />'
        ),
        "cta": (
            '<CTABand heading="Ready for the next step?" '
            'primaryCta={{ label: "Get started", href: "#details" }} />'
        ),
        "footer": f'<BrandFooter brandName={{{brand_js}}} description="Thoughtful service, clearly delivered." />',
        "trust": '<LogoMarquee heading="Built on trust" items={[{ label: "Personal service" }, { label: "Clear guidance" }]} />',
        "credentials": (
            '<CredentialStrip heading="Why clients choose us" items={['
            '{ title: "Experienced team", detail: "Careful guidance at every step." }'
            ']} />'
        ),
        "spotlight": '<SpotlightCard title="A better experience" description="Focused details that make every visit easier." />',
        "results": (
            '<ResultRail heading="Representative results" items={['
            '{ label: "Signature result", beforeSrc: "catalogue-result-before-1.jpg", afterSrc: "catalogue-result-after-1.jpg" }'
            ']} />'
        ),
        "booking": (
            '<BookingPanel heading="Choose a time" '
            'treatments={[{ id: "signature", name: "Signature service", duration: "60 min" }]} '
            'slots={[{ id: "slot-1", startsAt: "2026-07-14T10:00:00" }]} />'
        ),
        "header": f'<PageHeader title={{{title_js}}} description="A current view of the work that needs your attention." meta={{<span className="text-sm text-muted">Today</span>}} />',
        "kpis": (
            '<div className="grid grid-cols-1 gap-4 sm:grid-cols-3">'
            '<StatCard label="Active today" value="24" delta="+8%" hint="Compared with last week" />'
            '<StatCard label="In progress" value="11" delta="+2" hint="Open work items" />'
            '<StatCard label="Resolved" value="93%" delta="-2%" hint="Rolling 7-day rate" />'
            '</div>'
        ),
        "chart": (
            '<ChartCard title="Weekly performance" type="area" dataKey="value" xKey="day" '
            'data={[{ day: "Mon", value: 12 }, { day: "Tue", value: 18 }, { day: "Wed", value: 15 }, '
            '{ day: "Thu", value: 22 }, { day: "Fri", value: 19 }]} />'
        ),
        "filters": '<FilterBar searchPlaceholder="Search records" filters={[{ id: "all", label: "All", active: true }, { id: "open", label: "Open", active: false }]} />',
        "table": (
            '<DataTable columns={['
            '{ key: "name", header: "Name" }, '
            '{ key: "status", header: "Status" }, '
            '{ key: "updated", header: "Updated" }'
            ']} rows={['
            '{ name: "Primary record", status: "In progress", updated: "Today" }, '
            '{ name: "Follow-up item", status: "On hold", updated: "Yesterday" }, '
            '{ name: "Completed item", status: "Done", updated: "2 days ago" }'
            ']} />'
        ),
        "activity": (
            '<ActivityFeed heading="Activity" items={['
            '{ id: "activity-1", title: "Record updated", detail: "The latest details are ready.", time: "Just now" }, '
            '{ id: "activity-2", title: "Owner assigned", detail: "Waiting on confirmation.", time: "12m ago" }, '
            '{ id: "activity-3", title: "Note added", detail: "Customer asked for a callback.", time: "1h ago" }'
            ']} />'
        ),
        "risk": (
            '<RiskQueue heading="Needs attention" items={['
            '{ id: "risk-1", title: "Follow-up due", detail: "A client is waiting for confirmation.", severity: "medium" }'
            ']} />'
        ),
        "empty": '<EmptyState title="Nothing here yet" description="New records will appear here." />',
    }
    try:
        return samples[slot]
    except KeyError as exc:
        raise ValueError(f"Unsupported catalogue fallback slot: {slot}") from exc


def minimal_catalogue_page_scaffold(
    file_path: str,
    route: dict,
    *,
    brand_name: str | None = None,
) -> str:
    stem = canonical_workspace_path(file_path).split("/")[-1].rsplit(".", 1)[0]
    component = re.sub(r"[^A-Za-z0-9_]", "", stem) or "CataloguePage"
    if component[0].isdigit():
        component = f"Page{component}"
    skeleton_id = str(route["skeleton_id"])
    shell = expected_shell(route)
    slots = assigned_non_shell_slots(route)
    brand = brand_name or "Brand"
    title = str(route.get("title") or component.replace("Page", "") or "Overview")
    components = [shell, "getSkeleton"]
    if skeleton_id == "ops-dashboard":
        components.append("composeSkeletonLayout")
    else:
        components.append("SkeletonComposer")
    if shell == "PublicShell" and "PublicNav" not in components:
        components.append("PublicNav")
    for slot in slots:
        slot_component = _SLOT_COMPONENT.get(slot)
        if slot_component and slot_component not in components:
            components.append(slot_component)
    slot_lines = "\n".join(
        f"    {slot}: (\n      {_safe_slot_jsx(slot, brand, title)}\n    ),"
        for slot in slots
    )
    path = str(route.get("path") or "")
    is_member = path.startswith("/member") or "/member/" in canonical_workspace_path(file_path)
    if shell == "OpsShell":
        nav_import = "import { useAdminNavItems } from '@/lib/app-nav';\n"
        nav_hook = "  const adminNavItems = useAdminNavItems();\n"
        if skeleton_id == "ops-dashboard":
            body = (
                "  const { main, rail } = composeSkeletonLayout(SKELETON_ID, slots);\n\n"
                "  return (\n"
                f'    <{shell} brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}} rail={{rail}}>\n'
                "      <div data-skeleton={skeleton.id}>{main}</div>\n"
                f"    </{shell}>\n"
                "  );"
            )
        else:
            body = (
                "  return (\n"
                f'    <{shell} brandName={{{json.dumps(brand)}}} navItems={{adminNavItems}}>\n'
                "      <div data-skeleton={skeleton.id}>\n"
                "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
                "      </div>\n"
                f"    </{shell}>\n"
                "  );"
            )
    else:
        hook = "useMemberNavItems" if is_member else "usePublicNavItems"
        cta = "memberCta" if is_member else "publicCta"
        nav_import = f"import {{ {hook}, {cta} }} from '@/lib/app-nav';\n"
        nav_hook = f"  const navItems = {hook}();\n  const navCta = {cta}();\n"
        body = (
            "  return (\n"
            f'    <{shell} brandName={{{json.dumps(brand)}}} '
            f'nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>\n'
            "      <div data-skeleton={skeleton.id}>\n"
            "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
            "      </div>\n"
            f"    </{shell}>\n"
            "  );"
        )
    return f"""// deterministic catalogue contract scaffold
{nav_import}import {{ {", ".join(components)} }} from '@/ui';

const SKELETON_ID = {json.dumps(skeleton_id)} as const;

export default function {component}() {{
{nav_hook}  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
{slot_lines}
  }};

{body}
}}
"""


def enforce_catalogue_page_contract(
    file_path: str,
    content: str,
    architect: dict | None,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    route = catalogue_route_for_file(file_path, architect)
    if not route.get("skeleton_id"):
        return content, False
    if not validate_catalogue_page_content(content, route):
        return content, False
    return (
        minimal_catalogue_page_scaffold(
            file_path,
            route,
            brand_name=brand_name,
        ),
        True,
    )
