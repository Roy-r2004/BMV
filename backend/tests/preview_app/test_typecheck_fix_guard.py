"""A type "fix" that deletes the feature is worse than the type error.

`<CredentialStrip items={[{label, value}]} />` fails to typecheck against
`CredentialStripItem {title, detail}`. Deleting the component, emptying the
array, or casting to `any` all make `tsc` quiet and the page emptier — which is
the exact defect the typecheck loop exists to remove. So the loop rejects those
patches deterministically instead of trusting the prompt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.codegen.fix_agent import (
    fix_type_errors,
    regressive_fix_reason,
)
from app.application.preview_app.typecheck import TypecheckReport, parse_tsc_output
from app.application.prompts import PromptTemplate
from app.infrastructure.templating.renderer import JinjaTemplateRenderer

TEMPLATES_DIR = REPO_ROOT / "backend" / "app" / "templates"

ABOUT_PAGE = """import { CredentialStrip, MarketingHero } from '@/ui';

export default function AboutPage() {
  return (
    <main>
      <MarketingHero brandName="Jeanne Kassab Art" headline="Original Oil Paintings" />
      <CredentialStrip
        heading="Trusted by art lovers"
        items={[{ label: 'Since 2009', value: '15 years' }, { label: 'Shipped', value: '40 countries' }]}
      />
    </main>
  );
}
"""

FIXED_PAGE = ABOUT_PAGE.replace(
    "{ label: 'Since 2009', value: '15 years' }, { label: 'Shipped', value: '40 countries' }",
    "{ title: 'Since 2009', detail: '15 years' }, { title: 'Shipped', detail: '40 countries' }",
)

DELETED_COMPONENT_PAGE = """import { MarketingHero } from '@/ui';

export default function AboutPage() {
  return (
    <main>
      <MarketingHero brandName="Jeanne Kassab Art" headline="Original Oil Paintings" />
    </main>
  );
}
"""

EMPTIED_PAGE = ABOUT_PAGE.replace(
    "items={[{ label: 'Since 2009', value: '15 years' }, { label: 'Shipped', value: '40 countries' }]}",
    "items={[]}",
)

ANY_CAST_PAGE = ABOUT_PAGE.replace(
    "items={[{ label: 'Since 2009', value: '15 years' }, { label: 'Shipped', value: '40 countries' }]}",
    "items={[{ label: 'Since 2009', value: '15 years' }] as any}",
)

TS_ERRORS = (
    "src/pages/AboutPage.tsx(7,9): error TS2322: Type '{ label: string; value: string; }[]' is not "
    "assignable to type 'CredentialStripItem[]'.\n"
    "  Type '{ label: string; value: string; }' is missing the following properties from type "
    "'CredentialStripItem': title, detail\n"
)


def test_remapping_the_real_fields_is_accepted() -> None:
    assert regressive_fix_reason("src/pages/AboutPage.tsx", ABOUT_PAGE, FIXED_PAGE) == ""


def test_deleting_a_component_usage_is_rejected() -> None:
    reason = regressive_fix_reason("src/pages/AboutPage.tsx", ABOUT_PAGE, DELETED_COMPONENT_PAGE)

    assert "CredentialStrip" in reason
    assert "deletes component usage" in reason


def test_emptying_a_data_array_is_rejected() -> None:
    reason = regressive_fix_reason("src/pages/AboutPage.tsx", ABOUT_PAGE, EMPTIED_PAGE)

    assert "empties data collection" in reason
    assert "items" in reason


def test_emptying_a_mock_collection_is_rejected() -> None:
    before = "export const seed = {\n  kpis: [{ label: 'Sales', value: '12' }],\n};\n"
    after = "export const seed = {\n  kpis: [],\n};\n"

    assert "kpis" in regressive_fix_reason("src/data/mock.ts", before, after)


def test_any_cast_is_rejected() -> None:
    reason = regressive_fix_reason("src/pages/AboutPage.tsx", ABOUT_PAGE, ANY_CAST_PAGE)

    assert "escape hatch" in reason


def test_ts_ignore_is_rejected() -> None:
    after = ABOUT_PAGE.replace("      <CredentialStrip", "      {/* @ts-ignore */}\n      <CredentialStrip")

    assert "escape hatch" in regressive_fix_reason("src/pages/AboutPage.tsx", ABOUT_PAGE, after)


class _ScriptedAI:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def ask_chat(self, _model, messages, **_kwargs):
        self.prompts.append(messages[-1]["content"])
        return self.response


def _workspace(tmp_path: Path) -> Path:
    pages = tmp_path / "src" / "pages"
    pages.mkdir(parents=True)
    (pages / "AboutPage.tsx").write_text(ABOUT_PAGE, encoding="utf-8")
    return tmp_path


def _report() -> TypecheckReport:
    return TypecheckReport(status="errors", diagnostics=tuple(parse_tsc_output(TS_ERRORS)))


def test_rejected_patch_is_never_written(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    ai = _ScriptedAI(
        json.dumps(
            {"files": [{"path": "src/pages/AboutPage.tsx", "content": DELETED_COMPONENT_PAGE}]}
        )
    )

    fix_type_errors(
        workspace, _report(), {}, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR)),
    )

    on_disk = (workspace / "src" / "pages" / "AboutPage.tsx").read_text(encoding="utf-8")
    assert "CredentialStrip" in on_disk
    assert "Since 2009" in on_disk


def test_valid_patch_is_written(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    ai = _ScriptedAI(
        json.dumps({"files": [{"path": "src/pages/AboutPage.tsx", "content": FIXED_PAGE}]})
    )

    patched = fix_type_errors(
        workspace, _report(), {}, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR)),
    )

    on_disk = (workspace / "src" / "pages" / "AboutPage.tsx").read_text(encoding="utf-8")
    assert "src/pages/AboutPage.tsx" in patched
    assert "title: 'Since 2009'" in on_disk


def test_prompt_carries_diagnostics_declarations_and_the_prohibition(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    ui = workspace / "src" / "ui" / "public"
    ui.mkdir(parents=True)
    (ui / "CredentialStrip.tsx").write_text(
        "export interface CredentialStripItem { title: string; detail: string; }\n", encoding="utf-8"
    )
    ai = _ScriptedAI("not json")

    fix_type_errors(
        workspace, _report(), {}, ai, JinjaTemplateRenderer(str(TEMPLATES_DIR)),
    )

    prompt = ai.prompts[0]
    assert "error TS2322" in prompt
    assert "CredentialStripItem" in prompt
    assert "title: string" in prompt and "detail: string" in prompt
    assert "ABSOLUTELY FORBIDDEN" in prompt
    assert "items={[]}" in prompt
    assert "@ts-ignore" in prompt


def test_build_fix_prompt_still_renders_without_typecheck_inputs() -> None:
    renderer = JinjaTemplateRenderer(str(TEMPLATES_DIR))

    prompt = renderer.render(
        PromptTemplate.PREVIEW_APP_FIX,
        build_errors="Adjacent JSX elements must be wrapped in an enclosing tag.",
        file_tree="src/pages/HomePage.tsx",
        architect_json="{}",
        files_content="export default function Page() { return null }",
        catalogue_mode=False,
        catalogue_routes_json="{}",
    )

    assert "=== BUILD ERRORS ===" in prompt
    assert "make `vite build` succeed" in prompt
    assert "TYPE ERRORS" not in prompt
