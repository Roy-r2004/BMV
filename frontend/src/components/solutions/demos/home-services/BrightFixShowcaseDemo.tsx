import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/home-services-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { BrightFixLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { QuoteSubmission } from './brightfixData.ts';
import BrightFixCustomerSite from './BrightFixCustomerSite.tsx';

const BrightFixJobInbox = lazy(() => import('./BrightFixJobInbox.tsx'));
const BrightFixDispatch = lazy(() => import('./BrightFixDispatch.tsx'));
const BrightFixOpsHub = lazy(() => import('./BrightFixOpsHub.tsx'));

export type BrightFixView = 'site' | 'inbox' | 'dispatch' | 'ops';

const TABS: { id: BrightFixView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Customer site', short: 'Site', path: 'brightfix.app', role: 'Quote AI — job details, photos, urgency zones', icon: '◆' },
  { id: 'inbox', label: 'Job inbox', short: 'Inbox', path: 'brightfix.app/inbox', role: 'Dispatch AI scores urgency + skill match for every request', icon: '◎' },
  { id: 'dispatch', label: 'Route board', short: 'Routes', path: 'brightfix.app/dispatch', role: 'Zone map with live job pins — en route / in progress / done', icon: '▦' },
  { id: 'ops', label: 'Ops hub', short: 'Ops', path: 'brightfix.app/ops', role: 'Today\'s jobs, tech roster, revenue strip + review bot', icon: '◈' },
];

export default function BrightFixShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<BrightFixView>('site');
  const [submittedQuote, setSubmittedQuote] = useState<QuoteSubmission | null>(null);

  const goToView = useCallback((id: BrightFixView) => setView(id), []);

  const onQuoteSubmit = useCallback((quote: QuoteSubmission) => {
    setSubmittedQuote(quote);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--home-services">
      <div className="bf-frame-toolbar">
        <p className="sol-detail-demo__hint bf-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience bf-frame">
        <div className="bf-frame__accent" aria-hidden />
        <header className="bf-frame__head">
          <div className="bf-frame__brand">
            <span className="bf-frame__logo" aria-hidden>
              <BrightFixLogo className="bf-frame__logo-svg" />
            </span>
            <div>
              <p className="bf-frame__product">BrightFix Dispatch</p>
              <p className="bf-frame__tag">Home Services OS</p>
            </div>
          </div>
          <div className="bf-frame__url">
            {tab.path}
          </div>
          <span className="bf-frame__live">Live</span>
        </header>

        <nav className="bf-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`bf-frame__tab ${view === t.id ? 'bf-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="bf-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="bf-frame__viewport">
          <div className="bf-frame__view">
            <Suspense fallback={<div className="bf-frame__loading" />}>
              {view === 'site' && <BrightFixCustomerSite onQuoteSubmit={onQuoteSubmit} />}
              {view === 'inbox' && (
                <BrightFixJobInbox submittedQuote={submittedQuote} onClearQuote={() => setSubmittedQuote(null)} />
              )}
              {view === 'dispatch' && <BrightFixDispatch highlightJobId={submittedQuote ? 'a1' : undefined} />}
              {view === 'ops' && <BrightFixOpsHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Run the quote wizard → job lands in inbox with dispatch score → route board pins the tech → review bot fires after close.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my business
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
