/** Build packages shown after a live preview — choose plan, then reach out. */

export interface BuildAddon {
  id: string;
  name: string;
  description: string;
  /** Plans that already include this addon (cannot toggle off as extra). */
  includedIn?: Array<'launch' | 'growth'>;
  /** Why we suggested this for this business (shown as a small hint). */
  whyForYou?: string;
}

export interface BuildPlan {
  id: 'launch' | 'growth' | 'custom';
  name: string;
  tagline: string;
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
    timeline: '4–8 weeks',
    bestFor: 'Getting live fast with your core customer + owner flows',
    includes: [
      'Production build of your preview (public site + core journeys)',
      'Owner / admin basics',
      'AI from your preview, wired for production',
      'Payments on your main path (orders, booking, or checkout)',
      'Customer confirmations (email + WhatsApp/SMS basics)',
      'Brand colors, typography, and deploy',
      'Launch handoff + walkthrough',
    ],
  },
  {
    id: 'growth',
    name: 'Growth MVP',
    tagline: 'Launch + staff ops, polish, and post-launch care.',
    timeline: '8–12 weeks',
    highlight: true,
    badge: 'Most popular',
    bestFor: 'Teams that need staff roles, fuller automations, and care',
    includes: [
      'Everything in Launch MVP',
      'Staff / role dashboards from your preview',
      'Richer reminder & follow-up automations',
      'Domain extras scoped to your industry',
      'Cinematic polish pass',
      '30-day care after launch',
    ],
  },
  {
    id: 'custom',
    name: 'Custom / Scale',
    tagline: 'Integrations, multi-location, or ongoing product.',
    timeline: 'Scoped together',
    bestFor: 'Complex ops, POS/CRM links, or a longer partnership',
    includes: [
      'Everything in Growth MVP',
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

  // 1) AI — covered in Launch (and Growth). Never treat as a paid Launch add-on.
  if (aiNames.length >= 2) {
    push({
      id: 'ai-pack',
      name: `AI suite for ${brand}`,
      description: `Wire previewed AI live: ${aiNames.join(', ')}.`,
      includedIn: ['launch', 'growth'],
      whyForYou: 'Already in your preview — included in Launch.',
    });
  } else if (aiNames.length === 1) {
    push({
      id: 'ai-pack',
      name: `Production-ready ${aiNames[0]}`,
      description: `Take “${aiNames[0]}” from demo to live with your real data and guardrails.`,
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch MVP.',
    });
  } else {
    push({
      id: 'ai-pack',
      name: `AI assistant for ${brand}`,
      description: 'A branded AI helper trained on your offerings and FAQs.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch MVP.',
    });
  }

  // 2) Primary commerce — included in Launch (core MVP path)
  if (bucket === 'food' || hasOrder) {
    push({
      id: 'payments',
      name: 'Online ordering + payments',
      description: `Card checkout for ${brand} pickup/orders — cart through paid confirmation.`,
      includedIn: ['launch', 'growth'],
      whyForYou: 'Core Launch path — not an upgrade.',
    });
  } else if (bucket === 'beauty' || bucket === 'health' || bucket === 'fitness' || hasBooking) {
    push({
      id: 'payments',
      name: 'Booking deposits & payments',
      description: 'Take deposits or full payment when customers book — fewer no-shows.',
      includedIn: ['launch', 'growth'],
      whyForYou: hasNoShow
        ? 'Your brief called out no-shows — covered in Launch.'
        : 'Included in Launch so bookings can collect money.',
    });
  } else if (bucket === 'retail') {
    push({
      id: 'payments',
      name: 'Shop checkout + catalog',
      description: 'Sell featured products with real checkout and order status.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch — showcase becomes revenue.',
    });
  } else if (bucket === 'hospitality') {
    push({
      id: 'payments',
      name: 'Stay / experience booking payments',
      description: 'Secure reservations with deposits and confirmation emails.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch — paid holds, not open calendars.',
    });
  } else {
    push({
      id: 'payments',
      name: 'Payments for your main journey',
      description: 'Checkout wired into the primary action in your preview.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch so the demo path can collect money.',
    });
  }

  // 3) Messaging / reminders — included in Launch (basic); Growth keeps them too
  if (bucket === 'food') {
    push({
      id: 'messaging',
      name: 'Order & table confirmations',
      description: 'WhatsApp/SMS for order-ready alerts and reservation reminders.',
      includedIn: ['launch', 'growth'],
      whyForYou: hasNoShow
        ? 'Matches your no-show / phone-order pain — in Launch.'
        : 'Included in Launch so customers get real updates.',
    });
  } else if (bucket === 'beauty' || bucket === 'health' || bucket === 'fitness') {
    push({
      id: 'messaging',
      name: 'Appointment reminders',
      description: 'WhatsApp/SMS before visits + easy reschedule links.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch — protects your calendar.',
    });
  } else {
    push({
      id: 'messaging',
      name: 'Customer messaging',
      description: 'Confirmations and follow-ups on WhatsApp or SMS.',
      includedIn: ['launch', 'growth'],
      whyForYou: 'Included in Launch — where customers already reply.',
    });
  }

  // 4) Roles — included in Growth (staff dashboards)
  if (roles.length >= 2) {
    push({
      id: 'roles',
      name: `Dashboards for ${roles.slice(0, 3).join(' + ')}`,
      description: `Separate live workspaces for each role in your preview.`,
      includedIn: ['growth'],
      whyForYou: 'Your preview already defines these roles.',
    });
  } else if (bucket === 'food') {
    push({
      id: 'roles',
      name: 'Floor + kitchen ops views',
      description: 'Staff queue / ticket board separate from the owner dashboard.',
      includedIn: ['growth'],
      whyForYou: 'Cafe ops need more than one admin screen.',
    });
  } else if (bucket === 'beauty' || bucket === 'fitness') {
    push({
      id: 'roles',
      name: 'Front desk + practitioner views',
      description: 'Reception books; practitioners see today’s clients.',
      includedIn: ['growth'],
      whyForYou: 'Two jobs, two screens — fewer mix-ups.',
    });
  } else {
    push({
      id: 'roles',
      name: 'Extra staff / partner roles',
      description: 'Additional dashboards beyond the owner view.',
      includedIn: ['growth'],
      whyForYou: 'When more than one person runs the product daily.',
    });
  }

  // 5) Industry specialty — included in Growth; optional paid add-on on Launch
  if (bucket === 'food') {
    push({
      id: 'specialty',
      name: 'Live menu & allergen data',
      description: 'Editable menu, modifiers, and allergen facts feeding your AI answers.',
      includedIn: ['growth'],
      whyForYou: /allergen|diet/.test(text)
        ? 'Your plan includes allergen / dietary AI.'
        : 'Menus change — the app should too.',
    });
  } else if (bucket === 'beauty' || bucket === 'health') {
    push({
      id: 'specialty',
      name: 'Client notes & rebooking',
      description: 'Treatment history, photos, and smart rebook prompts.',
      includedIn: ['growth'],
      whyForYou: 'Repeat visits are the business model.',
    });
  } else if (bucket === 'fitness') {
    push({
      id: 'specialty',
      name: 'Class packs & memberships',
      description: 'Sell packs, track credits, and gate class booking.',
      includedIn: ['growth'],
      whyForYou: 'Studios grow on packs, not one-off visits.',
    });
  } else if (bucket === 'retail' || hasInventory) {
    push({
      id: 'specialty',
      name: 'Inventory & low-stock alerts',
      description: 'Track SKUs and warn before bestsellers run out.',
      includedIn: ['growth'],
      whyForYou: 'Retail dies when the shelf is empty online.',
    });
  } else if (bucket === 'education') {
    push({
      id: 'specialty',
      name: 'Class schedule & enrollments',
      description: 'Sessions, seats, and student confirmations.',
      includedIn: ['growth'],
      whyForYou: 'Education needs seats, not a static brochure.',
    });
  } else if (bucket === 'services') {
    push({
      id: 'specialty',
      name: 'Job / lead pipeline',
      description: 'Capture leads, assign jobs, and track status to done.',
      includedIn: ['growth'],
      whyForYou: 'Service businesses win on follow-through.',
    });
  } else {
    push({
      id: 'specialty',
      name: `Domain module for ${brand}`,
      description: 'A custom workflow module matched to your industry preview.',
      includedIn: ['growth'],
      whyForYou: 'Goes beyond a generic website template.',
    });
  }

  // 6) Polish + care — Growth includes both; Launch can add as optional upgrades
  push({
    id: 'cinema',
    name: `Cinematic polish for ${brand}`,
    description: 'Hero photography art-direction, motion, and brand-first craft.',
    includedIn: ['growth'],
    whyForYou: 'Makes the live product feel as premium as the preview.',
  });

  push({
    id: 'care',
    name: '30-day care after launch',
    description: 'Priority fixes and small iterations once you’re live.',
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

/** AI / API payload for client build packages (no prices). */
export interface BuildPlansPayload {
  recommended_plan_id?: BuildPlan['id'];
  plans?: BuildPlan[];
  addons?: BuildAddon[];
}

export function normalizeBuildPlansPayload(
  payload: BuildPlansPayload | null | undefined,
  fallbackCtx?: BuildAddonContext,
): { plans: BuildPlan[]; addons: BuildAddon[]; recommendedPlanId: BuildPlan['id'] } {
  const ids: BuildPlan['id'][] = ['launch', 'growth', 'custom'];
  const byId = new Map(
    (payload?.plans || [])
      .filter((p): p is BuildPlan => Boolean(p && ids.includes(p.id as BuildPlan['id'])))
      .map((p) => [p.id, p] as const),
  );
  const plans = ids.map((id) => {
    const ai = byId.get(id);
    const base = BUILD_PLANS.find((p) => p.id === id)!;
    if (!ai) return base;
    return {
      ...base,
      name: ai.name || base.name,
      tagline: ai.tagline || base.tagline,
      timeline: ai.timeline || base.timeline,
      bestFor: ai.bestFor || base.bestFor,
      includes: ai.includes?.length ? ai.includes : base.includes,
      badge: ai.badge ?? base.badge,
      highlight: id === 'growth' ? true : Boolean(ai.highlight),
    };
  });

  const addons =
    payload?.addons && payload.addons.length > 0
      ? payload.addons
          .filter((a) => a?.id && a?.name)
          .map((a) => ({
            id: a.id,
            name: a.name,
            description: a.description || '',
            whyForYou: a.whyForYou,
            includedIn: (a.includedIn || []).filter(
              (x): x is 'launch' | 'growth' => x === 'launch' || x === 'growth',
            ),
          }))
      : suggestBusinessAddons(fallbackCtx || {});

  const recommendedPlanId =
    payload?.recommended_plan_id && ids.includes(payload.recommended_plan_id)
      ? payload.recommended_plan_id
      : 'growth';

  return { plans, addons, recommendedPlanId };
}

export function addonAvailable(addon: BuildAddon, planId: BuildPlan['id']): boolean {
  if (planId === 'custom') return true;
  return !(addon.includedIn || []).includes(planId as 'launch' | 'growth');
}

export function addonIncluded(addon: BuildAddon, planId: BuildPlan['id']): boolean {
  if (planId === 'custom') return false;
  return (addon.includedIn || []).includes(planId as 'launch' | 'growth');
}

export function summarizeSelection(
  planId: BuildPlan['id'],
  selectedAddonIds: string[],
  catalog: BuildAddon[] = BUILD_ADDONS,
  plans: BuildPlan[] = BUILD_PLANS,
): string {
  const plan = plans.find((p) => p.id === planId);
  const included = catalog.filter((a) => addonIncluded(a, planId));
  const extras = catalog.filter(
    (a) => selectedAddonIds.includes(a.id) && addonAvailable(a, planId),
  );
  const parts = [
    `Package: ${plan?.name || planId}`,
    'Pricing: custom quote after scope (no public prices)',
  ];
  if (included.length) {
    parts.push(`Included in package: ${included.map((a) => a.name).join('; ')}`);
  }
  if (extras.length) {
    parts.push(`Optional add-ons: ${extras.map((a) => a.name).join('; ')}`);
  } else {
    parts.push('Optional add-ons: none');
  }
  return parts.join('\n');
}
