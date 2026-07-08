import type { ImageTheme } from './demoContent';
import type { VisualDemo } from '../../types/request';
import type { AppView, DashboardPage } from './previewTypes';

export interface NavItem {
  id: 'home' | 'services' | 'about' | 'contact';
  label: string;
}

export interface AppTab {
  id: AppView;
  label: string;
  short: string;
  urlSegment: string;
}

export interface InboxShell {
  title: string;
  subtitle: string;
  footer: string;
  quickReplies: string[];
  statusLabel: string;
}

export interface ScheduleShell {
  title: string;
  subtitle: string;
  addButton: string;
  todayLabel: string;
  slotsLabel: string;
  variant: 'calendar' | 'progress';
}

export interface DashboardNavItem {
  id: DashboardPage;
  label: string;
}

export interface AppShellConfig {
  tabs: AppTab[];
  inbox: InboxShell;
  schedule: ScheduleShell;
  dashboardNav: DashboardNavItem[];
  dashboardGreeting: string;
  dashboardSubtitle: string;
  leadsPanelTitle: string;
  bookingsPanelTitle: string;
  clientsPanelTitle: string;
  tableHeaders: { client: string; source: string; service: string; status: string };
}

export interface IndustryBranding {
  nav: NavItem[];
  featuresTitle: string;
  featuresSubtitle: string;
  headerVariant: 'light' | 'dark';
  primary: string;
  secondary: string;
  background: string;
  app: AppShellConfig;
}

const PALETTES: Record<ImageTheme, { primary: string; secondary: string; background: string }> = {
  fitness: { primary: '#ea580c', secondary: '#16a34a', background: '#fffbeb' },
  wellness: { primary: '#be185d', secondary: '#9333ea', background: '#fdf2f8' },
  saas: { primary: '#4f46e5', secondary: '#0891b2', background: '#f8fafc' },
  generic: { primary: '#0f766e', secondary: '#0369a1', background: '#f8fafc' },
};

const WEBSITE_NAV: Record<ImageTheme, NavItem[]> = {
  fitness: [
    { id: 'home', label: 'Home' },
    { id: 'services', label: 'Programs' },
    { id: 'about', label: 'Coach' },
    { id: 'contact', label: 'Join' },
  ],
  wellness: [
    { id: 'home', label: 'Home' },
    { id: 'services', label: 'Treatments' },
    { id: 'about', label: 'About' },
    { id: 'contact', label: 'Book' },
  ],
  saas: [
    { id: 'home', label: 'Home' },
    { id: 'services', label: 'Features' },
    { id: 'about', label: 'About' },
    { id: 'contact', label: 'Demo' },
  ],
  generic: [
    { id: 'home', label: 'Home' },
    { id: 'services', label: 'Services' },
    { id: 'about', label: 'About' },
    { id: 'contact', label: 'Contact' },
  ],
};

const COPY: Record<ImageTheme, { featuresTitle: string; featuresSubtitle: string }> = {
  fitness: {
    featuresTitle: 'Everything your clients need in one hub',
    featuresSubtitle: 'Meal plans, workouts, habits, and messaging — no more WhatsApp chaos.',
  },
  wellness: {
    featuresTitle: 'Premium client experience',
    featuresSubtitle: 'Booking, reminders, and follow-up built for your clinic.',
  },
  saas: {
    featuresTitle: 'Core platform capabilities',
    featuresSubtitle: 'The features that power your product from day one.',
  },
  generic: {
    featuresTitle: 'Built for how you work',
    featuresSubtitle: 'Key capabilities tailored to your business.',
  },
};

