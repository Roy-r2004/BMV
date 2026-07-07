import type { VisualDemo } from '../../types/request';
import type { ImageTheme } from './demoContent';
import { resolveIndustryBranding } from './industryBranding';

export function slugify(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 24) || 'yourproduct';
}

export function fontClass(style?: string) {
  if (!style) return 'font-sans';
  if (style.includes('serif')) return 'font-serif';
  return 'font-sans';
}

export function themeFromDemo(demo: VisualDemo, imageTheme?: ImageTheme) {
  if (imageTheme) {
    const b = resolveIndustryBranding(imageTheme, demo);
    return { primary: b.primary, secondary: b.secondary, bg: b.background };
  }
  const primary = demo.visual_theme?.primary_color || '#4f46e5';
  const secondary = demo.visual_theme?.secondary_color || '#06b6d4';
  const bg = demo.visual_theme?.background_color || '#ffffff';
  return { primary, secondary, bg };
}

export function hexAlpha(hex: string, alpha: number) {
  const h = hex.replace('#', '');
  if (h.length !== 6) return hex;
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
