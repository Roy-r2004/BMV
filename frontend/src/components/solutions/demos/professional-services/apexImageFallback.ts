import type { SyntheticEvent } from 'react';

const FALLBACK_HOME =
  'https://images.unsplash.com/photo-1497366216548-37526070297c?w=900&h=680&fit=crop&q=85';

export function onApexImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.axFallback === 'photo') {
    if (img.dataset.axFallbackSvg) return;
    img.dataset.axFallbackSvg = '1';
    img.src =
      'data:image/svg+xml,' +
      encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
          <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#475569"/>
          </linearGradient></defs>
          <rect width="900" height="680" fill="url(#g)"/>
          <text x="450" y="350" text-anchor="middle" font-family="system-ui,sans-serif" font-size="42" font-weight="700" fill="#e2e8f0">${(label || 'A').charAt(0)}</text>
        </svg>`,
      );
    return;
  }
  if (img.dataset.axFallback) return;
  img.dataset.axFallback = 'photo';
  img.src = FALLBACK_HOME;
}
