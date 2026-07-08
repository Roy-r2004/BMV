import type { SyntheticEvent } from 'react';

const FALLBACK_HOME =
  'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=900&h=680&fit=crop&q=85';

export function onPeakformImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.pfFallback === 'photo') {
    if (img.dataset.pfFallbackSvg) return;
    img.dataset.pfFallbackSvg = '1';
    img.src =
      'data:image/svg+xml,' +
      encodeURIComponent(
        `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
          <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#064e3b"/><stop offset="100%" stop-color="#059669"/>
          </linearGradient></defs>
          <rect width="900" height="680" fill="url(#g)"/>
          <text x="450" y="350" text-anchor="middle" font-family="system-ui,sans-serif" font-size="42" font-weight="700" fill="#d1fae5">${(label || 'P').charAt(0)}</text>
        </svg>`,
      );
    return;
  }
  if (img.dataset.pfFallback) return;
  img.dataset.pfFallback = 'photo';
  img.src = FALLBACK_HOME;
}
