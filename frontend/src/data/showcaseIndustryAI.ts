/**
 * Per-industry AI automation content for solution showcase demos.
 */
import type { AIWorkflowStep, FeatureCard, JourneyStep, PreviewContent } from '../types/request';

export interface IndustryAIConfig {
  aiWorkflow: AIWorkflowStep[];
  featureCards: FeatureCard[];
  userJourney: JourneyStep[];
  website: NonNullable<PreviewContent['website']>;
  /** Mark team replies as AI-sent in inbox */
  aiInbox?: boolean;
}

const wf = (steps: Array<[string, string]>): AIWorkflowStep[] =>
  steps.map(([title, description], i) => ({ step: i + 1, title, description }));

export const INDUSTRY_AI: Record<string, IndustryAIConfig> = {
  healthcare: {
    aiWorkflow: wf([
      ['AI intake chat', 'Qualifies symptoms, insurance, and treatment interest before a human sees the thread.'],
      ['Smart slot matching', 'Finds open rooms and practitioners — offers 2–3 times instantly.'],
      ['Auto reminders', 'SMS + WhatsApp reminders cut no-shows without front-desk calls.'],
      ['Daily clinic digest', 'Morning summary: who is arriving, open slots, and follow-ups due.'],
    ]),
    featureCards: [
      { title: 'AI patient intake', description: 'Answers FAQs, collects history, and routes to the right treatment — 24/7.', icon: 'spark' },
      { title: 'Instant booking', description: 'Patients pick a slot from live availability — synced to your calendar.', icon: 'clock' },
      { title: 'Reminder automation', description: 'Confirmations and day-before nudges sent automatically across channels.', icon: 'zap' },
      { title: 'Staff dashboard', description: 'One screen for today\'s patients, inquiries, and treatment pipeline.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Patient asks', description: 'DM, WhatsApp, or web chat — AI responds in seconds.' },
      { step: 2, title: 'AI qualifies', description: 'Intake questions answered; slot offered automatically.' },
      { step: 3, title: 'Booked & reminded', description: 'Confirmation + forms sent; reminders on autopilot.' },
      { step: 4, title: 'Team focuses on care', description: 'Dashboard shows who\'s coming — not who to call back.' },
    ],
    website: {
      eyebrow: 'Premium care · AI-assisted intake',
      ai_chips: ['24/7 AI intake', 'Auto booking', 'Smart reminders', 'Zero phone tag'],
      automation_title: 'Your front desk, automated',
      automation_subtitle: 'Harbor Care handles intake, scheduling, and follow-up while your team delivers treatment.',
      social_proof: '4.9★ from 380+ patients · avg reply under 30 seconds',
      testimonial: { quote: 'We cut no-shows in half. Patients book at midnight and AI handles the rest.', name: 'Dr. Elena Chen', role: 'Medical Director, Harbor Wellness', rating: 5 },
      services: [
        { name: 'Hydrafacial', description: 'Deep cleanse + glow — book online in 60 seconds.', duration: '45 min', cta: 'Book now' },
        { name: 'Botox consult', description: 'AI pre-screens questions; consult confirmed instantly.', duration: '30 min', cta: 'Book consult' },
        { name: 'IV wellness drip', description: 'Same-day slots when available — reminders included.', duration: '60 min', cta: 'Check availability' },
      ],
      about_paragraphs: [
        'Harbor Wellness combines clinical excellence with an AI front desk that never sleeps.',
        'From first DM to post-visit follow-up, every touchpoint is branded, fast, and automated.',
      ],
    },
    aiInbox: true,
  },

  'personal-care': {
    aiWorkflow: wf([
      ['DM → booking', 'Instagram and WhatsApp messages become confirmed chair slots automatically.'],
      ['Style memory', 'AI recalls fade type, barber preference, and usual timing for regulars.'],
      ['No-show shield', 'Smart reminders + waitlist backfill when someone cancels.'],
      ['Rebook nudges', 'Loyalty prompts when clients are due — fills slow afternoons.'],
    ]),
    featureCards: [
      { title: 'DM booking bot', description: 'Turn "any slots tomorrow?" into a confirmed chair in one thread.', icon: 'zap' },
      { title: 'Client memory', description: 'Preferences, barber, and history — every regular feels known.', icon: 'users' },
      { title: 'Reminder engine', description: 'Texts before appointments; auto-fills cancellations from waitlist.', icon: 'clock' },
      { title: 'Owner hub', description: 'Chair utilization, rebook rate, and today\'s revenue at a glance.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Client DMs', description: '"Fade tomorrow?" — AI responds instantly.' },
      { step: 2, title: 'Slot locked', description: 'Barber, time, and service confirmed in-chat.' },
      { step: 3, title: 'Reminded', description: 'Auto text before the appointment.' },
      { step: 4, title: 'Rebooked', description: 'AI nudges regulars before they drift away.' },
    ],
    website: {
      eyebrow: 'Studio Nine · Book in seconds',
      ai_chips: ['Instagram booking', 'Style memory', 'Waitlist fill', 'Loyalty nudges'],
      automation_title: 'From DM to chair — zero back-and-forth',
      automation_subtitle: 'Your barbers cut hair. AI handles scheduling, reminders, and rebooks.',
      social_proof: '4.8★ · 2,400+ cuts booked online this year',
      testimonial: { quote: 'Instagram DMs used to kill our flow. Now they book themselves.', name: 'Marcus Reid', role: 'Owner, Studio Nine', rating: 5 },
      services: [
        { name: 'Skin fade', description: 'Most popular — book Jay or Alex online.', duration: '45 min', cta: 'Book fade' },
        { name: 'Cut + beard', description: 'Full groom — AI remembers your last barber.', duration: '60 min', cta: 'Book combo' },
        { name: 'VIP slot', description: 'Priority booking for regulars — loyalty tracked automatically.', duration: '45 min', cta: 'Join VIP' },
      ],
    },
    aiInbox: true,
  },

  food: {
    aiWorkflow: wf([
      ['Menu Q&A bot', 'Answers allergens, specials, and dietary questions on web and WhatsApp.'],
      ['Table optimizer', 'AI suggests best table/section for party size and turn time.'],
      ['Order routing', 'Direct orders hit kitchen display — no aggregator middleman.'],
      ['Guest win-back', 'Repeat diners get personalized offers when they haven\'t visited in 30 days.'],
    ]),
    featureCards: [
      { title: 'AI menu assistant', description: 'Guests ask about dishes, allergens, and wine pairings — instantly.', icon: 'spark' },
      { title: 'Direct ordering', description: 'Branded checkout — keep margin, not platform fees.', icon: 'zap' },
      { title: 'Smart reservations', description: 'Party size, patio vs dining — auto-suggested and confirmed.', icon: 'clock' },
      { title: 'Kitchen ops board', description: 'Live orders, table status, and covers in one view.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Guest discovers', description: 'Menu, reviews, and reserve — cinematic branded site.' },
      { step: 2, title: 'AI assists', description: 'Questions answered; table or order confirmed.' },
      { step: 3, title: 'Kitchen synced', description: 'Orders and reservations flow to staff in real time.' },
      { step: 4, title: 'They come back', description: 'Automated offers bring repeat guests back.' },
    ],
    website: {
      eyebrow: 'Ember & Oak · Direct orders',
      ai_chips: ['Menu AI', 'Table planner', 'Kitchen sync', 'Guest win-back'],
      automation_title: 'Hospitality that runs itself',
      automation_subtitle: 'From party inquiries to kitchen tickets — AI keeps service smooth at peak hours.',
      social_proof: '4.9★ · 34% of revenue from direct orders (no fees)',
      testimonial: { quote: 'Large parties used to mean 20 phone calls. Now AI sends the menu and books the patio.', name: 'Sofia Marin', role: 'GM, Ember & Oak', rating: 5 },
      services: [
        { name: 'Chef\'s tasting', description: '7-course experience — AI handles dietary prefs upfront.', duration: '2.5 hrs', cta: 'Reserve' },
        { name: 'Patio private dining', description: 'Groups up to 12 — set menu link sent automatically.', duration: '3 hrs', cta: 'Inquire' },
        { name: 'Direct delivery', description: 'Order from our site — routed straight to kitchen.', duration: '35–50 min', cta: 'Order now' },
      ],
    },
    aiInbox: true,
  },

  'real-estate': {
    aiWorkflow: wf([
      ['Listing AI agent', 'Answers HOA, schools, and availability on every property page.'],
      ['Lead scoring', 'Hot buyers ranked by budget fit, timeline, and engagement.'],
      ['Viewing scheduler', 'Syncs agent calendars — offers slots without email ping-pong.'],
      ['Follow-up sequences', 'Auto nurture for warm leads who viewed but didn\'t book.'],
    ]),
    featureCards: [
      { title: 'Listing Q&A AI', description: 'Buyers get instant answers — agents get qualified leads.', icon: 'spark' },
      { title: 'Viewing scheduler', description: 'Book tours from the listing page in under a minute.', icon: 'clock' },
      { title: 'Lead scoring', description: 'AI ranks intent so agents call the right people first.', icon: 'chart' },
      { title: 'Agent CRM', description: 'Pipeline, viewings, and follow-ups in one cinematic dashboard.', icon: 'users' },
    ],
    userJourney: [
      { step: 1, title: 'Buyer browses', description: 'Stunning listings with embedded AI chat.' },
      { step: 2, title: 'AI qualifies', description: 'Budget, timeline, and property fit captured.' },
      { step: 3, title: 'Viewing booked', description: 'Agent calendar synced — confirmation sent.' },
      { step: 4, title: 'Agent closes', description: 'Hot leads surfaced — no cold chasing.' },
    ],
    website: {
      eyebrow: 'Northline Realty · AI buyer assistant',
      ai_chips: ['Listing AI', 'Lead scoring', 'Auto viewings', 'Nurture flows'],
      automation_title: 'Every listing works 24/7',
      automation_subtitle: 'Buyers get answers instantly. Agents get viewings on the calendar — not voicemails.',
      social_proof: '23 qualified leads this week · < 2 min avg response',
      testimonial: { quote: 'The AI answered HOA questions at 11pm. We had a viewing booked by morning.', name: 'Alex Porter', role: 'Lead Agent, Northline', rating: 5 },
      services: [
        { name: 'Buy a home', description: 'AI matches listings to budget and neighborhood prefs.', cta: 'Start search' },
        { name: 'Sell with us', description: 'Automated valuation request + agent callback scheduling.', cta: 'Get valuation' },
        { name: 'Book a viewing', description: 'Pick a slot from live agent availability.', cta: 'Schedule tour' },
      ],
    },
    aiInbox: true,
  },

  fitness: {
    aiWorkflow: wf([
      ['Class recommender', 'AI suggests programs based on goals and attendance history.'],
      ['Reschedule bot', 'Members move sessions in-app — calendar updates instantly.'],
      ['Renewal predictor', 'Flags at-risk members before they churn; auto-offers incentives.'],
      ['Coach digest', 'Daily adherence snapshot — who needs a nudge today.'],
    ]),
    featureCards: [
      { title: 'Smart class booking', description: 'Members book HIIT, yoga, or 1:1 — fill rate optimized by AI.', icon: 'zap' },
      { title: 'Progress tracking', description: 'Check-ins, habits, and photos — coaches see who\'s slipping.', icon: 'chart' },
      { title: 'Renewal automation', description: 'Reminders and win-back offers before memberships lapse.', icon: 'clock' },
      { title: 'Coach command center', description: 'Retention, class fill, and member chat in one hub.', icon: 'users' },
    ],
    userJourney: [
      { step: 1, title: 'Member joins', description: 'Trial or class pack — onboarding automated.' },
      { step: 2, title: 'AI coaches adherence', description: 'Reminders, reschedules, and program nudges.' },
      { step: 3, title: 'Progress visible', description: 'Member and coach see the same dashboard.' },
      { step: 4, title: 'Renewals handled', description: 'AI flags churn risk — offers sent automatically.' },
    ],
    website: {
      eyebrow: 'Peak Form · Train smarter',
      ai_chips: ['Class AI', 'Reschedule bot', 'Churn alerts', 'Coach digest'],
      automation_title: 'Retention on autopilot',
      automation_subtitle: 'Members stay accountable. Coaches see who needs attention — before they cancel.',
      social_proof: '89% 30-day retention · 142 active members',
      testimonial: { quote: 'Renewals used to slip through cracks. AI nudges members a week before they drift.', name: 'Coach Sam Liu', role: 'Head Coach, Peak Form', rating: 5 },
      services: [
        { name: 'HIIT unlimited', description: 'Peak-hour classes — AI optimizes your weekly schedule.', cta: 'Start trial' },
        { name: '12-week transform', description: 'Structured program with automated check-ins.', cta: 'Join program' },
        { name: '1:1 coaching', description: 'Book directly — progress synced to your coach.', cta: 'Book session' },
      ],
    },
    aiInbox: true,
  },

  'professional-services': {
    aiWorkflow: wf([
      ['Conflict scan', 'AI clears new matters against active client roster before consult is offered.'],
      ['Clause review', 'Uploaded contracts scanned — indemnity, liability, and termination risks flagged.'],
      ['Vault chaser', 'Encrypted doc requests with auto-reminders until billable-ready.'],
      ['Engagement draft', 'Letters pre-filled from matter data — partners review, not re-ask.'],
    ]),
    featureCards: [
      { title: 'Conflict scan', description: 'Instant clearance — no surprise conflicts after consult.', icon: 'shield' },
      { title: 'Clause review AI', description: 'Risk flags in vendor agreements before partner review.', icon: 'spark' },
      { title: 'Vault chaser', description: 'Auto-reminders until every file lands in secure vault.', icon: 'clock' },
      { title: 'Engagement draft', description: 'Letters 80% done from matter brief — billable faster.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Conflict cleared', description: 'Counsel AI scans roster — consult only when clear.' },
      { step: 2, title: 'Clause + vault', description: 'Contracts reviewed; missing files chased automatically.' },
      { step: 3, title: 'Partner consult', description: 'Calendar synced — brief includes clause flags.' },
      { step: 4, title: 'Billable-ready', description: 'Engagement drafted — partners advise, not chase.' },
    ],
    website: {
      eyebrow: 'Apex Legal · Counsel AI',
      ai_chips: ['Conflict scan', 'Clause review', 'Vault chaser', 'Engagement draft'],
      automation_title: 'Lawyers bill counsel — AI runs the admin layer',
      automation_subtitle: 'Conflict checks, clause flags, vault chasing, and engagement drafts — before partners bill a minute.',
      social_proof: '9 billable-ready this week · 0 conflict surprises · SOC2 vault',
      testimonial: { quote: 'Clause AI flagged indemnity before Rachel ever opened the file. That used to be a six-email spiral.', name: 'Rachel Holt', role: 'Partner, Apex Legal', rating: 5 },
    },
    aiInbox: true,
  },

  ecommerce: {
    aiWorkflow: wf([
      ['Natural search', 'Shoppers describe what they want — AI finds the right products.'],
      ['Smart bundles', 'Recommendations based on cart, season, and purchase history.'],
      ['Order assistant', 'Where is my order? Returns? AI resolves without support tickets.'],
      ['Inventory alerts', 'Low-stock and reorder suggestions for the seller dashboard.'],
    ]),
    featureCards: [
      { title: 'AI product search', description: '"Warm minimalist lamp for bedroom" — finds exact matches.', icon: 'spark' },
      { title: 'Smart recommendations', description: 'Bundles and upsells that feel helpful, not spammy.', icon: 'zap' },
      { title: 'Support automation', description: 'Order status and returns handled in chat.', icon: 'clock' },
      { title: 'Seller dashboard', description: 'Inventory, orders, and fulfillment in one cinematic view.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Shopper searches', description: 'Natural language — not filter maze.' },
      { step: 2, title: 'AI curates', description: 'Perfect matches and styled bundles.' },
      { step: 3, title: 'Checkout', description: 'Branded, fast, tracked end-to-end.' },
      { step: 4, title: 'You fulfill', description: 'Dashboard shows what to ship today.' },
    ],
    website: {
      eyebrow: 'Lumen Home · AI-powered shop',
      ai_chips: ['Natural search', 'Smart bundles', 'Order AI', 'Stock alerts'],
      automation_title: 'A storefront that understands shoppers',
      automation_subtitle: 'Discovery, support, and ops — automated so you scale without hiring.',
      social_proof: '4.8★ · 12k orders · 38% higher AOV with AI recs',
      testimonial: { quote: 'Customers describe vibes and AI finds the product. Support tickets dropped 40%.', name: 'Mia Chen', role: 'Founder, Lumen Home', rating: 5 },
    },
    aiInbox: true,
  },

  'home-services': {
    aiWorkflow: wf([
      ['Quote intake', 'AI captures job details, photos, and urgency from web or SMS.'],
      ['Dispatch optimizer', 'Routes jobs to nearest available tech by skill and location.'],
      ['Status updates', 'Customers get "on the way" and "job complete" automatically.'],
      ['Review requests', 'Five-star follow-ups sent after every completed job.'],
    ]),
    featureCards: [
      { title: 'Instant quote flow', description: 'Customers describe the job — AI prices and schedules.', icon: 'zap' },
      { title: 'Smart dispatch', description: 'Right tech, right time — no whiteboard chaos.', icon: 'users' },
      { title: 'Live job status', description: 'Homeowners track progress without calling the office.', icon: 'clock' },
      { title: 'Ops dashboard', description: 'Jobs, techs, and revenue today — one screen.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Customer requests', description: 'Quote form or SMS — AI qualifies the job.' },
      { step: 2, title: 'Tech dispatched', description: 'Calendar + route optimized automatically.' },
      { step: 3, title: 'Status shared', description: 'En route → in progress → done.' },
      { step: 4, title: 'Review collected', description: 'Automated ask for Google review.' },
    ],
    website: {
      eyebrow: 'BrightFix · Same-day service',
      ai_chips: ['Quote AI', 'Auto dispatch', 'Live status', 'Review bot'],
      automation_title: 'From leak to dispatched — in minutes',
      automation_subtitle: 'Fewer phone calls. Fuller schedules. Happier homeowners.',
      social_proof: '4.9★ · 1,800+ jobs completed · avg response 4 min',
      testimonial: { quote: 'Emergency calls get quoted and scheduled while I\'m still on the first job.', name: 'Tom Bright', role: 'Owner, BrightFix', rating: 5 },
    },
    aiInbox: true,
  },

  education: {
    aiWorkflow: wf([
      ['Session matcher', 'AI pairs students with the right tutor by subject and level.'],
      ['Homework reminders', 'Automated nudges before sessions with materials attached.'],
      ['Progress reports', 'Weekly summaries for parents — no manual email blasts.'],
      ['Payment automation', 'Packages, renewals, and receipts handled in-app.'],
    ]),
    featureCards: [
      { title: 'Smart scheduling', description: 'Students book tutors that fit their level and goals.', icon: 'clock' },
      { title: 'Material delivery', description: 'AI sends prep packs before each session.', icon: 'spark' },
      { title: 'Parent updates', description: 'Automated progress reports — professional and timely.', icon: 'chart' },
      { title: 'Tutor dashboard', description: 'Sessions, students, and payments in one place.', icon: 'users' },
    ],
    userJourney: [
      { step: 1, title: 'Student books', description: 'Subject, level, and availability captured.' },
      { step: 2, title: 'AI prepares', description: 'Materials and reminders sent automatically.' },
      { step: 3, title: 'Session delivered', description: 'Tutor focuses on teaching.' },
      { step: 4, title: 'Parents informed', description: 'Progress report lands in inbox.' },
    ],
    website: {
      eyebrow: 'Summit Tutoring · Results-driven',
      ai_chips: ['Tutor match', 'Prep automation', 'Parent reports', 'Auto billing'],
      automation_title: 'Teaching time protected',
      automation_subtitle: 'Scheduling, materials, and parent comms — automated around every session.',
      social_proof: '4.9★ · 94% parent satisfaction · 320 active students',
      testimonial: { quote: 'Parents get weekly updates without us writing a single email.', name: 'Dr. Nina Patel', role: 'Director, Summit Tutoring', rating: 5 },
    },
    aiInbox: true,
  },

  automotive: {
    aiWorkflow: wf([
      ['Service intake', 'AI captures VIN, symptoms, and photos for accurate estimates.'],
      ['Bay scheduler', 'Optimizes lift schedule by job type and parts availability.'],
      ['Status bot', 'Customers ask "is my car ready?" — AI answers from shop floor data.'],
      ['Service reminders', 'Oil change and inspection nudges based on mileage and history.'],
    ]),
    featureCards: [
      { title: 'Online service book', description: 'Customers pick service type and slot — synced to bays.', icon: 'clock' },
      { title: 'Status automation', description: '"In progress" and "ready for pickup" — no hold music.', icon: 'zap' },
      { title: 'Parts-aware scheduling', description: 'AI avoids booking jobs when parts aren\'t in stock.', icon: 'shield' },
      { title: 'Shop dashboard', description: 'Bays, techs, and today\'s revenue in real time.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Driver books', description: 'Service type + time online.' },
      { step: 2, title: 'Shop prepared', description: 'AI flags parts and bay assignment.' },
      { step: 3, title: 'Live updates', description: 'Customer notified at each stage.' },
      { step: 4, title: 'They return', description: 'Maintenance reminders keep bays full.' },
    ],
    website: {
      eyebrow: 'Metro Auto Care · Book online',
      ai_chips: ['Service intake', 'Bay scheduler', 'Status bot', 'Maintenance AI'],
      automation_title: 'Full bays, fewer phone calls',
      automation_subtitle: 'Drivers book and track service. Your team works — doesn\'t answer "is it ready?"',
      social_proof: '4.8★ · 6 bays · 92% schedule utilization',
      testimonial: { quote: 'Status texts cut our front-desk calls in half. Bays stay packed.', name: 'Mike Torres', role: 'Service Manager, Metro Auto', rating: 5 },
    },
    aiInbox: true,
  },

  hospitality: {
    aiWorkflow: wf([
      ['AI concierge', 'Answers amenities, local tips, and policies in any language.'],
      ['Direct booking engine', 'Best rate on your site — no OTA commission.'],
      ['Pre-arrival flow', 'Check-in details, upsells, and room prefs collected automatically.'],
      ['Guest win-back', 'Personalized offers when past guests haven\'t rebooked.'],
    ]),
    featureCards: [
      { title: '24/7 concierge AI', description: 'Guests get answers instantly — staff handle exceptions only.', icon: 'spark' },
      { title: 'Direct bookings', description: 'Commission-free reservations on your branded site.', icon: 'zap' },
      { title: 'Pre-arrival automation', description: 'Upsells, preferences, and check-in info collected pre-stay.', icon: 'clock' },
      { title: 'Guest ops hub', description: 'Occupancy, requests, and housekeeping in one dashboard.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Guest discovers', description: 'Cinematic hotel site with live availability.' },
      { step: 2, title: 'AI assists', description: 'Questions answered; booking confirmed direct.' },
      { step: 3, title: 'Pre-stay polished', description: 'Preferences and upsells handled automatically.' },
      { step: 4, title: 'They rebook', description: 'Win-back offers bring guests back direct.' },
    ],
    website: {
      eyebrow: 'The Row Hotel · Direct book',
      ai_chips: ['AI concierge', 'Direct rates', 'Pre-arrival flow', 'Guest win-back'],
      automation_title: 'Five-star experience — automated scale',
      automation_subtitle: 'Concierge-quality answers at 2am. Staff focus on in-person magic.',
      social_proof: '4.9★ · 78% direct bookings · multilingual AI',
      testimonial: { quote: 'Guests ask about parking at midnight. AI answers; we sleep.', name: 'Claire Dubois', role: 'GM, The Row Hotel', rating: 5 },
    },
    aiInbox: true,
  },

  nonprofit: {
    aiWorkflow: wf([
      ['Donation assistant', 'AI explains impact tiers and handles one-click gifts.'],
      ['Volunteer matcher', 'Skills and availability matched to open shifts automatically.'],
      ['Campaign updates', 'Donors get personalized impact stories on schedule.'],
      ['Grant digest', 'Team dashboard summarizes applications and deadlines due.'],
    ]),
    featureCards: [
      { title: 'Smart donate flow', description: 'Impact tiers explained — conversion optimized by AI.', icon: 'spark' },
      { title: 'Volunteer scheduling', description: 'Sign-ups, reminders, and shift fill automation.', icon: 'users' },
      { title: 'Donor nurture', description: 'Thank-you sequences and impact updates on autopilot.', icon: 'zap' },
      { title: 'Team dashboard', description: 'Campaigns, volunteers, and grants in one view.', icon: 'chart' },
    ],
    userJourney: [
      { step: 1, title: 'Supporter lands', description: 'Campaign page with clear impact story.' },
      { step: 2, title: 'AI guides gift', description: 'Amount, recurring, and thank-you instant.' },
      { step: 3, title: 'Volunteers sign up', description: 'Matched to the right events automatically.' },
      { step: 4, title: 'Team reports', description: 'Dashboard shows progress toward goal.' },
    ],
    website: {
      eyebrow: 'Harbor Community Fund · Give with impact',
      ai_chips: ['Donate AI', 'Volunteer match', 'Donor nurture', 'Grant digest'],
      automation_title: 'More impact — less admin',
      automation_subtitle: 'Fundraising, volunteers, and donor comms automated for lean teams.',
      social_proof: '$240k raised this quarter · 1,200 volunteers placed',
      testimonial: { quote: 'We\'re a team of four. AI handles donor follow-up we never had time for.', name: 'James Okonkwo', role: 'Executive Director, Harbor Fund', rating: 5 },
    },
    aiInbox: true,
  },
};

export function getIndustryAI(id: string): IndustryAIConfig | undefined {
  return INDUSTRY_AI[id];
}

export function tagAiMessages<T extends { role: string; text: string; ai_assisted?: boolean }>(
  messages: T[],
  enabled: boolean,
): T[] {
  if (!enabled) return messages;
  return messages.map((m) => (m.role === 'team' ? { ...m, ai_assisted: true } : m));
}
