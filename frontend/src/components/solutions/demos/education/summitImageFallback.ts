import type { SyntheticEvent } from 'react';

function portraitFallbackDataUrl(initial = 'S'): string {
  const letter = initial.trim().charAt(0).toUpperCase() || 'S';
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" viewBox="0 0 400 500">
        <defs>
          <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#083344"/>
            <stop offset="100%" stop-color="#0e7490"/>
          </linearGradient>
        </defs>
        <rect width="400" height="500" fill="url(#bg)"/>
        <circle cx="200" cy="190" r="72" fill="#22d3ee"/>
        <text x="200" y="214" text-anchor="middle" font-family="system-ui,sans-serif" font-size="72" font-weight="700" fill="#083344">${letter}</text>
        <text x="200" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="22" font-weight="600" fill="#ecfeff" opacity="0.8">Summit Tutoring</text>
      </svg>`,
    )
  );
}

export const SUMMIT_IMG_FALLBACK = portraitFallbackDataUrl();

export function onSummitImageError(e: SyntheticEvent<HTMLImageElement>, initial?: string) {
  const img = e.currentTarget;
  if (img.dataset.smFallback) return;
  img.dataset.smFallback = '1';
  img.src = initial ? portraitFallbackDataUrl(initial) : SUMMIT_IMG_FALLBACK;
}
