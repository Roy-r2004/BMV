import type { SyntheticEvent } from 'react';

const FALLBACK_HOME_IMAGE =
  'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=900&h=680&fit=crop&q=85';

function lumenFallbackDataUrl(label = 'L'): string {
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#4c1d95"/>
            <stop offset="55%" stop-color="#6d28d9"/>
            <stop offset="100%" stop-color="#7c3aed"/>
          </linearGradient>
          <radialGradient id="glow" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#a78bfa" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#a78bfa" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <rect width="900" height="680" fill="url(#g)"/>
        <rect width="900" height="680" fill="url(#glow)"/>
        <circle cx="450" cy="300" r="88" fill="none" stroke="#c4b5fd" stroke-width="2" opacity="0.35"/>
        <text x="450" y="318" text-anchor="middle" font-family="Georgia,serif" font-size="42" font-weight="700" fill="#ede9fe">${label}</text>
        <text x="450" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="14" letter-spacing="0.2em" fill="#ddd6fe" opacity="0.8">LUMEN HOME</text>
      </svg>`,
    )
  );
}

export const LUMEN_IMG_FALLBACK = FALLBACK_HOME_IMAGE;

export function onLumenImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.lhFallback === 'photo') {
    if (img.dataset.lhFallbackSvg) return;
    img.dataset.lhFallbackSvg = '1';
    img.src = label ? lumenFallbackDataUrl(label.charAt(0).toUpperCase()) : lumenFallbackDataUrl();
    return;
  }
  if (img.dataset.lhFallback) return;
  img.dataset.lhFallback = 'photo';
  img.src = FALLBACK_HOME_IMAGE;
}