const APP_SHELL: Record<ImageTheme, AppShellConfig> = {
  fitness: {
    tabs: [
      { id: 'website', label: 'Marketing site', short: 'Site', urlSegment: '' },
      { id: 'inbox', label: 'Client chat', short: 'Chat', urlSegment: 'messages' },
      { id: 'schedule', label: 'Client progress', short: 'Progress', urlSegment: 'progress' },
      { id: 'dashboard', label: 'Coach hub', short: 'Hub', urlSegment: 'admin' },
    ],
    inbox: {
      title: 'Client messages',
      subtitle: 'WhatsApp, Instagram & in-app — one thread per client',
      footer: 'Unified coaching inbox',
      quickReplies: ['Plan sent ✓', 'Great logging!', 'Check-in Thu 2pm'],
      statusLabel: 'Active client',
    },
    schedule: {
      title: 'Client progress',
      subtitle: 'Habits, meal logs, workouts & progress photos',
      addButton: '+ Log check-in',
      todayLabel: "Today's adherence",
      slotsLabel: 'Weekly habits',
      variant: 'progress',
    },
    dashboardNav: [
      { id: 'overview', label: 'Overview' },
      { id: 'clients', label: 'Active clients' },
      { id: 'bookings', label: 'Programs' },
      { id: 'leads', label: 'Adherence' },
      { id: 'settings', label: 'Settings' },
    ],
    dashboardGreeting: 'Coach dashboard',
    dashboardSubtitle: 'Client adherence and program delivery at a glance.',
    leadsPanelTitle: 'Adherence leaderboard',
    bookingsPanelTitle: 'Active programs',
    clientsPanelTitle: 'Client roster',
    tableHeaders: { client: 'Client', source: 'Channel', service: 'Program', status: 'Status' },
  },
  wellness: {
    tabs: [
      { id: 'website', label: 'Clinic website', short: 'Site', urlSegment: '' },
      { id: 'inbox', label: 'Patient inbox', short: 'Inbox', urlSegment: 'inbox' },
      { id: 'schedule', label: 'Appointments', short: 'Appts', urlSegment: 'calendar' },
      { id: 'dashboard', label: 'Clinic admin', short: 'Admin', urlSegment: 'dashboard' },
    ],
    inbox: {
      title: 'Patient inbox',
      subtitle: 'DMs, WhatsApp & booking inquiries',
      footer: 'Clinic communication hub',
      quickReplies: ['Slot available Thu', 'Send intake form', 'Confirm appointment'],
      statusLabel: 'Active inquiry',
    },
    schedule: {
      title: 'Appointment calendar',
      subtitle: 'Treatment rooms & practitioner schedule',
      addButton: '+ Block slot',
      todayLabel: "Today's appointments",
      slotsLabel: 'Available slots',
      variant: 'calendar',
    },
    dashboardNav: [
      { id: 'overview', label: 'Overview' },
      { id: 'leads', label: 'Inquiries' },
      { id: 'bookings', label: 'Appointments' },
      { id: 'clients', label: 'Patients' },
      { id: 'settings', label: 'Settings' },
    ],
    dashboardGreeting: 'Good morning',
    dashboardSubtitle: "Today's bookings, inquiries, and follow-ups.",
    leadsPanelTitle: 'New inquiries',
    bookingsPanelTitle: "Today's appointments",
    clientsPanelTitle: 'Recent patients',
    tableHeaders: { client: 'Patient', source: 'Source', service: 'Treatment', status: 'Status' },
  },
  saas: {
    tabs: [
      { id: 'website', label: 'Product site', short: 'Site', urlSegment: '' },
      { id: 'inbox', label: 'Support inbox', short: 'Support', urlSegment: 'support' },
      { id: 'schedule', label: 'Demo calls', short: 'Demos', urlSegment: 'meetings' },
      { id: 'dashboard', label: 'Ops dashboard', short: 'Ops', urlSegment: 'admin' },
    ],
    inbox: {
      title: 'Support inbox',
      subtitle: 'Live chat, email & onboarding threads',
      footer: 'Customer success hub',
      quickReplies: ['Onboarding link', 'Schedule demo', 'Escalate to eng'],
      statusLabel: 'Active ticket',
    },
    schedule: {
      title: 'Demo calendar',
      subtitle: 'Sales demos & onboarding calls',
      addButton: '+ New meeting',
      todayLabel: "Today's calls",
      slotsLabel: 'Open demo slots',
      variant: 'calendar',
    },
    dashboardNav: [
      { id: 'overview', label: 'Overview' },
      { id: 'leads', label: 'Pipeline' },
      { id: 'bookings', label: 'Meetings' },
      { id: 'clients', label: 'Accounts' },
      { id: 'settings', label: 'Settings' },
    ],
    dashboardGreeting: 'Product ops',
    dashboardSubtitle: 'Pipeline, activations, and account health.',
    leadsPanelTitle: 'Pipeline',
    bookingsPanelTitle: 'Scheduled demos',
    clientsPanelTitle: 'Active accounts',
    tableHeaders: { client: 'Account', source: 'Channel', service: 'Plan', status: 'Stage' },
  },
  generic: {
    tabs: [
      { id: 'website', label: 'Your website', short: 'Site', urlSegment: '' },
      { id: 'inbox', label: 'Messages', short: 'Inbox', urlSegment: 'inbox' },
      { id: 'schedule', label: 'Bookings', short: 'Book', urlSegment: 'calendar' },
      { id: 'dashboard', label: 'Dashboard', short: 'Admin', urlSegment: 'dashboard' },
    ],
    inbox: {
      title: 'Inbox',
      subtitle: 'All channels in one place',
      footer: 'Unified inbox',
      quickReplies: ['Thanks!', 'Booked ✓', 'Following up'],
      statusLabel: 'Active',
    },
    schedule: {
      title: 'Bookings',
      subtitle: 'Your calendar',
      addButton: '+ Block time',
      todayLabel: "Today's schedule",
      slotsLabel: 'Available slots',
      variant: 'calendar',
    },
    dashboardNav: [
      { id: 'overview', label: 'Overview' },
      { id: 'leads', label: 'Leads' },
      { id: 'bookings', label: 'Bookings' },
      { id: 'clients', label: 'Clients' },
      { id: 'settings', label: 'Settings' },
    ],
    dashboardGreeting: 'Good morning',
    dashboardSubtitle: "Here's what's happening today.",
    leadsPanelTitle: 'Leads',
    bookingsPanelTitle: 'Bookings',
    clientsPanelTitle: 'Clients',
    tableHeaders: { client: 'Client', source: 'Source', service: 'Service', status: 'Status' },
  },
};

