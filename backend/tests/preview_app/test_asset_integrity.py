"""Runtime asset integrity — a shipped preview must not reference images that 404."""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.asset_integrity import (
    blocking_missing_assets,
    repair_missing_asset_references,
    scan_asset_integrity,
)
from app.application.preview_app.quality_gate import (
    evaluate_quality_gate,
    heal_quality_gate,
)
from app.application.preview_app.workspace import write_file

_AI_HUB = """// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
"""
_MOCK = (
    'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
    "export const aiFeatures = [] as const;\n"
    "export const images = {\n"
    '  "hero": "https://images.pexels.com/photos/1/pexels-photo-1.jpeg",\n'
    '  "card1": "https://images.pexels.com/photos/2/pexels-photo-2.jpeg"\n'
    "};\n"
)


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pages" / "admin").mkdir(parents=True)
    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    public = tmp_path / "public"
    public.mkdir()
    (public / "catalogue-hero.jpg").write_bytes(b"jpeg")
    write_file(tmp_path, "src/pages/AiFeaturesPage.tsx", _AI_HUB)
    write_file(tmp_path, "src/App.tsx", "export default function App(){return null}")
    write_file(tmp_path, "src/data/mock.ts", _MOCK)
    return tmp_path


def test_scanner_reports_only_the_missing_reference(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/HomePage.tsx",
        "export default function HomePage(){\n"
        "  return (<div>\n"
        "    <img src=\"/catalogue-hero.jpg\" alt=\"hero\" />\n"
        "    <img src='/images/x.jpg' alt='missing' />\n"
        "  </div>);\n"
        "}\n",
    )
    report = scan_asset_integrity(ws)
    assert [ref.path for ref in report.missing] == ["/images/x.jpg"]
    assert report.missing[0].referenced_by == ("src/pages/HomePage.tsx",)
    assert report.missing[0].public_surface is True
    assert not report.ok


def test_scanner_ignores_remote_data_and_alias_references(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/HomePage.tsx",
        "import logo from '@/assets/logo.png';\n"
        "import './HomePage.css';\n"
        "export default function HomePage(){\n"
        "  return (<div>\n"
        "    <img src=\"https://images.pexels.com/photos/9/pexels-photo-9.jpeg\" />\n"
        "    <img src=\"http://cdn.example.com/a.png\" />\n"
        "    <img src=\"data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=\" />\n"
        "    <img src=\"//cdn.example.com/b.webp\" />\n"
        "    <video src={blobUrl} poster=\"blob:http://x/y.png\" />\n"
        "    <img src={`/images/${id}.jpg`} />\n"
        "    <img src={logo} />\n"
        "  </div>);\n"
        "}\n",
    )
    report = scan_asset_integrity(ws)
    assert report.missing == []
    assert report.ok


def test_scanner_accepts_asset_present_only_in_dist(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    (ws / "dist" / "assets").mkdir()
    (ws / "dist" / "assets" / "built-Ab12.png").write_bytes(b"png")
    write_file(
        ws,
        "src/pages/HomePage.tsx",
        'export default function HomePage(){ return <img src="/assets/built-Ab12.png" /> }\n',
    )
    assert scan_asset_integrity(ws).missing == []


def test_admin_only_break_is_not_blocking_but_public_break_is(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/admin/ManageArtworksPage.tsx",
        "export default function ManageArtworksPage(){\n"
        "  const rows = [{ image: '/images/mock-artwork-1.jpg' }];\n"
        "  return <img src={rows[0].image} />;\n"
        "}\n",
    )
    write_file(
        ws,
        "src/pages/HomePage.tsx",
        'export default function HomePage(){ return <img src="/catalogue-hero.jpg" /> }\n',
    )
    report = scan_asset_integrity(ws)
    assert [ref.path for ref in report.missing] == ["/images/mock-artwork-1.jpg"]
    assert report.missing[0].public_surface is False
    assert blocking_missing_assets(report) == []

    write_file(
        ws,
        "src/pages/HomePage.tsx",
        'export default function HomePage(){ return <img src="/hero-oil-painting.jpg" /> }\n',
    )
    report = scan_asset_integrity(ws)
    assert [ref.path for ref in blocking_missing_assets(report)] == [
        "/hero-oil-painting.jpg"
    ]


def test_repair_repoints_missing_reference_at_loadable_imagery(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/admin/DashboardPage.tsx",
        "export default function DashboardPage(){\n"
        "  return (<div>\n"
        "    <img src=\"/placeholder-winter-solstice.jpg\" />\n"
        "    <img src=\"/catalogue-hero.jpg\" />\n"
        "  </div>);\n"
        "}\n",
    )
    touched = repair_missing_asset_references(ws)
    assert touched == ["src/pages/admin/DashboardPage.tsx"]
    fixed = (ws / "src/pages/admin/DashboardPage.tsx").read_text(encoding="utf-8")
    assert "/placeholder-winter-solstice.jpg" not in fixed
    assert "https://images.pexels.com/photos/1/pexels-photo-1.jpeg" in fixed
    assert "/catalogue-hero.jpg" in fixed
    assert scan_asset_integrity(ws).ok


def test_gate_blocks_public_break_and_records_admin_break(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/admin/ManageArtworksPage.tsx",
        "export default function ManageArtworksPage(){ return <img src='/images/a.jpg' /> }\n",
    )
    write_file(
        ws,
        "src/pages/HomePage.tsx",
        'export default function HomePage(){ return <img src="/hero.jpg" /> }\n',
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert [i.code for i in report.issues if i.code.startswith("missing_")] == [
        "missing_public_asset"
    ]
    assert [i.code for i in report.warnings] == ["missing_internal_asset"]
    assert not report.ok

    heal_quality_gate(ws, {"routes": [], "roles": []}, brand_name="Brand", req=None)
    healed_report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert not [i for i in healed_report.issues if i.code.startswith("missing_")]
    assert not healed_report.warnings


def test_gate_flags_and_heals_empty_images_slot_map(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        "export const aiFeatures = [] as const;\n"
        "export const images = [];\n",
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert any(i.code == "empty_mock_images" for i in report.issues)
    assert not any(i.code == "empty_mock_export" for i in report.issues)

    healed = heal_quality_gate(ws, {"routes": [], "roles": []}, brand_name="Brand", req=None)
    assert "src/data/mock.ts" in healed
    mock = (ws / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "export const images = []" not in mock
    assert '"hero"' in mock
    assert not any(
        i.code == "empty_mock_images"
        for i in evaluate_quality_gate(ws, {}, require_ai_hub=True).issues
    )
