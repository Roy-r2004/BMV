"""Preview serving must 404 missing assets instead of SPA-falling-back to HTML."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse

from app.api.v1.routers import preview_apps


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "36" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>shell</html>", encoding="utf-8")
    (dist / "assets" / "index-Ab12Cd34.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "catalogue-hero.jpg").write_bytes(b"jpeg")
    return dist


def _serve(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, path: str):
    dist = _dist(tmp_path)
    monkeypatch.setattr(preview_apps, "get_dist_dir", lambda request_id: dist)
    return asyncio.run(preview_apps.serve_preview_app(36, path))


@pytest.mark.parametrize(
    "path",
    ["", "index.html", "works/crimson-tide", "admin/artworks", "works/crimson-tide/detail"],
)
def test_spa_routes_still_serve_the_shell(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, path: str
) -> None:
    response = _serve(monkeypatch, tmp_path, path)
    assert isinstance(response, FileResponse)
    assert Path(response.path).name == "index.html"


@pytest.mark.parametrize(
    "path",
    ["catalogue-hero.jpg", "assets/index-Ab12Cd34.js"],
)
def test_existing_assets_are_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, path: str
) -> None:
    response = _serve(monkeypatch, tmp_path, path)
    assert isinstance(response, FileResponse)
    assert Path(response.path).name == Path(path).name


@pytest.mark.parametrize(
    "path",
    [
        "images/mock-artwork-1.jpg",
        "placeholder-winter-solstice.jpg",
        "assets/index-Missing.js",
        "assets/index-Missing.css",
        "fonts/inter.woff2",
        "data/seed.json",
        "media/tour.mp4",
    ],
)
def test_missing_assets_404_instead_of_html_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, path: str
) -> None:
    with pytest.raises(HTTPException) as exc:
        _serve(monkeypatch, tmp_path, path)
    assert exc.value.status_code == 404


def test_asset_request_classification() -> None:
    assert preview_apps.is_asset_request("images/mock-artwork-1.jpg")
    assert preview_apps.is_asset_request("ASSETS/INDEX.CSS")
    assert not preview_apps.is_asset_request("works/crimson-tide")
    assert not preview_apps.is_asset_request("")
    assert not preview_apps.is_asset_request("gallery/2024-spring")
    assert not preview_apps.is_asset_request("some-page.html")
