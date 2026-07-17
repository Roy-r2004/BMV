from __future__ import annotations

import re
import tempfile
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.catalogue_contract import (
    minimal_catalogue_page_scaffold,
    validate_catalogue_page_content,
)
from app.application.preview_app.fallback import write_safe_stub
from app.application.preview_app.safety.imports import (
    normalize_ui_kit_imports,
    rewrite_invented_component_imports,
    restore_curated_ui_kit,
    sanitize_ui_component_apis,
    strip_forbidden_npm_imports,
)
from app.application.preview_app.safety.orchestrator import apply_workspace_guards
from app.application.preview_app.safety.pages import unwrap_route_layout_wrappers
from app.application.preview_app.safety.runtime import _ensure_tailwind_css
from app.infrastructure.templating.renderer import JinjaTemplateRenderer


def _write(root: Path, rel: str, content: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def _route() -> dict:
    return {
        "path": "/",
        "component_file": "src/pages/HomePage.tsx",
        "surface": "public",
        "skeleton_id": "public-home",
        "section_slots": ["hero", "features", "showcase", "process", "testimonials", "cta", "footer"],
    }


def test_import_policy_is_path_scoped() -> None:
    imports = """import * as React from 'react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { cva } from 'class-variance-authority';
import { LineChart } from 'recharts';
import { useReactTable } from '@tanstack/react-table';
import * as Dialog from '@radix-ui/react-dialog';
import * as Select from '@radix-ui/react-select';
import * as Tabs from '@radix-ui/react-tabs';
import * as Tooltip from '@radix-ui/react-tooltip';
import { motion } from 'motion/react';
import { Camera } from 'lucide-react';
import { toast } from 'sonner';
import { format } from 'date-fns';
"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        kit = _write(workspace, "src/ui/core/Curated.tsx", imports + "export const curated = true;\n")
        page = _write(workspace, "src/pages/HomePage.tsx", imports + "export default function HomePage() { return null; }\n")

        strip_forbidden_npm_imports(workspace)

        kit_text = kit.read_text(encoding="utf-8")
        page_text = page.read_text(encoding="utf-8")
        for source in (
            "clsx",
            "tailwind-merge",
            "class-variance-authority",
            "recharts",
            "@tanstack/react-table",
            "@radix-ui/react-dialog",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-tooltip",
            "motion/react",
            "lucide-react",
            "sonner",
            "date-fns",
        ):
            assert f"from '{source}'" in kit_text
            assert f"from '{source}'" not in page_text
        assert "UiHeadless" not in kit_text
        assert "UiHeadless" not in page_text


def test_forbidden_npm_imports_are_stripped_from_generated_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        mock = _write(
            workspace,
            "src/data/mock.ts",
            """import { features } from 'process';
import { helper } from '../lib/helper';
import type { Card } from '@/types';

export const brand = { name: 'Northstar' };
export const featureCards = [{ title: 'Fast' }];
""",
        )

        strip_forbidden_npm_imports(workspace)

        content = mock.read_text(encoding="utf-8")
        assert "from 'process'" not in content
        assert "from '../lib/helper'" in content
        assert "from '@/types'" in content
        assert "export const brand = { name: 'Northstar' };" in content
        assert "export const featureCards = [{ title: 'Fast' }];" in content


def test_generated_source_and_data_strip_remote_and_dynamic_import_forms() -> None:
    unsafe = """import remote from 'https://evil.invalid/module.ts';
import 'http://evil.invalid/side-effect.js';
const required = require('evil-package');
const moduleRequired = module.require('evil-package');
const dynamicLiteral = import('evil-package');
const sourceName = 'evil-package';
const dynamicVariable = import(sourceName);
import Legacy = require('evil-package');
const decoy = "require('safe-decoy')";
// import(sourceName)
"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(
            workspace,
            "src/pages/HomePage.tsx",
            unsafe + "export default function HomePage() { return <main>{decoy}</main>; }\n",
        )
        data = _write(
            workspace,
            "src/data/mock.ts",
            unsafe + "export const brand = { name: 'Northstar' };\n",
        )

        strip_forbidden_npm_imports(workspace)

        for target in (page, data):
            content = target.read_text(encoding="utf-8")
            assert "https://evil.invalid" not in content
            assert "http://evil.invalid" not in content
            assert "const required = require(" not in content
            assert "module.require(" not in content
            assert "dynamicLiteral = import(" not in content
            assert "dynamicVariable = import(" not in content
            assert "import Legacy =" not in content
            assert "\"require('safe-decoy')\"" in content
            assert "// import(sourceName)" in content
        assert "export default function HomePage" in page.read_text(encoding="utf-8")
        assert "export const brand" in data.read_text(encoding="utf-8")


