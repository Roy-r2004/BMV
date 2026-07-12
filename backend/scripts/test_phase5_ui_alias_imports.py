from __future__ import annotations

import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.safety import normalize_ui_kit_imports


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)

        owner_page = workspace / "src" / "pages" / "owner" / "Dashboard.tsx"
        write(
            owner_page,
            """import { Button } from '../../ui/Button';
import { Card } from '../../ui/Card';
import { cn } from '../../lib/cn';

export default function Dashboard() {
  return <Button className={cn('w-full')}>Open board</Button>;
}
""",
        )

        public_layout = workspace / "src" / "layouts" / "PublicLayout.tsx"
        write(
            public_layout,
            """import { PublicShell } from '../ui/PublicShell';
import UiIcon from '../components/UiIcons';

export default function PublicLayout() {
  return <PublicShell footer={<UiIcon name="check" />} />;
}
""",
        )

        already_aliased = workspace / "src" / "pages" / "Home.tsx"
        write(
            already_aliased,
            """import { MarketingHero } from '@/ui/MarketingHero';

export default function Home() {
  return <MarketingHero title="Daily menu" />;
}
""",
        )

        touched = normalize_ui_kit_imports(workspace)

        if "src/pages/owner/Dashboard.tsx" not in touched:
            raise AssertionError("Nested owner page should be rewritten to @/ui imports")
        if "src/layouts/PublicLayout.tsx" not in touched:
            raise AssertionError("Layout ui-kit imports should be rewritten to @/ui imports")
        if "src/pages/Home.tsx" in touched:
            raise AssertionError("Already-aliased imports should not be rewritten")

        owner_text = owner_page.read_text(encoding="utf-8")
        if "from '@/ui/Button'" not in owner_text or "from '@/ui/Card'" not in owner_text:
            raise AssertionError("Nested page ui imports were not normalized to @/ui/*")
        if "from '../../lib/cn'" not in owner_text:
            raise AssertionError("Non-ui imports must remain untouched")

        layout_text = public_layout.read_text(encoding="utf-8")
        if "from '@/ui/PublicShell'" not in layout_text:
            raise AssertionError("Layout ui import was not normalized to @/ui/*")
        if "from '../components/UiIcons'" not in layout_text:
            raise AssertionError("UiIcons import must remain untouched")


if __name__ == "__main__":
    main()
