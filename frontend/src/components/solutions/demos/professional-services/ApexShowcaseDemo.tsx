import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/professional-services-demo.css';
import '../../../../styles/apex-counsel-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { ApexLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { ConsultSlot } from './apexData.ts';
import ApexClientSite from './ApexClientSite.tsx';

const ApexClientInbox = lazy(() => import('./ApexClientInbox.tsx'));
const ApexMatterTracker = lazy(() => import('./ApexMatterTracker.tsx'));
const ApexPartnerHub = lazy(() => import('./ApexPartnerHub.tsx'));

export type ApexView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: ApexView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Firm portal', short: 'Portal', path: 'apexlegal.app', role: 'Counsel AI — conflict scan, clause review, vault chaser, engagement draft', icon: '◆' },
  { id: 'inbox', label: 'Vault queue', short: 'Vault', path: 'apexlegal.app/vault', role: 'Live vault queue — clause flags, conflict clearance, partner routing', icon: '◎' },
  { id: 'schedule', label: 'Matter portal', short: 'Matter', path: 'apexlegal.app/matters', role: 'Client matter timeline — vault %, clause review, engagement draft progress', icon: '▦' },
  { id: 'admin', label: 'Partner desk', short: 'Desk', path: 'apexlegal.app/admin', role: 'Partner briefing — today\'s consults + Counsel AI prep briefs per matter', icon: '◈' },
];

export default function ApexShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<ApexView>('site');
  const [bookedSlot, setBookedSlot] = useState<ConsultSlot | null>(null);

  const goToView = useCallback((id: ApexView) => setView(id), []);

  const onBookedConsult = useCallback((slot: ConsultSlot) => {
    setBookedSlot(slot);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Apex Legal');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--professional-services">
      <div className="ax-frame-toolbar">
        <p className="sol-detail-demo__hint ax-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience ax-frame">
        <div className="ax-frame__accent" aria-hidden />
        <header className="ax-frame__head">
          <div className="ax-frame__brand">
            <span className="ax-frame__logo" aria-hidden>
              <ApexLogo className="ax-frame__logo-svg" />
            </span>
            <div>
              <p className="ax-frame__product">{productLabel}</p>
              <p className="ax-frame__tag">Counsel AI OS</p>
            </div>
          </div>
          <div className="ax-frame__url">
            {tab.path}
          </div>
          <span className="ax-frame__live">Live</span>
        </header>

        <nav className="ax-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`ax-frame__tab ${view === t.id ? 'ax-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="ax-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="ax-frame__viewport">
          <div className="ax-frame__view">
            <Suspense fallback={<div className="ax-frame__loading" />}>
              {view === 'site' && <ApexClientSite onBookConsult={onBookedConsult} />}
              {view === 'inbox' && <ApexClientInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <ApexMatterTracker highlightClient="David Chen" />}
              {view === 'admin' && <ApexPartnerHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Run conflict check → watch live Counsel AI on vault queue → matter timeline with clause flags → partner desk funnel.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my firm
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
