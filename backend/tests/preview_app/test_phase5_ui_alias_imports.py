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

        # Canonical paths, because that is what was written. These used to name
        # the pre-canonicalize files — `Dashboard.tsx`, `Home.tsx`,
        # `Complex.tsx` — none of which exist once the pass has run, and that
        # was the whole content of the `write_file canonicalization` xfail. See
        # `test_normalize_reports_the_path_it_actually_wrote`.
        assert "src/pages/owner/DashboardPage.tsx" in touched, (
            "Nested owner page should be rewritten to @/ui imports"
        )
        assert "src/layouts/PublicLayout.tsx" in touched, (
            "Layout ui-kit imports should be rewritten to @/ui imports"
        )
        assert "src/pages/HomePage.tsx" in touched, (
            "Deep aliased imports should be collapsed to the barrel"
        )
        assert "src/pages/ComplexPage.tsx" in touched, (
            "Mixed multiline UI imports should be normalized"
        )
        for rel in touched:
            assert (workspace / rel).is_file(), f"reported {rel}, which is not on disk"

        # Content contracts below apply to whatever path the rewrite landed on.
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


def test_normalize_reports_the_path_it_actually_wrote() -> None:
    """Resolved the `write_file canonicalization` xfail. The rename stays.

    The xfail offered two ways out: stop `write_file` renaming out from under
    callers, or make the touched list report the post-canonicalize path. The
    rename is not optional — `write_trusted_contained_file` deletes the
    pre-canonical file on purpose, because leaving both means the import guards
    go on to "fix" a duplicate copy of the page and Vite bundles two of them on a
    case-sensitive filesystem. So: the reporting was wrong, not the rename.

    `write_file` now returns the path it wrote and the callers record that.
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
        touched = normalize_ui_kit_imports(workspace)

        assert touched == ["src/pages/owner/DashboardPage.tsx"]
        for rel in touched:
            assert (workspace / rel).is_file(), f"reported {rel}, which is not on disk"
        # The rename itself is pinned, so "fixing" this by keeping both files
        # fails here rather than silently reintroducing the duplicate page.
        assert not owner_page.is_file()
        assert "from '@/ui'" in (workspace / touched[0]).read_text()


def test_write_file_returns_the_canonical_path_for_every_shape() -> None:
    """The seam, not just the one caller that tripped over it."""
    from app.application.preview_app.workspace import write_file

    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        cases = {
            # renamed: not already `*Page.tsx`
            "src/pages/owner/Dashboard.tsx": "src/pages/owner/DashboardPage.tsx",
            # already canonical: unchanged
            "src/pages/HomePage.tsx": "src/pages/HomePage.tsx",
            # not a page: only lexically normalized
            "src/components/Nav.tsx": "src/components/Nav.tsx",
            "src/./components/Card.tsx": "src/components/Card.tsx",
        }
        for given, expected in cases.items():
            written = write_file(workspace, given, "export default function X() {}\n")
            assert written == expected, given
            assert (workspace / written).is_file(), written


def test_no_safety_pass_reports_a_path_it_renamed_away() -> None:
    """A guard for the class, since two passes had this bug and both were silent.

    `normalize_ui_kit_imports` and `strip_forbidden_npm_imports` both returned
    the pre-canonicalize path. Nothing failed, because those lists are only
    logged today — which is precisely why the next caller to trust one would
    have found out the hard way.
    """
    from app.application.preview_app import safety
    from app.application.preview_app.workspace import list_source_files

    source = (
        "import React from 'react';\n"
        "import { Button } from '../../ui/Button';\n"
        "import { Dialog } from '@headlessui/react';\n"
        "export default function Dashboard() { return <div><Button /><Dialog /></div>; }\n"
    )
    passes = [
        name
        for name in ("normalize_ui_kit_imports", "strip_forbidden_npm_imports")
        if getattr(safety, name, None)
    ]
    assert passes, "safety no longer exports the passes this guard covers"

    for name in passes:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            _write(workspace / "src" / "pages" / "owner" / "Dashboard.tsx", source)
            reported = getattr(safety, name)(workspace) or []
            on_disk = set(list_source_files(workspace))
            stale = [
                entry
                for entry in reported
                if "/" in str(entry) and str(entry) not in on_disk
            ]
            assert not stale, f"{name} reported {stale}; disk has {sorted(on_disk)}"
