import { RECIPE_ID } from './recipe-id';
import { SITE_DESIGN } from './site-design';

export type RecipeId =
  | 'editorial'
  | 'dense-ops'
  | 'warm-service'
  | 'bold-retail'
  | 'nocturne'
  | 'craft';

/** Distinct hero compositions — not just color variants of one layout. */
export type HeroVariant =
  | 'cinematic'
  | 'service'
  | 'compact'
  | 'product'
  | 'editorial'
  | 'atelier';
export type FeatureVariant = 'bento' | 'grid' | 'alternating';
export type ShellChrome = 'solid' | 'immersive';
export type NavVariant = 'default' | 'minimal' | 'stacked';
export type FooterVariant = 'statement' | 'compact' | 'columns';
export type BrandPlacement = 'start' | 'center';

export const HERO_VARIANTS: readonly HeroVariant[] = [
  'cinematic',
  'service',
  'compact',
  'product',
  'editorial',
  'atelier',
];
export const FEATURE_VARIANTS: readonly FeatureVariant[] = ['bento', 'grid', 'alternating'];
const SHELL_CHROMES: readonly ShellChrome[] = ['solid', 'immersive'];
const NAV_VARIANTS: readonly NavVariant[] = ['default', 'minimal', 'stacked'];
const FOOTER_VARIANTS: readonly FooterVariant[] = ['statement', 'compact', 'columns'];
const BRAND_PLACEMENTS: readonly BrandPlacement[] = ['start', 'center'];

/**
 * One distinct hero composition per recipe — do not collapse pairs.
 * Since Stage A (3.1) these maps are the DEFAULTS: the rendered value comes
 * from SiteSpec.design (`SITE_DESIGN`, resolved once in Python); the map
 * answers only when the design carries no valid value for this recipe.
 * Must stay 1:1 with backend design_recipes.py hero_variant values.
 */
const HERO_BY_RECIPE: Record<RecipeId, HeroVariant> = {
  editorial: 'editorial',
  'dense-ops': 'compact',
  'warm-service': 'service',
  'bold-retail': 'product',
  nocturne: 'cinematic',
  craft: 'atelier',
};

/** Must stay 1:1 with backend design_recipes.py feature_variant values. */
const FEATURE_BY_RECIPE: Record<RecipeId, FeatureVariant> = {
  editorial: 'alternating',
  'dense-ops': 'grid',
  'warm-service': 'bento',
  'bold-retail': 'bento',
  nocturne: 'alternating',
  craft: 'alternating',
};

const SHELL_BY_RECIPE: Record<RecipeId, ShellChrome> = {
  editorial: 'immersive',
  'dense-ops': 'solid',
  'warm-service': 'immersive',
  'bold-retail': 'immersive',
  nocturne: 'immersive',
  craft: 'immersive',
};

const NAV_BY_RECIPE: Record<RecipeId, NavVariant> = {
  editorial: 'default',
  'dense-ops': 'minimal',
  'warm-service': 'default',
  'bold-retail': 'minimal',
  nocturne: 'stacked',
  craft: 'default',
};

const FOOTER_BY_RECIPE: Record<RecipeId, FooterVariant> = {
  editorial: 'statement',
  'dense-ops': 'compact',
  'warm-service': 'compact',
  'bold-retail': 'statement',
  nocturne: 'statement',
  craft: 'columns',
};

const BRAND_BY_RECIPE: Record<RecipeId, BrandPlacement> = {
  editorial: 'center',
  'dense-ops': 'start',
  'warm-service': 'start',
  'bold-retail': 'start',
  nocturne: 'start',
  craft: 'start',
};

/**
 * Backend seals overlay-qualified ids (e.g. dense-ops-ledger). Kit maps by family only.
 * Without this, unknown ids silently fall through to warm-service hero/chrome.
 */
export function normalizeRecipeId(raw: string | null | undefined): RecipeId {
  const value = String(raw ?? '').trim();
  if (value && value in HERO_BY_RECIPE) return value as RecipeId;
  const families = Object.keys(HERO_BY_RECIPE) as RecipeId[];
  const hit = families
    .filter((family) => value === family || value.startsWith(`${family}-`))
    .sort((a, b) => b.length - a.length)[0];
  return hit ?? 'warm-service';
}

export function currentRecipeId(): RecipeId {
  const fromDom =
    typeof document !== 'undefined' ? document.documentElement.dataset.recipe : undefined;
  if (fromDom) return normalizeRecipeId(fromDom);
  return normalizeRecipeId(RECIPE_ID);
}

/**
 * SITE_DESIGN speaks for exactly one site — the one whose recipe it was
 * resolved for. It answers only when asked about that recipe (family match),
 * only with a value from the axis's declared valid set; anything else falls
 * back to the map default. Runtime-guarded because the emitted design is
 * data, not types.
 */
function designVariant<T extends string>(
  value: string | null | undefined,
  valid: readonly T[],
  recipeId: RecipeId
): T | null {
  if (normalizeRecipeId(SITE_DESIGN.recipe_id) !== recipeId) return null;
  return value != null && (valid as readonly string[]).includes(value) ? (value as T) : null;
}

export function recipeHeroVariant(recipeId: RecipeId = currentRecipeId()): HeroVariant {
  return designVariant(SITE_DESIGN.variants.hero, HERO_VARIANTS, recipeId) ?? HERO_BY_RECIPE[recipeId];
}

export function recipeFeatureVariant(recipeId: RecipeId = currentRecipeId()): FeatureVariant {
  return (
    designVariant(SITE_DESIGN.variants.feature, FEATURE_VARIANTS, recipeId) ??
    FEATURE_BY_RECIPE[recipeId]
  );
}

export function recipeShellChrome(recipeId: RecipeId = currentRecipeId()): ShellChrome {
  return designVariant(SITE_DESIGN.variants.shell, SHELL_CHROMES, recipeId) ?? SHELL_BY_RECIPE[recipeId];
}

export function recipeNavVariant(recipeId: RecipeId = currentRecipeId()): NavVariant {
  return designVariant(SITE_DESIGN.variants.nav, NAV_VARIANTS, recipeId) ?? NAV_BY_RECIPE[recipeId];
}

export function recipeFooterVariant(recipeId: RecipeId = currentRecipeId()): FooterVariant {
  return (
    designVariant(SITE_DESIGN.variants.footer, FOOTER_VARIANTS, recipeId) ??
    FOOTER_BY_RECIPE[recipeId]
  );
}

export function recipeBrandPlacement(recipeId: RecipeId = currentRecipeId()): BrandPlacement {
  return (
    designVariant(SITE_DESIGN.variants.brand_placement, BRAND_PLACEMENTS, recipeId) ??
    BRAND_BY_RECIPE[recipeId]
  );
}

/** Display type treatment — italic for editorial/warm/nocturne/craft, upright for ops/retail. */
export function recipeDisplayClass(recipeId: RecipeId = currentRecipeId()): string {
  if (recipeId === 'dense-ops' || recipeId === 'bold-retail') {
    return 'font-display not-italic tracking-tight';
  }
  return 'font-display italic tracking-[-0.04em]';
}
