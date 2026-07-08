import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/real-estate-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { NorthlineLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { ViewingSlot } from './northlineData.ts';
import NorthlineBuyerSite from './NorthlineBuyerSite.tsx';

const NorthlineBuyerInbox = lazy(() => import('./NorthlineBuyerInbox.tsx'));
const NorthlineViewings = lazy(() => import('./NorthlineViewings.tsx'));
const NorthlineAgentCRM = lazy(() => import('./NorthlineAgentCRM.tsx'));

export type NorthlineView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: NorthlineView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Listings site', short: 'Site', path: 'northline.app', role: 'Listing AI on every property — HOA, schools, comps, tours', icon: '◆' },
  { id: 'inbox', label: 'Buyer inbox', short: 'Inbox', path: 'northline.app/inbox', role: 'Lead scoring AI — budget fit, comp packs, viewing booking', icon: '◎' },
  { id: 'schedule', label: 'Viewings', short: 'View', path: 'northline.app/viewings', role: 'Agent calendars — today\'s route, confirmed tours', icon: '▦' },
  { id: 'admin', label: 'Agent CRM', short: 'CRM', path: 'northline.app/admin', role: 'AI-ranked pipeline — hot leads, nurture, agent handoff', icon: '◈' },
];

export default function NorthlineShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<NorthlineView>('site');
  const [bookedSlot, setBookedSlot] = useState<ViewingSlot | null>(null);

  const goToView = useCallback((id: NorthlineView) => setView(id), []);

  const onBookedViewing = useCallback((slot: ViewingSlot) => {
    setBookedSlot(slot);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const highlightBuyer = bookedSlot?.listingId === 'oak-lane' ? 'Alex P.' : undefined;
  const productLabel = useOverlayProduct('Northline');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--real-estate">
      <div className="nr-frame-toolbar">
        <p className="sol-detail-demo__hint nr-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience nr-frame">
        <div className="nr-frame__accent" aria-hidden />
        <header className="nr-frame__head">
          <div className="nr-frame__brand">
            <span className="nr-frame__logo" aria-hidden>
              <NorthlineLogo className="nr-frame__logo-svg" />
            </span>
            <div>
              <p className="nr-frame__product">{productLabel}</p>
              <p className="nr-frame__tag">Real Estate OS</p>
            </div>
          </div>
          <div className="nr-frame__url">
            {tab.path}
          </div>
          <span className="nr-frame__live">Live</span>
        </header>

        <nav className="nr-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`nr-frame__tab ${view === t.id ? 'nr-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="nr-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="nr-frame__viewport">
          <div className="nr-frame__view">
            <Suspense fallback={<div className="nr-frame__loading" />}>
              {view === 'site' && <NorthlineBuyerSite onBookViewing={onBookedViewing} />}
              {view === 'inbox' && <NorthlineBuyerInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <NorthlineViewings highlightBuyer={highlightBuyer} />}
              {view === 'admin' && <NorthlineAgentCRM />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Ask “Am I a hot lead?” → score 94 → book Sat tour → agent CRM lights up with a warm viewing.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my agency
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
