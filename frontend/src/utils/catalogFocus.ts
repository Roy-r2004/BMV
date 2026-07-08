import type { AIFeatureCatalogItem } from '../data/aiFeatureCatalog';

export type OverlayFocusTarget =
  | { type: 'section'; id: string }
  | { type: 'ai-chips' }
  | { type: 'hero-stats' }
  | { type: 'cta-primary' }
  | { type: 'cta-secondary' }
  | { type: 'hero' };

export function getCatalogFocusTarget(feature: AIFeatureCatalogItem): OverlayFocusTarget {
  const p = feature.patch;
  if (p.sections?.[0]?.id) return { type: 'section', id: p.sections[0].id };
  if (p.heroStats?.length) return { type: 'hero-stats' };
  if (p.aiChips?.length) return { type: 'ai-chips' };
  if (p.ctaPrimary) return { type: 'cta-primary' };
  if (p.ctaSecondary) return { type: 'cta-secondary' };
  return { type: 'hero' };
}

/** Ordered fallbacks — tries section first, then stats, chips, CTAs, hero */
export function getCatalogFocusTargets(feature: AIFeatureCatalogItem): OverlayFocusTarget[] {
  const p = feature.patch;
  const targets: OverlayFocusTarget[] = [];
  if (p.sections?.[0]?.id) targets.push({ type: 'section', id: p.sections[0].id });
  targets.push({ type: 'section', id: `catalog-feature-${feature.id}` });
  if (p.heroStats?.length) targets.push({ type: 'hero-stats' });
  if (p.aiChips?.length) targets.push({ type: 'ai-chips' });
  if (p.ctaPrimary) targets.push({ type: 'cta-primary' });
  if (p.ctaSecondary) targets.push({ type: 'cta-secondary' });
  targets.push({ type: 'hero' });
  return targets;
}

export function overlayFocusTargetAttr(target: OverlayFocusTarget): string {
  if (target.type === 'section') return `section-${target.id}`;
  return target.type;
}

export const DEMO_SCROLL_ROOT_ID = 'solution-live-demo';

const FLASH_CLASS = 'overlay-focus-flash';
const FLASH_MS = 2800;
const TARGET_WAIT_MS = 1200;

function findTargetElement(
  root: HTMLElement,
  candidates: OverlayFocusTarget[],
  options: { allowFallback: boolean },
): HTMLElement | null {
  for (const t of candidates) {
    const attr = overlayFocusTargetAttr(t);
    const match = root.querySelector<HTMLElement>(`[data-overlay-target="${attr}"]`);
    if (match) return match;
  }

  if (!options.allowFallback) return null;

  return (
    root.querySelector<HTMLElement>('[data-overlay-target="hero"]') ??
    root.querySelector<HTMLElement>('[data-overlay-target]')
  );
}

function findScrollableParent(el: HTMLElement): HTMLElement | null {
  let node: HTMLElement | null = el.parentElement;
  while (node) {
    const { overflowY } = getComputedStyle(node);
    if (overflowY === 'auto' || overflowY === 'scroll') return node;
    node = node.parentElement;
  }
  return null;
}

function pulseElement(el: HTMLElement) {
  el.classList.remove(FLASH_CLASS);
  void el.offsetWidth;
  el.classList.add(FLASH_CLASS);
  window.setTimeout(() => el.classList.remove(FLASH_CLASS), FLASH_MS);
}

export function scrollToOverlayTarget(
  target: OverlayFocusTarget,
  options?: { featureTitle?: string; fallbacks?: OverlayFocusTarget[] },
): boolean {
  const root = document.getElementById(DEMO_SCROLL_ROOT_ID);
  if (!root) return false;

  const candidates = [target, ...(options?.fallbacks ?? [])];
  const startedAt = performance.now();

  const focusWhenReady = () => {
    const timedOut = performance.now() - startedAt >= TARGET_WAIT_MS;
    const el = findTargetElement(root, candidates, { allowFallback: timedOut });
    if (!el) {
      if (!timedOut) {
        window.setTimeout(focusWhenReady, 80);
        return;
      }

      root.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      return;
    }

    const scrollParent = findScrollableParent(el);
    if (scrollParent) {
      const parentRect = scrollParent.getBoundingClientRect();
      const elRect = el.getBoundingClientRect();
      const offset = elRect.top - parentRect.top - Math.max(24, parentRect.height * 0.18);
      scrollParent.scrollTo({ top: scrollParent.scrollTop + offset, behavior: 'smooth' });
      root.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    pulseElement(el);

    if (options?.featureTitle) {
      const toast = document.getElementById('catalog-focus-toast');
      if (toast) {
        toast.textContent = `Showing “${options.featureTitle}” in your preview`;
        toast.classList.add('catalog-focus-toast--visible');
        window.setTimeout(() => toast.classList.remove('catalog-focus-toast--visible'), FLASH_MS);
      }
    }
  };

  window.setTimeout(focusWhenReady, 250);

  return true;
}

export function focusCatalogFeature(feature: AIFeatureCatalogItem): void {
  const targets = getCatalogFocusTargets(feature);
  scrollToOverlayTarget(targets[0], {
    featureTitle: feature.title,
    fallbacks: targets.slice(1),
  });
}
