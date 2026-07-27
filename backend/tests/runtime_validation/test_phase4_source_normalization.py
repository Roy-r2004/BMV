"""Phase 4 source normalization before Vite build."""
from __future__ import annotations

from pathlib import Path

from app.application.runtime_validation.workspace import (
    normalize_phase4_candidate_sources,
)


def test_normalize_phase4_candidate_sources_fixes_base_fonts_and_component_dom(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    business = candidate / "src" / "components" / "business"
    business.mkdir(parents=True)
    (candidate / "vite.config.ts").write_text(
        "export default defineConfig({\n  base: './',\n});\n",
        encoding="utf-8",
        newline="\n",
    )
    (candidate / "index.html").write_text(
        "<!DOCTYPE html><html><head>\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        "</head><body></body></html>\n",
        encoding="utf-8",
        newline="\n",
    )
    (business / "CompBookingStartComponent.tsx").write_text(
        "export function CompBookingStartComponent() {\n"
        "  return (\n"
        '    <div className="wrap">\n'
        "      <button>Start</button>\n"
        "    </div>\n"
        "  );\n"
        "}\n"
        'export const COMP_BOOKING_START_COMPONENT_ID = "COMP-BOOKING-START";\n',
        encoding="utf-8",
        newline="\n",
    )

    changed = normalize_phase4_candidate_sources(candidate)
    assert "vite.config.ts" in changed
    assert "index.html" in changed
    assert "src/components/business/CompBookingStartComponent.tsx" in changed
    assert "base: '/'" in (candidate / "vite.config.ts").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in (
        candidate / "index.html"
    ).read_text(encoding="utf-8")
    component = (
        business / "CompBookingStartComponent.tsx"
    ).read_text(encoding="utf-8")
    assert 'data-bmv-component-id="COMP-BOOKING-START"' in component
