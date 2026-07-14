"""Deterministic validation and minimal scaffolds for catalogue-owned pages."""
from __future__ import annotations

import json
import logging
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
            if clause[cursor] == ",":
                cursor += 1
                continue
            # `import { type TableColumn }` is erased at runtime — exported
            # types are not components and must not hit the component checks.
            type_only = clause[cursor] == "type"
            if type_only:
                cursor += 1
                if cursor >= end:
                    break
            exported = clause[cursor]
            local = exported
            if cursor + 2 < end and clause[cursor + 1] == "as":
                local = clause[cursor + 2]
                cursor += 3
            else:
                cursor += 1
            if (
                not type_only
                and re.match(r"^[A-Za-z_$][\w$]*$", exported)
                and re.match(r"^[A-Za-z_$][\w$]*$", local)
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
    """Collect simple function, class, const, interface, and type declarations.

    Interface/type names must be known so generics such as
    `useState<TradeInRequest[]>` are not misread as undefined JSX tags.
    """
    bindings: set[str] = set()
    for index, token in enumerate(tokens):
        if token in {"function", "class", "interface", "type"}:
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


_JSX_PRECEDING_KEYWORDS = {
    "return",
    "default",
    "typeof",
    "in",
    "of",
    "case",
    "await",
    "yield",
    "do",
    "else",
    "void",
}
_GENERIC_FOLLOW_TOKENS = {"(", "[", ".", "?", ":", "=", ";", ",", ")", ">", "&", "|", "}"}


def _skips_generic_arguments(tokens: list[str], start: int) -> bool:
    """True when tokens[start] opens a TypeScript generic argument list.

    Handles nesting (`useState<Record<string, string>>`), unions
    (`useState<Date | null>`), and array suffixes (`useState<Item[]>`). JSX
    never survives the scan because props introduce strings, braces, or
    parens, which break plausibility.
    """
    depth = 1
    probe = start + 1
    while probe < len(tokens) and depth:
        current = tokens[probe]
        if current == "<":
            depth += 1
        elif current == ">":
            depth -= 1
        elif current in {"(", ")", "{", "}", ";", "="} or current.startswith("\0"):
            return False
        if probe - start > 60:
            return False
        probe += 1
    return (
        depth == 0
        and probe < len(tokens)
        and tokens[probe] in _GENERIC_FOLLOW_TOKENS
    )


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
            and tokens[index - 1] not in _JSX_PRECEDING_KEYWORDS
            and _skips_generic_arguments(tokens, index)
        ):
            # Type arguments such as `useState<Record<string, string>>()` or
            # `React.ChangeEvent<HTMLInputElement>` are not JSX tags.
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
    # Validate against normalized imports — enforce_catalogue_page_contract
    # materializes the same rewrite before the file is written.
    tokens = _source_tokens(normalize_catalogue_page_imports(content or "", route))
    literal = "\0" + skeleton_id
    has_skeleton_const = _has_token_sequence(
        tokens,
        ["const", "SKELETON_ID", "=", literal, "as", "const"],
    )
    # The composer may reference the SKELETON_ID const or inline the assigned
    # skeleton id literal — both pin the page to the right skeleton.
    id_references = (
        ["SKELETON_ID"],
        [literal],
        ["{", "SKELETON_ID", "}"],
        ["{", literal, "}"],
    )
    composer_valid = False
    composer_uses_literal = False
    for index in range(len(tokens) - 1):
        if tokens[index:index + 2] != ["<", "SkeletonComposer"]:
            continue
        try:
            end = tokens.index(">", index + 2)
        except ValueError:
            continue
        invocation = tokens[index:end + 1]
        id_ok = any(
            _has_token_sequence(invocation, ["skeletonId", "=", *reference])
            for reference in id_references
        )
        if id_ok and _has_token_sequence(invocation, ["slots", "=", "{", "slots", "}"]):
            composer_valid = True
            composer_uses_literal = _has_token_sequence(
                invocation, ["skeletonId", "=", literal]
            ) or _has_token_sequence(invocation, ["skeletonId", "=", "{", literal, "}"])
            break
    # ops-dashboard pages may compose main/rail via composeSkeletonLayout
    # instead of rendering <SkeletonComposer /> directly.
    if not composer_valid:
        for reference in ("SKELETON_ID", literal):
            if _has_token_sequence(
                tokens, ["composeSkeletonLayout", "(", reference, ",", "slots", ")"]
            ):
                composer_valid = True
                composer_uses_literal = reference == literal
                break
    if not composer_valid:
        errors.append("SkeletonComposer invocation")
    if not has_skeleton_const and not (composer_valid and composer_uses_literal):
        errors.append("assigned skeleton literal")
    # Note: calling getSkeleton(SKELETON_ID) is encouraged but not required —
    # the composer resolves and validates the skeleton internally.
    shell = expected_shell(route)
    if shell and not _has_token_sequence(tokens, ["<", shell]):
        errors.append(shell)
    assigned_slots = assigned_non_shell_slots(route)
    skeleton = get_skeleton(skeleton_id)
    valid_slot_ids = {
        str(section)
        for section in (
            *(skeleton.get("requiredSections") or []),
            *(skeleton.get("optionalSections") or []),
        )
        if section != "shell"
    }
    slot_values = _declared_slot_values(tokens)
    actual_slots = set(slot_values)
    for slot in assigned_slots:
        if slot not in actual_slots or not _slot_value_is_present(slot_values[slot]):
            errors.append(f"slot:{slot}")
    # Unassigned-but-valid optional slots are welcome extra content; only
    # slot keys the skeleton does not know at all are rejected.
    for slot in sorted(actual_slots - set(assigned_slots) - valid_slot_ids):
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
    for source in sorted({
        source for source in import_sources if source not in _ALLOWED_CATALOGUE_IMPORTS
    }):
        errors.append(f"forbidden import:{source}")
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
    allowed_ui_names = set(component_metadata) | {
        "SkeletonComposer",
        "composeSkeletonLayout",
        "getSkeleton",
    }
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
}


