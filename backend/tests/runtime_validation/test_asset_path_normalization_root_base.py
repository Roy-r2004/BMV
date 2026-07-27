"""Relative Vite base breaks Phase 4 deep-route asset loading."""
from __future__ import annotations

from pathlib import Path

from app.application.runtime_validation.workspace import apply_deterministic_repair


def test_asset_path_normalization_converts_relative_base_to_root(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "vite.config.ts").write_text(
        "import { defineConfig } from 'vite';\n"
        "export default defineConfig({\n"
        "  base: './',\n"
        "});\n",
        encoding="utf-8",
        newline="\n",
    )
    (candidate / "index.html").write_text(
        "<!DOCTYPE html>\n"
        "<html><head>\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com" />\n'
        "</head><body><div id=\"root\"></div></body></html>\n",
        encoding="utf-8",
        newline="\n",
    )

    changed = apply_deterministic_repair(candidate, "asset_path_normalization")
    assert "vite.config.ts" in changed.split(",")
    assert "index.html" in changed.split(",")
    config = (candidate / "vite.config.ts").read_text(encoding="utf-8")
    assert "base: '/'" in config
    assert "base: './'" not in config
    assert "fonts.googleapis.com" not in (
        candidate / "index.html"
    ).read_text(encoding="utf-8")
