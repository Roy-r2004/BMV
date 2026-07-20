"""Automated quality lock — evaluate + heal without manual steps."""
from __future__ import annotations

from pathlib import Path

from app.application.preview_app.quality_gate import (
    evaluate_quality_gate,
    heal_quality_gate,
    run_quality_gate_with_heal,
)
from app.application.preview_app.workspace import write_file


def _ws(tmp_path: Path) -> Path:
    (tmp_path / "src" / "pages").mkdir(parents=True)
    (tmp_path / "src" / "data").mkdir(parents=True)
    (tmp_path / "dist").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
    return tmp_path


def test_gate_fails_utility_stub_ai_hub(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        """
export default function AiFeaturesPage() {
  return <Card title="Your details">Signature package · Qty 1 Ready to confirm</Card>;
}
""",
    )
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(ws, "src/App.tsx", 'export default function App(){return null}')
    write_file(ws, "src/data/mock.ts", 'export const brand = { name: "X" }')
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert not report.ok
    codes = {i.code for i in report.issues}
    assert "ai_hub_not_deck" in codes or "ai_hub_utility_stub" in codes


def test_heal_rewrites_dead_ai_advisor_links(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        """// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
""",
    )
    write_file(
        ws,
        "src/pages/AiAdvisorChatPage.tsx",
        """
export default function AiAdvisorChatPage() {
  return (
    <div>
      <Button href={"/ai-advisor/skill-assessment"}>Start</Button>
      <div data-ai-feature-panel="skill-level-assessor"><AiFeaturePanel /></div>
    </div>
  );
}
""",
    )
    write_file(
        ws,
        "src/App.tsx",
        'import AiAdvisorChatPage from "./pages/AiAdvisorChatPage";\n'
        '          <Route path="/ai-advisor" element={<AiAdvisorChatPage />} />\n',
    )
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        "export const aiFeatures = [] as const;\n",
    )
    architect = {
        "routes": [
            {
                "path": "/ai-advisor",
                "component_file": "src/pages/AiAdvisorChatPage.tsx",
                "surface": "public",
            }
        ],
        "roles": [],
    }
    healed = heal_quality_gate(ws, architect, brand_name="Brand", req=None)
    assert healed
    advisor = (ws / "src/pages/AiAdvisorChatPage.tsx").read_text(encoding="utf-8")
    assert "/ai-advisor/skill-assessment" not in advisor
    assert "#skill-level-assessor" in advisor
    app = (ws / "src/App.tsx").read_text(encoding="utf-8")
    assert "/ai-advisor/*" in app


def test_gate_passes_after_heal(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        "export default function X(){ return <div>Signature package Your details Ready to confirm</div> }",
    )
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [] };\nexport const aiFeatures = [] as const;\n',
    )
    report = run_quality_gate_with_heal(
        ws,
        {"routes": [], "roles": []},
        brand_name="Brand",
        req=None,
        require_ai_hub=True,
        allow_ai_repair=False,
    )
    assert report.ok
    hub = (ws / "src/pages/AiFeaturesPage.tsx").read_text(encoding="utf-8")
    assert "AiFeatureDeck" in hub


def test_ai_repair_runs_when_deterministic_heal_insufficient(tmp_path: Path, monkeypatch) -> None:
    """When deterministic heal cannot clear issues, sandboxed AI repair runs."""
    from app.application.preview_app import quality_gate as qg

    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        """// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
""",
    )
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [] };\nexport const aiFeatures = [] as const;\n',
    )
    write_file(
        ws,
        "src/pages/MysteryPage.tsx",
        'export default function MysteryPage(){ return <a href={"/ai-advisor/skill-assessment"}>x</a> }',
    )

    # Simulate "unknown" failure: skip mechanical heals so AI must act.
    monkeypatch.setattr(qg, "heal_quality_gate", lambda *a, **k: [])

    calls = {"n": 0}

    def fake_ai_repair(workspace, architect, issues, ai_provider=None):
        calls["n"] += 1
        from app.application.preview_app.quality_repair import apply_repair_ops

        return apply_repair_ops(
            workspace,
            [
                {
                    "op": "replace",
                    "path": "src/pages/MysteryPage.tsx",
                    "old": "/ai-advisor/skill-assessment",
                    "new": "#skill-level-assessor",
                }
            ],
        )

    monkeypatch.setattr(
        "app.application.preview_app.quality_repair.run_ai_quality_repair",
        fake_ai_repair,
    )

    report = qg.run_quality_gate_with_heal(
        ws,
        {"routes": [], "roles": []},
        brand_name="Brand",
        req=None,
        require_ai_hub=True,
        allow_ai_repair=True,
        max_ai_attempts=1,
    )
    assert calls["n"] == 1
    assert report.ok
    mystery = (ws / "src/pages/MysteryPage.tsx").read_text(encoding="utf-8")
    assert "#skill-level-assessor" in mystery


def test_gate_detects_and_heals_empty_mock_export(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        """// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
""",
    )
    write_file(ws, "src/pages/HomePage.tsx", "export default function HomePage(){return null}")
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        "export const products = [];\n"
        "export const aiFeatures = [] as const;\n",
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert any(i.code == "empty_mock_export" for i in report.issues)

    healed = heal_quality_gate(ws, {"routes": [], "roles": []}, brand_name="Brand", req=None)
    assert "src/data/mock.ts" in healed
    mock = (ws / "src/data/mock.ts").read_text(encoding="utf-8")
    assert "export const products = []" not in mock

    report2 = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert not any(i.code == "empty_mock_export" for i in report2.issues)


def test_gate_detects_empty_seed_page(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    write_file(
        ws,
        "src/pages/AiFeaturesPage.tsx",
        """// plan AI feature hub
import { AiFeatureDeck } from '@/ui';
import { aiFeatures } from '@/data/mock';
export default function AiFeaturesPage() {
  return <AiFeatureDeck features={aiFeatures} brandName="Brand" />;
}
""",
    )
    write_file(
        ws,
        "src/pages/ListPage.tsx",
        """
import { useState } from 'react';
export default function ListPage() {
  const [items, setItems] = useState([]);
  return <ul>{items.map((x: any) => <li key={x.id}>{x.name}</li>)}</ul>;
}
""",
    )
    write_file(ws, "src/App.tsx", "export default function App(){return null}")
    write_file(
        ws,
        "src/data/mock.ts",
        'export const navigation = { public: [{ path: "/", label: "Home" }] };\n'
        "export const aiFeatures = [] as const;\n",
    )
    report = evaluate_quality_gate(ws, {}, require_ai_hub=True)
    assert any(i.code == "empty_seed_page" and "ListPage" in i.path for i in report.issues)