def test_curated_ui_static_package_imports_remain_immutable() -> None:
    curated = """import * as React from 'react';
import { clsx } from 'clsx';
import { motion } from 'motion/react';
import { Camera } from 'lucide-react';
export const Curated = () => <motion.div className={clsx('x')}><Camera /></motion.div>;
"""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        kit = _write(workspace, "src/ui/public/Curated.tsx", curated)
        strip_forbidden_npm_imports(workspace)
        assert kit.read_text(encoding="utf-8") == curated


def test_ui_imports_normalize_to_combined_barrel_without_touching_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(
            workspace,
            "src/pages/owner/Dashboard.tsx",
            """import { Button } from '../../ui/core/Button';
import { Card } from '@/ui/core/Card';
import { brand } from '../../data/mock';
import { helper } from '../../lib/helper';

export default function Dashboard() { return <Button><Card>{brand.name}{helper()}</Card></Button>; }
""",
        )
        touched = normalize_ui_kit_imports(workspace)
        content = page.read_text(encoding="utf-8")
        assert touched == ["src/pages/owner/Dashboard.tsx"]
        assert "import { Button, Card } from '@/ui';" in content
        assert "../../data/mock" in content
        assert "../../lib/helper" in content
        assert "@/ui/core" not in content
        assert "../../ui/" not in content


def test_restore_curated_kit_replaces_and_removes_drift_safely() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        drift = _write(workspace, "src/ui/core/Button.tsx", "export const broken = true;\n")
        rogue = _write(workspace, "src/ui/Rogue.tsx", "export const rogue = true;\n")
        icons = _write(workspace, "src/components/UiIcons.tsx", "export default null;\n")
        outside = _write(workspace, "src/pages/Keep.tsx", "export default null;\n")

        restored = restore_curated_ui_kit(workspace)

        template = Path(__file__).resolve().parents[2] / "preview-template"
        assert drift.read_text(encoding="utf-8") == (
            template / "src/ui/core/Button.tsx"
        ).read_text(encoding="utf-8")
        assert icons.read_text(encoding="utf-8") == (
            template / "src/components/UiIcons.tsx"
        ).read_text(encoding="utf-8")
        assert not rogue.exists()
        assert outside.read_text(encoding="utf-8") == "export default null;\n"
        assert "src/ui/core/Button.tsx" in restored
        assert "src/components/UiIcons.tsx" in restored


def test_relevant_layout_and_component_repair_apis() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(
            workspace,
            "src/pages/HomePage.tsx",
            """import PublicLayout from '../layouts/PublicLayout';
import { Button } from '@/components/ui/Button';

export default function HomePage() {
  return <PublicLayout><Button size="xl" Icon={<span />}>Open</Button></PublicLayout>;
}
""",
        )
        assert rewrite_invented_component_imports(workspace) == ["src/pages/HomePage.tsx"]
        assert unwrap_route_layout_wrappers(workspace, "Northstar") == ["src/pages/HomePage.tsx"]
        assert sanitize_ui_component_apis(workspace) == ["src/pages/HomePage.tsx"]
        content = page.read_text(encoding="utf-8")
        assert "PublicLayout" not in content
        assert '<PublicShell brandName={"Northstar"}>' in content
        assert "import { Button, PublicShell } from '@/ui';" in content
        assert 'size="default"' in content
        assert "Icon=" not in content


def test_catalogue_fallback_uses_real_components_for_every_assigned_slot() -> None:
    route = _route()
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        write_safe_stub(
            workspace,
            route["component_file"],
            brand_name="Northstar",
            page_title="Home",
            route=route,
        )
        content = (workspace / route["component_file"]).read_text(encoding="utf-8")
        assert validate_catalogue_page_content(content, route) == []
        assert "from '@/ui'" in content
        assert "SkeletonComposer" in content
        assert "<PublicShell" in content
        for component in (
            "MarketingHero",
            "FeatureBento",
            "ProductShowcase",
            "ProcessSection",
            "TestimonialRail",
            "CTABand",
            "BrandFooter",
        ):
            assert f"<{component}" in content
        assert "<section aria-label=" not in content


