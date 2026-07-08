import type { SyntheticEvent } from 'react';

function portraitFallbackDataUrl(initial = 'H'): string {
  const letter = initial.trim().charAt(0).toUpperCase() || 'H';
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" viewBox="0 0 400 500">
        <defs>
          <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#14532d"/>
            <stop offset="100%" stop-color="#166534"/>
          </linearGradient>
        </defs>
        <rect width="400" height="500" fill="url(#bg)"/>
        <circle cx="200" cy="190" r="72" fill="#86efac"/>
        <text x="200" y="214" text-anchor="middle" font-family="system-ui,sans-serif" font-size="72" font-weight="700" fill="#14532d">${letter}</text>
        <text x="200" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="20" font-weight="600" fill="#dcfce7" opacity="0.85">Harbor Community Fund</text>
      </svg>`,
    )
  );
}

export const HARBOR_FUND_IMG_FALLBACK = portraitFallbackDataUrl();

export function onHarborFundImageError(e: SyntheticEvent<HTMLImageElement>, initial?: string) {
  const img = e.currentTarget;
  if (img.dataset.hgFallback) return;
  img.dataset.hgFallback = '1';
  img.src = initial ? portraitFallbackDataUrl(initial) : HARBOR_FUND_IMG_FALLBACK;
}
