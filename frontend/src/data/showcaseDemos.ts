/**
 * Hand-built interactive demos for each industry on /solutions — no AI pipeline.
 * Each entry feeds AppExperience with seeded copy, metrics, and flows tuned to sell.
 */
import type { AppConfig, PreviewContent, VisualDemo } from '../types/request';
import { getSolutionById, type IndustrySolution } from './solutions';
import { getIndustryAI, tagAiMessages } from './showcaseIndustryAI';

export interface SolutionShowcase {
  solutionId: string;
  businessName: string;
  industry: string;
  /** Shown in the fake browser URL bar */
  demoSlug: string;
  demo: VisualDemo;
}

interface ShowcasePalette {
  primary: string;
  secondary: string;
  background: string;
}

interface ShowcaseSpec {
  businessName: string;
  productName: string;
  demoSlug: string;
  industry: string;
  palette: ShowcasePalette;
  heroHeadline: string;
  heroSub: string;
  primaryCta: string;
  secondaryCta: string;
  appConfig: AppConfig;
  previewContent: PreviewContent;
  dashboardCards: Array<{ title: string; value: string; description: string }>;
  recentActivity: string[];
}

const ICONS = ['spark', 'shield', 'chart', 'zap', 'users', 'clock'];

function baseDemo(
  solution: IndustrySolution,
  spec: ShowcaseSpec,
): VisualDemo {
  const ai = getIndustryAI(solution.id);
  const features = ai?.featureCards ?? solution.capabilities.slice(0, 4).map((cap, i) => ({
    title: cap.split(' ').slice(0, 4).join(' '),
    description: cap,
    icon: ICONS[i % ICONS.length],
  }));

  const previewContent: PreviewContent = {
    ...spec.previewContent,
    image_theme: spec.previewContent.image_theme,
    website: {
      ...ai?.website,
      ...spec.previewContent.website,
    },
    inbox: spec.previewContent.inbox
      ? {
          ...spec.previewContent.inbox,
          messages: tagAiMessages(spec.previewContent.inbox.messages ?? [], ai?.aiInbox ?? false),
        }
      : spec.previewContent.inbox,
  };

  return {
    product_name: spec.productName,
    visual_theme: {
      style: 'cinematic',
      primary_color: spec.palette.primary,
      secondary_color: spec.palette.secondary,
      background_color: spec.palette.background,
      font_style: 'sans',
    },
    hero: {
      headline: spec.heroHeadline,
      subheadline: spec.heroSub,
      primary_cta: spec.primaryCta,
      secondary_cta: spec.secondaryCta,
    },
    feature_cards: features,
    user_journey: ai?.userJourney ?? [
      { step: 1, title: 'Discover', description: 'Clients find you online or through social.' },
      { step: 2, title: 'Engage', description: 'AI answers, qualifies, and books without phone tag.' },
      { step: 3, title: 'Automate', description: 'Reminders, follow-ups, and status updates run themselves.' },
      { step: 4, title: 'Grow', description: 'Your dashboard shows what matters — leads, revenue, retention.' },
    ],
    screen_mockups: [],
    admin_dashboard_preview: {
      should_show: true,
      cards: spec.dashboardCards,
      recent_activity: spec.recentActivity,
    },
    ai_workflow: ai?.aiWorkflow ?? [],
    final_cta: {
      headline: ai ? `Ready to automate ${spec.businessName}?` : `Ready for ${spec.businessName}?`,
      description: 'We customize this AI-powered platform to your brand and launch it for you.',
      button_text: 'Get started',
    },
    preview_content: previewContent,
    app_config: {
      ...spec.appConfig,
      home_sections: ['hero', 'features', 'ai', 'programs', 'journey', 'testimonial', 'cta'],
    },
  };
}

function scheduleAppts(
  items: Array<{ time: string; client: string; service: string; status: 'confirmed' | 'available' | 'pending' }>,
  weekStat: string,
  weekDetail: string,
): PreviewContent['schedule'] {
  return { appointments: items, week_stat: weekStat, week_detail: weekDetail };
}

function leads(rows: Array<{ name: string; source: string; service: string; status: string }>): PreviewContent['dashboard'] {
  return { leads: rows };
}