def test_catalogue_contract_rejects_wrong_surface_ui_import() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    wrong_surface = valid.replace(
        "import { PublicShell,",
        "import { OpsShell, PublicShell,",
        1,
    )
    errors = validate_catalogue_page_content(wrong_surface, route)
    assert "forbidden @/ui component:OpsShell" in errors


def test_catalogue_contract_rejects_invented_ui_prop() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    with_variant = valid.replace(
        "<MarketingHero ",
        '<MarketingHero variant="split" ',
        1,
    )
    invented = with_variant.replace(
        'variant="split"',
        'variant="split" inventedProp="nope"',
        1,
    )
    errors = validate_catalogue_page_content(invented, route)
    assert "invalid prop:MarketingHero.inventedProp" in errors


def test_catalogue_contract_rejects_invalid_literal_variant() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    with_variant = valid.replace(
        "<MarketingHero ",
        '<MarketingHero variant="split" ',
        1,
    )
    invalid = with_variant.replace('variant="split"', 'variant="giant"')
    errors = validate_catalogue_page_content(invalid, route)
    assert "invalid variant:MarketingHero.variant=giant" in errors


def test_catalogue_contract_accepts_valid_page_intrinsics_and_spreads() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    valid = valid.replace(
        "const slots = {",
        "const heroProps = {};\n  const slots = {",
        1,
    ).replace(
        '<MarketingHero brandName=',
        '<MarketingHero {...heroProps} data-testid="hero" aria-label="Hero" brandName=',
        1,
    ).replace(
        "<div data-skeleton={skeleton.id}>",
        '<div id="page" data-skeleton={skeleton.id} aria-live="polite">',
        1,
    )
    assert validate_catalogue_page_content(valid, route) == []


def test_catalogue_contract_rejects_undefined_uppercase_jsx_components() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    invalid = valid.replace(
        "const SKELETON_ID",
        """const runtimeGap = <Modal><TextArea /><Toggle /></Modal>;
const nestedGap = <div>Copy <NestedUndefined /></div>;
const decoy = "<StringOnly />";
// <CommentOnly />
/* <BlockCommentOnly /> */

const SKELETON_ID""",
        1,
    )

    errors = validate_catalogue_page_content(invalid, route)

    assert "undefined JSX component:Modal" in errors
    assert "undefined JSX component:TextArea" in errors
    assert "undefined JSX component:Toggle" in errors
    assert "undefined JSX component:NestedUndefined" in errors
    assert all("StringOnly" not in error for error in errors)
    assert all("CommentOnly" not in error for error in errors)
    assert all("BlockCommentOnly" not in error for error in errors)


def test_catalogue_contract_accepts_local_jsx_component_declarations() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    with_local_helpers = valid.replace(
        "const SKELETON_ID",
        """function FunctionHelper() { return <section />; }
class ClassHelper { render() { return <aside />; } }
const ConstHelper = () => <div />;
const Helpers = { ConstHelper };
type ExternalWidget = { id: string };
const genericTypeUse = factory<ExternalWidget>();
const helperPreview = (
  <FunctionHelper>
    <ClassHelper />
    <ConstHelper />
    <Helpers.ConstHelper />
  </FunctionHelper>
);

const SKELETON_ID""",
        1,
    )

    assert validate_catalogue_page_content(with_local_helpers, route) == []


def test_catalogue_contract_accepts_jsx_bound_by_allowed_imports() -> None:
    route = _route()
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    with_allowed_imports = (
        "import * as React from 'react';\n"
        "import { Link as PageLink } from 'react-router-dom';\n"
        + valid
    ).replace(
        "const SKELETON_ID",
        """const importedPreview = (
  <React.Fragment>
    <PageLink to="/" />
  </React.Fragment>
);

const SKELETON_ID""",
        1,
    )

    assert validate_catalogue_page_content(with_allowed_imports, route) == []


