"""Sandboxed quality repair — ops/script safety + apply path."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.application.preview_app.quality_repair import (
    apply_quality_repair_plan,
    apply_repair_ops,
    run_repair_script,
)
from app.application.preview_app.workspace import write_file


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pages").mkdir(parents=True)
    write_file(
        tmp_path,
        "src/pages/AiAdvisorChatPage.tsx",
        'export default function X(){ return <a href={"/ai-advisor/skill-assessment"}>Go</a> }',
    )
    return tmp_path


def test_ops_replace_under_src(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    touched = apply_repair_ops(
        ws,
        [
            {
                "op": "replace",
                "path": "src/pages/AiAdvisorChatPage.tsx",
                "old": "/ai-advisor/skill-assessment",
                "new": "#skill-level-assessor",
            }
        ],
    )
    assert touched == ["src/pages/AiAdvisorChatPage.tsx"]
    src = (ws / "src/pages/AiAdvisorChatPage.tsx").read_text(encoding="utf-8")
    assert "#skill-level-assessor" in src
    assert "/ai-advisor/skill-assessment" not in src


def test_ops_reject_path_traversal(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    touched = apply_repair_ops(
        ws,
        [{"op": "write", "path": "../evil.py", "content": "print(1)"}],
    )
    assert touched == []
    assert not (tmp_path.parent / "evil.py").exists()


def test_script_forbidden_import(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    with pytest.raises(ValueError, match="forbidden"):
        run_repair_script(ws, "import os\nos.system('echo hi')")


def test_script_can_replace_via_api(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    touched = run_repair_script(
        ws,
        """
src = read("src/pages/AiAdvisorChatPage.tsx")
write(
    "src/pages/AiAdvisorChatPage.tsx",
    src.replace("/ai-advisor/skill-assessment", "#skill-level-assessor"),
)
""",
    )
    assert "src/pages/AiAdvisorChatPage.tsx" in touched
    src = (ws / "src/pages/AiAdvisorChatPage.tsx").read_text(encoding="utf-8")
    assert "#skill-level-assessor" in src


def test_plan_prefers_ops_then_files(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    touched = apply_quality_repair_plan(
        ws,
        {
            "strategy": "ops",
            "ops": [
                {
                    "op": "replace",
                    "path": "src/pages/AiAdvisorChatPage.tsx",
                    "old": "Go",
                    "new": "Start",
                }
            ],
        },
    )
    assert touched
    assert "Start" in (ws / "src/pages/AiAdvisorChatPage.tsx").read_text(encoding="utf-8")


def test_blocks_template_owned_ui(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    (ws / "src" / "ui").mkdir(parents=True)
    write_file(ws, "src/ui/Button.tsx", "export const Button = () => null")
    architect = {"_catalogue_workspace": True, "routes": [{"skeleton_id": "public-home"}]}
    touched = apply_repair_ops(
        ws,
        [{"op": "write", "path": "src/ui/Button.tsx", "content": "hacked"}],
        architect,
    )
    assert touched == []
    assert "hacked" not in (ws / "src/ui/Button.tsx").read_text(encoding="utf-8")
