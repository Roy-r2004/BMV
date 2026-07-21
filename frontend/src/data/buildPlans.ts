/** Build packages shown after a live preview — choose plan, then reach out. */

export interface BuildAddon {
  id: string;
  name: string;
  description: string;
  /** Soft floor in USD; exact quote confirmed manually. */
  fromUsd: number;
  /** Plans that already include this addon (cannot toggle off as extra). */
  includedIn?: Array<'launch' | 'growth'>;
  /** Why we suggested this for this business (shown as a small hint). */
  whyForYou?: string;
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

export interface BuildAddonContext {
  businessName?: string | null;
  conceptName?: string | null;
  industry?: string | null;
  mainProblem?: string | null;
  desiredOutcome?: string | null;
  previewFeatures?: string[];
  aiFeatures?: Array<{ id?: string; name?: string; description?: string }>;
  roleLabels?: string[];
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

type IndustryBucket =
  | 'food'
  | 'beauty'
  | 'fitness'
  | 'health'
  | 'retail'
  | 'hospitality'
  | 'education'
  | 'services'
  | 'generic';

function bucketIndustry(industry: string | null | undefined): IndustryBucket {
  const t = (industry || '').toLowerCase();
  if (/restaurant|cafe|coffee|food|bakery|bistro|dining|bar/.test(t)) return 'food';
  if (/spa|salon|beauty|skin|aesthetic|wellness|massage|nail/.test(t)) return 'beauty';
  if (/fitness|gym|yoga|pilates|coach|training/.test(t)) return 'fitness';
  if (/clinic|dental|health|medical|therapy|physio/.test(t)) return 'health';
  if (/retail|fashion|shop|boutique|store|ecommerce/.test(t)) return 'retail';
  if (/hotel|hospitality|inn|resort/.test(t)) return 'hospitality';
  if (/school|tutor|education|course|academy|learning/.test(t)) return 'education';
  if (/service|trade|plumb|hvac|clean|agency|law|legal/.test(t)) return 'services';
  return 'generic';
}

function blob(ctx: BuildAddonContext): string {
  return [
    ctx.industry,
    ctx.mainProblem,
    ctx.desiredOutcome,
    ...(ctx.previewFeatures || []),
    ...(ctx.aiFeatures || []).map((f) => `${f.name || ''} ${f.description || ''}`),
    ...(ctx.roleLabels || []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

/**
 * Suggest add-ons tailored to this business / preview — not a generic catalog.
 * Always returns a short list (≈5–7) with clear “why for you” hints.
 */
export function suggestBusinessAddons(ctx: BuildAddonContext): BuildAddon[] {
  const brand = (ctx.businessName || ctx.conceptName || 'your business').trim();
  const bucket = bucketIndustry(ctx.industry);
  const text = blob(ctx);
  const aiNames = (ctx.aiFeatures || [])
    .map((f) => (f.name || '').trim())
    .filter(Boolean)
    .slice(0, 3);
  const roles = (ctx.roleLabels || []).map((r) => r.trim()).filter(Boolean);
  const hasBooking = /book|reserv|appoint|table|slot/.test(text);
  const hasOrder = /order|menu|cart|checkout|pickup|delivery/.test(text);
  const hasNoShow = /no-?show|phone|remind|whatsapp|sms/.test(text);
  const hasInventory = /inventory|stock|sku|catalog/.test(text);
  const out: BuildAddon[] = [];

  const push = (addon: BuildAddon) => {
    if (out.some((a) => a.id === addon.id)) return;
    out.push(addon);
  };

  // 1) AI — name real features from their preview when present
  if (aiNames.length >= 2) {
    push({
      id: 'ai-pack',
      name: `Full AI suite for ${brand}`,
      description: `Wire all previewed AI: ${aiNames.join(', ')}.`,
      fromUsd: 1200,
      includedIn: ['growth'],
      whyForYou: 'These AI features are already in your preview plan.',
    });
  } else if (aiNames.length === 1) {
    push({
      id: 'ai-pack',
      name: `Production-ready ${aiNames[0]}`,
      description: `Take “${aiNames[0]}” from demo to live with your real data and guardrails.`,
      fromUsd: 900,
      includedIn: ['growth'],
      whyForYou: 'Highlighted in your AI hub.',
    });
  } else {
    push({
      id: 'ai-pack',
      name: `AI assistant for ${brand}`,
      description: 'A branded AI helper trained on your offerings and FAQs.',
      fromUsd: 800,
      includedIn: ['growth'],
      whyForYou: 'Speeds up answers your customers already ask.',
    });
  }

  // 2) Industry-primary commerce / ops addon
  if (bucket === 'food' || hasOrder) {
    push({
      id: 'payments',
      name: 'Online ordering + payments',
      description: `Card checkout for ${brand} pickup/orders — cart through paid confirmation.`,
      fromUsd: 1400,
      includedIn: ['growth'],
      whyForYou: 'Cuts phone orders and missed tickets.',
    });
  } else if (bucket === 'beauty' || bucket === 'health' || bucket === 'fitness' || hasBooking) {
    push({
      id: 'payments',
      name: 'Booking deposits & payments',
      description: 'Take deposits or full payment when customers book — fewer no-shows.',
      fromUsd: 1200,
      includedIn: ['growth'],
      whyForYou: hasNoShow
        ? 'Your brief called out no-shows / phone friction.'
        : 'Booking businesses convert better with deposits.',
    });
  } else if (bucket === 'retail') {
    push({
      id: 'payments',
      name: 'Shop checkout + catalog',
      description: 'Sell featured products with real checkout and order status.',
      fromUsd: 1300,
      includedIn: ['growth'],
      whyForYou: 'Turns your showcase into revenue.',
    });
  } else if (bucket === 'hospitality') {
    push({
      id: 'payments',
      name: 'Stay / experience booking payments',
      description: 'Secure reservations with deposits and confirmation emails.',
      fromUsd: 1300,
      includedIn: ['growth'],
      whyForYou: 'Hospitality needs paid holds, not open calendars.',
    });
  } else {
    push({
      id: 'payments',
      name: 'Payments for your main journey',
      description: 'Checkout wired into the primary action in your preview.',
      fromUsd: 1200,
      includedIn: ['growth'],
      whyForYou: 'Makes the demo path collect real money.',
    });
  }

  // 3) Messaging / reminders — industry voice
  if (bucket === 'food') {
    push({
      id: 'messaging',
      name: 'Order & table reminders',
      description: 'WhatsApp/SMS for order-ready alerts and reservation reminders.',
      fromUsd: 900,
      includedIn: ['growth'],
      whyForYou: hasNoShow
        ? 'Matches your no-show / phone-order pain.'
        : 'Keeps tables and pickups on time.',
    });
  } else if (bucket === 'beauty' || bucket === 'health' || bucket === 'fitness') {
    push({
      id: 'messaging',
      name: 'Appointment reminder automations',
      description: 'WhatsApp/SMS before visits + easy reschedule links.',
      fromUsd: 900,
      includedIn: ['growth'],
      whyForYou: 'Protects your calendar from empty slots.',
    });
  } else {
    push({
      id: 'messaging',
      name: 'Customer messaging automations',
      description: 'Confirmations and follow-ups on WhatsApp or SMS.',
      fromUsd: 900,
      includedIn: ['growth'],
      whyForYou: 'Where your customers already reply.',
    });
  }

  // 4) Roles — use real role labels when we have them
  if (roles.length >= 2) {
    push({
      id: 'roles',
      name: `Dashboards for ${roles.slice(0, 3).join(' + ')}`,
      description: `Separate live workspaces for each role in your preview.`,
      fromUsd: 800,
      whyForYou: 'Your preview already defines these roles.',
    });
  } else if (bucket === 'food') {
    push({
      id: 'roles',
      name: 'Floor + kitchen ops views',
      description: 'Staff queue / ticket board separate from the owner dashboard.',
      fromUsd: 750,
      whyForYou: 'Cafe ops need more than one admin screen.',
    });
  } else if (bucket === 'beauty' || bucket === 'fitness') {
    push({
      id: 'roles',
      name: 'Front desk + practitioner views',
      description: 'Reception books; practitioners see today’s clients.',
      fromUsd: 750,
      whyForYou: 'Two jobs, two screens — fewer mix-ups.',
    });
  } else {
    push({
      id: 'roles',
      name: 'Extra staff / partner roles',
      description: 'Additional dashboards beyond the owner view.',
      fromUsd: 700,
      whyForYou: 'When more than one person runs the product daily.',
    });
  }

  // 5) Industry specialty
  if (bucket === 'food') {
    push({
      id: 'specialty',
      name: 'Live menu & allergen data',
      description: 'Editable menu, modifiers, and allergen facts feeding your AI answers.',
      fromUsd: 850,
      whyForYou: /allergen|diet/.test(text)
        ? 'Your plan includes allergen / dietary AI.'
        : 'Menus change — the app should too.',
    });
  } else if (bucket === 'beauty' || bucket === 'health') {
    push({
      id: 'specialty',
      name: 'Client notes & rebooking',
      description: 'Treatment history, photos, and smart rebook prompts.',
      fromUsd: 850,
      whyForYou: 'Repeat visits are the business model.',
    });
  } else if (bucket === 'fitness') {
    push({
      id: 'specialty',
      name: 'Class packs & memberships',
      description: 'Sell packs, track credits, and gate class booking.',
      fromUsd: 950,
      whyForYou: 'Studios grow on packs, not one-off visits.',
    });
  } else if (bucket === 'retail' || hasInventory) {
    push({
      id: 'specialty',
      name: 'Inventory & low-stock alerts',
      description: 'Track SKUs and warn before bestsellers run out.',
      fromUsd: 800,
      whyForYou: 'Retail dies when the shelf is empty online.',
    });
  } else if (bucket === 'education') {
    push({
      id: 'specialty',
      name: 'Class schedule & enrollments',
      description: 'Sessions, seats, and student confirmations.',
      fromUsd: 850,
      whyForYou: 'Education needs seats, not a static brochure.',
    });
  } else if (bucket === 'services') {
    push({
      id: 'specialty',
      name: 'Job / lead pipeline',
      description: 'Capture leads, assign jobs, and track status to done.',
      fromUsd: 900,
      whyForYou: 'Service businesses win on follow-through.',
    });
  } else {
    push({
      id: 'specialty',
      name: `Domain module for ${brand}`,
      description: 'A custom workflow module matched to your industry preview.',
      fromUsd: 850,
      whyForYou: 'Goes beyond a generic website template.',
    });
  }

  // 6) Always useful polish + care (shorter why)
  push({
    id: 'cinema',
    name: `Cinematic polish for ${brand}`,
    description: 'Hero photography art-direction, motion, and brand-first craft.',
    fromUsd: 600,
    whyForYou: 'Makes the live product feel as premium as the preview.',
  });

  push({
    id: 'care',
    name: '30-day care after launch',
    description: 'Priority fixes and small iterations once you’re live.',
    fromUsd: 500,
    includedIn: ['growth'],
    whyForYou: 'First month is when real customers find edge cases.',
  });

  return out.slice(0, 7);
}

/** Fallback catalog if context is empty (landing page, etc.). */
export const BUILD_ADDONS: BuildAddon[] = suggestBusinessAddons({
  businessName: 'your business',
  industry: 'general',
});

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
  catalog: BuildAddon[] = BUILD_ADDONS,
): number | null {
  const base = planBaseFrom(planId);
  if (base == null) return null;
  const extra = catalog
    .filter((a) => selectedAddonIds.includes(a.id) && addonAvailable(a, planId))
    .reduce((sum, a) => sum + a.fromUsd, 0);
  return base + extra;
}

export function summarizeSelection(
  planId: BuildPlan['id'],
  selectedAddonIds: string[],
  catalog: BuildAddon[] = BUILD_ADDONS,
): string {
  const plan = BUILD_PLANS.find((p) => p.id === planId);
  const addons = catalog.filter(
    (a) => selectedAddonIds.includes(a.id) && addonAvailable(a, planId),
  );
  const estimate = estimateFromUsd(planId, selectedAddonIds, catalog);
  const parts = [
    `Package: ${plan?.name || planId}`,
    estimate != null
      ? `Estimate: ${formatFromUsd(estimate)} USD (soft floor — exact quote after scope)`
      : 'Estimate: custom quote after scope call',
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