def test_catalogue_guard_scaffolds_undefined_jsx_after_deep_import_is_stripped() -> None:
    route = _route()
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    valid = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    with_deep_import = (
        "import { Modal, TextArea, Toggle } from '@/ui/unsupported/deep';\n"
        + valid
    ).replace(
        "// deterministic catalogue contract scaffold",
        "// model-generated catalogue page",
        1,
    ).replace(
        "const SKELETON_ID",
        "const runtimeGap = <Modal><TextArea /><Toggle /></Modal>;\n\nconst SKELETON_ID",
        1,
    )
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(workspace, route["component_file"], with_deep_import)
        _write(workspace, "src/data/mock.ts", "export const brand = { name: 'Northstar' };\n")

        apply_workspace_guards(
            workspace,
            architect,
            {"roles": []},
            {},
            "Northstar",
            "#123456",
            "#654321",
            "Atkinson",
            JinjaTemplateRenderer(),
        )

        guarded = page.read_text(encoding="utf-8")
        assert "deterministic catalogue contract scaffold" in guarded
        assert "<Modal>" not in guarded
        assert validate_catalogue_page_content(guarded, route) == []


def test_catalogue_guard_scaffolds_invalid_assigned_page() -> None:
    route = _route()
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(
            workspace,
            route["component_file"],
            "import { Camera } from 'lucide-react';\nexport default function HomePage() { return <main />; }\n",
        )
        _write(workspace, "src/data/mock.ts", "export const brand = { name: 'Northstar' };\n")
        apply_workspace_guards(
            workspace,
            architect,
            {"roles": []},
            {},
            "Northstar",
            "#123456",
            "#654321",
            "Atkinson",
            JinjaTemplateRenderer(),
        )
        content = page.read_text(encoding="utf-8")
        assert validate_catalogue_page_content(content, route) == []
        assert "<MarketingHero" in content
        assert "lucide-react" not in content


def test_catalogue_guard_scaffolds_null_required_slot_before_build() -> None:
    route = {
        "path": "/staff",
        "component_file": "src/pages/StaffDashboardPage.tsx",
        "surface": "ops",
        "skeleton_id": "ops-dashboard",
        "section_slots": ["header", "kpis", "chart", "filters", "table", "activity"],
    }
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    scaffold = minimal_catalogue_page_scaffold(
        route["component_file"],
        route,
        brand_name="Northstar",
    )
    # Null out the filters slot regardless of the exact FilterBar props in the scaffold.
    invalid = re.sub(
        r"    filters: \(\n(?:.*\n)*?    \),",
        "    filters: null,",
        scaffold,
        count=1,
    )
    assert "filters: null" in invalid
    assert "slot:filters" in validate_catalogue_page_content(invalid, route)
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        page = _write(workspace, route["component_file"], invalid)
        _write(workspace, "src/data/mock.ts", "export const brand = { name: 'Northstar' };\n")

        apply_workspace_guards(
            workspace,
            architect,
            {"roles": []},
            {},
            "Northstar",
            "#123456",
            "#654321",
            "Atkinson",
            JinjaTemplateRenderer(),
        )

        guarded = page.read_text(encoding="utf-8")
        assert "deterministic catalogue contract scaffold" in guarded
        assert "filters: null" not in guarded
        assert validate_catalogue_page_content(guarded, route) == []


def test_catalogue_guard_fails_closed_on_unknown_skeleton_and_preserves_kit() -> None:
    route = {
        **_route(),
        "skeleton_id": "unknown-skeleton",
    }
    architect = {"_catalogue_workspace": True, "routes": [route], "roles": []}
    template = REPO_ROOT / "backend" / "preview-template"
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        _write(
            workspace,
            route["component_file"],
            "export default function HomePage() { return <main />; }\n",
        )
        _write(workspace, "src/ui/core/Button.tsx", "export const drifted = true;\n")

        try:
            apply_workspace_guards(
                workspace,
                architect,
                {},
                {},
                "Northstar",
                "#123456",
                "#654321",
                "Inter",
                JinjaTemplateRenderer(),
            )
        except RuntimeError as exc:
            assert "Catalogue contract enforcement failed" in str(exc)
            assert "Unknown UI skeleton: unknown-skeleton" in str(exc)
        else:
            raise AssertionError("Unknown catalogue skeleton must stop guard execution")

        assert (workspace / "src/ui/core/Button.tsx").read_text(encoding="utf-8") == (
            template / "src/ui/core/Button.tsx"
        ).read_text(encoding="utf-8")


