import type { ReactNode } from 'react';

const common = {
  viewBox: '0 0 24 24',
  fill: 'none' as const,
  stroke: 'currentColor',
  strokeWidth: 1.75,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
};

/** One icon per concept, keyed by the concept's id in data/concepts. */
export const CONCEPT_ICONS: Record<string, ReactNode> = {
  // a cube and its wireframe copy
  'digital-twin': (
    <svg {...common}>
      <path d="M12 3l7 4v8l-7 4-7-4V7z" />
      <path d="M12 11l7-4M12 11L5 7M12 11v8" />
    </svg>
  ),
  // connected agents
  'ai-workforce': (
    <svg {...common}>
      <circle cx="12" cy="5" r="2.5" />
      <circle cx="5" cy="18" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M10.8 7.2L6.2 15.8M13.2 7.2l4.6 8.6M7.5 18h9" />
    </svg>
  ),
  // a crowd of personas
  'synthetic-customers': (
    <svg {...common}>
      <circle cx="12" cy="8" r="3" />
      <path d="M6 20a6 6 0 0 1 12 0" />
      <circle cx="4.5" cy="10" r="2" />
      <circle cx="19.5" cy="10" r="2" />
      <path d="M1.5 18a3.5 3.5 0 0 1 4-3.4M22.5 18a3.5 3.5 0 0 0-4-3.4" />
    </svg>
  ),
  // a pulse inside a cross
  'hospital-command': (
    <svg {...common}>
      <path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z" />
      <path d="M7 12h2.5l1.5-2.5 2 5 1.5-2.5H17" />
    </svg>
  ),
  // an eye over a shelf
  'vision-store': (
    <svg {...common}>
      <path d="M2 11s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 11 2 11z" />
      <circle cx="12" cy="11" r="2.5" />
      <path d="M4 21h16" />
    </svg>
  ),
  // a sparkle over a box
  'product-studio': (
    <svg {...common}>
      <path d="M4 10l8-4 8 4-8 4z" />
      <path d="M4 10v7l8 4 8-4v-7" />
      <path d="M18 2v3M16.5 3.5h3" />
    </svg>
  ),
  // a rising line on a ledger
  'finance-office': (
    <svg {...common}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M7 15l3-3 3 2 4-5" />
    </svg>
  ),
  // a shield around a node
  'sovereign-ai': (
    <svg {...common}>
      <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" />
      <circle cx="12" cy="11" r="2.5" />
      <path d="M12 13.5V16" />
    </svg>
  ),
  // two arrows meeting on a price tag
  'procurement-agent': (
    <svg {...common}>
      <path d="M3 12h7M14 12h7M7 8l-4 4 4 4M17 8l4 4-4 4" />
      <circle cx="12" cy="12" r="1.5" />
    </svg>
  ),
  // a checked shield over a document
  'compliance-officer': (
    <svg {...common}>
      <path d="M7 3h7l5 5v13H7z" />
      <path d="M14 3v5h5M10 14l2 2 4-4" />
    </svg>
  ),
  // a target with an arrow
  'ai-sales-team': (
    <svg {...common}>
      <circle cx="11" cy="13" r="7" />
      <circle cx="11" cy="13" r="3" />
      <path d="M11 13l9-9M16 4h4v4" />
    </svg>
  ),
  // a headset
  'voice-contact-center': (
    <svg {...common}>
      <path d="M4 14v-2a8 8 0 0 1 16 0v2" />
      <rect x="3" y="14" width="4" height="6" rx="1.5" />
      <rect x="17" y="14" width="4" height="6" rx="1.5" />
      <path d="M19 20c0 1-2 2-5 2" />
    </svg>
  ),
  // a play button in a frame
  'personal-video': (
    <svg {...common}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M10 9l5 3-5 3z" />
    </svg>
  ),
  // a price tag with a pulse
  'pricing-engine': (
    <svg {...common}>
      <path d="M3 12V4h8l10 10-8 8z" />
      <circle cx="7.5" cy="8.5" r="1.5" />
    </svg>
  ),
  // a clapperboard
  'ad-film-studio': (
    <svg {...common}>
      <rect x="3" y="9" width="18" height="12" rx="2" />
      <path d="M3 9l2-5 16 3-1 2M8 4.5l1.5 4M13 5.5l1.5 4" />
    </svg>
  ),
  // a cube in a phone
  'ar-commerce': (
    <svg {...common}>
      <rect x="6" y="2" width="12" height="20" rx="2" />
      <path d="M12 8l3 1.6v3.3L12 14.5 9 12.9V9.6z" />
      <path d="M11 19h2" />
    </svg>
  ),
  // a globe
  'localization-studio': (
    <svg {...common}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z" />
    </svg>
  ),
  // a shield with a star
  'brand-guardian': (
    <svg {...common}>
      <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z" />
      <path d="M12 8.5l1.1 2.2 2.4.3-1.8 1.7.5 2.4-2.2-1.2-2.2 1.2.5-2.4-1.8-1.7 2.4-.3z" />
    </svg>
  ),
  // a crane
  'site-twin': (
    <svg {...common}>
      <path d="M6 21V4h2v17M4 21h8M8 5h12l-3 3M8 5l4 4M17 8v5" />
      <rect x="15.5" y="13" width="3" height="3" />
    </svg>
  ),
  // a gear with a pulse
  'predictive-maintenance': (
    <svg {...common}>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </svg>
  ),
  // a bolt in a building
  'energy-autopilot': (
    <svg {...common}>
      <path d="M4 21V9l8-6 8 6v12z" />
      <path d="M13 9l-3 5h4l-3 5" />
    </svg>
  ),
};
