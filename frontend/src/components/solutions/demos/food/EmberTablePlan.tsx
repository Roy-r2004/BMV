import { useState } from 'react';
import { TONIGHT_TABLES, type Table } from './emberData.ts';

const WALKINS = [
  { name: 'Lee party (2)', wait: '~20 min', zone: 'Bar' },
  { name: 'Patel (3)', wait: '~40 min', zone: 'Main' },
];

const TIMELINE = [
  { time: '6:00', label: 'Miller seated', active: false },
  { time: '6:30', label: 'Chen seated', active: false },
  { time: '7:30', label: 'Anderson', active: false },
  { time: '7:45', label: 'Birthday party', active: true },
];

const ZONE_LABEL: Record<Table['zone'], string> = {
  main: 'Main dining',
  patio: 'Patio',
  bar: 'Bar',
};

interface Props {
  highlightGuest?: string;
}

export default function EmberTablePlan({ highlightGuest = 'Birthday party' }: Props) {
  const [zone, setZone] = useState<'all' | Table['zone']>('all');

  const tables = TONIGHT_TABLES.filter((t) => zone === 'all' || t.zone === zone);
  const seated = TONIGHT_TABLES.filter((t) => t.status === 'seated').length;
  const reserved = TONIGHT_TABLES.filter((t) => t.status === 'reserved').length;
  const open = TONIGHT_TABLES.filter((t) => t.status === 'open').length;
  const occupancy = Math.round(((seated + reserved) / TONIGHT_TABLES.length) * 100);

  return (
    <div className="eo-floor">
      <div className="eo-floor__grain" aria-hidden />
      <header className="eo-floor__head">
        <div>
          <p className="eo-floor__eyebrow">Tonight · Saturday service</p>
          <h2>Table plan</h2>
          <p className="eo-floor__sub">34 covers booked · live floor view</p>
        </div>
        <div className="eo-floor__stats">
          <article><strong>{seated}</strong><span>Seated</span></article>
          <article><strong>{reserved}</strong><span>Reserved</span></article>
          <article><strong>{open}</strong><span>Open</span></article>
        </div>
      </header>

      <div className="eo-floor__occupancy">
        <div className="eo-floor__occupancy-bar">
          <span style={{ width: `${occupancy}%` }} />
        </div>
        <span className="eo-floor__occupancy-label">{occupancy}% occupancy</span>
      </div>

      <div className="eo-floor__timeline">
        {TIMELINE.map((t) => (
          <div key={t.time} className={`eo-floor__timeline-item ${t.active ? 'eo-floor__timeline-item--active' : ''}`}>
            <time>{t.time}</time>
            <span>{t.label}</span>
          </div>
        ))}
      </div>

      <div className="eo-floor__toolbar">
        <div className="eo-floor__zones">
          {(['all', 'main', 'patio', 'bar'] as const).map((z) => (
            <button
              key={z}
              type="button"
              className={zone === z ? 'eo-floor__zone eo-floor__zone--on' : 'eo-floor__zone'}
              onClick={() => setZone(z)}
            >
              {z === 'all' ? 'All zones' : ZONE_LABEL[z]}
            </button>
          ))}
        </div>
        <button type="button" className="eo-floor__walkin-btn">+ Walk-in</button>
      </div>

      <div className="eo-floor__legend">
        <span><i className="eo-floor__dot eo-floor__dot--seated" /> Seated</span>
        <span><i className="eo-floor__dot eo-floor__dot--reserved" /> Reserved</span>
        <span><i className="eo-floor__dot eo-floor__dot--open" /> Open</span>
      </div>

      <div className="eo-floor__layout">
        <section className="eo-floor__grid-wrap">
          <div className="eo-floor__grid">
            {tables.map((t) => {
              const highlighted = t.guest === highlightGuest;
              return (
                <article
                  key={t.id}
                  className={`eo-floor__table eo-floor__table--${t.status} eo-floor__table--${t.zone} ${highlighted ? 'eo-floor__table--highlight' : ''}`}
                >
                  <header>
                    <strong>{t.label}</strong>
                    <span>{t.seats} top</span>
                  </header>
                  <span className="eo-floor__zone-chip">{ZONE_LABEL[t.zone]}</span>
                  {t.guest ? (
                    <>
                      <p className="eo-floor__guest">{t.guest}</p>
                      {t.time && <span className="eo-floor__time">{t.time}</span>}
                    </>
                  ) : (
                    <p className="eo-floor__open-label">Available</p>
                  )}
                  {highlighted && <span className="eo-floor__new-badge">Just booked</span>}
                </article>
              );
            })}
          </div>
        </section>

        <aside className="eo-floor__queue">
          <h3>Walk-in queue</h3>
          <ul>
            {WALKINS.map((w) => (
              <li key={w.name}>
                <strong>{w.name}</strong>
                <span>{w.wait}</span>
                <small>{w.zone}</small>
              </li>
            ))}
          </ul>
          <div className="eo-floor__turn">
            <p>Est. turn time</p>
            <strong>42 min</strong>
            <span>Main dining avg</span>
          </div>
        </aside>
      </div>
    </div>
  );
}