function appShell(partial: AppConfig): AppConfig {
  return {
    enabled_modules: ['website', 'inbox', 'schedule', 'dashboard'],
    schedule_variant: 'calendar',
    header_variant: 'light',
    hero_layout: 'split',
    home_sections: ['hero', 'features', 'programs', 'journey', 'cta'],
    ...partial,
  };
}

const SPECS: Record<string, ShowcaseSpec> = {
  healthcare: {
    businessName: 'Harbor Wellness Clinic',
    productName: 'Harbor Care',
    demoSlug: 'harborcare.app',
    industry: 'Healthcare & Clinics',
    palette: { primary: '#0284c7', secondary: '#06b6d4', background: '#f0f9ff' },
    heroHeadline: 'Book care online — without the phone maze',
    heroSub: 'AI intake, instant booking, and a calm patient experience your front desk will love.',
    primaryCta: 'Book appointment',
    secondaryCta: 'See treatments',
    appConfig: appShell({
      website_nav: [
        { id: 'home', label: 'Home' },
        { id: 'services', label: 'Treatments' },
        { id: 'about', label: 'Our team' },
        { id: 'contact', label: 'Book' },
      ],
      tabs: [
        { id: 'website', label: 'Patient site', short: 'Site', url_segment: '' },
        { id: 'inbox', label: 'Patient inbox', short: 'Inbox', url_segment: 'inbox' },
        { id: 'schedule', label: 'Appointments', short: 'Appts', url_segment: 'calendar' },
        { id: 'dashboard', label: 'Clinic admin', short: 'Admin', url_segment: 'dashboard' },
      ],
      features_section: { title: 'Everything patients expect — built in', subtitle: 'Intake, booking, reminders, and follow-up in one place.' },
      inbox: { title: 'Patient inbox', subtitle: 'WhatsApp, Instagram & web inquiries', footer: 'Clinic communication hub', status_label: 'New inquiry', quick_replies: ['Slot Thu 2pm', 'Send intake form', 'Confirm visit'] },
      schedule: { title: 'Today\'s schedule', subtitle: 'Rooms & practitioners', add_button: '+ Block slot', today_label: 'Today\'s appointments', slots_label: 'Open slots' },
      dashboard: {
        greeting: 'Good morning, Dr. Chen',
        subtitle: '12 appointments today · 3 new intakes to review',
        nav: [{ id: 'overview', label: 'Overview' }, { id: 'leads', label: 'Inquiries' }, { id: 'bookings', label: 'Appointments' }, { id: 'clients', label: 'Patients' }, { id: 'settings', label: 'Settings' }],
        leads_panel: 'New inquiries',
        bookings_panel: 'Today\'s appointments',
        clients_panel: 'Recent patients',
        fourth_metric: { title: 'No-show rate', value: '4%', sub: 'Down 38% vs last month' },
        settings_labels: ['Clinic profile', 'Treatment menu', 'WhatsApp connected', 'Reminder templates'],
      },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'Sarah M.', channel: 'Instagram', preview: 'Do you have Botox consults this week?', time: '2m', unread: true },
          { name: 'James L.', channel: 'WhatsApp', preview: 'Can I reschedule to Friday?', time: '18m' },
          { name: 'Emma R.', channel: 'Web chat', preview: 'What\'s included in the facial package?', time: '1h' },
        ],
        messages: [
          { role: 'user', text: 'Hi — do you have availability for a consult this Thursday?' },
          { role: 'team', text: 'Yes! We have 2:30pm or 4:00pm with Dr. Chen. Which works for you?' },
          { role: 'user', text: '2:30 works. Do I fill anything out beforehand?' },
        ],
        booked_banner: 'Intake form sent — appointment confirmed for Thu 2:30pm',
      },
      schedule: scheduleAppts(
        [
          { time: '9:00', client: 'Maria K.', service: 'Hydrafacial', status: 'confirmed' },
          { time: '10:30', client: 'David P.', service: 'Consult', status: 'confirmed' },
          { time: '14:00', client: 'Sarah M.', service: 'Botox consult', status: 'pending' },
          { time: '16:00', client: 'Lisa T.', service: 'Follow-up', status: 'confirmed' },
        ],
        '94%',
        'Booking fill rate this week',
      ),
      dashboard: leads([
        { name: 'Sarah M.', source: 'Instagram', service: 'Botox consult', status: 'Hot' },
        { name: 'James L.', source: 'WhatsApp', service: 'Reschedule', status: 'Active' },
        { name: 'Priya N.', source: 'Google', service: 'New patient', status: 'New' },
      ]),
    },
    dashboardCards: [
      { title: 'Appointments today', value: '12', description: '3 arriving in next hour' },
      { title: 'New inquiries', value: '8', description: '+3 since yesterday' },
      { title: 'Active patients', value: '486', description: 'Returning this quarter' },
      { title: 'No-show rate', value: '4%', description: 'Automated reminders on' },
    ],
    recentActivity: ['Sarah M. booked Botox consult', 'Intake form completed — James L.', 'Reminder sent — Maria K. 9am', 'New inquiry from Instagram — Emma R.'],
  },

  'personal-care': {
    businessName: 'Studio Nine Barbers',
    productName: 'Studio Nine',
    demoSlug: 'studionine.app',
    industry: 'Barbershop & Salon',
    palette: { primary: '#7c3aed', secondary: '#d946ef', background: '#faf5ff' },
    heroHeadline: 'Fill every chair — clients book in seconds',
    heroSub: 'Online booking, automatic reminders, and client history so regulars never slip away.',
    primaryCta: 'Book a cut',
    secondaryCta: 'View services',
    appConfig: appShell({
      website_nav: [
        { id: 'home', label: 'Home' },
        { id: 'services', label: 'Services' },
        { id: 'about', label: 'Barbers' },
        { id: 'contact', label: 'Book' },
      ],
      tabs: [
        { id: 'website', label: 'Salon site', short: 'Site', url_segment: '' },
        { id: 'inbox', label: 'Client DMs', short: 'DMs', url_segment: 'inbox' },
        { id: 'schedule', label: 'Chair calendar', short: 'Book', url_segment: 'calendar' },
        { id: 'dashboard', label: 'Owner hub', short: 'Hub', url_segment: 'admin' },
      ],
      features_section: { title: 'Built for busy chairs', subtitle: 'Booking, reminders, and loyalty — no more Instagram DM chaos.' },
      inbox: { title: 'Client messages', subtitle: 'Instagram, WhatsApp & SMS', footer: 'Unified client inbox', status_label: 'Booking request', quick_replies: ['Booked ✓', 'See you Thursday!', 'Added to waitlist'] },
      schedule: { title: 'Chair schedule', subtitle: 'Marcus · Jay · Alex', add_button: '+ Walk-in', today_label: 'Today\'s bookings', slots_label: 'Open slots' },
      dashboard: {
        greeting: 'Today at Studio Nine',
        subtitle: '18 bookings · 2 open chairs this afternoon',
        fourth_metric: { title: 'Rebook rate', value: '71%', sub: 'Clients back within 6 weeks' },
        settings_labels: ['Salon profile', 'Service menu', 'Instagram connected', 'Reminder timing'],
      },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'Mike T.', channel: 'Instagram', preview: 'Can I get a fade tomorrow?', time: '5m', unread: true },
          { name: 'Chris D.', channel: 'WhatsApp', preview: 'Same time next month?', time: '22m' },
        ],
        messages: [
          { role: 'user', text: 'Yo — any slots tomorrow around 5?' },
          { role: 'team', text: 'Jay has 5:15 or 6:00 open. Skin fade + beard?' },
          { role: 'user', text: '5:15 perfect. Book it' },
        ],
      },
      schedule: scheduleAppts(
        [
          { time: '11:00', client: 'Alex R.', service: 'Skin fade', status: 'confirmed' },
          { time: '12:30', client: 'Jordan P.', service: 'Cut + beard', status: 'confirmed' },
          { time: '17:15', client: 'Mike T.', service: 'Skin fade', status: 'confirmed' },
        ],
        '96%',
        'Chair utilization today',
      ),
      dashboard: leads([
        { name: 'Mike T.', source: 'Instagram', service: 'Skin fade', status: 'Booked' },
        { name: 'Chris D.', source: 'WhatsApp', service: 'Rebook', status: 'Due' },
      ]),
    },
    dashboardCards: [
      { title: 'Bookings today', value: '18', description: '2 walk-ins added' },
      { title: 'No-shows prevented', value: '6', description: 'Auto-reminders this week' },
      { title: 'Regular clients', value: '214', description: 'On loyalty track' },
      { title: 'Rebook rate', value: '71%', description: 'Up 12% this month' },
    ],
    recentActivity: ['Mike T. booked via Instagram', 'Reminder sent — Jordan P.', 'Chris D. rebooked for next month', 'Loyalty offer sent — 8 clients'],
  },

  food: {
    businessName: 'Ember & Oak Kitchen',
    productName: 'Ember Order',
    demoSlug: 'emberorder.app',
    industry: 'Restaurant & Cafe',
    palette: { primary: '#ea580c', secondary: '#f59e0b', background: '#fffbeb' },
    heroHeadline: 'Order direct — keep every dollar',
    heroSub: 'Branded online menu, table reservations, and a live kitchen board your staff actually uses.',
    primaryCta: 'Order now',
    secondaryCta: 'Reserve a table',
    appConfig: appShell({
      website_nav: [
        { id: 'home', label: 'Home' },
        { id: 'services', label: 'Menu' },
        { id: 'about', label: 'Story' },
        { id: 'contact', label: 'Reserve' },
      ],
      tabs: [
        { id: 'website', label: 'Guest site', short: 'Site', url_segment: '' },
        { id: 'inbox', label: 'Guest messages', short: 'Inbox', url_segment: 'inbox' },
        { id: 'schedule', label: 'Reservations', short: 'Tables', url_segment: 'reservations' },
        { id: 'dashboard', label: 'Kitchen ops', short: 'Ops', url_segment: 'admin' },
      ],
      features_section: { title: 'Direct orders & smooth service', subtitle: 'Menu, reservations, and order flow — no aggregator fees on direct sales.' },
      inbox: { title: 'Guest inbox', subtitle: 'Delivery questions & large party requests', footer: 'Front-of-house hub', status_label: 'Party of 8', quick_replies: ['Table ready', '45 min wait', 'Custom menu sent'] },
      schedule: { title: 'Table plan', subtitle: 'Main dining · patio · bar', add_button: '+ Walk-in', today_label: 'Tonight\'s reservations', slots_label: 'Open tables' },
      dashboard: {
        greeting: 'Kitchen dashboard',
        subtitle: '34 covers tonight · 12 orders in queue',
        leads_panel: 'Catering leads',
        bookings_panel: 'Reservations',
        clients_panel: 'Repeat guests',
        fourth_metric: { title: 'Direct orders', value: '€2.4k', sub: 'Today — no platform fees' },
        settings_labels: ['Menu manager', 'Table layout', 'Delivery zones', 'POS sync'],
      },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'Party of 8', channel: 'Web', preview: 'Birthday dinner Saturday — private area?', time: '8m', unread: true },
          { name: 'Tom H.', channel: 'WhatsApp', preview: 'Is the truffle pasta still on the menu?', time: '25m' },
        ],
        messages: [
          { role: 'user', text: 'Can we book a table for 8 this Saturday around 7:30?' },
          { role: 'team', text: 'We can do patio private section at 7:45 — I\'ll send a set menu link.' },
        ],
      },
      schedule: scheduleAppts(
        [
          { time: '18:00', client: 'Miller party (4)', service: 'Table 12', status: 'confirmed' },
          { time: '19:30', client: 'Chen (2)', service: 'Bar', status: 'confirmed' },
          { time: '20:15', client: 'Birthday (8)', service: 'Patio', status: 'pending' },
        ],
        '87%',
        'Table occupancy tonight',
      ),
      dashboard: leads([
        { name: 'Birthday party', source: 'Website', service: 'Patio 8-top', status: 'Pending' },
        { name: 'Tom H.', source: 'WhatsApp', service: 'Delivery', status: 'Ordered' },
      ]),
    },
    dashboardCards: [
      { title: 'Orders today', value: '47', description: '12 in kitchen now' },
      { title: 'Reservations', value: '22', description: '6 arriving next hour' },
      { title: 'Direct revenue', value: '€2.4k', description: 'No aggregator cut' },
      { title: 'Avg ticket', value: '€38', description: '+€6 vs last week' },
    ],
    recentActivity: ['New order #1842 — delivery', 'Table 12 marked seated', 'Party of 8 inquiry — menu sent', 'Repeat guest — Tom H. ordered again'],
  },

  'real-estate': {
    businessName: 'Northline Realty',
    productName: 'Northline',
    demoSlug: 'northline.app',
    industry: 'Real Estate',
    palette: { primary: '#4f46e5', secondary: '#2563eb', background: '#eef2ff' },
    heroHeadline: 'Capture buyers the moment they view a listing',
    heroSub: 'AI answers property questions, books viewings, and scores leads before they go cold.',
    primaryCta: 'Browse listings',
    secondaryCta: 'Book a viewing',
    appConfig: appShell({
      website_nav: [
        { id: 'home', label: 'Home' },
        { id: 'services', label: 'Listings' },
        { id: 'about', label: 'Agents' },
        { id: 'contact', label: 'Valuation' },
      ],
      tabs: [
        { id: 'website', label: 'Listings site', short: 'Site', url_segment: '' },
        { id: 'inbox', label: 'Buyer inbox', short: 'Inbox', url_segment: 'inbox' },
        { id: 'schedule', label: 'Viewings', short: 'View', url_segment: 'viewings' },
        { id: 'dashboard', label: 'Agent CRM', short: 'CRM', url_segment: 'admin' },
      ],
      features_section: { title: 'From browse to booked viewing', subtitle: 'Listings, AI Q&A, and a pipeline your agents trust.' },
      dashboard: {
        greeting: 'Agent pipeline',
        subtitle: '14 hot leads · 6 viewings today',
        leads_panel: 'Hot leads',
        bookings_panel: 'Viewings today',
        fourth_metric: { title: 'Avg response', value: '< 2m', sub: 'AI + agent handoff' },
        settings_labels: ['Agency profile', 'Listing feed', 'CRM sync', 'Viewing rules'],
      },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'Alex P.', channel: 'Listing chat', preview: 'Is 22 Oak Lane still available?', time: '3m', unread: true },
          { name: 'Nina S.', channel: 'WhatsApp', preview: 'Can we view Saturday morning?', time: '40m' },
        ],
        messages: [
          { role: 'user', text: 'What\'s the HOA fee on the 3-bed on Oak Lane?' },
          { role: 'team', text: '$240/mo — parking included. Want to book a viewing? Sat 10am is open.' },
        ],
      },
      schedule: scheduleAppts(
        [
          { time: '10:00', client: 'Alex P.', service: '22 Oak Lane', status: 'confirmed' },
          { time: '14:30', client: 'Nina S.', service: 'Park View #4', status: 'confirmed' },
        ],
        '23',
        'Qualified leads this week',
      ),
      dashboard: leads([
        { name: 'Alex P.', source: 'Listing AI', service: '22 Oak Lane', status: 'Hot' },
        { name: 'Nina S.', source: 'WhatsApp', service: 'Park View', status: 'Warm' },
      ]),
    },
    dashboardCards: [
      { title: 'Hot leads', value: '14', description: 'AI-scored this week' },
      { title: 'Viewings today', value: '6', description: '2 need follow-up' },
      { title: 'Listings live', value: '38', description: 'Across 3 agents' },
      { title: 'Avg response', value: '< 2m', description: 'AI + agent' },
    ],
    recentActivity: ['Alex P. booked viewing — Oak Lane', 'AI answered HOA question', 'Nina S. confirmed Sat viewing', 'New lead — Park View inquiry'],
  },

  fitness: {
    businessName: 'Peak Form Studio',
    productName: 'Peak Form',
    demoSlug: 'peakform.app',
    industry: 'Gym & Fitness',
    palette: { primary: '#059669', secondary: '#0d9488', background: '#ecfdf5' },
    heroHeadline: 'Members book, track, and stay accountable',
    heroSub: 'Class scheduling, memberships, and progress tracking — retention on autopilot.',
    primaryCta: 'Start free trial',
    secondaryCta: 'View classes',
    appConfig: appShell({
      header_variant: 'dark',
      schedule_variant: 'progress',
      bookings_panel_mode: 'programs',
      leads_panel_mode: 'adherence',
      website_nav: [
        { id: 'home', label: 'Home' },
        { id: 'services', label: 'Programs' },
        { id: 'about', label: 'Coaches' },
        { id: 'contact', label: 'Join' },
      ],
      tabs: [
        { id: 'website', label: 'Gym site', short: 'Site', url_segment: '' },
        { id: 'inbox', label: 'Member chat', short: 'Chat', url_segment: 'messages' },
        { id: 'schedule', label: 'Progress', short: 'Track', url_segment: 'progress' },
        { id: 'dashboard', label: 'Coach hub', short: 'Hub', url_segment: 'admin' },
      ],
      dashboard: {
        greeting: 'Coach dashboard',
        subtitle: '142 active members · 89% class fill',
        fourth_metric: { title: 'Retention', value: '89%', sub: '30-day active' },
        settings_labels: ['Studio profile', 'Class templates', 'Stripe billing', 'Check-in hours'],
      },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'Jordan K.', channel: 'App', preview: 'Missed yesterday — reschedule?', time: '12m', unread: true },
        ],
        messages: [
          { role: 'user', text: 'Can I move my HIIT slot to Thursday?' },
          { role: 'team', text: 'Done — 6:30pm HIIT is yours. See you there 💪' },
        ],
      },
      schedule: { appointments: [], week_stat: '87%', week_detail: 'Weekly check-in completion' },
      dashboard: leads([
        { name: 'Jordan K.', source: 'App', service: 'HIIT pass', status: 'Active' },
        { name: 'Sam L.', source: 'Referral', service: '12-week program', status: 'Trial' },
      ]),
    },
    dashboardCards: [
      { title: 'Class fill', value: '89%', description: 'Peak hours optimized' },
      { title: 'Active members', value: '142', description: '+8 this month' },
      { title: 'Renewals due', value: '12', description: 'Auto-reminders sent' },
      { title: 'Retention', value: '89%', description: '30-day active' },
    ],
    recentActivity: ['Jordan K. rescheduled HIIT', 'Sam L. started trial program', 'Renewal reminder — 12 members', 'New referral signup — Priya'],
  },
};

