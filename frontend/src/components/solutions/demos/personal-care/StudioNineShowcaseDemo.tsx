import { lazy, Suspense, useCallback, useState } from 'react';

import '../../../../styles/personal-care-demo.css';

import type { ShowcaseDemoProps } from '../showcaseRegistry';

import type { TimeSlot } from './studioData.ts';

import StudioClientSite from './StudioClientSite.tsx';



const StudioDMInbox = lazy(() => import('./StudioDMInbox.tsx'));

const StudioChairCalendar = lazy(() => import('./StudioChairCalendar.tsx'));

const StudioOwnerHub = lazy(() => import('./StudioOwnerHub.tsx'));



export type StudioView = 'site' | 'inbox' | 'schedule' | 'admin';



const TABS: { id: StudioView; label: string; short: string; path: string; role: string; icon: string }[] = [

  { id: 'site', label: 'Shop site', short: 'Site', path: 'studionine.app', role: 'Client site + style-memory DM bot on every page', icon: '✂' },

  { id: 'inbox', label: 'DM inbox', short: 'DMs', path: 'studionine.app/inbox', role: 'Instagram & WhatsApp — AI recalls fade, barber, waitlist fill', icon: '◎' },

  { id: 'schedule', label: 'The board', short: 'Board', path: 'studionine.app/board', role: 'Live chair view — barbers, walk-ins, next up', icon: '▦' },

  { id: 'admin', label: 'Owner', short: 'Owner', path: 'studionine.app/owner', role: 'Rebook AI + loyalty nudges — revenue and chair utilization', icon: '◈' },

];



export default function StudioNineShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {

  const [view, setView] = useState<StudioView>('site');

  const [bookedSlot, setBookedSlot] = useState<TimeSlot | null>(null);



  const goToView = useCallback((id: StudioView) => setView(id), []);



  const onBooked = useCallback((slot: TimeSlot) => {

    setBookedSlot(slot);

    setView('inbox');

  }, []);



  const tab = TABS.find((t) => t.id === view)!;



  return (

    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--personal-care">

      <div className="sn-frame-toolbar">

        <p className="sol-detail-demo__hint sn-frame-toolbar__hint">

          <span className="sol-detail-demo__hint-dot" aria-hidden />

          <strong>{tab.role}</strong>

        </p>

      </div>



      <div className="sol-detail-demo__experience sn-frame">

        <div className="sn-frame__stripe" aria-hidden />

        <header className="sn-frame__head">

          <div className="sn-frame__brand">

            <span className="sn-frame__logo">9</span>

            <div>

              <p className="sn-frame__product">Studio Nine</p>

              <p className="sn-frame__tag">Barbershop OS</p>

            </div>

          </div>

          <div className="sn-frame__url">


            {tab.path}

          </div>

          <span className="sn-frame__live">Live</span>

        </header>



        <nav className="sn-frame__tabs" aria-label="Demo views">

          {TABS.map((t) => (

            <button

              key={t.id}

              type="button"

              onClick={() => goToView(t.id)}

              className={`sn-frame__tab ${view === t.id ? 'sn-frame__tab--on' : ''}`}

              title={t.role}

            >

              <span className="sn-frame__tab-icon" aria-hidden>{t.icon}</span>

              <span className="hidden sm:inline">{t.label}</span>

              <span className="sm:hidden">{t.short}</span>

            </button>

          ))}

        </nav>



        <div className="sn-frame__viewport">
          <div className="sn-frame__view">
            <Suspense fallback={<div className="sn-frame__loading" />}>
              {view === 'site' && <StudioClientSite onBook={onBooked} />}
              {view === 'inbox' && <StudioDMInbox bookedSlot={bookedSlot} onClearBooking={() => setBookedSlot(null)} />}
              {view === 'schedule' && <StudioChairCalendar highlightClient={bookedSlot ? 'Mike T.' : undefined} />}
              {view === 'admin' && <StudioOwnerHub />}
            </Suspense>
          </div>
        </div>

      </div>



      <div className="sol-detail-demo__footer">

        <p className="sol-detail-demo__footer-copy">

          <strong>Try it:</strong> Tap “My usual fade” in DM chat → style memory books Jay → chair board fills without a phone call.

        </p>

        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">

          Get this for my shop

          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>

            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />

          </svg>

        </button>

      </div>

    </div>

  );

}


