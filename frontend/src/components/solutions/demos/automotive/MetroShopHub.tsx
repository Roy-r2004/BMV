import { useState } from 'react';
import { IconSparkle, MetroLogo } from '../shared/ShowcaseChatIcons.tsx';
import { COMPANY, TECHS, TODAY_METRICS, UPSELL_ALERTS } from './metroData.ts';
import { onMetroImageError } from './metroImageFallback.ts';

type HubTab = 'roster' | 'upsells' | 'revenue';

export default function MetroShopHub() {
  const [tab, setTab] = useState<HubTab>('roster');

  return (
    <div className="mt-hub">
      <aside className="mt-hub__nav">
        <div className="mt-hub__brand">
          <MetroLogo className="mt-hub__logo" />
          <div>
            <strong>Metro Shop Hub</strong>
            <span>Floor + revenue</span>
          </div>
        </div>
        <nav aria-label="Shop hub navigation">
          {(
            [
              { id: 'roster' as const, label: 'Tech roster', sub: "Who's on which bay" },
              { id: 'upsells' as const, label: 'Upsell alerts', sub: 'Maintenance AI' },
              { id: 'revenue' as const, label: "Today's board", sub: 'Cash + jobs' },
            ]
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? 'mt-hub__nav-btn mt-hub__nav-btn--on' : 'mt-hub__nav-btn'}
              onClick={() => setTab(item.id)}
            >
              <span>{item.label}</span>
              <em>{item.sub}</em>
            </button>
          ))}
        </nav>
        <div className="mt-hub__nav-foot">
          <span className="mt-hub__live-dot" />
          Shop floor live
        </div>
      </aside>

      <main className="mt-hub__main">
        <div className="mt-hub__hero-strip">
          <img src={COMPANY.shopImage} alt="" onError={(e) => onMetroImageError(e)} />
          <div className="mt-hub__hero-shade" aria-hidden />
          <p>4 bays lit · 3 techs on lift · 1 available</p>
        </div>

        <div className="mt-hub__revenue-strip">
          {TODAY_METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'mt-hub__metric mt-hub__metric--accent' : 'mt-hub__metric'}>
              <span>{m.label}</span>
              <strong>{m.value}</strong>
              <em>{m.sub}</em>
            </article>
          ))}
        </div>

        <div className="mt-hub__upsell-strip" aria-label="Upsell alerts">
          <div className="mt-hub__upsell-label">
            <IconSparkle className="mt-hub__sparkle" />
            <strong>Upsell alerts</strong>
          </div>
          <div className="mt-hub__upsell-scroll">
            {UPSELL_ALERTS.map((u) => (
              <article key={u.id} className={`mt-hub__upsell mt-hub__upsell--${u.urgency}`}>
                <strong>{u.item}</strong>
                <span>{u.customer} · {u.vehicle}</span>
                <em>{u.value}</em>
              </article>
            ))}
          </div>
        </div>

        <header className="mt-hub__head">
          <div>
            <p>{COMPANY.name}</p>
            <h1>{tab === 'roster' ? 'Tech roster' : tab === 'upsells' ? 'Maintenance recommendations' : "Today's revenue"}</h1>
          </div>
          <span className="mt-hub__badge">Live</span>
        </header>

        {tab === 'roster' && (
          <div className="mt-hub__roster">
            {TECHS.map((tech) => (
              <article key={tech.id} className={`mt-hub__tech mt-hub__tech--${tech.status}`}>
                <span className="mt-hub__tech-avatar">{tech.initials}</span>
                <div className="mt-hub__tech-info">
                  <strong>{tech.name}</strong>
                  <span>{tech.specialty}{tech.bay ? ` · Bay ${tech.bay}` : ''}</span>
                  <em>{tech.jobsToday} jobs today · {tech.rating}★</em>
                </div>
                <span className={`mt-hub__tech-status mt-hub__tech-status--${tech.status}`}>
                  {tech.status.replace('-', ' ')}
                </span>
              </article>
            ))}
          </div>
        )}

        {tab === 'upsells' && (
          <div className="mt-hub__upsell-list">
            <p className="mt-hub__upsell-intro">
              Maintenance AI surfaces recommendations from bay progress — staff present, customers approve.
            </p>
            {UPSELL_ALERTS.map((u) => (
              <article key={u.id} className={`mt-hub__upsell-row mt-hub__upsell-row--${u.urgency}`}>
                <div>
                  <strong>{u.item}</strong>
                  <span>{u.reason}</span>
                  <em>{u.customer} · {u.vehicle}</em>
                </div>
                <strong className="mt-hub__upsell-value">{u.value}</strong>
                <button type="button" className="mt-hub__upsell-btn">Present to customer</button>
              </article>
            ))}
          </div>
        )}

        {tab === 'revenue' && (
          <div className="mt-hub__revenue-detail">
            {TODAY_METRICS.map((m) => (
              <article key={m.label} className={m.accent ? 'mt-hub__rev-card mt-hub__rev-card--accent' : 'mt-hub__rev-card'}>
                <span>{m.label}</span>
                <strong>{m.value}</strong>
                <em>{m.sub}</em>
              </article>
            ))}
            <p className="mt-hub__revenue-note">
              Upsells accepted today: 7 jobs · $890 — driven by bay-floor alerts, not cold-calling.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