// Remaining industries — shared template with tailored copy
function specFromSolution(
  solution: IndustrySolution,
  extra: Partial<ShowcaseSpec> & Pick<ShowcaseSpec, 'businessName' | 'productName' | 'demoSlug' | 'palette' | 'heroHeadline' | 'heroSub' | 'primaryCta' | 'secondaryCta'>,
): ShowcaseSpec {
  const caps = solution.capabilities;
  return {
    industry: solution.name,
    appConfig: appShell({
      features_section: { title: `Built for ${solution.name.toLowerCase()}`, subtitle: solution.tagline },
    }),
    previewContent: {
      inbox: {
        conversations: [
          { name: 'New lead', channel: 'Website', preview: `Interested in ${caps[0]?.toLowerCase() || 'your services'}`, time: '6m', unread: true },
          { name: 'Returning client', channel: 'WhatsApp', preview: 'Can we move my appointment?', time: '30m' },
        ],
        messages: [
          { role: 'user', text: `Hi — I'd like to learn more about ${caps[0]?.toLowerCase() || 'your services'}.` },
          { role: 'team', text: 'Happy to help — I can book you in tomorrow at 2pm or send details by email.' },
        ],
      },
      schedule: scheduleAppts(
        [
          { time: '10:00', client: 'Alex M.', service: caps[0] || 'Service', status: 'confirmed' },
          { time: '14:00', client: 'Jordan P.', service: caps[1] || 'Follow-up', status: 'confirmed' },
        ],
        '18',
        'Bookings this week',
      ),
      dashboard: leads([
        { name: 'Alex M.', source: 'Website', service: caps[0] || 'Core', status: 'Hot' },
        { name: 'Jordan P.', source: 'Referral', service: caps[1] || 'Add-on', status: 'Active' },
      ]),
    },
    dashboardCards: [
      { title: 'New leads', value: '18', description: '+5 this week' },
      { title: 'Booked', value: '24', description: 'On calendar' },
      { title: 'Active clients', value: '156', description: 'Growing' },
      { title: 'Avg response', value: '< 5m', description: 'Across channels' },
    ],
    recentActivity: [`New inquiry — ${caps[0]}`, 'Appointment confirmed — Alex M.', 'Follow-up sent — Jordan P.', 'Dashboard synced'],
    ...extra,
  };
}

