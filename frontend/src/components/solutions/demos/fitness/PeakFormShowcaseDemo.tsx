import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/fitness-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { useOverlayProduct } from '../../../../context/ShowcaseOverlayContext.tsx';
import { PeakFormLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { ClassSlot } from './peakformData.ts';
import PeakFormMemberSite from './PeakFormMemberSite.tsx';

const PeakFormMemberInbox = lazy(() => import('./PeakFormMemberInbox.tsx'));
const PeakFormProgress = lazy(() => import('./PeakFormProgress.tsx'));
const PeakFormCoachHub = lazy(() => import('./PeakFormCoachHub.tsx'));

export type PeakFormView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: PeakFormView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Gym site', short: 'Site', path: 'peakform.app', role: 'Coach AI — class fit, trials, streak-aware booking', icon: '◆' },
  { id: 'inbox', label: 'Member chat', short: 'Chat', path: 'peakform.app/messages', role: 'Adherence AI — reschedules, PR logs, streak saves', icon: '◎' },
  { id: 'schedule', label: 'Progress', short: 'Track', path: 'peakform.app/progress', role: 'Weekly adherence, streaks, today\'s classes', icon: '▦' },
  { id: 'admin', label: 'Coach hub', short: 'Hub', path: 'peakform.app/admin', role: 'Churn predictor + member pipeline — who needs a nudge today', icon: '◈' },
];

export default function PeakFormShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<PeakFormView>('site');
  const [bookedSlot, setBookedSlot] = useState<ClassSlot | null>(null);

  const goToView = useCallback((id: PeakFormView) => setView(id), []);

  const onBookedClass = useCallback((slot: ClassSlot) => {
    setBookedSlot(slot);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const productLabel = useOverlayProduct('Peak Form');
  const highlightMember = bookedSlot?.programId === 'hiit' ? 'Jordan K.' : undefined;

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--fitness">
      <div className="pf-frame-toolbar">
        <p className="sol-detail-demo__hint pf-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience pf-frame">
        <div className="pf-frame__accent" aria-hidden />
        <header className="pf-frame__head">
          <div className="pf-frame__brand">
            <span className="pf-frame__logo" aria-hidden>
              <PeakFormLogo className="pf-frame__logo-svg" />
            </span>
            <div>
              <p className="pf-frame__product">{productLabel}</p>
              <p className="pf-frame__tag">Fitness OS</p>
            </div>
          </div>
          <div className="pf-frame__url">
            {tab.path}
          </div>
          <span className="pf-frame__live">Live</span>
        </header>

        <nav className="pf-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`pf-frame__tab ${view === t.id ? 'pf-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="pf-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="pf-frame__viewport">
          <div className="pf-frame__view">
            <Suspense fallback={<div className="pf-frame__loading" />}>
              {view === 'site' && <PeakFormMemberSite onBookClass={onBookedClass} />}
              {view === 'inbox' && <PeakFormMemberInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <PeakFormProgress highlightMember={highlightMember} />}
              {view === 'admin' && <PeakFormCoachHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Tap “Save my streak” → Adherence AI moves HIIT → coach hub flags who almost churned (and didn’t).
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my studio
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
