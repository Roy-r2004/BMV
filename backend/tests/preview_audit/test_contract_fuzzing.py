"""Lightweight contract fuzzing for Preview Generator v2 assumptions."""
from __future__ import annotations

import re

import pytest

from app.application.candidate_generation.deterministic import (
    component_export_symbol,
    page_export_symbol,
)
from app.application.candidate_generation.usage_validation import (
    validate_binding_against_source,
)
from app.domain.schemas.business_component_usage import (
    RequiredBusinessComponentBinding,
)


def _binding(component_id: str, page_id: str) -> RequiredBusinessComponentBinding:
    symbol = component_export_symbol(component_id)
    return RequiredBusinessComponentBinding(
        page_id=page_id,
        business_component_id=component_id,
        component_symbol=symbol,
        component_module_path=f"src/components/business/{symbol}.tsx",
        required_usage_count=1,
        required_props=(),
        action_ids=(),
        state_ids=(),
        evidence_ids=(),
        source_plan_revision="1.0",
        source_plan_hash="c" * 64,
    )


@pytest.mark.parametrize(
    "component_id,page_id",
    [
        ("COMP-HOME", "PAGE-HOME"),
        ("COMP-BOOKING-FORM", "PAGE-BOOKING"),
        ("COMP-AI-ASSIST", "PAGE-AI-FEATURES"),
        ("COMP-ADMIN-DASHBOARD", "PAGE-ADMIN"),
        ("COMP-X1", "PAGE-X1"),
    ],
)
def test_symbol_derivation_is_stable_and_traceable(component_id, page_id) -> None:
    symbol = component_export_symbol(component_id)
    page_symbol = page_export_symbol(page_id)
    assert re.fullmatch(r"[A-Z][A-Za-z0-9]*Component", symbol)
    assert re.fullmatch(r"[A-Z][A-Za-z0-9]*Page", page_symbol)
    # Round-trip: symbol contains normalized tokens from id.
    tokens = re.findall(r"[A-Za-z0-9]+", component_id)
    for token in tokens:
        assert token[:1].upper() + token[1:].lower() in symbol


@pytest.mark.parametrize(
    "import_style,expected",
    [
        (
            'import { CompHomeComponent } from "../components/business/CompHomeComponent";',
            "satisfied",
        ),
        (
            'import { CompHomeComponent as Home } from "../components/business/CompHomeComponent";\n'
            "export function PageHomePage(){return <main><Home /></main>}",
            "missing_mount",  # mount uses alias; validator requires symbol mount
        ),
        (
            'import { CompHomeComponent } from "@/components/business/CompHomeComponent";',
            "satisfied",
        ),
    ],
)
def test_import_styles_and_alias_assumptions(import_style, expected) -> None:
    binding = _binding("COMP-HOME", "PAGE-HOME")
    if "as Home" in import_style:
        source = import_style
    else:
        source = (
            import_style
            + "\n"
            + "export function PageHomePage(){\n"
            + '  return <main data-bmv-page-id="PAGE-HOME"><CompHomeComponent /></main>;\n'
            + "}\n"
        )
    item = validate_binding_against_source(
        source=source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == expected


def test_empty_optional_props_do_not_invent_requirements() -> None:
    binding = _binding("COMP-HOME", "PAGE-HOME")
    source = (
        'import { CompHomeComponent } from "../components/business/CompHomeComponent";\n'
        "export function PageHomePage(){\n"
        '  return <main data-bmv-page-id="PAGE-HOME"><CompHomeComponent /></main>;\n'
        "}\n"
    )
    item = validate_binding_against_source(
        source=source,
        binding=binding,
        component_file_exists=True,
    )
    assert item.result == "satisfied"
    assert item.required_props_present is True


def test_many_mandatory_components_all_required() -> None:
    page_id = "PAGE-HOME"
    bindings = [
        _binding(f"COMP-PART-{idx}", page_id) for idx in range(1, 6)
    ]
    imports = "\n".join(
        f'import {{ {b.component_symbol} }} from "../components/business/{b.component_symbol}";'
        for b in bindings
    )
    mounts = "\n".join(f"      <{b.component_symbol} />" for b in bindings)
    source = (
        imports
        + "\nexport function PageHomePage(){\n"
        + '  return (\n    <main data-bmv-page-id="PAGE-HOME">\n'
        + mounts
        + "\n    </main>\n  );\n}\n"
    )
    for binding in bindings:
        item = validate_binding_against_source(
            source=source,
            binding=binding,
            component_file_exists=True,
        )
        assert item.result == "satisfied"

    # Drop one mount -> that binding fails; others remain satisfied.
    dropped = bindings[0].component_symbol
    broken = source.replace(f"<{dropped} />", "<div />")
    failed = validate_binding_against_source(
        source=broken,
        binding=bindings[0],
        component_file_exists=True,
    )
    assert failed.result == "missing_mount"
    still_ok = validate_binding_against_source(
        source=broken,
        binding=bindings[1],
        component_file_exists=True,
    )
    assert still_ok.result == "satisfied"
