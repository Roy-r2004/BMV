import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { OverlaySection, OverlayStat, SolutionOverlay } from '../types/auth';

export interface ShowcaseOverlayValue {
  overlay: SolutionOverlay;
  solutionId?: string;
  displayBusinessName: string;
  heroHeadline?: string;
  heroSub?: string;
  tagline?: string;
  businessName?: string;
  productName?: string;
  primaryColor?: string;
  secondaryColor?: string;
  backgroundColor?: string;
  accentColor?: string;
  ctaPrimary?: string;
  ctaSecondary?: string;
  aiChips?: string[];
  heroStats?: OverlayStat[];
  sections?: OverlaySection[];
}

const ShowcaseOverlayContext = createContext<ShowcaseOverlayValue | null>(null);

interface ProviderProps {
  overlay?: SolutionOverlay;
  solutionId?: string;
  defaultBusinessName: string;
  children: ReactNode;
}

export function ShowcaseOverlayProvider({ overlay = {}, solutionId, defaultBusinessName, children }: ProviderProps) {
  const value = useMemo<ShowcaseOverlayValue>(
    () => ({
      overlay,
      solutionId,
      displayBusinessName: overlay.businessName ?? defaultBusinessName,
      heroHeadline: overlay.heroHeadline,
      heroSub: overlay.heroSub,
      tagline: overlay.tagline,
      businessName: overlay.businessName,
      productName: overlay.productName,
      primaryColor: overlay.primaryColor,
      secondaryColor: overlay.secondaryColor,
      backgroundColor: overlay.backgroundColor,
      accentColor: overlay.accentColor,
      ctaPrimary: overlay.ctaPrimary,
      ctaSecondary: overlay.ctaSecondary,
      aiChips: overlay.aiChips,
      heroStats: overlay.heroStats,
      sections: overlay.sections,
    }),
    [overlay, solutionId, defaultBusinessName],
  );

  return <ShowcaseOverlayContext.Provider value={value}>{children}</ShowcaseOverlayContext.Provider>;
}

export function useShowcaseOverlay(): ShowcaseOverlayValue {
  const ctx = useContext(ShowcaseOverlayContext);
  if (!ctx) {
    return {
      overlay: {},
      displayBusinessName: '',
    };
  }
  return ctx;
}

/** Brand shown in nav, footer, frame chrome */
export function useOverlayBrand(defaultName: string): string {
  const { businessName, productName } = useShowcaseOverlay();
  return businessName ?? productName ?? defaultName;
}

/** Short product label in demo title bars */
export function useOverlayProduct(defaultProduct: string): string {
  const { productName, businessName } = useShowcaseOverlay();
  return productName ?? businessName ?? defaultProduct;
}

export function resolveHeroLines(
  overlayHeadline: string | undefined,
  defaultPrimary: string,
  defaultAccent?: string,
): { primary: string; accent?: string } {
  if (!overlayHeadline?.trim()) {
    return { primary: defaultPrimary, accent: defaultAccent };
  }
  const text = overlayHeadline.trim();
  if (text.includes('\n')) {
    const parts = text.split('\n').map((s) => s.trim()).filter(Boolean);
    return { primary: parts[0], accent: parts.slice(1).join(' ') || undefined };
  }
  return { primary: text, accent: undefined };
}

export function resolveHeroSub(overlaySub: string | undefined, defaultSub: string): string {
  return overlaySub?.trim() || defaultSub;
}

export function resolveTagline(overlayTagline: string | undefined, defaultTagline: string): string {
  return overlayTagline?.trim() || defaultTagline;
}

export function useOverlayCta(defaultPrimary: string, defaultSecondary?: string) {
  const { ctaPrimary, ctaSecondary } = useShowcaseOverlay();
  return {
    primary: ctaPrimary?.trim() || defaultPrimary,
    secondary: ctaSecondary?.trim() || defaultSecondary,
  };
}
