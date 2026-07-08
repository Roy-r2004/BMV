export interface PlanPhase {
  step: string;
  title: string;
  duration: string;
  description: string;
}

export interface FeatureModule {
  title: string;
  description: string;
  items: string[];
}

export type DemoStatus = 'coming_soon' | 'live';

export interface IndustrySolution {
  id: string;
  name: string;
  icon: string;
  accent: string;
  tagline: string;
  description: string;
  capabilities: string[];
  highlights: string[];
  planPhases: PlanPhase[];
  featureModules: FeatureModule[];
  demoStatus: DemoStatus;
  demoUrl?: string;
}

function buildIncludedPlan(context: string, capabilities: string[]): PlanPhase[] {
  return [
    {
      step: '01',
      title: 'Ready-made platform',
      duration: 'Included',
      description: `A complete ${context} software package — already built, tested, and ready to deploy for your business.`,
    },
    {
      step: '02',
      title: 'Customer-facing tools',
      duration: 'Included',
      description: `Includes ${capabilities[0]} and ${capabilities[1]} — everything your clients need in one place.`,
    },
    {
      step: '03',
      title: 'Team dashboard & operations',
      duration: 'Included',
      description: `Includes ${capabilities[2]} and ${capabilities[3]} — run your business from one screen.`,
    },
    {
      step: '04',
      title: 'Customized & integrated',
      duration: 'We set it up',
      description:
        'We configure the software to your brand, workflow, and existing tools — then launch it for you.',
    },
  ];
}

function modules(
  customerTitle: string,
  customerDesc: string,
  opsTitle: string,
  opsDesc: string,
  capabilities: string[],
): FeatureModule[] {
  return [
    { title: customerTitle, description: customerDesc, items: capabilities.slice(0, 2) },
    { title: opsTitle, description: opsDesc, items: capabilities.slice(2, 4) },
  ];
}

function solution(
  base: Omit<IndustrySolution, 'highlights' | 'planPhases' | 'featureModules' | 'demoStatus' | 'demoUrl'> & {
    planContext: string;
    customerModule: { title: string; description: string };
    opsModule: { title: string; description: string };
    demoStatus?: DemoStatus;
    demoUrl?: string;
  },
): IndustrySolution {
  const { planContext, customerModule, opsModule, demoStatus = 'coming_soon', demoUrl, ...rest } = base;
  return {
    ...rest,
    highlights: rest.capabilities.slice(0, 2),
    planPhases: buildIncludedPlan(planContext, rest.capabilities),
    featureModules: modules(
      customerModule.title,
      customerModule.description,
      opsModule.title,
      opsModule.description,
      rest.capabilities,
    ),
    demoStatus,
    demoUrl,
  };
}

/**
 * Industry solution catalog — ready-made software we customize and integrate per business.
 * Detail pages show what's included in each package; live demos roll out progressively.
 */
