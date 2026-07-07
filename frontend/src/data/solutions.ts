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
    tagline: 'Turn DMs and calls into booked appointments with an AI intake assistant.',
    description:
      'A booking and intake system that qualifies patients, answers common questions, and keeps your front desk focused on care instead of scheduling.',
    capabilities: ['AI patient intake chat', 'Appointment booking & reminders', 'Staff dashboard & daily summaries', 'Treatment FAQ automation'],
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
    tagline: 'Fill every chair with automated booking, reminders, and repeat-client loyalty.',
    description:
      'Clients book online in seconds, get automatic reminders, and you get a simple dashboard to manage your day — no more back-and-forth on Instagram.',
    capabilities: ['Online booking & calendar', 'No-show reminders', 'Client history & preferences', 'Loyalty & rebooking prompts'],
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
    tagline: 'Online ordering and reservations that feel as good as your food tastes.',
    description:
      'A branded ordering and reservation experience for your restaurant, with a live dashboard for staff to manage tables and incoming orders.',
    capabilities: ['Digital menu & ordering', 'Table reservations', 'Order status for staff', 'Repeat-customer offers'],
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
    tagline: 'Capture and qualify leads the moment they view a listing.',
    description:
      'A listings site with an AI assistant that answers buyer questions, schedules viewings, and hands your agents a qualified lead — not a cold one.',
    capabilities: ['Listings showcase', 'AI buyer Q&A assistant', 'Viewing scheduler', 'Lead scoring dashboard'],
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
    tagline: 'Class bookings, memberships, and progress tracking in one place.',
    description:
      'Members book classes, track progress, and stay engaged — while you get a dashboard for attendance, memberships, and renewals.',
    capabilities: ['Class & session booking', 'Membership management', 'Progress tracking', 'Automated renewal reminders'],
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
    tagline: 'Client intake and document requests without the email back-and-forth.',
    description:
      'A client portal that handles intake forms, document collection, and scheduling — so your team spends time advising, not chasing paperwork.',
    capabilities: ['Client intake forms', 'Secure document requests', 'Consultation scheduling', 'Case/matter status dashboard'],
    planContext: 'legal or consulting firm',
    customerModule: {
      title: 'Client onboarding',
      description: 'Structured intake and secure uploads — professional from the first touch.',
    },
    opsModule: {
      title: 'Matter management',
      description: 'Status, scheduling, and document tracking without inbox chaos.',
    },
  }),
  solution({
    id: 'ecommerce',
    name: 'Retail & E-commerce',
    icon: 'cart',
    accent: 'from-purple-500 to-indigo-500',
    tagline: 'A storefront with AI product search that actually understands shoppers.',
    description:
      'An online storefront with natural-language product search, smart recommendations, and a seller dashboard to manage inventory and orders.',
    capabilities: ['Product storefront', 'AI-powered search & recs', 'Inventory dashboard', 'Order & fulfillment tracking'],
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
    tagline: 'Quote requests, scheduling, and dispatch — for plumbers, electricians, cleaners.',
    description:
      'Customers request quotes and book jobs online; you get a dispatch dashboard to assign and track work without juggling phone calls.',
    capabilities: ['Instant quote requests', 'Job scheduling & dispatch', 'Technician status updates', 'Customer follow-up automation'],
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
    tagline: 'Course booking, student portals, and progress tracking for tutors and schools.',
    description:
      'Students book sessions and track progress, while instructors get a portal to manage schedules, materials, and payments.',
    capabilities: ['Session/course booking', 'Student progress portal', 'Materials & resource sharing', 'Payment & package tracking'],
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
    tagline: 'Service booking and real-time repair status for shops and dealers.',
    description:
      'Customers book service appointments and track repair status online, cutting down the "is my car ready?" calls to your front desk.',
    capabilities: ['Service appointment booking', 'Live repair status', 'Estimate approvals', 'Service history records'],
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
    tagline: 'A booking engine and AI concierge for guest requests.',
    description:
      'Guests book stays and message an AI concierge for requests, while staff manage bookings and requests from one dashboard.',
    capabilities: ['Direct booking engine', 'AI concierge chat', 'Guest request dashboard', 'Automated pre-arrival messaging'],
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
    tagline: 'Donor management, event signups, and volunteer coordination.',
    description:
      'A donation and event platform with a dashboard to track donors, volunteers, and upcoming events — built for teams without a tech department.',
    capabilities: ['Donation & campaign pages', 'Event signup & RSVPs', 'Volunteer coordination', 'Donor & impact dashboard'],
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
