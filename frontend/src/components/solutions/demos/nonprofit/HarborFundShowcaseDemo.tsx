import { lazy, Suspense, useCallback, useState } from 'react';
import '../../../../styles/nonprofit-demo.css';
import type { ShowcaseDemoProps } from '../showcaseRegistry';
import { HarborFundLogo } from '../shared/ShowcaseChatIcons.tsx';
import type { Donation } from './harborFundData.ts';
import HarborDonorSite from './HarborDonorSite.tsx';

const HarborDonorInbox = lazy(() => import('./HarborDonorInbox.tsx'));
const HarborVolunteerBoard = lazy(() => import('./HarborVolunteerBoard.tsx'));
const HarborCampaignHub = lazy(() => import('./HarborCampaignHub.tsx'));

export type HarborFundView = 'site' | 'inbox' | 'volunteer' | 'hub';

const TABS: { id: HarborFundView; label: string; short: string; path: string; role: string; icon: string }[] = [
  { id: 'site', label: 'Donor site', short: 'Site', path: 'harborgive.app', role: 'Smart donate + impact meter + volunteer CTA — not a CRM homepage', icon: '◆' },
  { id: 'inbox', label: 'Donor inbox', short: 'Inbox', path: 'harborgive.app/inbox', role: 'Thank-you bot sends personalized receipts + impact stories', icon: '◎' },
  { id: 'volunteer', label: 'Volunteer board', short: 'Board', path: 'harborgive.app/volunteer', role: 'Skill match scores on opportunity cards', icon: '▦' },
  { id: 'hub', label: 'Campaign hub', short: 'Hub', path: 'harborgive.app/hub', role: 'Progress rings + donor segments + volunteer hours', icon: '◈' },
];

export default function HarborFundShowcaseDemo({ onRequestClick }: ShowcaseDemoProps) {
  const [view, setView] = useState<HarborFundView>('site');
  const [donation, setDonation] = useState<Donation | null>(null);

  const goToView = useCallback((id: HarborFundView) => setView(id), []);

  const onDonate = useCallback((d: Donation) => {
    setDonation(d);
    setView('inbox');
  }, []);

  const onVolunteerIntent = useCallback(() => {
    setView('volunteer');
  }, []);

  const tab = TABS.find((t) => t.id === view)!;

  return (
    <div className="sol-detail-demo__showcase sol-detail-demo__showcase--nonprofit">
      <div className="hg-frame-toolbar">
        <p className="sol-detail-demo__hint hg-frame-toolbar__hint">
          <span className="sol-detail-demo__hint-dot" aria-hidden />
          <strong>{tab.role}</strong>
        </p>
      </div>

      <div className="sol-detail-demo__experience hg-frame">
        <div className="hg-frame__accent" aria-hidden />
        <header className="hg-frame__head">
          <div className="hg-frame__brand">
            <span className="hg-frame__logo" aria-hidden>
              <HarborFundLogo className="hg-frame__logo-svg" />
            </span>
            <div>
              <p className="hg-frame__product">Harbor Give</p>
              <p className="hg-frame__tag">Nonprofit OS</p>
            </div>
          </div>
          <div className="hg-frame__url">
            {tab.path}
          </div>
          <span className="hg-frame__live">Live</span>
        </header>

        <nav className="hg-frame__tabs" aria-label="Demo views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => goToView(t.id)}
              className={`hg-frame__tab ${view === t.id ? 'hg-frame__tab--on' : ''}`}
              title={t.role}
            >
              <span className="hg-frame__tab-icon" aria-hidden>{t.icon}</span>
              <span className="hidden sm:inline">{t.label}</span>
              <span className="sm:hidden">{t.short}</span>
            </button>
          ))}
        </nav>

        <div className="hg-frame__viewport">
          <div className="hg-frame__view">
            <Suspense fallback={<div className="hg-frame__loading" />}>
              {view === 'site' && (
                <HarborDonorSite onDonate={onDonate} onVolunteerIntent={onVolunteerIntent} />
              )}
              {view === 'inbox' && (
                <HarborDonorInbox donation={donation} onClearDonation={() => setDonation(null)} />
              )}
              {view === 'volunteer' && <HarborVolunteerBoard />}
              {view === 'hub' && <HarborCampaignHub />}
            </Suspense>
          </div>
        </div>
      </div>

      <div className="sol-detail-demo__footer">
        <p className="sol-detail-demo__footer-copy">
          <strong>Try it:</strong> Pick $50 suggested gift → confirm → inbox shows personalized thank-you receipt → open Volunteer board for skill match scores.
        </p>
        <button type="button" onClick={onRequestClick} className="sol-detail-demo__footer-cta">
          Get this for my nonprofit
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
