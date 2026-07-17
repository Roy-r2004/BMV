from __future__ import annotations

import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.application.preview_app.safety.imports import normalize_ui_kit_imports


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

        complex_imports = workspace / "src" / "pages" / "Complex.tsx"
        write(
            complex_imports,
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

        if "src/pages/owner/Dashboard.tsx" not in touched:
            raise AssertionError("Nested owner page should be rewritten to @/ui imports")
        if "src/layouts/PublicLayout.tsx" not in touched:
            raise AssertionError("Layout ui-kit imports should be rewritten to @/ui imports")
        if "src/pages/Home.tsx" not in touched:
            raise AssertionError("Deep aliased imports should be collapsed to the barrel")
        if "src/pages/Complex.tsx" not in touched:
            raise AssertionError("Mixed multiline UI imports should be normalized")

        owner_text = owner_page.read_text(encoding="utf-8")
        if "import { Button, Card } from '@/ui';" not in owner_text:
            raise AssertionError("Nested page ui imports were not combined at the @/ui barrel")
        if "from '../../lib/cn'" not in owner_text:
            raise AssertionError("Non-ui imports must remain untouched")

        layout_text = public_layout.read_text(encoding="utf-8")
        if "from '@/ui'" not in layout_text or "PublicShell" not in layout_text:
            raise AssertionError("Layout ui import was not normalized to the @/ui barrel")
        if "from '../components/UiIcons'" not in layout_text:
            raise AssertionError("UiIcons import must remain untouched")

        home_text = already_aliased.read_text(encoding="utf-8")
        if "import { MarketingHero } from '@/ui';" not in home_text:
            raise AssertionError("Deep @/ui import was not collapsed to the public barrel")

        complex_text = complex_imports.read_text(encoding="utf-8")
        if "Button as DefaultButton" not in complex_text:
            raise AssertionError("Representable deep default import was not converted to a named barrel alias")
        if "Button as NamedButton" not in complex_text:
            raise AssertionError("Named alias was not preserved")
        if "import type { ButtonProps, MarketingHeroProps as HeroProps } from '@/ui';" not in complex_text:
            raise AssertionError("Type-only and inline type imports were not preserved")
        if "import * as Ui from '@/ui';" not in complex_text:
            raise AssertionError("Valid barrel namespace import must remain intact")
        if "import * as RelativeUi from '@/ui';" not in complex_text:
            raise AssertionError("Relative barrel namespace import should normalize safely")
        if "DeepCard from" in complex_text or "UnknownDefault from" in complex_text:
            raise AssertionError("Unsupported deep namespace/default imports must be removed")
        if "@/ui/" in complex_text or "../ui/" in complex_text:
            raise AssertionError("No deep or relative UI import path may remain")
        if "brand as brandAlias" not in complex_text or "helperAlias from '@/lib/helper'" not in complex_text:
            raise AssertionError("Non-UI aliases must remain untouched")


if __name__ == "__main__":
    main()
