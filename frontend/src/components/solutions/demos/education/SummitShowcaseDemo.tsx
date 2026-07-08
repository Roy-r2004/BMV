import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/education-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { SummitLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { SessionSlot } from './summitData.ts';
import SummitStudentSite from './SummitStudentSite.tsx';

const SummitFamilyInbox = lazy(() => import('./SummitFamilyInbox.tsx'));
const SummitSessionCalendar = lazy(() => import('./SummitSessionCalendar.tsx'));
const SummitTutorHub = lazy(() => import('./SummitTutorHub.tsx'));

export type SummitView = 'site' | 'inbox' | 'schedule' | 'admin';

const TABS: { id: SummitView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Student site', short: 'Site', path: 'summitlearn.app', role: 'Tutor matcher — subject + level pairing, not generic booking', icon: '◆' },
  { id: 'inbox', label: 'Family inbox', short: 'Inbox', path: 'summitlearn.app/inbox', role: 'Prep packs + parent reports delivered to family threads', icon: '◎' },
  { id: 'schedule', label: 'Session week', short: 'Week', path: 'summitlearn.app/sessions', role: 'Materials attached per session slot — prep automation visible', icon: '▦' },
  { id: 'admin', label: 'Tutor hub', short: 'Hub', path: 'summitlearn.app/hub', role: 'Tutor roster + progress rings + auto billing strip', icon: '◈' },
];

export default function SummitShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<SummitView>('site');
  const [bookedSlot, setBookedSlot] = useState<SessionSlot | null>(null);

  const goToView = useCallback((id: SummitView) => setView(id), []);

  const onBookedSession = useCallback((slot: SessionSlot) => {
    setBookedSlot(slot);
    setView('inbox');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;
  const highlightStudent = bookedSlot ? 'Ava M.' : undefined;

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--education">
      <div className="sm-frame-toolbar">
        <p className="sol-detail-demo__hint sm-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience sm-frame">
        <div className="sm-frame__accent" aria-hidden />
        <header className="sm-frame__head">
          <div className="sm-frame__brand">
            <span className="sm-frame__logo" aria-hidden>
              <SummitLogo className="sm-frame__logo-svg" />
            </span>
            <div>
              <p className="sm-frame__product">Summit Tutoring</p>
              <p className="sm-frame__tag">Education OS</p>
            </div>
          </div>
          <div className="sm-frame__url">
            {tab.path}
          </div>
          <span className="sm-frame__live">Live</span>
        </header>

        <nav className="sm-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`sm-frame__tab ${view === t.id ? 'sm-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="sm-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="sm-frame__viewport">
          <div className="sm-frame__view">
            <Suspense fallback={<div className="sm-frame__loading" />}>
              {view === 'site' && <SummitStudentSite onBookSession={onBookedSession} />}
              {view === 'inbox' && <SummitFamilyInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <SummitSessionCalendar highlightStudent={highlightStudent} />}
              {view === 'admin' && <SummitTutorHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Subjects → Mathematics → Algebra II → watch AI match → select Elena → confirm slot → inbox shows prep pack.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my center
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
