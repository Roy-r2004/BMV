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
from app.application.preview_app.catalogue_contract.scaffold import (
    LISTING_FACE_COMPONENTS,
    has_listing_face_component,
)
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

_SCHEDULE_FACE_MARKER = "// schedule listing scaffold"
_SCHEDULE_FACE_REQUIRED = (
    "PublicShell",
    "PublicNav",
    "MarketingHero",
    "ScheduleRail",
    "CTABand",
    "BrandFooter",
)
_DIRECTORY_FACE_MARKER = "// directory listing scaffold"
# The items component is checked separately — CatalogGrid or ProductShowcase.
_DIRECTORY_FACE_REQUIRED = (
    "PublicShell",
    "PublicNav",
    "PageHeader",
    "CTABand",
    "BrandFooter",
)
_CONFIRM_FACE_MARKER = "// composed confirmation page (ConfirmStage)"
_CONFIRM_FACE_REQUIRED = (
    "PublicShell",
    "PublicNav",
    "ConfirmStage",
    "BrandFooter",
)
_AI_HUB_FACE_MARKER = "// plan AI feature hub"
_AI_HUB_FACE_REQUIRED = (
    "PublicShell",
    "PublicNav",
    "AiFeatureDeck",
)


def _validate_schedule_listing_face(content: str) -> list[str]:
    """Accept dedicated ScheduleRail listing pages (not SkeletonComposer clones)."""
    errors: list[str] = []
    text = content or ""
    for name in _SCHEDULE_FACE_REQUIRED:
        if name not in text:
            errors.append(f"missing schedule face component:{name}")
    if "@/ui" not in text:
        errors.append("missing @/ui import")
    if "BRAND_MANIFEST" not in text:
        errors.append("missing BRAND_MANIFEST services binding")
    return errors


def _validate_directory_listing_face(content: str) -> list[str]:
    """Accept doctor/provider directory pages (not homepage MarketingHero clones)."""
    errors: list[str] = []
    text = content or ""
    for name in _DIRECTORY_FACE_REQUIRED:
        if name not in text:
            errors.append(f"missing directory face component:{name}")
    if not has_listing_face_component(text):
        errors.append(
            "missing directory face component:" + "|".join(LISTING_FACE_COMPONENTS)
        )
    if "@/ui" not in text:
        errors.append("missing @/ui import")
    if "BRAND_MANIFEST" not in text:
        errors.append("missing BRAND_MANIFEST services binding")
    if "seed.hero" in text:
        errors.append("directory face must not reuse seed.hero")
    return errors


def _validate_confirm_stage_face(content: str) -> list[str]:
    """Accept ConfirmStage confirmation pages (utility compositor face)."""
    errors: list[str] = []
    text = content or ""
    if _CONFIRM_FACE_MARKER not in text:
        return ["confirm stage face marker"]
    for name in _CONFIRM_FACE_REQUIRED:
        if name not in text:
            errors.append(f"missing confirm face component:{name}")
    if "@/ui" not in text:
        errors.append("missing @/ui import")
    return errors


def _validate_ai_hub_face(content: str) -> list[str]:
    """Accept AiFeatureDeck hub pages — never public-utility checkout stubs."""
    errors: list[str] = []
    text = content or ""
    if _AI_HUB_FACE_MARKER not in text and "AiFeatureDeck" not in text:
        return ["ai hub face marker"]
    for name in _AI_HUB_FACE_REQUIRED:
        if name not in text:
            errors.append(f"missing ai hub face component:{name}")
    if "@/ui" not in text:
        errors.append("missing @/ui import")
    if "aiFeatures" not in text and "ai_features" not in text:
        errors.append("missing aiFeatures binding")
    # Reject the utility stub that used to overwrite this page.
    if "Signature package" in text or (
        "Your details" in text and "Ready to confirm" in text
    ):
        errors.append("utility checkout stub on ai hub")
    return errors


