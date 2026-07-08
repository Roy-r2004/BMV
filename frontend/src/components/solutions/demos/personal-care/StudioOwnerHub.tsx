import { useState } from 'react';
import {
  CHAIRS,
  BARBERS,
  SERVICES,
  TODAY_BOOKINGS,
  getBarber,
} from './studioData.ts';
import { onStudioImageError } from './studioImageFallback.ts';

type HubPage = 'today' | 'menu' | 'team' | 'loyalty' | 'connect';

const METRICS = [
  { label: 'Revenue today', value: '$1,840', sub: '+$220 vs last Thu', up: true, accent: true },
  { label: 'Bookings', value: '18', sub: '2 walk-ins added', up: true },
  { label: 'Rebook rate', value: '71%', sub: '+12% this month', up: true },
  { label: 'No-shows saved', value: '6', sub: 'SMS reminders', up: false },
];

const BARBER_REV = [
  { id: 'marcus', rev: '$720', cuts: 8, pct: 39, tip: '$84' },
  { id: 'jay', rev: '$680', cuts: 7, pct: 37, tip: '$72' },
  { id: 'alex', rev: '$440', cuts: 5, pct: 24, tip: '$48' },
];

const ACTIVITY = [
  { text: 'Mike T. booked via website', detail: 'Thu 5:15 · Jay · Chair 2', time: '2m', type: 'book' },
  { text: 'Instagram DM auto-replied', detail: 'Fade pricing · Devon S.', time: '8m', type: 'ai' },
  { text: 'Chris D. earned loyalty stamp', detail: '5 of 8 — Nine Club', time: '15m', type: 'loyalty' },
  { text: 'Walk-in added — Sam K.', detail: 'Queue #1 · ~18 min', time: '22m', type: 'walkin' },
  { text: 'Reminder sent — Jordan P.', detail: '12:30 PM cut + beard', time: '1h', type: 'auto' },
];

const TOP_CLIENTS = [
  { name: 'Chris D.', visits: 24, spent: '$1,240', tag: 'VIP' },
  { name: 'Mike T.', visits: 12, spent: '$680', tag: 'Regular' },
  { name: 'Alex R.', visits: 9, spent: '$420', tag: 'Regular' },
];

const NAV: { id: HubPage; label: string }[] = [
  { id: 'today', label: 'Today' },
  { id: 'menu', label: 'Menu' },
  { id: 'team', label: 'Team' },
  { id: 'loyalty', label: 'Loyalty' },
  { id: 'connect', label: 'Connect' },
];

const REV_BARS = [62, 74, 68, 82, 91, 88, 76];

