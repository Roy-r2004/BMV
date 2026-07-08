import type { SyntheticEvent } from 'react';

type SceneKind = 'meals' | 'youth' | 'housing' | 'community' | 'default';

/** Atmospheric scene SVGs — no letter portrait badges. */
function sceneFallback(kind: SceneKind = 'default'): string {
  const scenes: Record<SceneKind, { a: string; b: string; label: string; mark: string }> = {
    meals: {
      a: '#0f2e1c',
      b: '#166534',
      label: 'Pier kitchen',
      mark: '<circle cx="52" cy="328" r="10" fill="#86efac"/><rect x="42" y="338" width="20" height="8" rx="2" fill="#dcfce7"/>',
    },
    youth: {
      a: '#0a1f12',
      b: '#14532d',
      label: 'Youth mentorship',
      mark: '<rect x="40" y="318" width="24" height="28" rx="2" fill="#86efac"/><path d="M44 326h16M44 332h12" stroke="#14532d" stroke-width="2"/>',
    },
    housing: {
      a: '#1a3a28',
      b: '#14532d',
      label: 'Housing stability',
      mark: '<path d="M40 342 L52 318 L64 342 Z" fill="#86efac"/><rect x="46" y="330" width="12" height="12" fill="#dcfce7"/>',
    },
    community: {
      a: '#14532d',
      b: '#0f2e1c',
      label: 'Harbor Fund',
      mark: '<circle cx="52" cy="334" r="14" fill="none" stroke="#86efac" stroke-width="3"/><circle cx="52" cy="334" r="4" fill="#d97706"/>',
    },
    default: {
      a: '#14532d',
      b: '#166534',
      label: 'Harbor Community Fund',
      mark: '<path d="M40 342h24l-4-10h-16z" fill="#86efac"/><rect x="48" y="316" width="8" height="16" fill="#dcfce7"/>',
    },
  };
  const s = scenes[kind] ?? scenes.default;
  return (
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">
        <defs>
          <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="${s.a}"/>
            <stop offset="100%" stop-color="${s.b}"/>
          </linearGradient>
          <linearGradient id="veil" x1="0" y1="0.35" x2="0" y2="1">
            <stop offset="0%" stop-color="#000" stop-opacity="0"/>
            <stop offset="100%" stop-color="#06140c" stop-opacity="0.78"/>
          </linearGradient>
        </defs>
        <rect width="640" height="400" fill="url(#g)"/>
        <circle cx="520" cy="70" r="130" fill="#22c55e" opacity="0.1"/>
        <circle cx="90" cy="300" r="100" fill="#d97706" opacity="0.08"/>
        <path d="M0 280 Q160 240 320 270 T640 250 L640 400 L0 400 Z" fill="#0a1f12" opacity="0.35"/>
        <rect width="640" height="400" fill="url(#veil)"/>
        ${s.mark}
        <text x="78" y="348" font-family="Georgia,'Times New Roman',serif" font-size="22" fill="#f0fdf4">${s.label}</text>
      </svg>`,
    )
  );
}

const SCENE_BY_HINT: Array<{ test: RegExp; kind: SceneKind }> = [
  { test: /meal|kitchen|food|pier/i, kind: 'meals' },
  { test: /youth|mentor|tutor|school/i, kind: 'youth' },
  { test: /rent|hous|home|evict|buffer|housing/i, kind: 'housing' },
  { test: /community|volunteer|harbor/i, kind: 'community' },
];

export const HARBOR_FUND_IMG_FALLBACK = sceneFallback('default');

export function sceneFallbackForStory(id: string): string {
  if (id === 'meals') return sceneFallback('meals');
  if (id === 'youth') return sceneFallback('youth');
  if (id === 'housing') return sceneFallback('housing');
  return sceneFallback('default');
}

export function onHarborFundImageError(e: SyntheticEvent<HTMLImageElement>, hint?: string) {
  const img = e.currentTarget;
  if (img.dataset.hgFallback) return;
  img.dataset.hgFallback = '1';
  const source = `${hint ?? ''} ${img.alt ?? ''} ${img.dataset.hgScene ?? ''} ${img.src ?? ''}`;
  const match = SCENE_BY_HINT.find((s) => s.test.test(source));
  img.src = sceneFallback(match?.kind ?? 'default');
}
