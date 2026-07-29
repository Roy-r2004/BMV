"""The generated shell must carry the real business identity, not "Preview App"."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.assemble import (
    _npm_package_name,
    write_app_shell,
    write_plumbing_mock,
)

TEMPLATE_DIR = REPO_ROOT / "backend" / "preview-template"
ADVERSARIAL_BRAND = 'Jeanne & "Kassab" <Art> — Café Ñoño'


def _shell_workspace(tmp: str) -> Path:
    """A workspace holding exactly the shell files prepare_workspace copies."""
    workspace = Path(tmp)
    for name in ("index.html", "package.json"):
        shutil.copy2(TEMPLATE_DIR / name, workspace / name)
    return workspace


def _title(workspace: Path) -> str:
    match = re.search(
        r"<title>(.*?)</title>",
        (workspace / "index.html").read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match, "shell lost its <title>"
    return match.group(1)


def _descriptions(workspace: Path) -> list[str]:
    return re.findall(
        r'<meta\s+name="description"\s+content="(.*?)"\s*/?>',
        (workspace / "index.html").read_text(encoding="utf-8"),
    )


def test_shell_carries_brand_title_and_description() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _shell_workspace(tmp)
        write_app_shell(
            workspace,
            "Jeanne Kassab Art",
            "Original oil paintings that evoke calm and captivate the beholder.",
        )
        html = (workspace / "index.html").read_text(encoding="utf-8")
        assert "Preview App" not in html
        assert _title(workspace) == "Jeanne Kassab Art"
        assert _descriptions(workspace) == [
            "Original oil paintings that evoke calm and captivate the beholder."
        ]
        assert '<script type="module" src="/src/main.tsx">' in html
        assert "fonts.googleapis.com" in html

        manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        assert manifest["name"] == "jeanne-kassab-art"
        assert manifest["type"] == "module"
        assert "react" in manifest["dependencies"]
        assert "vite" in manifest["devDependencies"]


def test_shell_escapes_adversarial_brand_and_stays_valid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _shell_workspace(tmp)
        write_app_shell(workspace, ADVERSARIAL_BRAND, 'A & B\'s "finest" <works>')
        html = (workspace / "index.html").read_text(encoding="utf-8")

        assert _title(workspace) == (
            "Jeanne &amp; &quot;Kassab&quot; &lt;Art&gt; — Café Ñoño"
        )
        assert _descriptions(workspace) == [
            "A &amp; B&#x27;s &quot;finest&quot; &lt;works&gt;"
        ]
        # No raw markup-breaking characters escaped into the head.
        head = html.split("</head>", 1)[0]
        assert "<Art>" not in head
        assert 'content="A & B' not in head
        assert head.count("<title>") == 1
        assert html.count("<head>") == 1 and html.count("</head>") == 1

        manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        assert manifest["name"] == "jeanne-kassab-art-cafe-nono"
        assert re.fullmatch(r"[a-z0-9][a-z0-9._-]*", manifest["name"])
        assert len(manifest["name"]) <= 214


def test_shell_stamp_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _shell_workspace(tmp)
        write_app_shell(workspace, "Atelier Nine", "First pass description.")
        write_app_shell(workspace, "Atelier Nine", "Second pass description.")
        assert _descriptions(workspace) == ["Second pass description."]
        assert _title(workspace) == "Atelier Nine"
        html = (workspace / "index.html").read_text(encoding="utf-8")
        assert html.count("<title>") == 1


def test_npm_package_name_never_yields_an_invalid_name() -> None:
    assert _npm_package_name("Clay & Kiln") == "clay-kiln"
    assert _npm_package_name("  __Nine__  ") == "nine"
    assert _npm_package_name(".hidden") == "hidden"
    assert _npm_package_name("日本") == "preview-app"
    assert _npm_package_name("") == "preview-app"
    assert _npm_package_name(None) == "preview-app"  # type: ignore[arg-type]
    assert _npm_package_name("Favicon.ICO") == "favicon-ico"
    assert len(_npm_package_name("Studio " * 200)) <= 214
    for raw in ("Clay & Kiln", "日本", ".hidden", "Studio " * 200, "A/B Testing Co"):
        assert re.fullmatch(r"[a-z0-9][a-z0-9._-]*", _npm_package_name(raw))


def test_plumbing_mock_stamps_the_shell_with_the_resolved_brand() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _shell_workspace(tmp)
        write_plumbing_mock(
            workspace,
            {"routes": [{"path": "/", "title": "Home", "layout": "public"}], "roles": []},
            {},
            ADVERSARIAL_BRAND,
            "#0f766e",
            "#0b5853",
            mock_seed={
                "hero": {
                    "subcopy": "Original oil paintings, hung by appointment in the Beirut studio.",
                }
            },
        )
        assert _title(workspace) == (
            "Jeanne &amp; &quot;Kassab&quot; &lt;Art&gt; — Café Ñoño"
        )
        assert _descriptions(workspace) == [
            "Original oil paintings, hung by appointment in the Beirut studio."
        ]
        manifest = json.loads((workspace / "package.json").read_text(encoding="utf-8"))
        assert manifest["name"] == "jeanne-kassab-art-cafe-nono"


def test_plumbing_mock_falls_back_to_a_brand_description() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = _shell_workspace(tmp)
        write_plumbing_mock(
            workspace,
            {"routes": [], "roles": []},
            {},
            "Atelier Nine",
            "#0f766e",
            "#0b5853",
            mock_seed={"hero": {"subcopy": "too short"}},
        )
        descriptions = _descriptions(workspace)
        assert len(descriptions) == 1
        assert descriptions[0].startswith("Atelier Nine")
        assert len(descriptions[0]) <= 160


def main() -> None:
    test_shell_carries_brand_title_and_description()
    test_shell_escapes_adversarial_brand_and_stays_valid()
    test_shell_stamp_is_idempotent()
    test_npm_package_name_never_yields_an_invalid_name()
    test_plumbing_mock_stamps_the_shell_with_the_resolved_brand()
    test_plumbing_mock_falls_back_to_a_brand_description()


if __name__ == "__main__":
    main()
