import type { SyntheticEvent } from 'react';

const FALLBACK_HOTEL_IMAGE =
  'https://images.unsplash.com/photo-1566073771259-6a8506099945?w=900&h=680&fit=crop&q=85';

function hotelFallbackDataUrl(label = 'R'): string {
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#1a0f12"/>
            <stop offset="55%" stop-color="#4a1525"/>
            <stop offset="100%" stop-color="#7a1f35"/>
          </linearGradient>
          <radialGradient id="glow" cx="50%" cy="40%" r="60%">
            <stop offset="0%" stop-color="#9f1239" stop-opacity="0.4"/>
            <stop offset="100%" stop-color="#9f1239" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <rect width="900" height="680" fill="url(#g)"/>
        <rect width="900" height="680" fill="url(#glow)"/>
        <rect x="380" y="240" width="140" height="140" rx="8" fill="none" stroke="#f5e6d3" stroke-width="2" opacity="0.35"/>
        <text x="450" y="325" text-anchor="middle" font-family="Georgia,serif" font-size="48" font-weight="700" fill="#f5e6d3">${label}</text>
        <text x="450" y="370" text-anchor="middle" font-family="system-ui,sans-serif" font-size="12" letter-spacing="0.28em" fill="#d4a574" opacity="0.85">THE ROW HOTEL</text>
      </svg>`,
    )
  );
}

export const ROW_IMG_FALLBACK = FALLBACK_HOTEL_IMAGE;

export function onRowImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.rhFallback === 'photo') {
    if (img.dataset.rhFallbackSvg) return;
    img.dataset.rhFallbackSvg = '1';
    img.src = label ? hotelFallbackDataUrl(label.charAt(0).toUpperCase()) : hotelFallbackDataUrl();
    return;
  }
  if (img.dataset.rhFallback) return;
  img.dataset.rhFallback = 'photo';
  img.src = FALLBACK_HOTEL_IMAGE;
}