def _safe_slot_jsx(slot: str, brand: str, title: str) -> str:
    brand_js = json.dumps(brand)
    title_js = json.dumps(title)
    samples = {
        "hero": (
            f'<MarketingHero brandName={{{brand_js}}} headline={{{title_js}}} '
            'subcopy="A clear, considered experience built around your next step." '
            'primaryCta={{ label: "Get started", href: "#details" }} '
            'imageSrc={images.hero} imageAlt="" />'
        ),
        "features": (
            '<FeatureBento heading="What you can expect" items={['
            '{ title: "Simple planning", description: "Everything needed to make a confident choice." }, '
            '{ title: "Thoughtful service", description: "A consistent experience from first visit to follow-up." }'
            ']} />'
        ),
        "products": (
            '<ProductShowcase heading="Featured picks" items={['
            '{ title: "Signature item", description: "A dependable starting point.", imageSrc: images.card1, imageAlt: "" }, '
            '{ title: "Everyday essential", description: "Built for daily use.", imageSrc: images.card2, imageAlt: "" }'
            ']} />'
        ),
        "showcase": (
            '<ProductShowcase heading="Featured experiences" items={['
            '{ title: "Signature service", description: "A dependable starting point.", imageSrc: images.card1, imageAlt: "" }, '
            '{ title: "Everyday essential", description: "Built for daily use.", imageSrc: images.card2, imageAlt: "" }'
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
            '{ label: "Signature result", beforeSrc: images.card2, afterSrc: images.card3 }'
            ']} />'
        ),
        "booking": (
            '<BookingPanel heading="Choose a time" '
            'treatments={[{ id: "signature", name: "Signature service", duration: "60 min" }]} '
            'slots={[{ id: "slot-1", startsAt: "2026-07-14T10:00:00" }]} />'
        ),
        "workspace": (
            '<Card title="Your details" description="Everything for this step in one place.">'
            '<p className="text-sm text-muted">Items, totals, and confirmation details appear here.</p>'
            '</Card>'
        ),
        "summary": (
            '<Card title="Summary" description="Totals update as you make changes.">'
            '<p className="text-sm text-muted">Review everything before you confirm.</p>'
            '</Card>'
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
    needs_images = any("images." in _safe_slot_jsx(slot, brand, title) for slot in slots)
    images_import = "import { images } from '@/data/mock';\n" if needs_images else ""
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
        # Cinematic homes get the transparent-over-hero header by default.
        chrome_attr = ' chrome="immersive"' if skeleton_id == "public-home" else ""
        body = (
            "  return (\n"
            f'    <{shell} brandName={{{json.dumps(brand)}}}{chrome_attr} '
            f'nav={{<PublicNav items={{navItems}} cta={{navCta}} />}}>\n'
            "      <div data-skeleton={skeleton.id}>\n"
            "        <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />\n"
            "      </div>\n"
            f"    </{shell}>\n"
            "  );"
        )
    return f"""// deterministic catalogue contract scaffold
{nav_import}{images_import}import {{ {", ".join(components)} }} from '@/ui';

const SKELETON_ID = {json.dumps(skeleton_id)} as const;

export default function {component}() {{
{nav_hook}  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {{
{slot_lines}
  }};

{body}
}}
"""


# Component prop/variant mismatches never break a Vite build (esbuild strips
# types; unknown props are ignored at runtime). They stay in the error list as
# retry feedback but must not cost the user the whole AI page.
_TOLERATED_ERROR_PREFIXES = ("invalid prop:", "invalid variant:")


def blocking_contract_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if not error.startswith(_TOLERATED_ERROR_PREFIXES)
    ]


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


_SLOTS_DECL_RE = re.compile(r"const\s+slots\s*(?::\s*[\w$<>,.\s\[\]]+?)?=\s*\{")
_UI_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]@/ui['\"]\s*;?")
_IMAGES_IMPORT_RE = re.compile(
    r"import\s*\{[^}]*\bimages\b[^}]*\}\s*from\s*['\"]@/data/mock['\"]"
)


def repair_missing_catalogue_slots(
    content: str,
    route: dict,
    *,
    brand_name: str | None = None,
) -> tuple[str, bool]:
    """Inject deterministic JSX for missing required slots into an AI page.

    Applies only when missing slots are the page's sole contract violations —
    a page that reasonably skipped optional-ish marketing sections keeps its
    business-specific content instead of being replaced by a generic scaffold.
    Structural, import, or prop errors still require regeneration.
    """
    errors = blocking_contract_errors(validate_catalogue_page_content(content, route))
    if not errors:
        return content, False
    missing = {error.split(":", 1)[1] for error in errors if error.startswith("slot:")}
    if not missing or any(not error.startswith("slot:") for error in errors):
        return content, False

    declaration = _SLOTS_DECL_RE.search(content)
    ui_import = _UI_IMPORT_RE.search(content)
    if not declaration or not ui_import:
        return content, False

    brand = brand_name or "Brand"
    title = str(route.get("title") or "Overview")
    ordered_missing = [
        slot for slot in assigned_non_shell_slots(route) if slot in missing
    ]
    if set(ordered_missing) != missing:
        return content, False
    try:
        injected = "".join(
            f"\n    {slot}: (\n      {_safe_slot_jsx(slot, brand, title)}\n    ),"
            for slot in ordered_missing
        )
    except ValueError:
        return content, False
    # A slot declared with an empty value (`cta: null,`) would shadow the
    # injected default (later key wins) — drop the dead declaration first.
    for slot in ordered_missing:
        content = re.sub(
            rf"\n\s*{re.escape(slot)}\s*:\s*(?:null|undefined|false|\{{\s*\}})\s*,?",
            "",
            content,
            count=1,
        )
    declaration = _SLOTS_DECL_RE.search(content)
    if not declaration:
        return content, False
    repaired = content[: declaration.end()] + injected + content[declaration.end():]

    existing_named = {
        token.strip().split(" as ")[0].replace("type ", "").strip()
        for token in ui_import.group(1).split(",")
        if token.strip()
    }
    needed = list(
        dict.fromkeys(
            component
            for slot in ordered_missing
            if (component := _SLOT_COMPONENT.get(slot))
            and component not in existing_named
        )
    )
    if needed:
        current = ui_import.group(1).strip().rstrip(",").strip()
        merged = ", ".join(filter(None, [current, ", ".join(needed)]))
        repaired = repaired.replace(
            ui_import.group(0),
            f"import {{ {merged} }} from '@/ui';",
            1,
        )

    needs_images = any(
        "images." in _safe_slot_jsx(slot, brand, title) for slot in ordered_missing
    )
    if needs_images and not _IMAGES_IMPORT_RE.search(repaired):
        repaired = "import { images } from '@/data/mock';\n" + repaired

    if blocking_contract_errors(validate_catalogue_page_content(repaired, route)):
        return content, False
    logging.getLogger(__name__).info(
        "Catalogue page healed by slot injection route=%s slots=%s",
        route.get("path"),
        ordered_missing,
    )
    return repaired, True


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
    content = normalize_catalogue_page_imports(content, route)
    if not blocking_contract_errors(validate_catalogue_page_content(content, route)):
        return content, False
    repaired, healed = repair_missing_catalogue_slots(
        content,
        route,
        brand_name=brand_name,
    )
    if healed:
        return repaired, False
    return (
        minimal_catalogue_page_scaffold(
            file_path,
            route,
            brand_name=brand_name,
        ),
        True,
    )
