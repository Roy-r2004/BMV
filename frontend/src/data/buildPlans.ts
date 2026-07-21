/** Build packages shown after a live preview — choose plan, then reach out. */

export interface BuildAddon {
  id: string;
  name: string;
  description: string;
  /** Soft floor in USD; exact quote confirmed manually. */
  fromUsd: number;
  /** Plans that already include this addon (cannot toggle off as extra). */
  includedIn?: Array<'launch' | 'growth'>;
}

export interface BuildPlan {
  id: 'launch' | 'growth' | 'custom';
  name: string;
  tagline: string;
  /** Soft floor; null = custom quote only */
  fromUsd: number | null;
  timeline: string;
  highlight?: boolean;
  badge?: string;
  includes: string[];
  bestFor: string;
}

export const BUILD_PLANS: BuildPlan[] = [
  {
    id: 'launch',
    name: 'Launch MVP',
    tagline: 'Ship the preview you just saw — for real.',
    fromUsd: 3500,
    timeline: '4–8 weeks',
    bestFor: 'Getting live fast with your core customer + owner flows',
    includes: [
      'Production build of your preview (public site + core journeys)',
      'Owner / admin basics',
      '1–2 AI features from your plan',
      'Brand colors, typography, and deploy',
      'Launch handoff + walkthrough',
    ],
  },
  {
    id: 'growth',
    name: 'Growth MVP',
    tagline: 'Launch + make it earn and run itself.',
    fromUsd: 7500,
    timeline: '8–12 weeks',
    highlight: true,
    badge: 'Most popular',
    bestFor: 'Teams that want payments, AI, and polish in one go',
    includes: [
      'Everything in Launch MVP',
      'Payments / booking / ordering polish',
      'Extra AI features + automations',
      'WhatsApp or SMS reminders (where applicable)',
      'More pages & roles as scoped',
      '30 days of post-launch tweaks',
    ],
  },
  {
    id: 'custom',
    name: 'Custom / Scale',
    tagline: 'Integrations, multi-location, or ongoing product.',
    fromUsd: null,
    timeline: 'Scoped together',
    bestFor: 'Complex ops, POS/CRM links, or a longer partnership',
    includes: [
      'Everything you need beyond Growth',
      'Third-party integrations',
      'Advanced roles & permissions',
      'Custom workflows and reporting',
      'Dedicated scope call before we quote',
    ],
  },
];

export const BUILD_ADDONS: BuildAddon[] = [
  {
    id: 'ai-pack',
    name: 'Extra AI pack',
    description: 'Additional AI features beyond the plan baseline.',
    fromUsd: 800,
    includedIn: ['growth'],
  },
  {
    id: 'payments',
    name: 'Payments checkout',
    description: 'Card payments wired into order or booking flows.',
    fromUsd: 1200,
    includedIn: ['growth'],
  },
  {
    id: 'messaging',
    name: 'WhatsApp / SMS automations',
    description: 'Confirmations, reminders, and no-show nudges.',
    fromUsd: 900,
    includedIn: ['growth'],
  },
  {
    id: 'roles',
    name: 'Extra staff roles',
    description: 'Additional dashboards for staff, managers, or partners.',
    fromUsd: 700,
  },
  {
    id: 'cinema',
    name: 'Cinematic brand polish',
    description: 'Deeper motion, photography art-direction, and hero craft.',
    fromUsd: 600,
  },
  {
    id: 'care',
    name: '30-day care plan',
    description: 'Priority fixes and small iterations after launch.',
    fromUsd: 500,
    includedIn: ['growth'],
  },
];

export function formatFromUsd(amount: number | null): string {
  if (amount == null) return 'Custom quote';
  return `From $${amount.toLocaleString('en-US')}`;
}

export function planBaseFrom(planId: BuildPlan['id']): number | null {
  return BUILD_PLANS.find((p) => p.id === planId)?.fromUsd ?? null;
}

export function addonAvailable(addon: BuildAddon, planId: BuildPlan['id']): boolean {
  if (planId === 'custom') return true;
  return !(addon.includedIn || []).includes(planId as 'launch' | 'growth');
}

export function addonIncluded(addon: BuildAddon, planId: BuildPlan['id']): boolean {
  if (planId === 'custom') return false;
  return (addon.includedIn || []).includes(planId as 'launch' | 'growth');
}

/** Soft estimate: plan floor + selected add-ons (custom stays null). */
export function estimateFromUsd(
  planId: BuildPlan['id'],
  selectedAddonIds: string[],
): number | null {
  const base = planBaseFrom(planId);
  if (base == null) return null;
  const extra = BUILD_ADDONS.filter(
    (a) => selectedAddonIds.includes(a.id) && addonAvailable(a, planId),
  ).reduce((sum, a) => sum + a.fromUsd, 0);
  return base + extra;
}

export function summarizeSelection(
  planId: BuildPlan['id'],
  selectedAddonIds: string[],
): string {
  const plan = BUILD_PLANS.find((p) => p.id === planId);
  const addons = BUILD_ADDONS.filter(
    (a) => selectedAddonIds.includes(a.id) && addonAvailable(a, planId),
  );
  const estimate = estimateFromUsd(planId, selectedAddonIds);
  const parts = [
    `Package: ${plan?.name || planId}`,
    estimate != null ? `Estimate: ${formatFromUsd(estimate)} USD (soft floor — exact quote after scope)` : 'Estimate: custom quote after scope call',
  ];
  if (addons.length) {
    parts.push(
      `Add-ons: ${addons.map((a) => `${a.name} (+$${a.fromUsd})`).join('; ')}`,
    );
  } else {
    parts.push('Add-ons: none');
  }
  return parts.join('\n');
}
