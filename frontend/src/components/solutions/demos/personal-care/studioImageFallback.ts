import type { SyntheticEvent } from 'react';

function portraitFallbackDataUrl(initial = '9'): string {
  const letter = initial.trim().charAt(0).toUpperCase() || '9';
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" viewBox="0 0 400 500">
        <defs>
          <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#1a1714"/>
            <stop offset="100%" stop-color="#2d2620"/>
          </linearGradient>
        </defs>
        <rect width="400" height="500" fill="url(#bg)"/>
        <circle cx="200" cy="190" r="72" fill="#c9a227"/>
        <text x="200" y="214" text-anchor="middle" font-family="system-ui,sans-serif" font-size="72" font-weight="700" fill="#1a1714">${letter}</text>
        <text x="200" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="22" font-weight="600" fill="#f5f0e8" opacity="0.7">Studio Nine</text>
      </svg>`,
    )
  );
}

/** Neutral barbershop placeholder when Unsplash fails to load */
export const STUDIO_IMG_FALLBACK = portraitFallbackDataUrl();

export function onStudioImageError(e: SyntheticEvent<HTMLImageElement>, initial?: string) {
  const img = e.currentTarget;
  if (img.dataset.snFallback) return;
  img.dataset.snFallback = '1';
  img.src = initial ? portraitFallbackDataUrl(initial) : STUDIO_IMG_FALLBACK;
}
