import type { SyntheticEvent } from 'react';

const FALLBACK_FOOD_IMAGE =
  'https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=900&h=680&fit=crop&q=85';

function foodFallbackDataUrl(label = 'E'): string {
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#1c1917"/>
            <stop offset="55%" stop-color="#431407"/>
            <stop offset="100%" stop-color="#7c2d12"/>
          </linearGradient>
          <radialGradient id="glow" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#ea580c" stop-opacity="0.35"/>
            <stop offset="100%" stop-color="#ea580c" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <rect width="900" height="680" fill="url(#g)"/>
        <rect width="900" height="680" fill="url(#glow)"/>
        <circle cx="450" cy="300" r="88" fill="none" stroke="#fb923c" stroke-width="2" opacity="0.35"/>
        <text x="450" y="318" text-anchor="middle" font-family="Georgia,serif" font-size="42" font-weight="700" fill="#ffedd5">${label}</text>
        <text x="450" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="14" letter-spacing="0.2em" fill="#fdba74" opacity="0.8">EMBER &amp; OAK</text>
      </svg>`,
    )
  );
}

export const EMBER_IMG_FALLBACK = FALLBACK_FOOD_IMAGE;

export function onEmberImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.eoFallback === 'photo') {
    if (img.dataset.eoFallbackSvg) return;
    img.dataset.eoFallbackSvg = '1';
    img.src = label ? foodFallbackDataUrl(label.charAt(0).toUpperCase()) : foodFallbackDataUrl();
    return;
  }
  if (img.dataset.eoFallback) return;
  img.dataset.eoFallback = 'photo';
  img.src = FALLBACK_FOOD_IMAGE;
}
