import type { ReactElement } from 'react';

const cls = 'w-6 h-6';
const common = {
  viewBox: '0 0 24 24',
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  className: cls,
  'aria-hidden': true,
};

export const SOLUTION_ICONS: Record<string, ReactElement> = {
  pulse: (
    <svg {...common}>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  scissors: (
    <svg {...common}>
      <circle cx="6" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M20 4L8.12 15.88M14.47 14.48L20 20M8.12 8.12L12 12" />
    </svg>
  ),
  utensils: (
    <svg {...common}>
      <path d="M3 2v7c0 1.1.9 2 2 2h0a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7" />
    </svg>
  ),
  home: (
    <svg {...common}>
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M9 22V12h6v10" />
    </svg>
  ),
  dumbbell: (
    <svg {...common}>
      <path d="M6.5 6.5l11 11M21 21l-1-1M4 4l-1-1M3 7l4-4M17 21l4-4M4.5 12.5l-2 2a2.12 2.12 0 1 0 3 3l2-2M18.5 9.5l2-2a2.12 2.12 0 0 0-3-3l-2 2" />
    </svg>
  ),
  briefcase: (
    <svg {...common}>
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
    </svg>
  ),
  cart: (
    <svg {...common}>
      <circle cx="9" cy="21" r="1" />
      <circle cx="20" cy="21" r="1" />
      <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6" />
    </svg>
  ),
  wrench: (
    <svg {...common}>
      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
    </svg>
  ),
  graduation: (
    <svg {...common}>
      <path d="M22 10L12 5 2 10l10 5 10-5z" />
      <path d="M6 12v5c0 1.5 3 3 6 3s6-1.5 6-3v-5" />
    </svg>
  ),
  car: (
    <svg {...common}>
      <path d="M5 17h14M5 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0zm14 0a2 2 0 1 1-4 0 2 2 0 0 1 4 0zM3 17V9l2-5h14l2 5v8" />
    </svg>
  ),
  bed: (
    <svg {...common}>
      <path d="M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20" />
      <path d="M6 8V6a2 2 0 0 1 2-2h3a2 2 0 0 1 2 2v2" />
    </svg>
  ),
  heart: (
    <svg {...common}>
      <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1L12 21l7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z" />
    </svg>
  ),
};
