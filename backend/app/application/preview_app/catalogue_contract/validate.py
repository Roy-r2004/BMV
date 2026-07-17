"""Catalogue page content validation."""
from __future__ import annotations

import re

from app.application.preview_app.catalogue_contract.bindings import (
    _ALLOWED_CATALOGUE_IMPORTS,
    _jsx_opening_props,
    _local_component_bindings,
    _REACT_GLOBAL_PROPS,
    _runtime_import_bindings,
    _ui_named_imports,
    _uppercase_jsx_roots,
)
from app.application.preview_app.catalogue_contract.imports import normalize_catalogue_page_imports
from app.application.preview_app.catalogue_contract.slots import (
    _declared_slot_values,
    _slot_value_is_present,
    assigned_non_shell_slots,
    expected_shell,
)
from app.application.preview_app.catalogue_contract.tokenize import (
    _has_token_sequence,
    _source_tokens,
)
from app.application.ui_catalogue import compact_skeleton_contract, get_skeleton

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


_TOLERATED_ERROR_PREFIXES = ("invalid prop:", "invalid variant:")


def blocking_contract_errors(errors: list[str]) -> list[str]:
    return [
        error
        for error in errors
        if not error.startswith(_TOLERATED_ERROR_PREFIXES)
    ]

