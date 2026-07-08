import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/hospitality-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { RowLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { BookingHold } from './rowData.ts';
import RowGuestSite from './RowGuestSite.tsx';

const RowGuestInbox = lazy(() => import('./RowGuestInbox.tsx'));
const RowHousekeeping = lazy(() => import('./RowHousekeeping.tsx'));
const RowOpsHub = lazy(() => import('./RowOpsHub.tsx'));

export type RowView = 'site' | 'inbox' | 'housekeeping' | 'ops';

const TABS: { id: RowView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Guest site', short: 'Site', path: 'therowhotel.app', role: 'Concierge AI — room prefs, local picks, late checkout · direct book', icon: '◆' },
  { id: 'inbox', label: 'Guest inbox', short: 'Inbox', path: 'therowhotel.app/inbox', role: 'Concierge AI handles threads — memory, late C/O, local recs', icon: '◎' },
  { id: 'housekeeping', label: 'Housekeeping', short: 'HK', path: 'therowhotel.app/hk', role: 'Floor-by-floor board — dirty / clean / inspected · desk sync', icon: '▦' },
  { id: 'ops', label: 'Ops hub', short: 'Ops', path: 'therowhotel.app/ops', role: 'Tonight mission control · front desk · HK sync · RevPAR · guest memory', icon: '◈' },
];

export default function RowShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<RowView>('site');
  const [bookedHold, setBookedHold] = useState<BookingHold | null>(null);

  const goToView = useCallback((id: RowView) => setView(id), []);

  const onBook = useCallback((hold: BookingHold) => {
    setBookedHold(hold);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Row Guest');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--hospitality">
      <div className="rh-frame-toolbar">
        <p className="sol-detail-demo__hint rh-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience rh-frame">
        <div className="rh-frame__accent" aria-hidden />
        <header className="rh-frame__head">
          <div className="rh-frame__brand">
            <span className="rh-frame__logo" aria-hidden>
              <RowLogo className="rh-frame__logo-svg" />
            </span>
            <div>
              <p className="rh-frame__product">{productLabel}</p>
              <p className="rh-frame__tag">Hospitality OS</p>
            </div>
          </div>
          <div className="rh-frame__url">
            {tab.path}
          </div>
          <span className="rh-frame__live">Live</span>
        </header>

        <nav className="rh-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`rh-frame__tab ${view === t.id ? 'rh-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="rh-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="rh-frame__viewport">
          <div className="rh-frame__view">
            <Suspense fallback={<div className="rh-frame__loading" />}>
              {view === 'site' && <RowGuestSite onBook={onBook} />}
              {view === 'inbox' && (
                <RowGuestInbox bookedHold={bookedHold} onClearBooking={() => setBookedHold(null)} />
              )}
              {view === 'housekeeping' && (
                <RowHousekeeping highlightRoom={bookedHold?.roomId === 'row-pent' ? '504' : bookedHold ? '403' : undefined} />
              )}
              {view === 'ops' && <RowOpsHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Ask for late checkout → Concierge applies guest memory → housekeeping board updates → Ops Tonight shows RevPAR & VIP ticker.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my hotel
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
