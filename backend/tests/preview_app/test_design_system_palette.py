"""The derived brand palette rides through every design_system fallback.

`brand_palette.derive_palette` computes `text` / `muted` / `background` /
`surface` from the brand's own identity, and `design_brief` stores them on the
run's design system. The fallback writers (`patterns.design_system_dict` and
everything that renders it into `mock.ts`) used to discard all four and emit
hardcoded neutrals — and `surface_color` was omitted entirely. These tests pin
the threading at the producer and at both repair paths that write `mock.ts`.

They also pin the unification: `mock_data` used to carry its own diverging copy
of the function, so the font-name fix (8fe8955) never reached brand_contract's
consumers — `font_family` must be the font's *name*, never the squashed slug.
"""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.patterns import design_system_dict
from app.application.preview_app.safety.brand_contract import (
    ensure_brand_paths,
    ensure_brand_shape,
)
from app.application.preview_app.safety.mock_data import repair_typed_mock_exports
from app.application.preview_app.workspace import read_file, write_file

_PALETTE = {
    "text_color": "#1a2b3c",
    "muted_text_color": "#5a6b7c",
    "background_color": "#f6f2ea",
    "surface_color": "#fffdf9",
}


def test_design_system_dict_threads_the_derived_palette() -> None:
    ds = design_system_dict("#8b1e3f", "#2f6f4f", "Fraunces", _PALETTE)
    assert ds["text_color"] == "#1a2b3c"
    assert ds["muted_text_color"] == "#5a6b7c"
    assert ds["background_color"] == "#f6f2ea"
    assert ds["surface_color"] == "#fffdf9"
    assert ds["primary_color"] == "#8b1e3f"


def test_design_system_dict_falls_back_without_a_palette() -> None:
    ds = design_system_dict("#8b1e3f", "#2f6f4f", "Fraunces")
    assert ds["text_color"] == "#0f172a"
    assert ds["muted_text_color"] == "#475569"
    assert ds["background_color"] == "#fafafa"
    # surface_color exists even in fallback — pages read it; omission was the defect.
    assert ds["surface_color"] == "#ffffff"


def test_design_system_dict_font_family_is_the_name_not_the_slug() -> None:
    # The unification pin: brand_contract imports this exact function, so a
    # squashed `font_family` here is a squashed font on every contract path.
    ds = design_system_dict("#8b1e3f", "#2f6f4f", '"Source Sans 3", sans-serif')
    assert ds["font_family"] == "Source Sans 3"
    assert "family=source+sans+3" in ds["font_import_url"]


def test_repair_typed_mock_exports_writes_the_palette(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/data/mock.ts",
        'export const design_system = ["seeded stub"];\n',
    )
    replaced = repair_typed_mock_exports(
        tmp_path, "Osteria Vinci", "#8b1e3f", "#2f6f4f", "Fraunces", _PALETTE
    )
    assert "design_system" in replaced
    mock = read_file(tmp_path, "src/data/mock.ts")
    assert '"text_color": "#1a2b3c"' in mock
    assert '"muted_text_color": "#5a6b7c"' in mock
    assert '"background_color": "#f6f2ea"' in mock
    assert '"surface_color": "#fffdf9"' in mock


def test_usage_driven_injection_carries_the_palette() -> None:
    # The `_default_brand_top_value` path: a scanned page reads
    # brand.design_system.* and the brand object lacks the key entirely.
    mock = 'export const brand = {\n  name: "Osteria Vinci",\n};\n'
    updated, logs = ensure_brand_paths(
        mock,
        {("design_system", "text_color")},
        brand_name="Osteria Vinci",
        primary="#8b1e3f",
        secondary="#2f6f4f",
        font="Fraunces",
        design=_PALETTE,
    )
    assert logs, "the injection did not fire — fixture too small to reach the rule"
    assert '"text_color": "#1a2b3c"' in updated
    assert '"surface_color": "#fffdf9"' in updated


def test_ensure_brand_shape_patch_carries_the_palette(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        "src/data/mock.ts",
        "export const brand = {\n  name: \"Osteria Vinci\",\n};\n",
    )
    write_file(
        tmp_path,
        "src/pages/HomePage.tsx",
        "export default function HomePage() {\n"
        "  return <div style={{ color: brand.design_system.text_color }} />;\n"
        "}\n",
    )
    changed = ensure_brand_shape(
        tmp_path, "Osteria Vinci", "#8b1e3f", "#2f6f4f", "Fraunces", _PALETTE
    )
    assert changed
    mock = read_file(tmp_path, "src/data/mock.ts")
    assert '"text_color": "#1a2b3c"' in mock
    assert '"surface_color": "#fffdf9"' in mock
