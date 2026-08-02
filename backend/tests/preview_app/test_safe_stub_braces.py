"""Regression: safe stubs must emit single-brace TS object literals, not `{{ ... }}`."""
from __future__ import annotations

import re
import tempfile
from pathlib import Path

from app.application.preview_app.fallback import (
    find_double_brace_object_literals,
    repair_double_brace_object_literals_in_text,
    scan_and_repair_double_brace_literals,
    write_safe_stub,
)

_INVALID_OBJECT_START = re.compile(r"\{\{\s*(?:label|detail|status|k|v)\s*:")
_VALID_ROW = re.compile(
    r"\{\s*label:\s*\"[^\"]+\",\s*detail:\s*\"[^\"]+\",\s*status:\s*\"[^\"]+\"\s*\}"
)


def _assert_stub_ok(content: str, label: str) -> None:
    hits = find_double_brace_object_literals(content)
    assert not hits, f"{label}: found double-brace object literal(s): {hits[:3]!r}"
    assert not _INVALID_OBJECT_START.search(content), (
        f"{label}: raw `{{ label:` still present"
    )
    assert _VALID_ROW.search(content), (
        f"{label}: expected at least one valid `{{ label: ... }}` row object"
    )
    # Valid JSX attribute objects must still be allowed by the detector.
    jsx = 'const x = <div style={{ color: "red" }} />;'
    assert not find_double_brace_object_literals(jsx), (
        "detector must ignore JSX style={{ ... }} objects"
    )


def test_write_safe_stub_emits_single_brace_row_objects() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src" / "pages").mkdir(parents=True)
        path = "src/pages/HomePage.tsx"
        write_safe_stub(
            root,
            path,
            brand_name="Lumina Aesthetics",
            industry="clinic / medical aesthetics",
            page_title="Home",
        )
        content = (root / path).read_text(encoding="utf-8")
        _assert_stub_ok(content, "write_safe_stub clinic")

        admin_rel = "src/pages/owner/AdminClientsPage.tsx"
        write_safe_stub(
            root,
            admin_rel,
            brand_name="Lumina",
            industry="beauty spa salon",
            page_title="Clients",
        )
        admin_path = next(root.rglob("AdminClientsPage.tsx"))
        admin = admin_path.read_text(encoding="utf-8")
        _assert_stub_ok(admin, "write_safe_stub salon")


def test_double_brace_detector_ignores_jsx_style_and_object_props() -> None:
    assert not find_double_brace_object_literals('const style = {{ color: "red" }};'), (
        "detector falsely flagged style={{ color }}"
    )

    # Catalogue components legitimately pass object-valued JSX props with
    # two braces: one JSX expression brace plus one object literal brace.
    catalogue_jsx = (
        '<MarketingHero\n'
        '  primaryCta={{ label: "Get started", onClick: () => navigate("/start") }}\n'
        '  secondaryCta={{ label: "Learn more", href: "#details" }}\n'
        '/>\n'
    )
    assert not find_double_brace_object_literals(catalogue_jsx), (
        "detector falsely flagged a JSX object-valued prop"
    )
    unchanged, jsx_repairs = repair_double_brace_object_literals_in_text(catalogue_jsx)
    assert unchanged == catalogue_jsx and not jsx_repairs, (
        "repair corrupted a valid JSX object-valued prop"
    )


def test_repair_collapses_double_brace_row_objects() -> None:
    bad = (
        'const rows = [\n'
        '  {{ label: "9:15 · New patient", detail: "Room 2 · intake done", status: "Ready" }},\n'
        '  {{ label: "10:00 · Follow-up", detail: "Dr. Chen", status: "Live" }},\n'
        '];\n'
        'const style = {{ color: "red" }};\n'  # not our pattern (no label/k key) — leave alone
    )
    fixed, n = repair_double_brace_object_literals_in_text(bad)
    assert n == 2, f"expected 2 row repairs, got {n}"
    assert not find_double_brace_object_literals(fixed), (
        f"repair left double braces: {fixed!r}"
    )
    assert "{{ label:" not in fixed, "repair left `{{ label:`"
    assert '{ label: "9:15 · New patient"' in fixed, (
        "repair did not produce single-brace row objects"
    )

    # Non-row shapes the model emits (partial keys / expressions) must also
    # collapse — this is what hard-failed PaintingDetailPage on req 17.
    partial = (
        'const meta = [\n'
        '  {{ label: painting.title }},\n'
        '  {{ label: "Size", detail: painting.size }},\n'
        '];\n'
        'const cta = {{ label: "Inquire", href: "/contact" }};\n'
    )
    partial_fixed, partial_n = repair_double_brace_object_literals_in_text(partial)
    assert partial_n >= 1, f"expected partial double-brace repairs, got {partial_n}"
    assert not find_double_brace_object_literals(partial_fixed), (
        f"partial repair left double braces: {partial_fixed!r}"
    )
    assert "{{ label:" not in partial_fixed, "partial repair left `{{ label:`"


def test_scan_and_repair_double_brace_literals_across_workspace() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "src" / "pages").mkdir(parents=True)
        bad = (
            'const rows = [\n'
            '  {{ label: "9:15 · New patient", detail: "Room 2 · intake done", status: "Ready" }},\n'
            '  {{ label: "10:00 · Follow-up", detail: "Dr. Chen", status: "Live" }},\n'
            '];\n'
            'const style = {{ color: "red" }};\n'
        )
        partial = (
            'const meta = [\n'
            '  {{ label: painting.title }},\n'
            '  {{ label: "Size", detail: painting.size }},\n'
            '];\n'
            'const cta = {{ label: "Inquire", href: "/contact" }};\n'
        )
        corrupt = root / "src" / "pages" / "BrokenPage.tsx"
        corrupt.write_text(bad + "\n" + partial, encoding="utf-8")
        repaired = scan_and_repair_double_brace_literals(root)
        assert "src/pages/BrokenPage.tsx" in repaired, (
            f"scan_and_repair missed BrokenPage: {repaired}"
        )
        after = corrupt.read_text(encoding="utf-8")
        assert "{{ label:" not in after, "workspace scan left `{{ label:`"


def test_icon_key_helper_and_import_regexes() -> None:
    # Named icon key helper + trailing-comment import stripping stay in safety.py;
    # smoke-check the helpers without a full workspace.
    from app.application.preview_app.patterns import (
        _IMPORT_FROM_RE,
        _SIDE_EFFECT_IMPORT_RE,
    )
    from app.application.preview_app.safety.ui_icons import _icon_export_to_key

    assert _icon_export_to_key("CalendarIcon") == "calendar", (
        "CalendarIcon key mapping broken"
    )
    assert _icon_export_to_key("DollarSignIcon") == "dollar-sign", (
        "DollarSignIcon key mapping broken"
    )

    commented = "import { Dialog } from '@headlessui/react'; // modal shell\n"
    assert _IMPORT_FROM_RE.search(commented), (
        "import regex must match trailing // comments"
    )
    side = "import 'react-datepicker/dist/react-datepicker.css';\n"
    assert _SIDE_EFFECT_IMPORT_RE.search(side), (
        "side-effect CSS import regex must match"
    )
