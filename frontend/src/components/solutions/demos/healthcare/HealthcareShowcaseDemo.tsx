import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/healthcare-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import type { TimeSlot } from './harborData';
import HarborPatientSite from './HarborPatientSite.tsx';

const HarborAIIntake = lazy(() => import('./HarborAIIntake.tsx'));
const HarborSchedule = lazy(() => import('./HarborSchedule.tsx'));
const HarborClinicAdmin = lazy(() => import('./HarborClinicAdmin.tsx'));

export type HarborView = 'site' | 'intake' | 'schedule' | 'admin';

const TABS: { id: HarborView; label: string; short: string; path: string; role: string }[] = [
  { id: 'site', label: 'Patient website', short: 'Site', path: 'harborwellness.com', role: 'Patient site + Harbor clinical intake AI on every page' },
  { id: 'intake', label: 'AI patient intake', short: 'Intake', path: 'harborcare.app/inbox', role: 'Clinical intake AI — forms, insurance, slot matching + escalation queue' },
  { id: 'schedule', label: 'Clinic calendar', short: 'Calendar', path: 'harborcare.app/schedule', role: 'Front desk — today\'s appointments' },
  { id: 'admin', label: 'Practice admin', short: 'Admin', path: 'harborcare.app/admin', role: 'Manager — rooms, services, staff' },
];

export default function HealthcareShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<HarborView>('site');
  const [bookedSlot, setBookedSlot] = useState<TimeSlot | null>(null);

  const goToView = useCallback((id: HarborView) => setView(id), []);

  const onBooked = useCallback((slot: TimeSlot) => {
    setBookedSlot(slot);
    setView('intake');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Harbor Care');

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--healthcare">
      <div className="hc-demo-toolbar">
        <p className="sol-detail-demo__hint hc-demo-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong> — switch tabs to explore each role.
        </p>
      </div>

      <div className="sol-detail-demo__experience sol-detail-demo__experience--cinematic hc-demo-shell">
        <div className="hc-demo">
          <div className="hc-demo__titlebar">
            <div className="hc-demo__lights">
              <span /><span /><span />
            </div>
            <p className="hc-demo__product">{productLabel} · Healthcare platform</p>
            <span className="hc-demo__titlebar-spacer" aria-hidden />
          </div>

          <div className="hc-demo__chrome">
            <div className="hc-demo__url">
              <svg viewBox="0 0 24 24" className="hc-demo__lock" fill="currentColor" aria-hidden>
                <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z" />
              </svg>
              <span>{tab.path}</span>
            </div>
            <span className="hc-demo__live">
              <span className="hc-demo__live-dot" />
              Live demo
            </span>
          </div>

          <div className="hc-demo__tabs">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => goToView(t.id)}
                className={`hc-demo__tab ${view === t.id ? 'hc-demo__tab--active' : ''}`}
                title={t.role}
              >
                <span className="hidden sm:inline">{t.label}</span>
                <span className="sm:hidden">{t.short}</span>
              </button>
            ))}
          </div>

          <div className="hc-demo__viewport">
            <div className="hc-demo__view">
              <Suspense fallback={<div className="hc-demo__loading" />}>
                {view === 'site' && <HarborPatientSite onBook={onBooked} />}
                {view === 'intake' && <HarborAIIntake bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
                {view === 'schedule' && <HarborSchedule highlightPatient={bookedSlot ? 'Sarah M.' : undefined} />}
                {view === 'admin' && <HarborClinicAdmin />}
              </Suspense>
            </div>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try the flow:</strong> Open intake chat → “Send intake now” → Harbor books after hours while your front desk sleeps.
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
