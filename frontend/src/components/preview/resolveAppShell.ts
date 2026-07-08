import type { AppConfig, VisualDemo } from '../../types/request';
import type { ImageTheme } from './demoContent';
import {
  type AppShellConfig,
  type IndustryBranding,
  type NavItem,
  getThemeDefaults,
  paletteForTheme,
  isGenericColor,
} from './industryBranding';
import type { AppView, DashboardPage } from './previewTypes';

type HomeSectionId = 'hero' | 'features' | 'ai' | 'programs' | 'journey' | 'testimonial' | 'cta';

export interface ResolvedShell extends IndustryBranding {
  homeSections: HomeSectionId[];
  heroLayout: 'split' | 'centered';
  leadsPanelMode: 'table' | 'adherence';
  bookingsPanelMode: 'appointments' | 'programs';
  fourthMetric: { title: string; value: string; sub: string };
  settingsLabels: string[];
}

const VALID_VIEWS = new Set<AppView>(['website', 'inbox', 'schedule', 'dashboard']);
const VALID_SECTIONS = new Set<HomeSectionId>(['hero', 'features', 'ai', 'programs', 'journey', 'testimonial', 'cta']);
const VALID_DASH: Set<DashboardPage> = new Set(['overview', 'leads', 'bookings', 'clients', 'settings']);

function mapNav(raw: AppConfig['website_nav'], fallback: NavItem[]): NavItem[] {
  if (!raw?.length) return fallback;
  return raw
    .filter((n) => n.id === 'home' || n.id === 'services' || n.id === 'about' || n.id === 'contact')
    .map((n) => ({ id: n.id, label: n.label }));
}

function mapAppConfigToShell(ac: AppConfig, theme: ImageTheme): AppShellConfig {
  const defaults = getThemeDefaults(theme);
  const enabled = new Set((ac.enabled_modules || defaults.enabledModules).filter((m) => VALID_VIEWS.has(m as AppView)));
  const tabs = (ac.tabs?.length ? ac.tabs : defaults.tabs)
    .map((t) => ({
      id: t.id as AppView,
      label: t.label,
      short: t.short,
      urlSegment: ('url_segment' in t && t.url_segment) ? t.url_segment : ('urlSegment' in t ? (t as { urlSegment: string }).urlSegment : t.id),
    }))
    .filter((t) => enabled.has(t.id));

  return {
    tabs: tabs.length ? tabs : defaults.tabs,
    inbox: {
      title: ac.inbox?.title || defaults.inbox.title,
      subtitle: ac.inbox?.subtitle || defaults.inbox.subtitle,
      footer: ac.inbox?.footer || defaults.inbox.footer,
      quickReplies: ac.inbox?.quick_replies?.length ? ac.inbox.quick_replies : defaults.inbox.quickReplies,
      statusLabel: ac.inbox?.status_label || defaults.inbox.statusLabel,
    },
    schedule: {
      title: ac.schedule?.title || defaults.schedule.title,
      subtitle: ac.schedule?.subtitle || defaults.schedule.subtitle,
      addButton: ac.schedule?.add_button || defaults.schedule.addButton,
      todayLabel: ac.schedule?.today_label || defaults.schedule.todayLabel,
      slotsLabel: ac.schedule?.slots_label || defaults.schedule.slotsLabel,
      variant: ac.schedule_variant === 'progress' ? 'progress' : 'calendar',
    },
    dashboardNav: (ac.dashboard?.nav || defaults.dashboardNav)
      .map((n) => ({ id: n.id as DashboardPage, label: n.label }))
      .filter((n) => VALID_DASH.has(n.id)),
    dashboardGreeting: ac.dashboard?.greeting || defaults.dashboardGreeting,
    dashboardSubtitle: ac.dashboard?.subtitle || defaults.dashboardSubtitle,
    leadsPanelTitle: ac.dashboard?.leads_panel || defaults.leadsPanelTitle,
    bookingsPanelTitle: ac.dashboard?.bookings_panel || defaults.bookingsPanelTitle,
    clientsPanelTitle: ac.dashboard?.clients_panel || defaults.clientsPanelTitle,
    tableHeaders: ac.dashboard?.table_headers
      ? {
          client: ac.dashboard.table_headers.client,
          source: ac.dashboard.table_headers.source,
          service: ac.dashboard.table_headers.service,
          status: ac.dashboard.table_headers.status,
        }
      : defaults.tableHeaders,
  };
}

