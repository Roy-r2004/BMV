import type { SolutionOverlay } from '../types/auth';

export type AIFeatureCategory = 'chat' | 'automation' | 'scoring' | 'scheduling' | 'reminders' | 'ops';

export interface AIFeatureCatalogItem {
  id: string;
  title: string;
  description: string;
  category: AIFeatureCategory;
  icon: string;
  /** Overlay fields applied when user integrates this feature */
  patch: Partial<SolutionOverlay>;
}

const cat = (c: AIFeatureCategory) => c;

function section(
  id: string,
  title: string,
  body: string,
  style: 'highlight' | 'cards' | 'banner' | 'stats' = 'highlight',
  bullets?: string[],
) {
  return { id, title, body, style, bullets };
}

/** Pre-built AI features per industry — one-click integrate into the user's personal copy */
export const AI_FEATURE_CATALOG: Record<string, AIFeatureCatalogItem[]> = {
  healthcare: [
    {
      id: 'hc-intake-chat',
      title: 'AI patient intake',
      description: '24/7 chat qualifies symptoms, insurance, and treatment interest before staff sees the thread.',
      category: cat('chat'),
      icon: 'spark',
      patch: {
        aiChips: ['24/7 AI intake', 'Auto booking', 'Smart reminders'],
        sections: [
          section(
            'ai-intake',
            'AI patient intake',
            'Harbor Intake AI answers FAQs, collects history, and routes to the right treatment — around the clock.',
          ),
        ],
      },
    },
    {
      id: 'hc-slot-matching',
      title: 'Smart slot matching',
      description: 'Finds open rooms and practitioners — offers 2–3 times instantly in chat.',
      category: cat('scheduling'),
      icon: 'clock',
      patch: {
        aiChips: ['Live slots', 'Room matching', 'Instant confirm'],
        ctaSecondary: 'Check availability',
      },
    },
    {
      id: 'hc-reminders',
      title: 'Auto reminders',
      description: 'SMS and WhatsApp confirmations cut no-shows without front-desk calls.',
      category: cat('reminders'),
      icon: 'zap',
      patch: {
        aiChips: ['SMS reminders', 'WhatsApp nudges', 'No-show shield'],
        sections: [
          section('ai-reminders', 'Reminder automation', 'Confirmations and day-before nudges sent automatically across channels.'),
        ],
      },
    },
    {
      id: 'hc-clinic-digest',
      title: 'Daily clinic digest',
      description: 'Morning summary: arrivals, open slots, and follow-ups due.',
      category: cat('ops'),
      icon: 'chart',
      patch: {
        sections: [
          section(
            'ai-digest',
            'Daily clinic digest',
            'Morning AI summary for your team — who is arriving, open slots, and follow-ups due.',
            'stats',
            ['12 today', '3 open slots', '5 follow-ups'],
          ),
        ],
      },
    },
    {
      id: 'hc-telehealth-triage',
      title: 'Telehealth triage',
      description: 'Routes virtual vs in-person visits based on symptoms and insurance.',
      category: cat('automation'),
      icon: 'users',
      patch: {
        aiChips: ['Telehealth triage', 'Virtual routing', 'Insurance check'],
        ctaSecondary: 'Start virtual visit',
      },
    },
    {
      id: 'hc-insurance-verify',
      title: 'Insurance verifier',
      description: 'Checks coverage and copay before the patient books — fewer surprises.',
      category: cat('scoring'),
      icon: 'shield',
      patch: {
        sections: [
          section(
            'ai-insurance',
            'Insurance verification',
            'AI confirms coverage and copay in chat before appointments are confirmed.',
          ),
        ],
      },
    },
  ],

  'personal-care': [
    {
      id: 'pc-dm-booking',
      title: 'DM → booking bot',
      description: 'Instagram and WhatsApp messages become confirmed chair slots automatically.',
      category: cat('chat'),
      icon: 'zap',
      patch: { aiChips: ['Instagram booking', 'DM replies', 'Instant confirm'], ctaPrimary: 'Book via DM' },
    },
    {
      id: 'pc-style-memory',
      title: 'Style memory',
      description: 'AI recalls fade type, barber preference, and usual timing for regulars.',
      category: cat('automation'),
      icon: 'users',
      patch: {
        aiChips: ['Style memory', 'Barber prefs', 'Regulars VIP'],
        sections: [section('ai-style', 'Style memory AI', 'Every regular feels known — fade, barber, and timing remembered automatically.')],
      },
    },
    {
      id: 'pc-waitlist',
      title: 'Waitlist fill',
      description: 'Smart reminders plus waitlist backfill when someone cancels.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { aiChips: ['Waitlist fill', 'Cancel backfill', 'Text reminders'] },
    },
    {
      id: 'pc-rebook',
      title: 'Rebook nudges',
      description: 'Loyalty prompts when clients are due — fills slow afternoons.',
      category: cat('automation'),
      icon: 'chart',
      patch: {
        sections: [section('ai-rebook', 'Rebook automation', 'AI nudges regulars before they drift — fills slow afternoons automatically.')],
      },
    },
    {
      id: 'pc-loyalty-points',
      title: 'Loyalty points AI',
      description: 'Tracks visits, rewards, and birthday offers without a punch card.',
      category: cat('automation'),
      icon: 'spark',
      patch: { aiChips: ['Loyalty AI', 'Birthday offers', 'Points track'] },
    },
    {
      id: 'pc-product-recs',
      title: 'Product recommendations',
      description: 'Suggests pomades, treatments, and retail at checkout in chat.',
      category: cat('chat'),
      icon: 'chart',
      patch: {
        sections: [section('ai-retail', 'Retail recommendations', 'AI suggests products based on service history — sold in-chair or shipped.')],
      },
    },
  ],

  food: [
    {
      id: 'food-menu-ai',
      title: 'Menu Q&A AI',
      description: 'Answers allergens, specials, and dietary questions on web and WhatsApp.',
      category: cat('chat'),
      icon: 'spark',
      patch: { aiChips: ['Menu AI', 'Allergen aware', 'Wine pairing'], ctaSecondary: 'Ask the menu' },
    },
    {
      id: 'food-table-planner',
      title: 'Table optimizer',
      description: 'AI suggests best table and section for party size and turn time.',
      category: cat('scheduling'),
      icon: 'clock',
      patch: { aiChips: ['Table planner', 'Party sizing', 'Patio routing'] },
    },
    {
      id: 'food-direct-orders',
      title: 'Direct order routing',
      description: 'Orders hit kitchen display — no aggregator middleman.',
      category: cat('ops'),
      icon: 'zap',
      patch: {
        sections: [section('ai-direct', 'Direct ordering', 'Branded checkout keeps margin — orders route straight to kitchen.')],
      },
    },
    {
      id: 'food-winback',
      title: 'Guest win-back',
      description: 'Personalized offers when diners have not visited in 30 days.',
      category: cat('automation'),
      icon: 'chart',
      patch: { aiChips: ['Guest win-back', 'Loyalty offers', '30-day trigger'] },
    },
    {
      id: 'food-reservation-hold',
      title: 'Reservation hold AI',
      description: 'Holds tables for 10 minutes while guests finish ordering or traveling.',
      category: cat('scheduling'),
      icon: 'clock',
      patch: { ctaPrimary: 'Reserve a table', aiChips: ['Smart holds', 'No-show guard', 'SMS confirm'] },
    },
    {
      id: 'food-kitchen-pacing',
      title: 'Kitchen pacing',
      description: 'Staggers tickets so the line never floods — consistent ticket times.',
      category: cat('ops'),
      icon: 'users',
      patch: {
        sections: [section('ai-kitchen', 'Kitchen pacing AI', 'Ticket flow optimized by party size and prep time — steadier service, happier guests.')],
      },
    },
  ],

  'real-estate': [
    {
      id: 're-listing-ai',
      title: 'Listing Q&A AI',
      description: 'Answers HOA, schools, and availability on every property page.',
      category: cat('chat'),
      icon: 'spark',
      patch: {
        aiChips: ['Listing AI', 'HOA answers', 'School data'],
        sections: [section('ai-listing', 'Listing AI on every page', 'Buyers get instant answers on HOA, schools, and comps — agents get qualified leads.')],
      },
    },
    {
      id: 're-lead-scoring',
      title: 'Lead scoring',
      description: 'Hot buyers ranked by budget fit, timeline, and engagement.',
      category: cat('scoring'),
      icon: 'chart',
      patch: {
        aiChips: ['Lead scoring', 'Hot-lead rank', 'Budget fit'],
        heroStats: [
          { label: 'Qualified this week', value: '23' },
          { label: 'Avg response', value: '<2m' },
          { label: 'Hot-lead score', value: '94' },
        ],
      },
    },
    {
      id: 're-viewing-scheduler',
      title: 'Viewing scheduler',
      description: 'Syncs agent calendars — offers tour slots without email ping-pong.',
      category: cat('scheduling'),
      icon: 'clock',
      patch: { ctaPrimary: 'Book a viewing', aiChips: ['Auto viewings', 'Calendar sync', 'Tour confirm'] },
    },
    {
      id: 're-nurture',
      title: 'Follow-up nurture',
      description: 'Auto nurture for warm leads who viewed but did not book.',
      category: cat('automation'),
      icon: 'zap',
      patch: {
        sections: [section('ai-nurture', 'Lead nurture flows', 'Automated follow-up for warm buyers who viewed listings but have not booked a tour yet.')],
      },
    },
    {
      id: 're-open-house',
      title: 'Open house promoter',
      description: 'Auto-invites matched buyers and collects RSVPs for every open house.',
      category: cat('automation'),
      icon: 'users',
      patch: {
        aiChips: ['Open house AI', 'Buyer match', 'RSVP flow'],
        ctaSecondary: 'RSVP to open house',
      },
    },
    {
      id: 're-market-report',
      title: 'Market report AI',
      description: 'Generates neighborhood comps and price trends on demand in chat.',
      category: cat('scoring'),
      icon: 'chart',
      patch: {
        sections: [section('ai-market', 'Instant market reports', 'Buyers and sellers get AI-generated comp summaries — shareable in one click.')],
        heroStats: [
          { label: 'Avg days on market', value: '18' },
          { label: 'Median price', value: '$485k' },
        ],
      },
    },
  ],

  fitness: [
    {
      id: 'fit-class-rec',
      title: 'Class recommender',
      description: 'AI suggests programs based on goals and attendance history.',
      category: cat('automation'),
      icon: 'spark',
      patch: { aiChips: ['Class AI', 'Goal matching', 'Smart schedule'] },
    },
    {
      id: 'fit-reschedule',
      title: 'Reschedule bot',
      description: 'Members move sessions in-app — calendar updates instantly.',
      category: cat('chat'),
      icon: 'clock',
      patch: { ctaSecondary: 'Reschedule in chat', aiChips: ['1-tap reschedule', 'Calendar sync'] },
    },
    {
      id: 'fit-churn',
      title: 'Churn predictor',
      description: 'Flags at-risk members before they cancel; auto-offers incentives.',
      category: cat('scoring'),
      icon: 'chart',
      patch: {
        aiChips: ['Churn alerts', 'Retention offers', 'Coach nudges'],
        sections: [section('ai-churn', 'Churn prevention', 'AI flags at-risk members and sends win-back offers before they cancel.')],
      },
    },
    {
      id: 'fit-coach-digest',
      title: 'Coach digest',
      description: 'Daily adherence snapshot — who needs a nudge today.',
      category: cat('ops'),
      icon: 'users',
      patch: { aiChips: ['Coach digest', 'Adherence view', 'Daily nudges'] },
    },
    {
      id: 'fit-progress-tracker',
      title: 'Progress tracker',
      description: 'Visual milestones and PR celebrations keep members motivated.',
      category: cat('automation'),
      icon: 'zap',
      patch: {
        sections: [section('ai-progress', 'Progress milestones', 'AI tracks PRs and streaks — members see wins and coaches know who to cheer on.')],
      },
    },
    {
      id: 'fit-nutrition-coach',
      title: 'Nutrition coach',
      description: "Macro tips and meal ideas tied to each member's program goals.",
      category: cat('chat'),
      icon: 'spark',
      patch: { aiChips: ['Nutrition AI', 'Macro tips', 'Meal ideas'], ctaSecondary: 'Ask nutrition coach' },
    },
  ],

  'professional-services': [
    {
      id: 'apex-conflict',
      title: 'Conflict scan',
      description: 'AI clears new matters against active client roster before consult.',
      category: cat('scoring'),
      icon: 'shield',
      patch: { aiChips: ['Conflict scan', 'Roster check', 'Clear to consult'] },
    },
    {
      id: 'apex-clause',
      title: 'Clause review AI',
      description: 'Uploaded contracts scanned — indemnity and liability risks flagged.',
      category: cat('automation'),
      icon: 'spark',
      patch: {
        sections: [section('ai-clause', 'Clause review AI', 'Vendor agreements scanned — indemnity, liability, and termination risks flagged before partner review.')],
      },
    },
    {
      id: 'apex-vault',
      title: 'Vault chaser',
      description: 'Encrypted doc requests with auto-reminders until billable-ready.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { aiChips: ['Vault chaser', 'Doc reminders', 'Secure upload'] },
    },
    {
      id: 'apex-engagement',
      title: 'Engagement draft',
      description: 'Letters pre-filled from matter data — partners review, not re-ask.',
      category: cat('ops'),
      icon: 'chart',
      patch: { ctaPrimary: 'Draft engagement', aiChips: ['Engagement draft', 'Matter prefill'] },
    },
    {
      id: 'apex-deadline-tracker',
      title: 'Deadline tracker',
      description: 'Court dates, filings, and client deadlines in one AI-maintained calendar.',
      category: cat('reminders'),
      icon: 'clock',
      patch: {
        aiChips: ['Deadline AI', 'Filing alerts', 'Court dates'],
        sections: [section('ai-deadlines', 'Deadline intelligence', 'Never miss a filing — AI surfaces upcoming deadlines with matter context.')],
      },
    },
    {
      id: 'apex-billing-predict',
      title: 'Billing prediction',
      description: 'Forecasts billable hours and flags matters trending over budget.',
      category: cat('ops'),
      icon: 'chart',
      patch: { aiChips: ['Billing forecast', 'Budget alerts', 'Utilization'] },
    },
  ],

  ecommerce: [
    {
      id: 'lum-search',
      title: 'Natural language search',
      description: 'Shoppers describe what they want — AI finds the right products.',
      category: cat('chat'),
      icon: 'spark',
      patch: { aiChips: ['Natural search', 'Vision match', 'Style finder'] },
    },
    {
      id: 'lum-bundles',
      title: 'Smart bundles',
      description: 'Recommendations based on cart, season, and purchase history.',
      category: cat('automation'),
      icon: 'zap',
      patch: { sections: [section('ai-bundles', 'Smart bundles', 'AI-curated product bundles based on cart, season, and purchase history.')] },
    },
    {
      id: 'lum-order-ai',
      title: 'Order assistant',
      description: 'Where is my order? Returns? AI resolves without support tickets.',
      category: cat('chat'),
      icon: 'clock',
      patch: { aiChips: ['Order AI', 'Return help', 'Track shipment'] },
    },
    {
      id: 'lum-stock',
      title: 'Inventory alerts',
      description: 'Low-stock and reorder suggestions on the seller dashboard.',
      category: cat('ops'),
      icon: 'chart',
      patch: { aiChips: ['Stock alerts', 'Reorder hints', 'Seller hub'] },
    },
    {
      id: 'lum-size-finder',
      title: 'Size finder AI',
      description: 'Shoppers enter height and fit preference — AI recommends the right size.',
      category: cat('automation'),
      icon: 'users',
      patch: { ctaSecondary: 'Find my size', aiChips: ['Size AI', 'Fit quiz', 'Fewer returns'] },
    },
    {
      id: 'lum-abandoned-cart',
      title: 'Abandoned cart recovery',
      description: 'Personalized nudges and offers when shoppers leave items behind.',
      category: cat('reminders'),
      icon: 'zap',
      patch: {
        sections: [section('ai-cart', 'Cart recovery', 'AI sends timed reminders with dynamic discounts — recover revenue automatically.')],
      },
    },
  ],

  'home-services': [
    {
      id: 'bf-quote',
      title: 'Quote intake AI',
      description: 'Captures job details, photos, and urgency from web or SMS.',
      category: cat('chat'),
      icon: 'zap',
      patch: { ctaPrimary: 'Get a quote', aiChips: ['Quote AI', 'Photo upload', 'Urgency routing'] },
    },
    {
      id: 'bf-dispatch',
      title: 'Smart dispatch',
      description: 'Routes jobs to nearest available tech by skill and location.',
      category: cat('ops'),
      icon: 'users',
      patch: { aiChips: ['Auto dispatch', 'Route optimize', 'Skill match'] },
    },
    {
      id: 'bf-status',
      title: 'Live job status',
      description: 'Customers get on-the-way and job-complete updates automatically.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { sections: [section('ai-status', 'Live job status', 'Homeowners track progress — en route, in progress, done — without calling the office.')] },
    },
    {
      id: 'bf-reviews',
      title: 'Review requests',
      description: 'Five-star follow-ups sent after every completed job.',
      category: cat('automation'),
      icon: 'chart',
      patch: { aiChips: ['Review bot', 'Google asks', 'Post-job follow-up'] },
    },
    {
      id: 'bf-seasonal-prep',
      title: 'Seasonal prep campaigns',
      description: 'AI launches HVAC winter tune-ups or gutter cleanings before peak season.',
      category: cat('automation'),
      icon: 'spark',
      patch: {
        aiChips: ['Seasonal campaigns', 'Tune-up blasts', 'Peak prep'],
        sections: [section('ai-seasonal', 'Seasonal outreach', 'Automated campaigns before weather shifts — fill the schedule early.')],
      },
    },
    {
      id: 'bf-estimate-followup',
      title: 'Estimate follow-up',
      description: 'Nudges homeowners who requested quotes but have not scheduled yet.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { ctaPrimary: 'Schedule now', aiChips: ['Quote follow-up', 'Estimate nudge', 'Close more jobs'] },
    },
  ],

  education: [
    {
      id: 'sm-match',
      title: 'Tutor matcher',
      description: 'AI pairs students with the right tutor by subject and level.',
      category: cat('scoring'),
      icon: 'spark',
      patch: { aiChips: ['Tutor match', 'Level fit', 'Subject AI'], ctaPrimary: 'Find your tutor' },
    },
    {
      id: 'sm-prep',
      title: 'Homework reminders',
      description: 'Automated nudges before sessions with materials attached.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { aiChips: ['Prep automation', 'Material send', 'Session nudges'] },
    },
    {
      id: 'sm-parent',
      title: 'Parent progress reports',
      description: 'Weekly summaries for parents — no manual email blasts.',
      category: cat('automation'),
      icon: 'chart',
      patch: { sections: [section('ai-parent', 'Parent reports', 'Weekly AI-generated progress summaries — professional and on time.')] },
    },
    {
      id: 'sm-billing',
      title: 'Payment automation',
      description: 'Packages, renewals, and receipts handled in-app.',
      category: cat('ops'),
      icon: 'zap',
      patch: { aiChips: ['Auto billing', 'Package renew', 'Receipts'] },
    },
    {
      id: 'sm-attendance-ai',
      title: 'Attendance insights',
      description: 'Flags students missing sessions and suggests intervention steps.',
      category: cat('scoring'),
      icon: 'chart',
      patch: {
        aiChips: ['Attendance AI', 'At-risk alerts', 'Intervention tips'],
        heroStats: [
          { label: 'Sessions this term', value: '24' },
          { label: 'Attendance rate', value: '96%' },
        ],
      },
    },
    {
      id: 'sm-curriculum-path',
      title: 'Learning path AI',
      description: 'Adaptive curriculum sequences based on quiz results and pace.',
      category: cat('automation'),
      icon: 'spark',
      patch: {
        sections: [section('ai-path', 'Adaptive learning paths', "AI adjusts lesson order and difficulty based on each student's progress.")],
      },
    },
  ],

  automotive: [
    {
      id: 'mt-booking',
      title: 'Service booking AI',
      description: 'Books the right bay and service type from natural language.',
      category: cat('chat'),
      icon: 'spark',
      patch: { ctaPrimary: 'Book service', aiChips: ['Bay AI', 'Service match', 'Online booking'] },
    },
    {
      id: 'mt-status',
      title: 'Status bot',
      description: 'Texts every repair stage — customer never has to call.',
      category: cat('reminders'),
      icon: 'clock',
      patch: { aiChips: ['Status bot', 'SMS updates', 'Progress track'], ctaSecondary: 'Track my car' },
    },
    {
      id: 'mt-parts',
      title: 'Parts ETA tracker',
      description: 'AI updates customers when parts arrive and work can begin.',
      category: cat('automation'),
      icon: 'zap',
      patch: { sections: [section('ai-parts', 'Parts ETA updates', 'Customers notified automatically when parts land and the lift is ready.')] },
    },
    {
      id: 'mt-shop-hub',
      title: 'Shop floor hub',
      description: 'Bay board, tech assignments, and daily throughput in one view.',
      category: cat('ops'),
      icon: 'chart',
      patch: { aiChips: ['Shop hub', 'Bay board', 'Tech assign'] },
    },
    {
      id: 'mt-warranty-check',
      title: 'Warranty checker',
      description: 'Looks up OEM warranty status before quoting out-of-pocket work.',
      category: cat('scoring'),
      icon: 'shield',
      patch: { aiChips: ['Warranty AI', 'OEM lookup', 'Coverage check'] },
    },
    {
      id: 'mt-fleet-diagnostics',
      title: 'Fleet diagnostics',
      description: 'Bulk vehicle health reports for commercial fleet accounts.',
      category: cat('ops'),
      icon: 'users',
      patch: {
        sections: [section('ai-fleet', 'Fleet health dashboard', 'Commercial clients get AI-summarized diagnostics across every vehicle in the lot.')],
        ctaSecondary: 'Fleet report',
      },
    },
  ],

  hospitality: [
    {
      id: 'row-concierge',
      title: 'Concierge AI',
      description: 'Answers amenities, local tips, and upgrade offers 24/7.',
      category: cat('chat'),
      icon: 'spark',
      patch: { aiChips: ['Concierge AI', 'Local tips', 'Upgrades'], ctaSecondary: 'Ask concierge' },
    },
    {
      id: 'row-upsell',
      title: 'Room upsell',
      description: 'AI offers suite upgrades based on availability and stay profile.',
      category: cat('automation'),
      icon: 'zap',
      patch: { sections: [section('ai-upsell', 'Smart upsell', 'Suite and late-checkout offers based on availability and guest profile.')] },
    },
    {
      id: 'row-housekeeping',
      title: 'Housekeeping sync',
      description: 'Room-ready status flows to front desk and guest app.',
      category: cat('ops'),
      icon: 'clock',
      patch: { aiChips: ['Housekeeping sync', 'Room ready', 'Floor ops'] },
    },
    {
      id: 'row-direct',
      title: 'Direct booking',
      description: 'Book direct incentives and abandoned-cart recovery.',
      category: cat('automation'),
      icon: 'chart',
      patch: { ctaPrimary: 'Book direct', aiChips: ['Direct book', 'Best rate', 'Cart recovery'] },
    },
    {
      id: 'row-event-planner',
      title: 'Event planner AI',
      description: 'Weddings and conferences — AI coordinates rooms, catering, and AV.',
      category: cat('scheduling'),
      icon: 'spark',
      patch: {
        aiChips: ['Event AI', 'Group blocks', 'Catering sync'],
        sections: [section('ai-events', 'Group & event planning', 'AI coordinates room blocks, catering, and AV for weddings and conferences.')],
      },
    },
    {
      id: 'row-guest-feedback',
      title: 'Guest feedback digest',
      description: 'Summarizes reviews and in-stay surveys — surfaces issues fast.',
      category: cat('ops'),
      icon: 'chart',
      patch: { aiChips: ['Feedback AI', 'Review digest', 'Issue alerts'] },
    },
  ],

  nonprofit: [
    {
      id: 'hg-donate-ai',
      title: 'Donation assistant',
      description: 'Guides donors through impact, amounts, and recurring gifts.',
      category: cat('chat'),
      icon: 'spark',
      patch: { ctaPrimary: 'Donate now', aiChips: ['Donate AI', 'Impact stories', 'Recurring gifts'] },
    },
    {
      id: 'hg-campaign',
      title: 'Campaign pages',
      description: 'AI-built campaign microsites with goal thermometers.',
      category: cat('automation'),
      icon: 'zap',
      patch: { sections: [section('ai-campaign', 'Campaign builder', 'Launch goal-tracked campaign pages with AI-written impact copy.')] },
    },
    {
      id: 'hg-volunteer',
      title: 'Volunteer matcher',
      description: 'Matches skills and availability to open volunteer shifts.',
      category: cat('scheduling'),
      icon: 'clock',
      patch: { aiChips: ['Volunteer match', 'Shift fill', 'Skills map'], ctaSecondary: 'Volunteer' },
    },
    {
      id: 'hg-donor',
      title: 'Donor nurture',
      description: 'Thank-you sequences and re-engagement for lapsed donors.',
      category: cat('reminders'),
      icon: 'chart',
      patch: { aiChips: ['Donor nurture', 'Thank-you flow', 'Re-engage'] },
    },
    {
      id: 'hg-grant-finder',
      title: 'Grant finder AI',
      description: 'Matches your mission to open grants and drafts LOI outlines.',
      category: cat('scoring'),
      icon: 'shield',
      patch: {
        aiChips: ['Grant match', 'LOI drafts', 'Deadline track'],
        sections: [section('ai-grants', 'Grant discovery', 'AI surfaces matching grants and drafts letter-of-intent outlines for your team.')],
      },
    },
    {
      id: 'hg-impact-dashboard',
      title: 'Impact dashboard',
      description: 'Live beneficiary stats and stories for board reports and donors.',
      category: cat('ops'),
      icon: 'chart',
      patch: {
        heroStats: [
          { label: 'Lives impacted', value: '2,400' },
          { label: 'Programs active', value: '12' },
          { label: 'Volunteer hours', value: '8.2k' },
        ],
        ctaSecondary: 'See our impact',
      },
    },
  ],
};

