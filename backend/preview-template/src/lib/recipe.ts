import { RECIPE_ID } from './recipe-id';

export type RecipeId =
  | 'editorial'
  | 'dense-ops'
  | 'warm-service'
  | 'bold-retail'
  | 'nocturne'
  | 'craft';

/** Distinct hero compositions — not just color variants of one layout. */
export type HeroVariant = 'cinematic' | 'service' | 'compact' | 'product' | 'editorial';
export type FeatureVariant = 'bento' | 'grid' | 'alternating';

/** One distinct hero composition per recipe — do not collapse pairs. */
const HERO_BY_RECIPE: Record<RecipeId, HeroVariant> = {
  editorial: 'editorial',
  'dense-ops': 'compact',
  'warm-service': 'service',
  'bold-retail': 'product',
  nocturne: 'cinematic',
  craft: 'service',
};

const FEATURE_BY_RECIPE: Record<RecipeId, FeatureVariant> = {
  editorial: 'alternating',
  'dense-ops': 'grid',
  'warm-service': 'bento',
  'bold-retail': 'grid',
  nocturne: 'alternating',
  craft: 'bento',
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

/** Display type treatment — italic for editorial/warm/nocturne/craft, upright for ops/retail. */
export function recipeDisplayClass(recipeId: RecipeId = currentRecipeId()): string {
  if (recipeId === 'dense-ops' || recipeId === 'bold-retail') {
    return 'font-display not-italic tracking-tight';
  }
  return 'font-display italic tracking-[-0.04em]';
}
