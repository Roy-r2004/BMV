import { useMemo, useState } from 'react';
import { PeakFormLogo } from '../shared/ShowcaseChatIcons.tsx';
import { COACHES, HUB_MEMBERS, PROGRAMS, STUDIO, type Member } from './peakformData.ts';
import { onPeakformImageError } from './peakformImageFallback.ts';

type HubPage = 'members' | 'programs' | 'coaches' | 'connect';

const METRICS = [
  { label: 'Class fill', value: '89%', sub: 'Peak hours optimized', accent: true },
  { label: 'Active members', value: '142', sub: '+8 this month' },
  { label: 'Renewals due', value: '12', sub: 'Auto-reminders sent' },
  { label: 'Retention', value: '89%', sub: '30-day active' },
];

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'members', label: 'Members', sub: 'Adherence' },
  { id: 'programs', label: 'Programs', sub: 'Class templates' },
  { id: 'coaches', label: 'Coaches', sub: 'Team roster' },
  { id: 'connect', label: 'Connect', sub: 'Integrations' },
];

const PAGE_TITLE: Record<HubPage, string> = {
  members: 'Coach hub',
  programs: 'Program manager',
  coaches: 'Coach roster',
  connect: 'Connections',
};

const KANBAN: { score: Member['score']; label: string; hint: string }[] = [
  { score: 'active', label: 'Active', hint: 'On program' },
  { score: 'trial', label: 'Trial', hint: 'Convert' },
  { score: 'at-risk', label: 'At risk', hint: 'Re-engage' },
];

const CONNECT = [
  { name: 'Stripe billing', detail: 'Memberships + class packs', on: true },
  { name: 'Check-in kiosk', detail: 'QR scan at door', on: true },
  { name: 'Wearable sync', detail: 'Apple Health · Whoop', on: true },
  { name: 'Reminder SMS', detail: 'Class nudges + streaks', on: true },
];

const SCORE_LABEL: Record<Member['score'], string> = {
  active: 'Active',
  trial: 'Trial',
  'at-risk': 'At risk',
};

export default function PeakFormCoachHub() {
  const [page, setPage] = useState<HubPage>('members');

  const membersByScore = useMemo(() => {
    const map: Record<Member['score'], Member[]> = { active: [], trial: [], 'at-risk': [] };
    HUB_MEMBERS.forEach((m) => map[m.score].push(m));
    return map;
  }, []);

  return (
    <div className="pf-hub">
      <aside className="pf-hub__nav">
        <div className="pf-hub__brand">
          <PeakFormLogo className="pf-hub__brand-logo" />
          <div>
            <strong>Peak Form Hub</strong>
            <span>Coach dashboard</span>
          </div>
        </div>
        <nav aria-label="Hub navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'pf-hub__nav-btn pf-hub__nav-btn--on' : 'pf-hub__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="pf-hub__nav-label">{item.label}</span>
              <span className="pf-hub__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className="pf-hub__nav-foot">
          <span className="pf-hub__nav-live" />
          Studio live
        </div>
      </aside>

      <main className="pf-hub__main">
        <div className="pf-hub__hero-strip">
          <img src={STUDIO.floorImage} alt="" onError={onPeakformImageError} />
          <div className="pf-hub__hero-shade" aria-hidden />
          <div className="pf-hub__hero-grain" aria-hidden />
          <div className="pf-hub__hero-copy">
            <p>Thursday evening block</p>
            <strong>142 active members · 89% class fill</strong>
          </div>
        </div>

        <header className="pf-hub__head">
          <div>
            <p className="pf-hub__head-eyebrow">{STUDIO.name}</p>
            <h1>{PAGE_TITLE[page]}</h1>
            <p>Thursday · 6:15 PM · 34 check-ins today</p>
          </div>
          <span className="pf-hub__live">Live</span>
        </header>

        <div className="pf-hub__metrics">
          {METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'pf-hub__metric pf-hub__metric--accent' : 'pf-hub__metric'}>
              <strong>{m.value}</strong>
              <span>{m.label}</span>
              <small>{m.sub}</small>
            </article>
          ))}
        </div>

        {page === 'members' && (
          <>
            <div className="pf-hub__ai-banner pf-hub__ai-banner--alert">
              <div>
                <strong>3 members about to cancel — AI already sent win-backs</strong>
                <p>Missed 2+ classes flagged · offers out · coach digest at 7am so you stop silent churn</p>
              </div>
              <span className="pf-hub__ai-banner-tag">Revenue saved</span>
            </div>
            <div className="pf-hub__kanban">
            {KANBAN.map((col) => (
              <section key={col.score} className="pf-hub__column">
                <header>
                  <h3>{col.label}</h3>
                  <span>{col.hint}</span>
                </header>
                <ul>
                  {membersByScore[col.score].map((m) => (
                    <li key={m.id}>
                      <article className={`pf-hub__member pf-hub__member--${m.score}`}>
                        <div className="pf-hub__member-top">
                          <strong>{m.name}</strong>
                          <span className={`pf-hub__score pf-hub__score--${m.score}`}>{SCORE_LABEL[m.score]}</span>
                        </div>
                        <p className="pf-hub__member-program">{m.program}</p>
                        <div className="pf-hub__member-meta">
                          <span>{m.source}</span>
                          <span>{m.streak}</span>
                        </div>
                        <footer>{m.lastActivity}</footer>
                      </article>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          </>
        )}

        {page === 'programs' && (
          <div className="pf-hub__programs">
            {PROGRAMS.map((p) => (
              <article key={p.id} className="pf-hub__program-card">
                <img src={p.imageUrl} alt={p.name} loading="lazy" onError={(e) => onPeakformImageError(e, p.name)} />
                <div>
                  <h3>{p.name}</h3>
                  <p>{p.category} · {p.duration} · {p.price}</p>
                  {p.tag && <em>{p.tag}</em>}
                </div>
                <button type="button">Edit</button>
              </article>
            ))}
          </div>
        )}

        {page === 'coaches' && (
          <div className="pf-hub__coaches">
            {COACHES.map((c) => (
              <article key={c.id} className="pf-hub__coach-card">
                <img src={c.imageUrl} alt={c.name} loading="lazy" onError={(e) => onPeakformImageError(e, c.photoInitial)} />
                <div>
                  <h3>{c.name}</h3>
                  <p>{c.title}</p>
                  <p className="pf-hub__coach-bio">{c.bio}</p>
                  <div className="pf-hub__coach-tags">
                    {c.specialties.map((t) => <span key={t}>{t}</span>)}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {page === 'connect' && (
          <div className="pf-hub__connect">
            {CONNECT.map((c) => (
              <article key={c.name} className={c.on ? 'pf-hub__connect-card pf-hub__connect-card--on' : 'pf-hub__connect-card'}>
                <div>
                  <h3>{c.name}</h3>
                  <p>{c.detail}</p>
                </div>
                <span className="pf-hub__toggle" aria-hidden>{c.on ? 'On' : 'Off'}</span>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