export function resolvePreviewShell(demo: VisualDemo, imageTheme: ImageTheme): ResolvedShell {
  const ac = demo.app_config;
  const palette = paletteForTheme(imageTheme);
  const vt = demo.visual_theme;
  const usePalette = isGenericColor(vt?.primary_color);
  const defaults = getThemeDefaults(imageTheme);

  if (!ac) {
    const legacy = {
      nav: defaults.websiteNav,
      featuresTitle: defaults.featuresTitle,
      featuresSubtitle: defaults.featuresSubtitle,
      headerVariant: defaults.headerVariant,
      primary: usePalette ? palette.primary : vt?.primary_color || palette.primary,
      secondary: usePalette ? palette.secondary : vt?.secondary_color || palette.secondary,
      background: usePalette ? palette.background : vt?.background_color || palette.background,
      app: {
        tabs: defaults.tabs,
        inbox: defaults.inbox,
        schedule: defaults.schedule,
        dashboardNav: defaults.dashboardNav,
        dashboardGreeting: defaults.dashboardGreeting,
        dashboardSubtitle: defaults.dashboardSubtitle,
        leadsPanelTitle: defaults.leadsPanelTitle,
        bookingsPanelTitle: defaults.bookingsPanelTitle,
        clientsPanelTitle: defaults.clientsPanelTitle,
        tableHeaders: defaults.tableHeaders,
      },
      homeSections: defaults.homeSections,
      heroLayout: defaults.heroLayout,
      leadsPanelMode: defaults.leadsPanelMode,
      bookingsPanelMode: defaults.bookingsPanelMode,
      fourthMetric: defaults.fourthMetric,
      settingsLabels: defaults.settingsLabels,
    };
    return legacy;
  }

  const app = mapAppConfigToShell(ac, imageTheme);
  const sections = (ac.home_sections || defaults.homeSections).filter((s) => VALID_SECTIONS.has(s as HomeSectionId)) as HomeSectionId[];

  return {
    nav: mapNav(ac.website_nav, defaults.websiteNav),
    featuresTitle: ac.features_section?.title || defaults.featuresTitle,
    featuresSubtitle: ac.features_section?.subtitle || defaults.featuresSubtitle,
    headerVariant: ac.header_variant === 'dark' ? 'dark' : ac.header_variant === 'light' ? 'light' : defaults.headerVariant,
    primary: usePalette ? palette.primary : vt?.primary_color || palette.primary,
    secondary: usePalette ? palette.secondary : vt?.secondary_color || palette.secondary,
    background: usePalette ? palette.background : vt?.background_color || palette.background,
    app,
    homeSections: sections.length ? sections : defaults.homeSections,
    heroLayout: ac.hero_layout === 'centered' ? 'centered' : 'split',
    leadsPanelMode: ac.leads_panel_mode === 'adherence' ? 'adherence' : 'table',
    bookingsPanelMode: ac.bookings_panel_mode === 'programs' ? 'programs' : 'appointments',
    fourthMetric: ac.dashboard?.fourth_metric || defaults.fourthMetric,
    settingsLabels: ac.dashboard?.settings_labels?.length ? ac.dashboard.settings_labels : defaults.settingsLabels,
  };
}

export function primaryTabId(shell: ResolvedShell): AppView {
  return shell.app.tabs[0]?.id ?? 'website';
}