def test_catalogue_fallback_typechecks_with_template() -> None:
    route = _route()
    template = REPO_ROOT / "backend" / "preview-template"
    with tempfile.TemporaryDirectory(dir=template) as tmp:
        workspace = Path(tmp)
        shutil.copytree(template / "src", workspace / "src")
        for name in ("tsconfig.json", "tsconfig.app.json", "tsconfig.node.json", "vite.config.ts"):
            shutil.copy2(template / name, workspace / name)
        write_safe_stub(
            workspace,
            route["component_file"],
            brand_name="Northstar",
            page_title="Home",
            route=route,
        )
        tsc = template / "node_modules" / ".bin" / "tsc.cmd"
        result = subprocess.run(
            [str(tsc), "-b"],
            cwd=workspace,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_generated_theme_has_complete_brand_parameterized_catalogue_tokens() -> None:
    renderer = JinjaTemplateRenderer()
    css = renderer.render(
        "codegen/index_css.j2",
        primary="#123456",
        secondary="#654321",
        font_family='"Atkinson", system-ui, sans-serif',
    )
    for token in (
        "--color-background",
        "--color-foreground",
        "--color-muted",
        "--color-card",
        "--color-border-subtle",
        "--color-brand",
        "--color-brand-dark",
        "--color-accent",
        "--color-ring",
        "--color-chart",
        "--font-sans",
        "--font-display",
        "--radius-ui",
        "--shadow-ui",
        "--glow-atmosphere",
        "--treatment-light",
    ):
        assert token in css
    assert "#123456" in css
    assert "#654321" in css
    for fixed in ("#3a342e", "#2a251f", "#8a8176", "#f4f1ec"):
        assert fixed not in css

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        index_css = _write(
            workspace,
            "src/index.css",
            '@import "tailwindcss";\n@theme { --color-brand: #123456; }\n',
        )
        assert _ensure_tailwind_css(
            workspace,
            "#123456",
            "#654321",
            "Atkinson",
        )
        guarded = index_css.read_text(encoding="utf-8")
        for token in (
            "--color-background",
            "--color-foreground",
            "--color-muted",
            "--color-card",
            "--color-border-subtle",
            "--color-accent",
            "--color-ring",
            "--color-chart",
            "--font-display",
            "--radius-ui",
            "--shadow-ui",
            "--glow-atmosphere",
            "--treatment-light",
        ):
            assert token in guarded
        assert "#654321" in guarded


def main() -> None:
    test_import_policy_is_path_scoped()
    test_forbidden_npm_imports_are_stripped_from_generated_data()
    test_generated_source_and_data_strip_remote_and_dynamic_import_forms()
    test_curated_ui_static_package_imports_remain_immutable()
    test_ui_imports_normalize_to_combined_barrel_without_touching_data()
    test_restore_curated_kit_replaces_and_removes_drift_safely()
    test_relevant_layout_and_component_repair_apis()
    test_catalogue_fallback_uses_real_components_for_every_assigned_slot()
    test_catalogue_contract_rejects_wrong_surface_ui_import()
    test_catalogue_contract_rejects_invented_ui_prop()
    test_catalogue_contract_rejects_invalid_literal_variant()
    test_catalogue_contract_accepts_valid_page_intrinsics_and_spreads()
    test_catalogue_contract_rejects_undefined_uppercase_jsx_components()
    test_catalogue_contract_accepts_local_jsx_component_declarations()
    test_catalogue_contract_accepts_jsx_bound_by_allowed_imports()
    test_catalogue_guard_scaffolds_undefined_jsx_after_deep_import_is_stripped()
    test_catalogue_guard_scaffolds_invalid_assigned_page()
    test_catalogue_guard_scaffolds_null_required_slot_before_build()
    test_catalogue_guard_fails_closed_on_unknown_skeleton_and_preserves_kit()
    test_catalogue_fallback_typechecks_with_template()
    test_generated_theme_has_complete_brand_parameterized_catalogue_tokens()


if __name__ == "__main__":
    main()
