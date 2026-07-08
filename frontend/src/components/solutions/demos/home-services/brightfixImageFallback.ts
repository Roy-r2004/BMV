import type { SyntheticEvent } from 'react';

const FALLBACK_PLUMB_IMAGE =
  'https://images.unsplash.com/photo-1585705326261-c378a7e9a8c2?w=900&h=680&fit=crop&q=85';

function brightfixFallbackDataUrl(label = 'B'): string {
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#1c1917"/>
            <stop offset="55%" stop-color="#78350f"/>
            <stop offset="100%" stop-color="#ea580c"/>
          </linearGradient>
          <radialGradient id="glow" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#f59e0b" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#f59e0b" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <rect width="900" height="680" fill="url(#g)"/>
        <rect width="900" height="680" fill="url(#glow)"/>
        <circle cx="450" cy="300" r="88" fill="none" stroke="#fbbf24" stroke-width="2" opacity="0.35"/>
        <text x="450" y="318" text-anchor="middle" font-family="system-ui,sans-serif" font-size="42" font-weight="700" fill="#fffbeb">${label}</text>
        <text x="450" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="14" letter-spacing="0.2em" fill="#fcd34d" opacity="0.8">BRIGHTFIX</text>
      </svg>`,
    )
  );
}

export const BRIGHTFIX_IMG_FALLBACK = FALLBACK_PLUMB_IMAGE;

export function onBrightfixImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.bfFallback === 'photo') {
    if (img.dataset.bfFallbackSvg) return;
    img.dataset.bfFallbackSvg = '1';
    img.src = label ? brightfixFallbackDataUrl(label.charAt(0).toUpperCase()) : brightfixFallbackDataUrl();
    return;
  }
  if (img.dataset.bfFallback) return;
  img.dataset.bfFallback = 'photo';
  img.src = FALLBACK_PLUMB_IMAGE;
}