def validate_catalogue_page_content(content: str, route: dict) -> list[str]:
    skeleton_id = str(route.get("skeleton_id") or "")
    text = content or ""
    path = str(route.get("path") or "").rstrip("/").lower()
    page_id = str(route.get("app_spec_page_id") or route.get("page_id") or "").casefold()
    is_ai_hub = (
        path == "/ai-features"
        or page_id == "page-ai-features"
        or _AI_HUB_FACE_MARKER in text
        or (
            "AiFeatureDeck" in text
            and "AiFeaturesPage" in text
        )
    )
    if is_ai_hub:
        return _validate_ai_hub_face(text)
    if not skeleton_id:
        return []
    # A page's *face* has to survive a rewrite. Both markers are comments, and
    # refine is the one writer guaranteed to drop them: request 66's
    # CollectionPage was refined three times and rejected wholesale each time
    # with every assigned slot reported missing — `slot:hero`, `slot:trust`,
    # `slot:filters`, all seven — because a listing face has no `slots` object
    # to declare them in and, once its marker was gone, was judged as though it
    # should have one. `SkeletonComposer` is the structural tell: a slot-composed
    # page has one, a dedicated listing face never does.
    composed = "SkeletonComposer" in text
    if _SCHEDULE_FACE_MARKER in text or (not composed and "<ScheduleRail" in text):
        return _validate_schedule_listing_face(text)
    if _DIRECTORY_FACE_MARKER in text or (
        not composed and has_listing_face_component(text)
    ):
        return _validate_directory_listing_face(text)
    if _CONFIRM_FACE_MARKER in text or (
        "ConfirmStage" in text and "composed confirmation page" in text
    ):
        return _validate_confirm_stage_face(text)
    errors: list[str] = []
    # Validate against normalized imports — enforce_catalogue_page_contract
    # materializes the same rewrite before the file is written.
    tokens = _source_tokens(normalize_catalogue_page_imports(text, route))
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
    # Public detail must stay painting-first. AI slot_fill on request 50 swapped
    # variant="item" for a recipe atelier billboard and replaced itemSpecs with
    # seed.credentials ("Why Brand") — reject so repair re-scaffolds.
    if skeleton_id == "public-detail" and shell == "PublicShell":
        if 'variant="item"' not in text and "variant={'item'}" not in text:
            errors.append("detail painting-first hero (variant=item)")
        # Must bind specs to the resolved item — seed.credentials is the marketing
        # "Why brand" strip that buried the painting on request 50.
        if not re.search(r"items=\{\s*itemSpecs\s*\}", text):
            errors.append("detail itemSpecs binding")
        if not re.search(r"""href:\s*['"]#inquire['"]""", text):
            errors.append("detail inquire CTA (#inquire)")
        if re.search(r"items=\{\s*seed\.credentials", text):
            errors.append("detail seed.credentials instead of itemSpecs")
        if re.search(
            r"""(credentialsHeading|heading)=\{\s*(seed\.credentialsHeading\s*\?\?\s*)?['"]Why\s""",
            text,
        ) or re.search(r"""heading=\{_js\(["']Why\s""", text):
            errors.append("detail buried Why-brand credentials")
    # Catalogue / listing faces must bind the per-item photo pool — card/hero
    # slots are lifestyle and shipped people-in-museums on request 62's gallery.
    if skeleton_id in {"public-catalog", "public-home"} and shell == "PublicShell":
        if "CatalogGrid" in text or "ProductShowcase" in text:
            if "images.item1" not in text and "images.item2" not in text:
                errors.append("catalogue item photo pool (images.item*)")
            if re.search(
                r"imageSrc:\s*\[images\.(?:card|hero)",
                text,
            ) or re.search(r"PAINTING_IMAGES\s*=\s*\[[\s\S]*images\.(?:card|hero)", text):
                errors.append("catalogue lifestyle imageSrc (card/hero)")
    # Dead hash CTAs on public faces — #details / bare #contact never resolve.
    if shell == "PublicShell" and re.search(
        r"""href:\s*['"]#(details|contact)['"]""", text
    ):
        errors.append("dead hash CTA (#details/#contact)")
    # Contact pages must keep the inquiry form (and #inquire anchor). Request 50
    # shipped /contact as a public-home marketing clone — CTAs to /contact#inquire
    # then scrolled nowhere useful. Match on path only (titles like "Inquire about
    # this piece" must not trigger this on detail pages).
    path_l = str(route.get("path") or "").rstrip("/").lower()
    if re.search(r"(^|/)(contact|contact-us)(/|$)", path_l):
        if "InquiryPanel" not in text:
            errors.append("contact InquiryPanel")
        # InquiryPanel renders id="inquire" at runtime — composed pages import
        # the kit component and do not restate the attribute in source.
        if (
            "InquiryPanel" not in text
            and 'id="inquire"' not in text
            and "id={'inquire'}" not in text
        ):
            errors.append("contact #inquire anchor")
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

