/** The groups the /solutions showroom is organised by, in page order. */
export const CONCEPT_GROUPS = ['Run the business', 'Grow revenue', 'Create', 'See the physical world'] as const;
export type ConceptGroup = (typeof CONCEPT_GROUPS)[number];

export interface Concept {
  id: string;
  name: string;
  group: ConceptGroup;
  /** Who buys it, in the visitor's terms. */
  industry: string;
  tagline: string;
  /** The organisation this is for, in one line. */
  buyer: string;
  /** What is different once it runs. Qualitative on purpose: these are
   *  concepts, so there are no results to quote. */
  change: string;
  features: string[];
  /** Screen names; each one is drawn as a panel on /solutions, and its name
   *  picks the panel's layout (see components/concepts/screenTexture). */
  screens: string[];
}

/**
 * Concepts of large AI systems we can build: whole operations run, simulated
 * or understood by AI, not single tools. They are ideas shown screen by
 * screen, not delivered client projects, and the page labels them so.
 * Within each group the most gripping comes first.
 */
export const CONCEPTS: Concept[] = [
  // ── run the business ──────────────────────────────────────────────────
  {
    id: 'digital-twin',
    name: 'Business Digital Twin',
    group: 'Run the business',
    industry: 'Logistics & manufacturing',
    tagline:
      'A living copy of your entire operation, fed by live data, that simulates next quarter before you have to live it.',
    buyer: 'Operations where one wrong decision ripples through every site, truck and shift.',
    change: 'Every big decision is tested on the twin first, so the real operation only gets the version that works.',
    features: [
      'Live model of sites, stock, fleet and people',
      'Run "what if" scenarios before committing',
      'Bottlenecks predicted before they form',
      'AI recommends the next move, you approve it',
      'Every decision and its outcome recorded',
    ],
    screens: ['Live operations map', 'Scenario simulator', 'Forecast timeline', 'Decision log'],
  },
  {
    id: 'ai-workforce',
    name: 'Autonomous AI Workforce',
    group: 'Run the business',
    industry: 'Company-wide operations',
    tagline:
      'Teams of AI agents that run the back office end to end, handing work to each other and to your people for the big calls.',
    buyer: 'Companies whose growth is capped by how many people they can hire and train.',
    change: 'Work that used to queue for a person moves on its own, with people approving what matters.',
    features: [
      'Specialist agents for finance, operations and support',
      'Agents pass work to each other like a real team',
      'People approve anything above a set threshold',
      'Every action explained and auditable',
      'New agents added as the business grows',
    ],
    screens: ['Agent command center', 'Task board', 'Approval inbox', 'Agent chat'],
  },
  {
    id: 'finance-office',
    name: 'Autonomous Finance Office',
    group: 'Run the business',
    industry: 'Finance teams',
    tagline:
      'The books reconcile themselves every day, cash is forecast weeks ahead, and anything unusual is flagged the moment it happens.',
    buyer: 'Finance teams that spend every month-end reconciling instead of advising.',
    change: 'Month-end stops being a crunch; the numbers are ready whenever someone asks.',
    features: [
      'Transactions matched and reconciled daily',
      'Cash forecast updated continuously',
      'Anomalies and fraud patterns flagged live',
      'Month-end close prepared automatically',
      'Plain-language answers about any number',
    ],
    screens: ['Live ledger', 'Cash forecast', 'Anomaly radar', 'Month-end close'],
  },
  {
    id: 'procurement-agent',
    name: 'AI Procurement Negotiator',
    group: 'Run the business',
    industry: 'Procurement & supply chain',
    tagline:
      'Agents that compare suppliers, negotiate terms by email within the limits you set, and place the order when the deal is right.',
    buyer: 'Companies buying from dozens of suppliers with a team too small to chase every quote.',
    change: 'Every purchase gets shopped around and negotiated, not just the big ones.',
    features: [
      'Supplier quotes gathered and compared',
      'Negotiates within limits you set',
      'Prices and contract terms tracked over time',
      'Orders placed after your approval',
      'Risks flagged for every supplier',
    ],
    screens: ['Supplier compare', 'Negotiation chat', 'Approval inbox', 'Spend dashboard'],
  },
  {
    id: 'compliance-officer',
    name: 'AI Compliance Officer',
    group: 'Run the business',
    industry: 'Finance, health & insurance',
    tagline:
      'Reads every new regulation, maps it to your processes, and watches daily operations for anything that would fail an audit.',
    buyer: 'Regulated businesses where compliance is a permanent scramble.',
    change: 'Audits stop being a surprise; gaps are found and fixed long before anyone inspects.',
    features: [
      'New regulations read and summarised',
      'Each rule mapped to your processes',
      'Daily checks across systems and documents',
      'Audit evidence collected as you go',
      'An owner and a deadline for every gap',
    ],
    screens: ['Regulation feed', 'Control map', 'Audit evidence viewer', 'Gap dashboard'],
  },
  {
    id: 'sovereign-ai',
    name: 'Sovereign Company AI',
    group: 'Run the business',
    industry: 'Banks, government & regulated industries',
    tagline:
      "Your own AI model, trained on your organisation's knowledge and running entirely on your own servers.",
    buyer: 'Organisations that cannot send their data to anyone else’s cloud.',
    change: 'Every team gets an expert assistant, and not a byte of data leaves the building.',
    features: [
      'Open-weight model tuned to your organisation',
      'Runs on infrastructure you own',
      'Every answer cites its source',
      'Permissions and audit trail built in',
      'Improves as your knowledge grows',
    ],
    screens: ['Ask the company', 'Model training studio', 'Answer with sources', 'Access & audit'],
  },

  // ── grow revenue ──────────────────────────────────────────────────────
  {
    id: 'synthetic-customers',
    name: 'Synthetic Customer Lab',
    group: 'Grow revenue',
    industry: 'Consumer brands & product teams',
    tagline:
      'Test a product, a price or an ad on thousands of simulated customers before you launch it to a single real one.',
    buyer: 'Brands that spend months and budgets finding out what customers think after launch.',
    change: 'Ideas are pressure-tested in days, and only the strongest ones reach the market.',
    features: [
      'Customer personas built from your real data',
      'Products, prices and ads tested in simulation',
      'Reactions broken down by segment',
      'Objections surfaced before real customers raise them',
      'A launch readiness view for every idea',
    ],
    screens: ['Persona universe', 'Concept test', 'Reaction heatmap', 'Launch readiness dashboard'],
  },
  {
    id: 'ai-sales-team',
    name: 'AI Sales Development Team',
    group: 'Grow revenue',
    industry: 'B2B sales',
    tagline:
      "AI reps that research every prospect, write outreach worth replying to, handle the replies and book meetings on your team's calendar.",
    buyer: 'Companies whose pipeline depends on how many hours reps spend prospecting.',
    change: 'The pipeline fills itself, and people spend their time on the conversations that close.',
    features: [
      'Prospect research from public sources',
      'Personal outreach, not templates',
      'Replies handled and qualified',
      'Meetings booked straight into calendars',
      'Every conversation visible to your team',
    ],
    screens: ['Prospect research', 'Outreach editor', 'Reply inbox', 'Meeting calendar'],
  },
  {
    id: 'voice-contact-center',
    name: 'Voice AI Contact Center',
    group: 'Grow revenue',
    industry: 'Customer service',
    tagline:
      "Every call answered at once, in the caller's language, resolved end to end where it can be, and handed to a person with full context where it can't.",
    buyer: 'Brands whose customers wait on hold at every peak.',
    change: 'No hold music at busy times, and agents only take the calls that need a human.',
    features: [
      'Answers every call, day or night',
      "Speaks the caller's language",
      'Handles orders, bookings and account questions',
      'Hands over to people with the whole conversation',
      'Every call summarised and searchable',
    ],
    screens: ['Live calls map', 'Call transcript', 'Handover queue', 'Service dashboard'],
  },
  {
    id: 'personal-video',
    name: 'Personal Video Studio',
    group: 'Grow revenue',
    industry: 'Marketing & customer success',
    tagline:
      'A personal video for every customer, in your own voice and likeness, generated from one recording and your customer data.',
    buyer: "Teams that know personal outreach works but can't record a thousand videos.",
    change: 'Every customer gets a message that feels made for them.',
    features: [
      'One recording becomes thousands of personal videos',
      'Names, details and offers drawn from your data',
      'Your own voice and likeness, with your consent',
      'Many languages from the same recording',
      'Views and replies tracked per video',
    ],
    screens: ['Video render', 'Script editor', 'Audience list', 'Engagement dashboard'],
  },
  {
    id: 'pricing-engine',
    name: 'Dynamic Pricing Engine',
    group: 'Grow revenue',
    industry: 'Retail, travel & e-commerce',
    tagline: 'Prices that move with demand, stock and competitors, inside the rules you set, and explain every change.',
    buyer: 'Businesses whose prices change once a season while the market changes every day.',
    change: 'Prices follow the market daily, and nobody has to update a spreadsheet.',
    features: [
      'Demand and competitor prices watched continuously',
      'Price changes stay inside your guardrails',
      'Every change explained in plain words',
      'New prices tested before they roll out',
      'Margin and sell-through tracked live',
    ],
    screens: ['Price radar', 'Demand forecast', 'Rules editor', 'Price test results'],
  },

  // ── create ────────────────────────────────────────────────────────────
  {
    id: 'product-studio',
    name: 'Generative Product Studio',
    group: 'Create',
    industry: 'Consumer products',
    tagline:
      'Describe a product in one sentence; get design variants, photoreal renders, packaging and a launch campaign.',
    buyer: 'Product teams whose ideas wait months for design, samples and marketing.',
    change: 'An idea becomes a full launch-ready concept in an afternoon, ready to test and refine.',
    features: [
      'Product concepts from a written brief',
      'Photoreal renders in every variant',
      'Packaging designed to your brand',
      'Launch campaign drafted alongside',
      'Designs tested with the Synthetic Customer Lab',
    ],
    screens: ['Idea to render', 'Design variants', 'Packaging studio', 'Campaign builder'],
  },
  {
    id: 'ad-film-studio',
    name: 'AI Ad Film Studio',
    group: 'Create',
    industry: 'Brands & agencies',
    tagline: 'From a one-line brief to storyboards, a finished video ad, and every size for every channel.',
    buyer: 'Brands that need more video than their budget can shoot.',
    change: 'Campaigns are tested in many versions instead of betting everything on one expensive shoot.',
    features: [
      'Storyboard from a written brief',
      'Scenes, voice-over and music generated',
      'Every format for every channel',
      'Brand rules applied to every frame',
      'Versions ready for testing',
    ],
    screens: ['Storyboard', 'Scene render', 'Voice-over editor', 'Channel formats'],
  },
  {
    id: 'ar-commerce',
    name: '3D & AR Commerce',
    group: 'Create',
    industry: 'Retail & furniture',
    tagline:
      'Turns ordinary product photos into 3D models shoppers can spin, and place in their own room through their phone.',
    buyer: "Stores whose returns start with 'it looked different online'.",
    change: 'Shoppers see the product at true size in their own space before they buy.',
    features: [
      '3D models made from product photos',
      'Placed in your room through the phone camera',
      'True to size, in every colour',
      'Works on your existing store',
      'Which products get explored in 3D, tracked',
    ],
    screens: ['3D model render', 'Room placement', 'Product variants', 'Engagement insights'],
  },
  {
    id: 'localization-studio',
    name: 'Global Localisation Studio',
    group: 'Create',
    industry: 'Media, education & e-commerce',
    tagline:
      'Your videos, courses and product pages in dozens of languages, in the same voice, lip-synced, and adapted to each culture.',
    buyer: 'Companies with a global audience and content in one language.',
    change: 'Every market gets content that feels local, on the day it launches.',
    features: [
      'Video dubbed in your own voice',
      'Lip-sync to the new language',
      'Cultural adaptation, not just translation',
      'Product pages and courses included',
      'Review step for native speakers',
    ],
    screens: ['Language map', 'Video dubbing', 'Translation review', 'Market dashboard'],
  },
  {
    id: 'brand-guardian',
    name: 'Brand & Legal Guardian',
    group: 'Create',
    industry: 'Marketing teams',
    tagline:
      'Checks every ad, post and email against your brand rules and advertising law before it goes out, and suggests the fix.',
    buyer: 'Teams publishing more content than anyone can review.',
    change: 'Everything published is on-brand and cleared, without a review bottleneck.',
    features: [
      'Brand voice and visuals checked',
      'Advertising claims checked against the rules',
      'Fixes suggested, not just flagged',
      'Works inside the tools your team already uses',
      'A record of every approval',
    ],
    screens: ['Content review', 'Issue heatmap', 'Fix suggestions', 'Approval log'],
  },

  // ── see the physical world ────────────────────────────────────────────
  {
    id: 'vision-store',
    name: 'Vision-Powered Store',
    group: 'See the physical world',
    industry: 'Retail chains',
    tagline:
      'Cameras that understand the store: empty shelves, long queues and misplaced stock are spotted and fixed on their own.',
    buyer: 'Retailers who find out about empty shelves from customers who already left.',
    change: 'Shelves stay full and staff go where they are needed, guided by what the store can see.',
    features: [
      'Shelf gaps detected as they happen',
      'Queues predicted and staff alerted',
      'Footfall mapped across every aisle',
      'Replenishment ordered automatically',
      'Store layouts tested against real movement',
    ],
    screens: ['Live store vision', 'Shelf gaps', 'Footfall heatmap', 'Auto-replenishment'],
  },
  {
    id: 'hospital-command',
    name: 'Hospital Command Center',
    group: 'See the physical world',
    industry: 'Healthcare systems',
    tagline:
      'Sees the whole hospital at once: predicts patient flow and bed demand, and writes clinical notes while the doctor talks.',
    buyer: 'Hospitals and clinic networks where beds, staff and paperwork are always the bottleneck.',
    change: 'Pressure is seen hours ahead, and clinicians spend their time with patients instead of screens.',
    features: [
      'Patient flow predicted ward by ward',
      'Bed and staffing needs forecast ahead of time',
      'Clinical notes drafted from the consultation',
      'Discharges planned before the rush',
      'One live view for the whole hospital',
    ],
    screens: ['Hospital flow map', 'Bed forecast', 'Ambient clinical notes', 'Staffing planner'],
  },
  {
    id: 'site-twin',
    name: 'Construction Site Twin',
    group: 'See the physical world',
    industry: 'Construction & infrastructure',
    tagline:
      'Drones and cameras scan the site every day and compare it with the plan, so delays and mistakes show up the day they happen.',
    buyer: 'Contractors who discover problems weeks later, when they are expensive.',
    change: 'Progress is measured, not reported, and issues are fixed while they are still cheap.',
    features: [
      'Daily scans by drone or site camera',
      'Progress compared with the building plan',
      'Deviations flagged with their exact location',
      'Safety risks spotted on site',
      'Owner reports written automatically',
    ],
    screens: ['Site scan render', 'Plan vs reality compare', 'Progress timeline', 'Issue map'],
  },
  {
    id: 'predictive-maintenance',
    name: 'Predictive Maintenance Radar',
    group: 'See the physical world',
    industry: 'Manufacturing & fleets',
    tagline:
      'Listens to machines and vehicles through their sensors and warns you before a failure, not after the breakdown.',
    buyer: 'Plants and fleets where one breakdown stops everything.',
    change: 'Repairs are planned in quiet hours instead of rushed after a breakdown.',
    features: [
      'Live sensor data from every machine',
      'Early warning of likely failures',
      'Repairs scheduled around production',
      'Spare parts ordered ahead of time',
      'A health view for every asset',
    ],
    screens: ['Machine health heatmap', 'Failure forecast', 'Maintenance planner', 'Parts orders'],
  },
  {
    id: 'energy-autopilot',
    name: 'Energy Autopilot',
    group: 'See the physical world',
    industry: 'Buildings, campuses & factories',
    tagline:
      'Runs heating, cooling and power across your buildings on its own, using weather, energy prices and occupancy to cut waste.',
    buyer: 'Organisations whose energy bill is one of their biggest costs.',
    change: 'Buildings use energy when it is cheap and needed, without anyone touching a thermostat.',
    features: [
      'Heating, cooling and lighting run automatically',
      'Weather and energy prices factored in',
      'Rooms only conditioned when they are used',
      'Solar and batteries scheduled smartly',
      'Savings and emissions reported',
    ],
    screens: ['Building energy map', 'Price and weather forecast', 'Control rules editor', 'Savings dashboard'],
  },
];
