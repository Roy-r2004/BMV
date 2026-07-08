import type { SolutionShowcase } from '../data/showcaseDemos';
import type { SolutionOverlay } from '../types/auth';

export function hasOverlayCustomizations(overlay: SolutionOverlay): boolean {
  return Object.keys(overlay).some((k) => {
    const v = overlay[k as keyof SolutionOverlay];
    if (Array.isArray(v)) return v.length > 0;
    return v != null && v !== '';
  });
}

export function mergeShowcaseWithOverlay(
  base: SolutionShowcase,
  overlay: SolutionOverlay,
): SolutionShowcase {
  if (!hasOverlayCustomizations(overlay)) return base;

  const demo = {
    ...base.demo,
    visual_theme: { ...base.demo.visual_theme },
    hero: { ...base.demo.hero },
  };

  if (overlay.productName) demo.product_name = overlay.productName;
  if (overlay.heroHeadline) demo.hero.headline = overlay.heroHeadline;
  if (overlay.heroSub) demo.hero.subheadline = overlay.heroSub;
  if (overlay.primaryColor) demo.visual_theme.primary_color = overlay.primaryColor;
  if (overlay.secondaryColor) demo.visual_theme.secondary_color = overlay.secondaryColor;
  if (overlay.backgroundColor) demo.visual_theme.background_color = overlay.backgroundColor;

  if (overlay.tagline && demo.preview_content?.website) {
    demo.preview_content = {
      ...demo.preview_content,
      website: { ...demo.preview_content.website, eyebrow: overlay.tagline },
    };
  }

  if (overlay.aiChips?.length && demo.preview_content?.website) {
    demo.preview_content = {
      ...demo.preview_content,
      website: { ...demo.preview_content.website, ai_chips: overlay.aiChips },
    };
  }

  return {
    ...base,
    businessName: overlay.businessName ?? base.businessName,
    demo,
  };
}
