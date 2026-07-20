"""BRAND_MANIFEST must include services[] — ClassesPage calls .services.filter()."""
from __future__ import annotations

import json
from pathlib import Path

from app.application.preview_app.safety.mock_data import (
    _default_export_value,
    ensure_mock_exports,
)


def test_default_brand_manifest_includes_services():
    raw = _default_export_value("BRAND_MANIFEST", {}, {}, {}, "Clay & Kiln")
    data = json.loads(raw)
    assert isinstance(data.get("services"), list)
    assert data["services"]
    assert isinstance(data.get("products"), list)


def test_ensure_mock_exports_adds_full_brand_manifest(tmp_path: Path):
    (tmp_path / "src/data").mkdir(parents=True)
    (tmp_path / "src/pages").mkdir(parents=True)
    (tmp_path / "src/data/mock.ts").write_text(
        'export const brand = { name: "Clay & Kiln", tagline: "x" };\n',
        encoding="utf-8",
    )
    (tmp_path / "src/pages/ClassesPage.tsx").write_text(
        "import { BRAND_MANIFEST } from '../data/mock';\n"
        "export default function ClassesPage() {\n"
        "  return BRAND_MANIFEST.services.filter(Boolean);\n"
        "}\n",
        encoding="utf-8",
    )

    added = ensure_mock_exports(tmp_path, {}, {}, {}, "Clay & Kiln")
    assert "BRAND_MANIFEST" in added
    mock = (tmp_path / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "export const BRAND_MANIFEST" in mock
    assert '"services"' in mock
    # Must not be a bare brand spread without services.
    assert "...brand" not in mock.split("BRAND_MANIFEST", 1)[1][:200]
