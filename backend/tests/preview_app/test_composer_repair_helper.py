"""SkeletonComposer repair must inject into the page return, not a helper."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.application.preview_app.catalogue_contract.repair import (  # noqa: E402
    repair_skeleton_composer_invocation,
)


def test_composer_repair_skips_helper_return() -> None:
    route = {
        "path": "/",
        "title": "Home",
        "skeleton_id": "public-home",
        "surface": "public",
        "section_slots": ["hero", "features", "cta", "footer"],
    }
    # Missing SkeletonComposer; helper return sits above the page return.
    src = """
import { MarketingHero, FeatureBento, CTABand, BrandFooter, getSkeleton, PublicShell, PublicNav } from '@/ui';
import { usePublicNavItems, publicCta } from '@/lib/app-nav';
import { images, seed } from '@/data/mock';

const SKELETON_ID = "public-home" as const;
const RECIPE_ORDER = ["hero", "features", "cta", "footer"] as const;

function icon() {
  return (
    <span>x</span>
  );
}

export default function HomePage() {
  const navItems = usePublicNavItems();
  const navCta = publicCta();
  const skeleton = getSkeleton(SKELETON_ID);
  const slots = {
    hero: <MarketingHero brandName="Acme" headline="Hi" />,
    features: <FeatureBento title="Features" items={[]} />,
    cta: <CTABand title="Go" />,
    footer: <BrandFooter brandName="Acme" />,
  };
  return (
    <PublicShell brandName="Acme" nav={<PublicNav items={navItems} cta={navCta} />}>
      <div data-skeleton={skeleton.id}>
        {icon()}
      </div>
    </PublicShell>
  );
}
"""
    out, healed = repair_skeleton_composer_invocation(src, route)
    assert healed, "expected composer heal"
    helper_idx = out.index("function icon")
    export_idx = out.index("export default function HomePage")
    composer_idx = out.index("<SkeletonComposer")
    assert helper_idx < export_idx < composer_idx, (
        "SkeletonComposer must land in the default-export return, not the helper"
    )
    # Old bug used str.replace(..., 1) on the first return ( — prove we didn't.
    helper_return_region = out[helper_idx:export_idx]
    assert "<SkeletonComposer" not in helper_return_region


def main() -> None:
    test_composer_repair_skips_helper_return()
    print("OK: composer repair helper-skip test passed")


if __name__ == "__main__":
    main()
