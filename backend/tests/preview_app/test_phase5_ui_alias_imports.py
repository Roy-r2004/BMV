"""Phase 5: relative/deep UI kit imports must normalize to the `@/ui` barrel."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.application.preview_app.safety.imports import normalize_ui_kit_imports


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_page(workspace: Path, stem: str) -> str:
    """Read a page after `write_file` may have canonicalized `Foo.tsx` → `FooPage.tsx`."""
    matches = sorted(workspace.rglob(f"{stem}.tsx")) + sorted(
        workspace.rglob(f"{stem}Page.tsx")
    )
    assert matches, f"expected a {stem} page under {workspace}"
    return matches[0].read_text(encoding="utf-8")


def test_normalize_ui_kit_imports_rewrites_relative_and_deep_paths() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)

        _write(
            workspace / "src" / "pages" / "owner" / "Dashboard.tsx",
            """import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { cn } from '../../lib/cn';

export default function Dashboard() {
  return <Button className={cn('w-full')}>Open board</Button>;
}
""",
        )

        _write(
            workspace / "src" / "layouts" / "PublicLayout.tsx",
            """import { PublicShell } from '../ui/PublicShell';
import UiIcon from '../components/UiIcons';

export default function PublicLayout() {
  return <PublicShell footer={<UiIcon name="check" />} />;
}
""",
        )

        _write(
            workspace / "src" / "pages" / "Home.tsx",
            """import { MarketingHero } from '@/ui/MarketingHero';

export default function Home() {
  return <MarketingHero title="Daily menu" />;
}
""",
        )

        _write(
            workspace / "src" / "pages" / "Complex.tsx",
            """import DefaultButton, {
  type ButtonProps,
  Button as NamedButton,
} from '../ui/core/Button';
import type {
  MarketingHeroProps as HeroProps,
} from '@/ui/public/MarketingHero';
import * as DeepCard from '@/ui/core/Card';
import UnknownDefault from '@/ui/made-up/UnknownDefault';
import * as Ui from '@/ui';
import * as RelativeUi from '../ui';
import { brand as brandAlias } from '@/data/mock';
import helperAlias from '@/lib/helper';

export const aliases = { Ui, RelativeUi, brandAlias, helperAlias };
""",
        )

        touched = normalize_ui_kit_imports(workspace)

        assert "src/pages/owner/Dashboard.tsx" in touched, (
            "Nested owner page should be rewritten to @/ui imports"
        )
        assert "src/layouts/PublicLayout.tsx" in touched, (
            "Layout ui-kit imports should be rewritten to @/ui imports"
        )
        assert "src/pages/Home.tsx" in touched, (
            "Deep aliased imports should be collapsed to the barrel"
        )
        assert "src/pages/Complex.tsx" in touched, (
            "Mixed multiline UI imports should be normalized"
        )

        # `write_file` now canonicalizes `Dashboard.tsx` → `DashboardPage.tsx`
        # (and Home/Complex likewise). Content contracts below still apply to
        # whatever path the rewrite landed on.
        owner_text = _read_page(workspace, "Dashboard")
        assert "import { Button, Card } from '@/ui';" in owner_text, (
            "Nested page ui imports were not combined at the @/ui barrel"
        )
        assert "from '../../lib/cn'" in owner_text, (
            "Non-ui imports must remain untouched"
        )

        layout_text = (workspace / "src" / "layouts" / "PublicLayout.tsx").read_text(
            encoding="utf-8"
        )
        assert "from '@/ui'" in layout_text and "PublicShell" in layout_text, (
            "Layout ui import was not normalized to the @/ui barrel"
        )
        assert "from '../components/UiIcons'" in layout_text, (
            "UiIcons import must remain untouched"
        )

        home_text = _read_page(workspace, "Home")
        assert "import { MarketingHero } from '@/ui';" in home_text, (
            "Deep @/ui import was not collapsed to the public barrel"
        )

        complex_text = _read_page(workspace, "Complex")
        assert "Button as DefaultButton" in complex_text, (
            "Representable deep default import was not converted to a named barrel alias"
        )
        assert "Button as NamedButton" in complex_text, (
            "Named alias was not preserved"
        )
        assert (
            "import type { ButtonProps, MarketingHeroProps as HeroProps } from '@/ui';"
            in complex_text
        ), "Type-only and inline type imports were not preserved"
        assert "import * as Ui from '@/ui';" in complex_text, (
            "Valid barrel namespace import must remain intact"
        )
        assert "import * as RelativeUi from '@/ui';" in complex_text, (
            "Relative barrel namespace import should normalize safely"
        )
        assert "DeepCard from" not in complex_text and "UnknownDefault from" not in complex_text, (
            "Unsupported deep namespace/default imports must be removed"
        )
        assert "@/ui/" not in complex_text and "../ui/" not in complex_text, (
            "No deep or relative UI import path may remain"
        )
        assert (
            "brand as brandAlias" in complex_text
            and "helperAlias from '@/lib/helper'" in complex_text
        ), "Non-UI aliases must remain untouched"


@pytest.mark.xfail(
    reason=(
        "stale harness path: write_file canonicalizes Dashboard.tsx→DashboardPage.tsx "
        "so the original Path handle is gone after normalize_ui_kit_imports; "
        "the content contracts still hold on the canonical path "
        "(see test_normalize_ui_kit_imports_rewrites_relative_and_deep_paths). "
        "Kept as a loud marker that the pre-canonicalize Path assumption is dead."
    ),
    strict=True,
)
def test_normalize_leaves_original_page_path_readable() -> None:
    """Original script held Path objects across write_file's rename.

    This is the exact failure the uncollected script would hit if run today.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        owner_page = workspace / "src" / "pages" / "owner" / "Dashboard.tsx"
        _write(
            owner_page,
            """import { Button } from '../../ui/Button';
export default function Dashboard() { return <Button />; }
""",
        )
        normalize_ui_kit_imports(workspace)
        # Intentionally read the pre-canonicalize path — must fail until
        # normalize/write_file stops renaming out from under callers, or the
        # touched list reports the post-canonicalize path and callers update.
        assert owner_page.is_file(), (
            "write_file renamed Dashboard.tsx out from under the caller Path"
        )
