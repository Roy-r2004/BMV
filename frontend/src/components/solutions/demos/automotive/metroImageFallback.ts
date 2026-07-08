import type { SyntheticEvent } from 'react';

const FALLBACK_AUTO_IMAGE =
  'https://images.unsplash.com/photo-1619642751034-765dfdf7c58e?w=900&h=680&fit=crop&q=85';

function metroFallbackDataUrl(label = 'M'): string {
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#0a0a0b"/>
            <stop offset="45%" stop-color="#1c1c1f"/>
            <stop offset="100%" stop-color="#3f3f46"/>
          </linearGradient>
          <radialGradient id="glow" cx="55%" cy="35%" r="55%">
            <stop offset="0%" stop-color="#e11d48" stop-opacity="0.28"/>
            <stop offset="100%" stop-color="#e11d48" stop-opacity="0"/>
          </radialGradient>
        </defs>
        <rect width="900" height="680" fill="url(#g)"/>
        <rect width="900" height="680" fill="url(#glow)"/>
        <rect x="350" y="220" width="200" height="140" rx="4" fill="none" stroke="#a1a1aa" stroke-width="2" opacity="0.4"/>
        <text x="450" y="300" text-anchor="middle" font-family="Impact,sans-serif" font-size="48" fill="#fafafa" letter-spacing="4">${label}</text>
        <text x="450" y="360" text-anchor="middle" font-family="system-ui,sans-serif" font-size="14" letter-spacing="0.28em" fill="#a1a1aa" opacity="0.9">METRO AUTO</text>
      </svg>`,
    )
  );
}

export const METRO_IMG_FALLBACK = FALLBACK_AUTO_IMAGE;

export function onMetroImageError(e: SyntheticEvent<HTMLImageElement>, label?: string) {
  const img = e.currentTarget;
  if (img.dataset.mtFallback === 'photo') {
    if (img.dataset.mtFallbackSvg) return;
    img.dataset.mtFallbackSvg = '1';
    img.src = label ? metroFallbackDataUrl(label.charAt(0).toUpperCase()) : metroFallbackDataUrl();
    return;
  }
  if (img.dataset.mtFallback) return;
  img.dataset.mtFallback = 'photo';
  img.src = FALLBACK_AUTO_IMAGE;
}