export default function StudioOwnerHub() {
  const [page, setPage] = useState<HubPage>('today');
  const [autoReminders, setAutoReminders] = useState(true);
  const [autoDM, setAutoDM] = useState(true);

  return (
    <div className="sn-hub">
      <nav className="sn-hub__nav" aria-label="Owner sections">
        {NAV.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`sn-hub__nav-btn ${page === item.id ? 'sn-hub__nav-btn--on' : ''}`}
            onClick={() => setPage(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      <div className="sn-hub__body">
        {page === 'today' && (
          <>
            <header className="sn-hub__head">
              <div>
                <p className="sn-hub__greet">Good afternoon, Marcus</p>
                <h1>Thursday at Studio Nine</h1>
                <p className="sn-hub__head-sub">3 chairs full · 2 walk-ins · IG inbox clear</p>
              </div>
              <div className="sn-hub__head-actions">
                <span className="sn-hub__sync"><span className="sn-hub__sync-dot" /> Live</span>
                <button type="button" className="sn-hub__btn">+ Booking</button>
              </div>
            </header>

            <div className="sn-hub__metrics">
              {METRICS.map((m) => (
                <article key={m.label} className={`sn-hub__metric ${m.accent ? 'sn-hub__metric--accent' : ''}`}>
                  <p>{m.label}</p>
                  <strong>{m.value}</strong>
                  <small className={m.up ? 'sn-hub__metric-up' : ''}>{m.sub}</small>
                </article>
              ))}
            </div>

            <div className="sn-hub__ai-banner">
              <div>
                <strong>Rebook AI just filled 3 empty chairs tomorrow</strong>
                <p>14 regulars due · style-memory DMs convert at 71% · slow afternoons stay profitable</p>
              </div>
              <span className="sn-hub__ai-banner-tag">Money printer</span>
            </div>

            <div className="sn-hub__grid">
              <section className="sn-hub__panel sn-hub__panel--chart">
                <div className="sn-hub__panel-head">
                  <h2>Revenue · last 7 days</h2>
                  <span className="sn-hub__panel-tag">+$840 vs prior week</span>
                </div>
                <div className="sn-hub__rev-chart">
                  {REV_BARS.map((h, i) => (
                    <div key={i} className={`sn-hub__rev-bar ${i === REV_BARS.length - 1 ? 'sn-hub__rev-bar--today' : ''}`}>
                      <span style={{ height: `${h}%` }} />
                      <em>{['T', 'W', 'T', 'F', 'S', 'S', 'M'][i]}</em>
                    </div>
                  ))}
                </div>
              </section>

              <section className="sn-hub__panel sn-hub__panel--wide">
                <div className="sn-hub__panel-head">
                  <h2>Per-barber breakdown</h2>
                  <span className="sn-hub__panel-tag">Tips included</span>
                </div>
                <div className="sn-hub__barber-rev">
                  {BARBER_REV.map((b) => {
                    const barber = getBarber(b.id);
                    return (
                      <div key={b.id} className="sn-hub__barber-rev-row">
                        <img src={barber?.imageUrl} alt="" onError={(e) => onStudioImageError(e, barber?.photoInitial)} />
                        <div className="sn-hub__barber-rev-info">
                          <strong>{barber?.name}</strong>
                          <span>{b.cuts} cuts · {b.tip} tips</span>
                          <div className="sn-hub__barber-rev-bar"><span style={{ width: `${b.pct}%` }} /></div>
                        </div>
                        <em>{b.rev}</em>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="sn-hub__panel">
                <h2>Live activity</h2>
                <ul className="sn-hub__activity">
                  {ACTIVITY.map((a) => (
                    <li key={a.text} className={`sn-hub__activity-item sn-hub__activity-item--${a.type}`}>
                      <span />
                      <div>
                        <strong>{a.text}</strong>
                        <p>{a.detail}</p>
                        <time>{a.time}</time>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="sn-hub__panel">
                <h2>Up next on the board</h2>
                <ul className="sn-hub__schedule">
                  {TODAY_BOOKINGS.filter((b) => b.client !== '—').slice(0, 5).map((b) => (
                    <li key={b.client + b.time}>
                      <span>{b.time}</span>
                      <div>
                        <strong>{b.client}</strong>
                        <small>{b.service} · {getBarber(b.barberId)?.name.split(' ')[0]}</small>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="sn-hub__panel">
                <h2>Top clients</h2>
                <ul className="sn-hub__top-clients">
                  {TOP_CLIENTS.map((c) => (
                    <li key={c.name}>
                      <span className="sn-hub__top-avatar">{c.name.charAt(0)}</span>
                      <div>
                        <strong>{c.name}</strong>
                        <small>{c.visits} visits · {c.spent}</small>
                      </div>
                      <span className={`sn-hub__pill ${c.tag === 'VIP' ? 'sn-hub__pill--vip' : ''}`}>{c.tag}</span>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </>
        )}

        {page === 'menu' && (
          <>
            <header className="sn-hub__head">
              <div>
                <span className="sn-hub__page-eyebrow">Synced to studionine.app</span>
                <h1>Service menu</h1>
              </div>
              <button type="button" className="sn-hub__btn">+ Add service</button>
            </header>
            <div className="sn-hub__menu-list">
              {SERVICES.map((s) => (
                <article key={s.id} className="sn-hub__menu-item">
                  <span className="sn-hub__menu-icon">{s.icon}</span>
                  <div>
                    <strong>{s.name}</strong>
                    <span>{s.duration} · {s.tag}</span>
                  </div>
                  <em>{s.price}</em>
                  <span className={`sn-hub__pill ${s.published ? 'sn-hub__pill--on' : ''}`}>{s.published ? 'Live' : 'Draft'}</span>
                  <button type="button">Edit</button>
                </article>
              ))}
            </div>
          </>
        )}

        {page === 'team' && (
          <>
            <header className="sn-hub__head">
              <div>
                <span className="sn-hub__page-eyebrow">3 barbers · 3 chairs</span>
                <h1>Your team</h1>
              </div>
              <button type="button" className="sn-hub__btn">+ Invite</button>
            </header>
            <div className="sn-hub__team-grid">
              {BARBERS.map((b) => (
                <article key={b.id} className="sn-hub__team-card">
                  <div className="sn-hub__team-photo">
                    <img src={b.imageUrl} alt={b.name} onError={(e) => onStudioImageError(e, b.photoInitial)} />
                  </div>
                  <h3>{b.name}</h3>
                  <p>{b.title}</p>
                  <span className="sn-hub__team-spec">{b.specialties.join(' · ')}</span>
                  <div className="sn-hub__team-stat">
                    <strong>{TODAY_BOOKINGS.filter((a) => a.barberId === b.id && a.client !== '—').length}</strong>
                    <span>cuts today</span>
                  </div>
                  <span className={`sn-hub__pill ${b.visibleOnWebsite ? 'sn-hub__pill--on' : ''}`}>
                    {b.visibleOnWebsite ? 'On site' : 'Hidden'}
                  </span>
                </article>
              ))}
            </div>
            <section className="sn-hub__chairs">
              <h2>Chair stations</h2>
              <div className="sn-hub__chair-grid">
                {CHAIRS.map((c) => (
                  <article key={c.id} className="sn-hub__chair-card">
                    <strong>{c.name}</strong>
                    <span>{getBarber(c.barberId)?.name}</span>
                    <ul>{c.equipment.map((e) => <li key={e}>{e}</li>)}</ul>
                    <span className="sn-hub__pill sn-hub__pill--on">{c.status}</span>
                  </article>
                ))}
              </div>
            </section>
          </>
        )}

        {page === 'loyalty' && (
          <>
            <header className="sn-hub__head">
              <div>
                <span className="sn-hub__page-eyebrow">Nine Club</span>
                <h1>Loyalty program</h1>
              </div>
            </header>
            <div className="sn-hub__loyalty-hero">
              <div className="sn-hub__loyalty-stats">
                <div><strong>214</strong><span>Members</span></div>
                <div><strong>38</strong><span>Free cuts redeemed</span></div>
                <div><strong>71%</strong><span>6-week rebook</span></div>
              </div>
              <div className="sn-hub__loyalty-preview" aria-label="Sample stamp card">
                {Array.from({ length: 8 }).map((_, i) => (
                  <span key={i} className={i < 5 ? 'sn-hub__stamp sn-hub__stamp--on' : 'sn-hub__stamp'}>{i < 5 ? '✂' : ''}</span>
                ))}
              </div>
            </div>
            <section className="sn-hub__panel">
              <h2>How it works</h2>
              <p>8 cuts = 1 free. Stamps auto-apply on check-in. VIP clients get priority slots and skip walk-in wait.</p>
              <div className="sn-hub__loyalty-rules">
                <div><strong>Auto-stamp</strong><span>On every check-in</span></div>
                <div><strong>VIP threshold</strong><span>10+ visits</span></div>
                <div><strong>Rebook nudge</strong><span>At 5 weeks idle</span></div>
              </div>
            </section>
          </>
        )}

        {page === 'connect' && (
          <>
            <header className="sn-hub__head">
              <div>
                <span className="sn-hub__page-eyebrow">Integrations</span>
                <h1>Connections & automations</h1>
              </div>
            </header>
            <div className="sn-hub__connect-grid">
              <article className="sn-hub__connect-card sn-hub__connect-card--on">
                <span className="sn-hub__connect-icon sn-hub__connect-icon--ig">◎</span>
                <div>
                  <strong>Instagram DMs</strong>
                  <p>Connected · AI booking on · 142 threads/wk</p>
                </div>
                <span className="sn-hub__pill sn-hub__pill--on">Live</span>
              </article>
              <article className="sn-hub__connect-card sn-hub__connect-card--on">
                <span className="sn-hub__connect-icon sn-hub__connect-icon--wa">◈</span>
                <div>
                  <strong>WhatsApp Business</strong>
                  <p>Connected · 48 threads this week</p>
                </div>
                <span className="sn-hub__pill sn-hub__pill--on">Live</span>
              </article>
              <article className="sn-hub__connect-card sn-hub__connect-card--on">
                <span className="sn-hub__connect-icon">✂</span>
                <div>
                  <strong>Shop website</strong>
                  <p>studionine.app · 4 services live</p>
                </div>
                <span className="sn-hub__pill sn-hub__pill--on">Live</span>
              </article>
            </div>
            <section className="sn-hub__auto">
              <h2>Automations</h2>
              {[
                { id: 'dm', title: 'DM auto-reply', desc: 'Books from Instagram & WhatsApp 24/7', on: autoDM, toggle: () => setAutoDM(!autoDM) },
                { id: 'remind', title: 'Booking reminders', desc: 'SMS 2h before · cuts no-shows 42%', on: autoReminders, toggle: () => setAutoReminders(!autoReminders) },
                { id: 'stamp', title: 'Loyalty stamps', desc: 'Auto-stamp on check-in', on: true, toggle: undefined },
                { id: 'rebook', title: 'Rebook nudge', desc: 'DM regulars at 5 weeks since last cut', on: true, toggle: undefined },
              ].map((a) => (
                <label key={a.id} className="sn-hub__toggle-row">
                  <div>
                    <strong>{a.title}</strong>
                    <p>{a.desc}</p>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={a.on}
                    className={`sn-hub__toggle ${a.on ? 'sn-hub__toggle--on' : ''}`}
                    onClick={a.toggle}
                    disabled={!a.toggle}
                  >
                    <span />
                  </button>
                </label>
              ))}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
