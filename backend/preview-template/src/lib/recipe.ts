import { RECIPE_ID } from './recipe-id';

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

/**
 * One distinct hero composition per recipe — do not collapse pairs.
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

export function currentRecipeId(): RecipeId {
  const fromDom =
    typeof document !== 'undefined'
      ? (document.documentElement.dataset.recipe as RecipeId | undefined)
      : undefined;
  if (fromDom && fromDom in HERO_BY_RECIPE) return fromDom;
  if (RECIPE_ID in HERO_BY_RECIPE) return RECIPE_ID as RecipeId;
  return 'warm-service';
}

export function recipeHeroVariant(recipeId: RecipeId = currentRecipeId()): HeroVariant {
  return HERO_BY_RECIPE[recipeId];
}

export function recipeFeatureVariant(recipeId: RecipeId = currentRecipeId()): FeatureVariant {
  return FEATURE_BY_RECIPE[recipeId];
}

export function recipeShellChrome(recipeId: RecipeId = currentRecipeId()): ShellChrome {
  return SHELL_BY_RECIPE[recipeId];
}

export function recipeNavVariant(recipeId: RecipeId = currentRecipeId()): NavVariant {
  return NAV_BY_RECIPE[recipeId];
}

export function recipeFooterVariant(recipeId: RecipeId = currentRecipeId()): FooterVariant {
  return FOOTER_BY_RECIPE[recipeId];
}

export function recipeBrandPlacement(recipeId: RecipeId = currentRecipeId()): BrandPlacement {
  return BRAND_BY_RECIPE[recipeId];
}

/** Display type treatment — italic for editorial/warm/nocturne/craft, upright for ops/retail. */
export function recipeDisplayClass(recipeId: RecipeId = currentRecipeId()): string {
  if (recipeId === 'dense-ops' || recipeId === 'bold-retail') {
    return 'font-display not-italic tracking-tight';
  }
  return 'font-display italic tracking-[-0.04em]';
}