export const INDUSTRY_SOLUTIONS: IndustrySolution[] = [
  solution({
    id: 'healthcare',
    name: 'Healthcare & Clinics',
    icon: 'pulse',
    accent: 'from-blue-500 to-cyan-500',
    tagline: 'Clinical intake AI that books patients while your team focuses on care.',
    description:
      'Harbor-style patient portal with AI intake that qualifies symptoms, offers live slots, and sends reminders — so your front desk stops playing phone tag.',
    capabilities: ['Clinical intake AI chat', 'Smart slot matching & reminders', 'Clinic admin dashboard', 'Treatment FAQ automation'],
    demoStatus: 'live',
    planContext: 'clinic or practice',
    customerModule: {
      title: 'Patient experience',
      description: 'Everything your patients touch before and between visits — fast, clear, and on-brand.',
    },
    opsModule: {
      title: 'Practice operations',
      description: 'What your team sees every day — fewer calls, clearer schedules, less admin.',
    },
  }),
  solution({
    id: 'personal-care',
    name: 'Barbershops & Salons',
    icon: 'scissors',
    accent: 'from-violet-500 to-fuchsia-500',
    tagline: 'Turn Instagram DMs into confirmed chairs — with style memory for every regular.',
    description:
      'Studio-style booking where AI recalls fade type, barber preference, and timing — fills cancellations from waitlist and nudges clients before they drift.',
    capabilities: ['DM booking bot', 'Style memory for regulars', 'Waitlist fill & reminders', 'Owner hub & chair utilization'],
    demoStatus: 'live',
    planContext: 'salon or barbershop',
    customerModule: {
      title: 'Client booking flow',
      description: 'Frictionless scheduling that works from Instagram, Google, or your website.',
    },
    opsModule: {
      title: 'Chair & team management',
      description: 'Run the day from one screen — who is in, who is coming, who to win back.',
    },
  }),
  solution({
    id: 'food',
    name: 'Restaurants & Cafes',
    icon: 'utensils',
    accent: 'from-orange-500 to-amber-500',
    tagline: 'Menu concierge AI, direct orders, and a kitchen board that runs peak service.',
    description:
      'Ember-style guest site where AI answers allergens and wine pairings, optimizes tables, routes direct orders to kitchen, and win-backs repeat diners.',
    capabilities: ['Menu concierge AI', 'Direct ordering & reservations', 'Kitchen ops board', 'Guest win-back offers'],
    demoStatus: 'live',
    planContext: 'restaurant or cafe',
    customerModule: {
      title: 'Guest ordering & reservations',
      description: 'A branded front door for dine-in, pickup, and delivery — no third-party fees on direct orders.',
    },
    opsModule: {
      title: 'Kitchen & floor ops',
      description: 'Real-time order flow and table management so service stays smooth at peak hours.',
    },
  }),
  solution({
    id: 'real-estate',
    name: 'Real Estate',
    icon: 'home',
    accent: 'from-indigo-500 to-blue-600',
    tagline: 'Listing AI that answers at 11pm and books viewings by morning.',
    description:
      'Northline-style listings with embedded AI that handles HOA questions, scores buyer intent, syncs agent calendars, and nurtures warm leads automatically.',
    capabilities: ['Listing Q&A AI', 'Lead scoring & nurture', 'Viewing scheduler', 'Agent CRM pipeline'],
    demoStatus: 'live',
    planContext: 'real estate agency',
    customerModule: {
      title: 'Buyer journey',
      description: 'Listings, questions, and viewings — captured while interest is highest.',
    },
    opsModule: {
      title: 'Agent pipeline',
      description: 'Prioritized leads and activity so agents spend time closing, not chasing.',
    },
  }),
  solution({
    id: 'fitness',
    name: 'Gyms & Fitness Coaching',
    icon: 'dumbbell',
    accent: 'from-emerald-500 to-teal-500',
    tagline: 'Adherence coach AI that keeps members accountable and flags churn before it happens.',
    description:
      'Peak Form-style member portal with class recommender, reschedule bot, progress tracking, and a coach hub that shows who needs a nudge today.',
    capabilities: ['Smart class booking', 'Progress & adherence tracking', 'Churn alerts & renewals', 'Coach command center'],
    demoStatus: 'live',
    planContext: 'gym or coaching business',
    customerModule: {
      title: 'Member portal',
      description: 'Book sessions, track goals, and stay accountable between visits.',
    },
    opsModule: {
      title: 'Retention & revenue',
      description: 'Memberships, renewals, and attendance insights in one operational view.',
    },
  }),
  solution({
    id: 'professional-services',
    name: 'Legal & Consulting',
    icon: 'briefcase',
    accent: 'from-slate-600 to-slate-800',
    tagline: 'Counsel AI — conflict scans, clause review, and vault chasing before partners bill a minute.',
    description:
      'Apex-style firm portal where AI clears conflicts, flags contract risks, chases encrypted documents, and drafts engagements — partners advise, not chase admin.',
    capabilities: ['Conflict scan AI', 'Clause review & risk flags', 'Vault chaser & secure uploads', 'Engagement draft & matter dossiers'],
    demoStatus: 'live',
    planContext: 'legal or consulting firm',
    customerModule: {
      title: 'Counsel AI portal',
      description: 'Conflict scans, clause review, and secure vault — professional from the first touch.',
    },
    opsModule: {
      title: 'Partner desk',
      description: 'Matter dossiers, engagement drafts, and billable-ready tracking without inbox chaos.',
    },
  }),
  solution({
    id: 'ecommerce',
    name: 'Retail & E-commerce',
    icon: 'cart',
    accent: 'from-purple-500 to-indigo-500',
    tagline: 'Shopper AI that understands "warm minimalist lamp" — not filter mazes.',
    description:
      'Lumen-style storefront with natural-language search, AI-curated bundles, order support chat, and a seller hub with stock alerts and fulfillment tracking.',
    capabilities: ['Natural language product search', 'AI style bundles & recs', 'Order support automation', 'Seller inventory & fulfillment hub'],
    demoStatus: 'live',
    planContext: 'retail or e-commerce brand',
    customerModule: {
      title: 'Shopper experience',
      description: 'Discovery, search, and checkout tuned to how your customers actually buy.',
    },
    opsModule: {
      title: 'Seller operations',
      description: 'Inventory, orders, and fulfillment visibility from one dashboard.',
    },
  }),
  solution({
    id: 'home-services',
    name: 'Home Services',
    icon: 'wrench',
    accent: 'from-yellow-500 to-orange-500',
    tagline: 'Quote AI to dispatch in minutes — emergency calls quoted while you\'re on the first job.',
    description:
      'BrightFix-style customer site with job wizard, dispatch AI scoring, zone route board, and ops hub — live status updates and review bot after every visit.',
    capabilities: ['Quote AI & job wizard', 'Smart dispatch scoring', 'Live job status updates', 'Ops hub & review automation'],
    demoStatus: 'live',
    planContext: 'home services company',
    customerModule: {
      title: 'Customer requests',
      description: 'Quotes and bookings online — fewer missed calls, faster response.',
    },
    opsModule: {
      title: 'Field dispatch',
      description: 'Assign jobs, track technicians, and automate follow-ups after every visit.',
    },
  }),
  solution({
    id: 'education',
    name: 'Education & Tutoring',
    icon: 'graduation',
    accent: 'from-cyan-500 to-blue-500',
    tagline: 'Tutor matcher AI that pairs students, sends prep packs, and reports to parents automatically.',
    description:
      'Summit-style student portal with subject matching, family inbox for prep materials, session calendar with attached resources, and tutor hub with auto-billing.',
    capabilities: ['Tutor match AI', 'Prep pack automation', 'Parent progress reports', 'Tutor hub & auto billing'],
    demoStatus: 'live',
    planContext: 'tutoring or education business',
    customerModule: {
      title: 'Student experience',
      description: 'Book sessions, access materials, and see progress in one place.',
    },
    opsModule: {
      title: 'Instructor admin',
      description: 'Schedules, packages, and payments without spreadsheets.',
    },
  }),
  solution({
    id: 'automotive',
    name: 'Automotive Services',
    icon: 'car',
    accent: 'from-red-500 to-rose-600',
    tagline: 'Service bot books bays online — customers track repair progress without calling.',
    description:
      'Metro-style shop with service menu booking, bay scheduler AI, live status bot, and shop hub with upsell alerts — full bays, fewer front-desk calls.',
    capabilities: ['Online service booking', 'Bay scheduler AI', 'Live repair status bot', 'Shop hub & upsell alerts'],
    demoStatus: 'live',
    planContext: 'auto shop or dealership',
    customerModule: {
      title: 'Driver portal',
      description: 'Book service and follow repair progress without calling the front desk.',
    },
    opsModule: {
      title: 'Service bay ops',
      description: 'Estimates, approvals, and vehicle history tied to every job.',
    },
  }),
  solution({
    id: 'hospitality',
    name: 'Hospitality & Hotels',
    icon: 'bed',
    accent: 'from-teal-500 to-emerald-600',
    tagline: 'Direct bookings plus AI concierge — guests get answers at 2am, staff handle exceptions.',
    description:
      'The Row-style luxury site with room gallery, concierge AI with guest memory, housekeeping floor board, and occupancy ops hub — commission-free direct rates.',
    capabilities: ['Direct booking engine', '24/7 AI concierge', 'Housekeeping floor board', 'Occupancy ops hub'],
    demoStatus: 'live',
    planContext: 'hotel or hospitality property',
    customerModule: {
      title: 'Guest journey',
      description: 'Direct bookings and concierge support before, during, and after the stay.',
    },
    opsModule: {
      title: 'Front desk & ops',
      description: 'Requests, messaging, and arrivals from a single operational hub.',
    },
  }),
  solution({
    id: 'nonprofit',
    name: 'Nonprofits & Community Orgs',
    icon: 'heart',
    accent: 'from-pink-500 to-rose-500',
    tagline: 'Donate AI, volunteer matcher, and campaign hub — built for teams of four, not forty.',
    description:
      'Harbor Fund-style donor site with impact meter, smart gift tiers, volunteer skill board, thank-you automation, and campaign progress rings.',
    capabilities: ['Smart donate flow AI', 'Volunteer skill matcher', 'Thank-you automation', 'Campaign & impact dashboard'],
    demoStatus: 'live',
    planContext: 'nonprofit or community organization',
    customerModule: {
      title: 'Community engagement',
      description: 'Donate, sign up, and volunteer — simple paths for supporters to take action.',
    },
    opsModule: {
      title: 'Impact tracking',
      description: 'Donors, events, and volunteers organized for teams that wear many hats.',
    },
  }),
];

export function getSolutionById(id: string): IndustrySolution | undefined {
  return INDUSTRY_SOLUTIONS.find((s) => s.id === id);
}
