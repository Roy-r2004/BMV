"""Regression: safe stubs must emit single-brace TS object literals, not `{{ ... }}`."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.fallback import (  # noqa: E402
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
    if hits:
        raise AssertionError(f"{label}: found double-brace object literal(s): {hits[:3]!r}")
    if _INVALID_OBJECT_START.search(content):
        raise AssertionError(f"{label}: raw `{{ label:` still present")
    if not _VALID_ROW.search(content):
        raise AssertionError(f"{label}: expected at least one valid `{{ label: ... }}` row object")
    # Valid JSX attribute objects must still be allowed by the detector.
    jsx = 'const x = <div style={{ color: "red" }} />;'
    if find_double_brace_object_literals(jsx):
        raise AssertionError("detector must ignore JSX style={{ ... }} objects")


def main() -> None:
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

        write_safe_stub(
            root,
            "src/pages/owner/AdminClientsPage.tsx",
            brand_name="Lumina",
            industry="beauty spa salon",
            page_title="Clients",
        )
        admin = (root / "src/pages/owner/AdminClientsPage.tsx").read_text(encoding="utf-8")
        _assert_stub_ok(admin, "write_safe_stub salon")

        # Deterministic repair path for already-corrupted files.
        bad = (
            'const rows = [\n'
            '  {{ label: "9:15 · New patient", detail: "Room 2 · intake done", status: "Ready" }},\n'
            '  {{ label: "10:00 · Follow-up", detail: "Dr. Chen", status: "Live" }},\n'
            '];\n'
            'const style = {{ color: "red" }};\n'  # not our pattern (no label/k key) — leave alone
        )
        # The style line uses `{{ color` — detector should NOT flag it.
        if find_double_brace_object_literals('const style = {{ color: "red" }};'):
            raise AssertionError("detector falsely flagged style={{ color }}")

        # Catalogue components legitimately pass object-valued JSX props with
        # two braces: one JSX expression brace plus one object literal brace.
        catalogue_jsx = (
            '<MarketingHero\n'
            '  primaryCta={{ label: "Get started", onClick: () => navigate("/start") }}\n'
            '  secondaryCta={{ label: "Learn more", href: "#details" }}\n'
            '/>\n'
        )
        if find_double_brace_object_literals(catalogue_jsx):
            raise AssertionError("detector falsely flagged a JSX object-valued prop")
        unchanged, jsx_repairs = repair_double_brace_object_literals_in_text(catalogue_jsx)
        if unchanged != catalogue_jsx or jsx_repairs:
            raise AssertionError("repair corrupted a valid JSX object-valued prop")

        fixed, n = repair_double_brace_object_literals_in_text(bad)
        if n != 2:
            raise AssertionError(f"expected 2 row repairs, got {n}")
        if find_double_brace_object_literals(fixed):
            raise AssertionError(f"repair left double braces: {fixed!r}")
        if "{{ label:" in fixed:
            raise AssertionError("repair left `{{ label:`")
        if '{ label: "9:15 · New patient"' not in fixed:
            raise AssertionError("repair did not produce single-brace row objects")

        corrupt = root / "src" / "pages" / "BrokenPage.tsx"
        corrupt.write_text(bad, encoding="utf-8")
        repaired = scan_and_repair_double_brace_literals(root)
        if "src/pages/BrokenPage.tsx" not in repaired:
            raise AssertionError(f"scan_and_repair missed BrokenPage: {repaired}")
        after = corrupt.read_text(encoding="utf-8")
        if "{{ label:" in after:
            raise AssertionError("workspace scan left `{{ label:`")

    # Named icon key helper + trailing-comment import stripping stay in safety.py;
    # smoke-check the helpers without a full workspace.
    from app.application.preview_app.patterns import (  # noqa: E402
        _IMPORT_FROM_RE,
        _SIDE_EFFECT_IMPORT_RE,
    )
    from app.application.preview_app.safety.ui_icons import _icon_export_to_key  # noqa: E402

    if _icon_export_to_key("CalendarIcon") != "calendar":
        raise AssertionError("CalendarIcon key mapping broken")
    if _icon_export_to_key("DollarSignIcon") != "dollar-sign":
        raise AssertionError("DollarSignIcon key mapping broken")

    commented = "import { Dialog } from '@headlessui/react'; // modal shell\n"
    if not _IMPORT_FROM_RE.search(commented):
        raise AssertionError("import regex must match trailing // comments")
    side = "import 'react-datepicker/dist/react-datepicker.css';\n"
    if not _SIDE_EFFECT_IMPORT_RE.search(side):
        raise AssertionError("side-effect CSS import regex must match")

    print("OK: safe stub braces + double-brace repair regression passed")


if __name__ == "__main__":
    main()
