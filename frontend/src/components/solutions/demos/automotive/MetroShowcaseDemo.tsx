import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/automotive-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { MetroLogo } from '../shared/ShowcaseChatIcons.tsx';
import { preferredBayForService, type BookingSubmission } from './metroData.ts';
import MetroCustomerSite from './MetroCustomerSite.tsx';

const MetroServiceInbox = lazy(() => import('./MetroServiceInbox.tsx'));
const MetroBayBoard = lazy(() => import('./MetroBayBoard.tsx'));
const MetroShopHub = lazy(() => import('./MetroShopHub.tsx'));

export type MetroView = 'site' | 'inbox' | 'bays' | 'hub';

const TABS: { id: MetroView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Customer site', short: 'Site', path: 'metroauto.app', role: 'Service Bot — book a bay, track live status, SMS progress', icon: '◆' },
  { id: 'inbox', label: 'Service inbox', short: 'Inbox', path: 'metroauto.app/inbox', role: 'Bay assignment AI scores every request by job type + lift fit', icon: '◎' },
  { id: 'bays', label: 'Bay board', short: 'Bays', path: 'metroauto.app/bays', role: '4 lifts with status lights — progress streamed to customers', icon: '▦' },
  { id: 'hub', label: 'Shop hub', short: 'Hub', path: 'metroauto.app/hub', role: 'Tech roster · today\'s revenue · upsell alert strip', icon: '◈' },
];

export default function MetroShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<MetroView>('site');
  const [submittedBooking, setSubmittedBooking] = useState<BookingSubmission | null>(null);

  const goToView = useCallback((id: MetroView) => setView(id), []);

  const onBookSubmit = useCallback((booking: BookingSubmission) => {
    setSubmittedBooking(booking);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Metro Service');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--automotive">
      <div className="mt-frame-toolbar">
        <p className="sol-detail-demo__hint mt-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience mt-frame">
        <div className="mt-frame__accent" aria-hidden />
        <header className="mt-frame__head">
          <div className="mt-frame__brand">
            <span className="mt-frame__logo" aria-hidden>
              <MetroLogo className="mt-frame__logo-svg" />
            </span>
            <div>
              <p className="mt-frame__product">{productLabel}</p>
              <p className="mt-frame__tag">Automotive OS</p>
            </div>
          </div>
          <div className="mt-frame__url">
            {tab.path}
          </div>
          <span className="mt-frame__live">Live</span>
        </header>

        <nav className="mt-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`mt-frame__tab ${view === t.id ? 'mt-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="mt-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="mt-frame__viewport">
          <div className="mt-frame__view">
            <Suspense fallback={<div className="mt-frame__loading" />}>
              {view === 'site' && <MetroCustomerSite onBookSubmit={onBookSubmit} />}
              {view === 'inbox' && (
                <MetroServiceInbox submittedBooking={submittedBooking} onClearBooking={() => setSubmittedBooking(null)} />
              )}
              {view === 'bays' && (
                <MetroBayBoard
                  highlightBay={submittedBooking ? preferredBayForService(submittedBooking.serviceId) : undefined}
                />
              )}
              {view === 'hub' && <MetroShopHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Book a bay (service → vehicle → slot) → request lands in inbox with bay AI → board lights the lift → shop hub surfaces upsells + revenue.
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
