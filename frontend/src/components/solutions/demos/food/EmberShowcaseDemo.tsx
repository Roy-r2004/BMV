import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/food-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { EmberLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { ReservationSlot } from './emberData.ts';
import EmberGuestSite from './EmberGuestSite.tsx';

const EmberGuestInbox = lazy(() => import('./EmberGuestInbox.tsx'));
const EmberTablePlan = lazy(() => import('./EmberTablePlan.tsx'));
const EmberKitchenOps = lazy(() => import('./EmberKitchenOps.tsx'));

export type EmberView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: EmberView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Guest site', short: 'Site', path: 'emberorder.app', role: 'Menu concierge AI — allergens, parties, direct orders', icon: '◆' },
  { id: 'inbox', label: 'Guest inbox', short: 'Inbox', path: 'emberorder.app/inbox', role: 'Menu AI routes dietary Qs, set menus & patio parties to kitchen', icon: '◎' },
  { id: 'schedule', label: 'Table plan', short: 'Tables', path: 'emberorder.app/tables', role: 'Live floor view — main, patio, bar, walk-ins', icon: '▦' },
  { id: 'admin', label: 'Kitchen ops', short: 'Ops', path: 'emberorder.app/ops', role: 'Menu AI dietary routing + kitchen queue — service command center', icon: '◈' },
];

export default function EmberShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<EmberView>('site');
  const [bookedSlot, setBookedSlot] = useState<ReservationSlot | null>(null);

  const goToView = useCallback((id: EmberView) => setView(id), []);

  const onReserved = useCallback((slot: ReservationSlot) => {
    setBookedSlot(slot);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Ember Order');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--food">
      <div className="eo-frame-toolbar">
        <p className="sol-detail-demo__hint eo-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience eo-frame">
        <div className="eo-frame__ember" aria-hidden />
        <header className="eo-frame__head">
          <div className="eo-frame__brand">
            <span className="eo-frame__logo" aria-hidden>
              <EmberLogo className="eo-frame__logo-svg" />
            </span>
            <div>
              <p className="eo-frame__product">{productLabel}</p>
              <p className="eo-frame__tag">Restaurant OS</p>
            </div>
          </div>
          <div className="eo-frame__url">
            {tab.path}
          </div>
          <span className="eo-frame__live">Live</span>
        </header>

        <nav className="eo-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`eo-frame__tab ${view === t.id ? 'eo-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="eo-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="eo-frame__viewport">
          <div className="eo-frame__view">
            <Suspense fallback={<div className="eo-frame__loading" />}>
              {view === 'site' && <EmberGuestSite onReserve={onReserved} />}
              {view === 'inbox' && <EmberGuestInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <EmberTablePlan highlightGuest={bookedSlot ? 'Birthday party' : undefined} />}
              {view === 'admin' && <EmberKitchenOps />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Ask “GF for 4?” → Menu AI tags allergens → party lands on patio → kitchen stays in sync (no 30% fees).
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my restaurant
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