export function getCatalogForSolution(solutionId: string): AIFeatureCatalogItem[] {
  return AI_FEATURE_CATALOG[solutionId] ?? [];
}

export function isFeatureIntegrated(overlay: { integratedFeatures?: string[] }, featureId: string): boolean {
  return overlay.integratedFeatures?.includes(featureId) ?? false;
}

export function getFeaturePreviewLines(feature: AIFeatureCatalogItem): string[] {
  const lines: string[] = [];
  const p = feature.patch;
  if (p.aiChips?.length) {
    lines.push(`AI chips: ${p.aiChips.join(' · ')}`);
  }
  if (p.sections?.length) {
    const titles = p.sections.map((s) => s.title).filter(Boolean);
    if (titles.length === 1) lines.push(`New section: “${titles[0]}”`);
    else if (titles.length > 1) lines.push(`New sections: ${titles.map((t) => `“${t}”`).join(', ')}`);
  }
  if (p.ctaPrimary) lines.push(`Primary button → “${p.ctaPrimary}”`);
  if (p.ctaSecondary) lines.push(`Secondary button → “${p.ctaSecondary}”`);
  if (p.heroStats?.length) {
    lines.push(`Hero stats: ${p.heroStats.map((s) => `${s.label} ${s.value}`).join(' · ')}`);
  }
  if (p.heroHeadline) lines.push(`Hero headline → “${p.heroHeadline}”`);
  if (p.tagline) lines.push(`Tagline → “${p.tagline}”`);
  return lines;
}
