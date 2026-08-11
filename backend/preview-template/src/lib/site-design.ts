/** SiteSpec.design — resolved once in Python (site_design.py). Overwritten per preview by write_index_css. */
export interface SiteDesign {
  version: string;
  recipe_id: string;
  palette: { primary: string; secondary: string };
  typography: {
    font_family: string;
    font_sans: string;
    font_display: string;
    font_import: string;
  };
  tokens: {
    radius_ui: string;
    bg_mix: string;
    fg_mix: string;
    muted_mix: string;
    border_mix: string;
    shadow: string;
    shadow_alpha: string;
    glow: string;
    card: string;
    atmosphere: string;
  };
  variants: {
    hero: string | null;
    feature: string | null;
    shell: string | null;
    nav: string | null;
    footer: string | null;
    brand_placement: string | null;
  };
  density: string | null;
  type_ramp: { source: string; steps: null };
  spacing: {
    section_x: string;
    section_x_lg: string;
    section_y: string;
    section_y_lg: string;
  };
  container: { max: string };
  grid: { catalog_archetype: string };
  image_treatment: { policy: string };
  motion: {
    identity: string;
    ease: number[] | null;
    stagger_ms: number | null;
    travel: string | null;
    reveal: string | null;
  };
}

export const SITE_DESIGN: SiteDesign = {
  "version": "1.1",
  "recipe_id": "warm-service",
  "palette": {
    "primary": "#6366f1",
    "secondary": "#6366f1"
  },
  "typography": {
    "font_family": "\"Inter\", system-ui, sans-serif",
    "font_sans": "\"Nunito Sans\", \"Segoe UI\", sans-serif",
    "font_display": "\"Libre Baskerville\", Georgia, serif",
    "font_import": "@import url(\"https://fonts.googleapis.com/css2?family=Libre+Baskerville:ital,wght@0,400;0,700;1,400&family=Nunito+Sans:wght@400;500;600;700&display=swap\");"
  },
  "tokens": {
    "radius_ui": "1.05rem",
    "bg_mix": "6%",
    "fg_mix": "36%",
    "muted_mix": "30%",
    "border_mix": "15%",
    "shadow": "0 28px 52px -32px",
    "shadow_alpha": "36%",
    "glow": "16%",
    "card": "#fffaf5",
    "atmosphere": "radial-gradient(95% 70% at 95% 0%, color-mix(in srgb, var(--color-brand) 18%, transparent), transparent 55%), radial-gradient(60% 45% at 5% 30%, color-mix(in srgb, var(--color-accent) 10%, transparent), transparent 50%), linear-gradient(180deg, #fff7ef, transparent 40%)"
  },
  "variants": {
    "hero": "service",
    "feature": "bento",
    "shell": "immersive",
    "nav": "default",
    "footer": "compact",
    "brand_placement": "start"
  },
  "density": null,
  "type_ramp": {
    "source": "tailwind-default",
    "steps": null
  },
  "spacing": {
    "section_x": "1.5rem",
    "section_x_lg": "3rem",
    "section_y": "7rem",
    "section_y_lg": "9rem"
  },
  "container": {
    "max": "92rem"
  },
  "grid": {
    "catalog_archetype": "uniform"
  },
  "image_treatment": {
    "policy": "cover"
  },
  "motion": {
    "identity": "warm-rise",
    "ease": [
      0.34,
      1.3,
      0.64,
      1.0
    ],
    "stagger_ms": 90,
    "travel": "16px",
    "reveal": "rise"
  }
};
