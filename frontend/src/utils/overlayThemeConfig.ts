/** Per-industry CSS selectors for live color theming from user overlay */
export interface OverlayThemeSelectors {
  scope: string;
  primaryButtons: string[];
  accentText: string[];
  navCta?: string[];
  siteBackground?: string;
}

export const OVERLAY_THEME_SELECTORS: Record<string, OverlayThemeSelectors> = {
  healthcare: {
    scope: '.sol-detail-demo__showcase--healthcare',
    primaryButtons: ['.hc-site__btn--primary', '.hc-site__nav-cta'],
    accentText: ['.hc-site__hero-title span', '.hc-site__eyebrow'],
    siteBackground: '.hc-site',
  },
  'personal-care': {
    scope: '.sol-detail-demo__showcase--personal-care',
    primaryButtons: ['.sn-shop__btn--gold', '.sn-shop__nav-cta'],
    accentText: ['.sn-shop__hero-title span', '.sn-shop__eyebrow'],
    siteBackground: '.sn-shop',
  },
  food: {
    scope: '.sol-detail-demo__showcase--food',
    primaryButtons: ['.eo-guest__btn--primary'],
    accentText: ['.eo-guest__hero-title span'],
    siteBackground: '.eo-guest',
  },
  'real-estate': {
    scope: '.sol-detail-demo__showcase--real-estate',
    primaryButtons: ['.nr-site__btn--primary', '.nr-site__nav-cta'],
    accentText: ['.nr-site__hero-title span', '.nr-site__hero-eyebrow'],
    siteBackground: '.nr-site',
  },
  fitness: {
    scope: '.sol-detail-demo__showcase--fitness',
    primaryButtons: ['.pf-site__btn--primary'],
    accentText: ['.pf-site__hero-title span'],
    siteBackground: '.pf-site',
  },
  'professional-services': {
    scope: '.sol-detail-demo__showcase--professional-services',
    primaryButtons: ['.ax-site__btn--gold', '.ax-site__btn--primary'],
    accentText: ['.ax-counsel-hero h1 em', '.ax-counsel-hero__eyebrow'],
    siteBackground: '.ax-site',
  },
  ecommerce: {
    scope: '.sol-detail-demo__showcase--ecommerce',
    primaryButtons: ['.lh-shop__btn--primary', '.lh-shop__search button'],
    accentText: ['.lh-shop__hero-copy h1 em', '.lh-shop__hero-eyebrow'],
    siteBackground: '.lh-shop',
  },
  'home-services': {
    scope: '.sol-detail-demo__showcase--home-services',
    primaryButtons: ['.bf-site__btn--primary'],
    accentText: ['.bf-site__brand-mark'],
    siteBackground: '.bf-site',
  },
  education: {
    scope: '.sol-detail-demo__showcase--education',
    primaryButtons: ['.sm-site__btn--primary'],
    accentText: ['.sm-site__hero-brand'],
    siteBackground: '.sm-site',
  },
  automotive: {
    scope: '.sol-detail-demo__showcase--automotive',
    primaryButtons: ['.mt-site__btn--primary'],
    accentText: ['.mt-site__brand-mark'],
    siteBackground: '.mt-site',
  },
  hospitality: {
    scope: '.sol-detail-demo__showcase--hospitality',
    primaryButtons: ['.rh-guest__btn--primary', '.rh-guest__btn--gold'],
    accentText: ['.rh-guest__hero-title span'],
    siteBackground: '.rh-guest',
  },
  nonprofit: {
    scope: '.sol-detail-demo__showcase--nonprofit',
    primaryButtons: ['.hg-site__btn--primary'],
    accentText: ['.hg-site__hero-brand'],
    siteBackground: '.hg-site',
  },
};

export function buildOverlayThemeCss(
  solutionId: string,
  colors: {
    primary?: string;
    secondary?: string;
    background?: string;
    accent?: string;
  },
): string {
  const cfg = OVERLAY_THEME_SELECTORS[solutionId];
  if (!cfg) return '';

  const lines: string[] = [];
  const { scope } = cfg;

  if (colors.primary) {
    for (const sel of cfg.primaryButtons) {
      lines.push(
        `${scope} ${sel} { background: ${colors.primary} !important; border-color: ${colors.primary} !important; }`,
      );
    }
  }

  if (colors.secondary) {
    for (const sel of cfg.accentText) {
      lines.push(`${scope} ${sel} { color: ${colors.secondary} !important; }`);
    }
    if (cfg.navCta) {
      for (const sel of cfg.navCta) {
        lines.push(`${scope} ${sel} { color: ${colors.secondary} !important; }`);
      }
    }
  }

  if (colors.accent) {
    lines.push(`${scope} .overlay-custom-section { border-color: ${colors.accent}40 !important; }`);
    lines.push(`${scope} .overlay-custom-section__cta { background: ${colors.accent} !important; }`);
  }

  if (colors.background && cfg.siteBackground) {
    lines.push(`${scope} ${cfg.siteBackground} { background-color: ${colors.background} !important; }`);
  }

  return lines.join('\n');
}