const MORE_SPECS: Record<string, Partial<ShowcaseSpec> & Pick<ShowcaseSpec, 'businessName' | 'productName' | 'demoSlug' | 'palette' | 'heroHeadline' | 'heroSub' | 'primaryCta' | 'secondaryCta'>> = {
  'professional-services': {
    businessName: 'Apex Legal Group',
    productName: 'Counsel AI',
    demoSlug: 'apexlegal.app',
    palette: { primary: '#1e3a5f', secondary: '#c9a227', background: '#faf8f4' },
    heroHeadline: 'Counsel AI — conflict cleared before consult',
    heroSub: 'Clause review, vault chasing, and engagement drafts — partners bill counsel, not admin.',
    primaryCta: 'Open matter',
    secondaryCta: 'Book partner consult',
  },
  ecommerce: {
    businessName: 'Lumen Home Goods',
    productName: 'Lumen Store',
    demoSlug: 'lumenstore.app',
    palette: { primary: '#7c3aed', secondary: '#6366f1', background: '#f5f3ff' },
    heroHeadline: 'A storefront that understands what shoppers mean',
    heroSub: 'AI search, smart recommendations, and inventory you control — not a marketplace.',
    primaryCta: 'Shop collection',
    secondaryCta: 'Track order',
  },
  'home-services': {
    businessName: 'BrightFix Plumbing',
    productName: 'BrightFix Dispatch',
    demoSlug: 'brightfix.app',
    palette: { primary: '#f59e0b', secondary: '#ea580c', background: '#fffbeb' },
    heroHeadline: 'Quotes and jobs booked online — not over the phone',
    heroSub: 'Customers request service; you dispatch techs and automate follow-up.',
    primaryCta: 'Get a quote',
    secondaryCta: 'Emergency call',
  },
  education: {
    businessName: 'Summit Tutoring Co.',
    productName: 'Summit Learn',
    demoSlug: 'summitlearn.app',
    palette: { primary: '#0891b2', secondary: '#0284c7', background: '#ecfeff' },
    heroHeadline: 'Students book sessions and track progress',
    heroSub: 'Scheduling, materials, and payments — tutors focus on teaching.',
    primaryCta: 'Book a session',
    secondaryCta: 'View courses',
  },
  automotive: {
    businessName: 'Metro Auto Care',
    productName: 'Metro Service',
    demoSlug: 'metroauto.app',
    palette: { primary: '#dc2626', secondary: '#e11d48', background: '#fff1f2' },
    heroHeadline: 'Service booked online — status updates automatically',
    heroSub: 'Fewer "is my car ready?" calls; happier customers and a full bay schedule.',
    primaryCta: 'Book service',
    secondaryCta: 'Check status',
  },
  hospitality: {
    businessName: 'The Row Hotel',
    productName: 'Row Guest',
    demoSlug: 'therowhotel.app',
    palette: { primary: '#7a1f35', secondary: '#d4a574', background: '#f8f1e9' },
    heroHeadline: 'Direct bookings and an AI concierge',
    heroSub: 'Guests book stays and get answers instantly — staff manage everything in one hub.',
    primaryCta: 'Book your stay',
    secondaryCta: 'Ask concierge',
  },
  nonprofit: {
    businessName: 'Harbor Community Fund',
    productName: 'Harbor Give',
    demoSlug: 'harborgive.app',
    palette: { primary: '#166534', secondary: '#d97706', background: '#f0fdf4' },
    heroHeadline: 'Donate, volunteer, and show up — made simple',
    heroSub: 'Campaign pages, event RSVPs, and donor tracking for teams without a tech department.',
    primaryCta: 'Donate now',
    secondaryCta: 'Volunteer',
  },
};