export interface ThemeDefaults extends AppShellConfig {
  enabledModules: AppView[];
  websiteNav: NavItem[];
  featuresTitle: string;
  featuresSubtitle: string;
  headerVariant: 'light' | 'dark';
  homeSections: Array<'hero' | 'features' | 'ai' | 'programs' | 'journey' | 'testimonial' | 'cta'>;
  heroLayout: 'split' | 'centered';
  leadsPanelMode: 'table' | 'adherence';
  bookingsPanelMode: 'appointments' | 'programs';
  fourthMetric: { title: string; value: string; sub: string };
  settingsLabels: string[];
}

const THEME_META: Record<ImageTheme, Omit<ThemeDefaults, keyof AppShellConfig>> = {
  fitness: {
    enabledModules: ['website', 'inbox', 'schedule', 'dashboard'],
    websiteNav: WEBSITE_NAV.fitness,
    featuresTitle: COPY.fitness.featuresTitle,
    featuresSubtitle: COPY.fitness.featuresSubtitle,
    headerVariant: 'dark',
    homeSections: ['hero', 'features', 'programs', 'journey'],
    heroLayout: 'split',
    leadsPanelMode: 'adherence',
    bookingsPanelMode: 'programs',
    fourthMetric: { title: 'Meal logging', value: '87%', sub: 'Weekly average' },
    settingsLabels: ['Coach profile', 'Meal plan templates', 'WhatsApp connected', 'Check-in hours'],
  },
  wellness: {
    enabledModules: ['website', 'inbox', 'schedule', 'dashboard'],
    websiteNav: WEBSITE_NAV.wellness,
    featuresTitle: COPY.wellness.featuresTitle,
    featuresSubtitle: COPY.wellness.featuresSubtitle,
    headerVariant: 'light',
    homeSections: ['hero', 'programs', 'features', 'journey'],
    heroLayout: 'split',
    leadsPanelMode: 'table',
    bookingsPanelMode: 'appointments',
    fourthMetric: { title: 'Avg reply', value: '< 30s', sub: 'Across channels' },
    settingsLabels: ['Clinic profile', 'Treatment menu', 'WhatsApp connected', 'Booking hours'],
  },
  saas: {
    enabledModules: ['website', 'inbox', 'schedule', 'dashboard'],
    websiteNav: WEBSITE_NAV.saas,
    featuresTitle: COPY.saas.featuresTitle,
    featuresSubtitle: COPY.saas.featuresSubtitle,
    headerVariant: 'light',
    homeSections: ['hero', 'features', 'journey', 'programs'],
    heroLayout: 'centered',
    leadsPanelMode: 'table',
    bookingsPanelMode: 'appointments',
    fourthMetric: { title: 'Activation', value: '68%', sub: 'Trial → paid' },
    settingsLabels: ['Workspace', 'Stripe connected', 'Slack alerts', 'Demo calendar'],
  },
  generic: {
    enabledModules: ['website', 'inbox', 'schedule', 'dashboard'],
    websiteNav: WEBSITE_NAV.generic,
    featuresTitle: COPY.generic.featuresTitle,
    featuresSubtitle: COPY.generic.featuresSubtitle,
    headerVariant: 'light',
    homeSections: ['hero', 'features', 'programs'],
    heroLayout: 'split',
    leadsPanelMode: 'table',
    bookingsPanelMode: 'appointments',
    fourthMetric: { title: 'Avg reply', value: '< 30s', sub: 'Across channels' },
    settingsLabels: ['Business name', 'Instagram connected', 'WhatsApp connected', 'Booking hours'],
  },
};

export function paletteForTheme(theme: ImageTheme) {
  return PALETTES[theme];
}

export { isGenericColor };

export function getThemeDefaults(theme: ImageTheme): ThemeDefaults {
  return { ...APP_SHELL[theme], ...THEME_META[theme] };
}

function isGenericColor(hex?: string) {
  if (!hex) return true;
  const h = hex.toLowerCase();
  return h === '#2563eb' || h === '#4f46e5' || h === '#0d9488' || h === '#06b6d4';
}

export function resolveIndustryBranding(theme: ImageTheme, demo: VisualDemo): IndustryBranding {
  const palette = PALETTES[theme];
  const vt = demo.visual_theme;
  const usePalette = isGenericColor(vt?.primary_color);
  const defaults = getThemeDefaults(theme);

  return {
    nav: defaults.websiteNav,
    featuresTitle: defaults.featuresTitle,
    featuresSubtitle: defaults.featuresSubtitle,
    headerVariant: defaults.headerVariant,
    primary: usePalette ? palette.primary : vt?.primary_color || palette.primary,
    secondary: usePalette ? palette.secondary : vt?.secondary_color || palette.secondary,
    background: usePalette ? palette.background : vt?.background_color || palette.background,
    app: defaults,
  };
}
