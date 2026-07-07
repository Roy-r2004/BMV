import { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import type { VisualDemo } from '../../types/request';
import { resolvePreviewContent } from './demoContent';
import { resolvePreviewShell, primaryTabId, type ResolvedShell } from './resolveAppShell';
import { fontClass } from './liveSiteTheme';
import DesktopWindow from './DesktopWindow';
import PublicWebsiteView, { type WebsitePage } from './app/PublicWebsiteView';
import InboxView from './app/InboxView';
import ScheduleView from './app/ScheduleView';
import ProgressView from './app/ProgressView';
import DashboardView from './app/DashboardView';
import type { AppView, DashboardPage } from './previewTypes';

export type { AppView } from './previewTypes';

interface HistoryEntry {
  view: AppView;
  sub?: string;
}

interface Props {
  demo: VisualDemo;
  businessName?: string;
  industry?: string | null;
  previewFeatures?: string[];
}

const ease = [0.22, 1, 0.36, 1] as const;

export default function AppExperience({ demo, businessName, industry, previewFeatures }: Props) {
  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });
  const branding: ResolvedShell = resolvePreviewShell(demo, content.imageTheme);
  const primary = branding.primary;
  const secondary = branding.secondary;
  const bg = branding.background;
  const font = fontClass(demo.visual_theme?.font_style);
  const [view, setView] = useState<AppView>(() => primaryTabId(branding));
  const [websitePage, setWebsitePage] = useState<WebsitePage>('home');
  const [dashboardPage, setDashboardPage] = useState<DashboardPage>('overview');
  const [history, setHistory] = useState<HistoryEntry[]>([{ view: 'website', sub: 'home' }]);
  const [historyIdx, setHistoryIdx] = useState(0);

  const siteSlug = businessName?.toLowerCase().replace(/[^a-z0-9]/g, '') || 'yourbusiness';
  const appSlug = demo.product_name.toLowerCase().replace(/\s/g, '');

  const appShell = branding.app;
  const activeTab = appShell.tabs.find((t) => t.id === view);

  const currentUrl =
    view === 'website'
      ? `https://${siteSlug}.com${websitePage === 'home' ? '' : `/${websitePage}`}`
      : `https://${appSlug}.app/${activeTab?.urlSegment || view}${dashboardPage !== 'overview' && view === 'dashboard' ? `/${dashboardPage}` : ''}`;

  const pushHistory = useCallback((entry: HistoryEntry) => {
    setHistory((h) => {
      const trimmed = h.slice(0, historyIdx + 1);
      return [...trimmed, entry];
    });
    setHistoryIdx((i) => i + 1);
  }, [historyIdx]);

  const navigateView = (v: AppView) => {
    setView(v);
    pushHistory({ view: v, sub: v === 'website' ? websitePage : v === 'dashboard' ? dashboardPage : v });
  };

  const navigateWebsite = (page: WebsitePage) => {
    setWebsitePage(page);
    setView('website');
    pushHistory({ view: 'website', sub: page });
  };

  const navigateDashboard = (page: DashboardPage) => {
    setDashboardPage(page);
    setView('dashboard');
    pushHistory({ view: 'dashboard', sub: page });
  };

  const goBack = () => {
    if (historyIdx <= 0) return;
    const next = historyIdx - 1;
    const entry = history[next];
    setHistoryIdx(next);
    setView(entry.view);
    if (entry.view === 'website' && entry.sub) setWebsitePage(entry.sub as WebsitePage);
    if (entry.view === 'dashboard' && entry.sub) setDashboardPage(entry.sub as DashboardPage);
  };

  const goForward = () => {
    if (historyIdx >= history.length - 1) return;
    const next = historyIdx + 1;
    const entry = history[next];
    setHistoryIdx(next);
    setView(entry.view);
    if (entry.view === 'website' && entry.sub) setWebsitePage(entry.sub as WebsitePage);
    if (entry.view === 'dashboard' && entry.sub) setDashboardPage(entry.sub as DashboardPage);
  };

  return (
    <div className={`app-experience-root ${font}`} style={{ backgroundColor: bg }}>
      <DesktopWindow
        title={view === 'website' ? (businessName || demo.product_name) : demo.product_name}
        url={currentUrl}
        canGoBack={historyIdx > 0}
        canGoForward={historyIdx < history.length - 1}
        onBack={goBack}
        onForward={goForward}
      >
        {/* App tabs */}
        <div className="desktop-app-tabs">
          {appShell.tabs.map((v) => (
            <button
              key={v.id}
              type="button"
              onClick={() => navigateView(v.id)}
              className={`desktop-app-tab ${view === v.id ? 'desktop-app-tab--active' : ''}`}
              style={view === v.id ? { borderColor: primary, color: primary, backgroundColor: `${primary}10` } : undefined}
            >
              <span className="hidden sm:inline">{v.label}</span>
              <span className="sm:hidden">{v.short}</span>
            </button>
          ))}
        </div>

        {/* Tab context hint */}
        <div className="desktop-tab-hint">
          {view === 'website' && (
            <span>Public website — what your customers see when they visit. Click the nav links to explore pages.</span>
          )}
          {view === 'inbox' && (
            <span>Inbox / messages — how you and your team handle client communication inside the platform.</span>
          )}
          {view === 'schedule' && (
            <span>Booking & schedule — how clients book appointments and how you manage your calendar.</span>
          )}
          {view === 'dashboard' && (
            <span>Owner dashboard — your business at a glance: bookings, clients, revenue, and settings.</span>
          )}
        </div>

        <div className="app-experience-viewport relative bg-slate-50 min-h-[min(72dvh,640px)] sm:min-h-0">
          <AnimatePresence mode="wait">
            <motion.div
              key={`${view}-${view === 'website' ? websitePage : view === 'dashboard' ? dashboardPage : ''}`}
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -12 }}
              transition={{ duration: 0.3, ease }}
              className="absolute inset-0 overflow-y-auto overflow-x-hidden"
            >
              {view === 'website' && (
                <PublicWebsiteView
                  demo={demo}
                  businessName={businessName}
                  industry={industry}
                  previewFeatures={previewFeatures}
                  branding={branding}
                  content={content}
                  primary={primary}
                  secondary={secondary}
                  page={websitePage}
                  onNavigate={navigateWebsite}
                />
              )}
              {view === 'inbox' && (
                <InboxView
                  demo={demo}
                  businessName={businessName}
                  industry={industry}
                  previewFeatures={previewFeatures}
                  shell={appShell}
                  primary={primary}
                  secondary={secondary}
                />
              )}
              {view === 'schedule' && appShell.schedule.variant === 'progress' && (
                <ProgressView
                  demo={demo}
                  businessName={businessName}
                  industry={industry}
                  previewFeatures={previewFeatures}
                  shell={appShell}
                  primary={primary}
                  secondary={secondary}
                />
              )}
              {view === 'schedule' && appShell.schedule.variant === 'calendar' && (
                <ScheduleView
                  demo={demo}
                  businessName={businessName}
                  industry={industry}
                  previewFeatures={previewFeatures}
                  shell={appShell}
                  primary={primary}
                  secondary={secondary}
                />
              )}
              {view === 'dashboard' && (
                <DashboardView
                  demo={demo}
                  businessName={businessName}
                  industry={industry}
                  previewFeatures={previewFeatures}
                  shell={appShell}
                  imageTheme={content.imageTheme}
                  leadsPanelMode={branding.leadsPanelMode}
                  bookingsPanelMode={branding.bookingsPanelMode}
                  fourthMetric={branding.fourthMetric}
                  settingsLabels={branding.settingsLabels}
                  primary={primary}
                  secondary={secondary}
                  page={dashboardPage}
                  onNavigate={navigateDashboard}
                />
              )}
            </motion.div>
          </AnimatePresence>
        </div>
      </DesktopWindow>
    </div>
  );
}