function buildAllShowcases(): Record<string, SolutionShowcase> {
  const out: Record<string, SolutionShowcase> = {};

  for (const solution of Object.keys(SPECS)) {
    const sol = getSolutionById(solution);
    if (!sol) continue;
    const spec = SPECS[solution];
    out[solution] = {
      solutionId: solution,
      businessName: spec.businessName,
      industry: spec.industry,
      demoSlug: spec.demoSlug,
      demo: baseDemo(sol, spec),
    };
  }

  for (const [id, partial] of Object.entries(MORE_SPECS)) {
    const sol = getSolutionById(id);
    if (!sol) continue;
    const spec = specFromSolution(sol, partial as Parameters<typeof specFromSolution>[1]);
    out[id] = {
      solutionId: id,
      businessName: spec.businessName,
      industry: spec.industry,
      demoSlug: spec.demoSlug,
      demo: baseDemo(sol, spec),
    };
  }

  return out;
}

export const SHOWCASE_DEMOS = buildAllShowcases();

export function getShowcaseDemo(solutionId: string): SolutionShowcase | undefined {
  return SHOWCASE_DEMOS[solutionId];
}

export function hasShowcaseDemo(solutionId: string): boolean {
  return Boolean(SHOWCASE_DEMOS[solutionId]);
}
