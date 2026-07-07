/** Minimal SVG icons for live site preview — no emoji, no AI branding. */

import type { CSSProperties, ReactElement } from 'react';

const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.75, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };

export function LiveFeatureIcon({ name, className = 'w-5 h-5' }: { name: string; className?: string }) {
  const key = name?.toLowerCase() || 'default';

  const icons: Record<string, ReactElement> = {
    users: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
    sparkles: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M12 3v3M12 18v3M5 12H2M22 12h-3" /><circle cx="12" cy="12" r="3" />
      </svg>
    ),
    chart: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M3 3v18h18" /><path d="M7 16l4-6 4 3 5-8" />
      </svg>
    ),
    bell: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    ),
    calendar: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4M8 2v4M3 10h18" />
      </svg>
    ),
    chat: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    shield: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
    zap: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
      </svg>
    ),
    heart: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
      </svg>
    ),
    star: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
      </svg>
    ),
    default: (
      <svg viewBox="0 0 24 24" className={className} {...stroke}>
        <rect x="3" y="3" width="18" height="18" rx="3" /><path d="M3 9h18M9 21V9" />
      </svg>
    ),
  };

  return icons[key] ?? icons.default;
}

export function MessageAvatar({
  name,
  className = 'w-10 h-10',
  style,
}: {
  name: string;
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <span
      className={`${className} rounded-full flex items-center justify-center text-white text-sm font-semibold shrink-0`}
      style={style}
      aria-hidden
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}
