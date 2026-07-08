import { useEffect, useState, type CSSProperties } from 'react';
import { RowLogo } from '../shared/ShowcaseChatIcons.tsx';
import {
  HOTEL,
  OCCUPANCY_BARS,
  REVENUE_METRICS,
  TODAY_ARRIVALS,
  TODAY_DEPARTURES,
  GUEST_MEMORIES,
  TONIGHT_STATS,
  VIP_TICKER,
  CONCIERGE_QUEUE,
  HOUSEKEEPING_SUMMARY,
  FLOOR_HEAT,
  ROOM_TYPE_MIX,
  CHANNEL_MIX,
  REVENUE_PACE,
} from './rowData.ts';

type HubTab = 'tonight' | 'occupancy' | 'desk' | 'hk' | 'memory' | 'revenue';

const NAV: { id: HubTab; label: string; sub: string; icon: string }[] = [
  { id: 'tonight', label: 'Tonight', sub: 'Mission control', icon: '◈' },
  { id: 'occupancy', label: 'Occupancy', sub: 'Week + floor heat', icon: '▣' },
  { id: 'desk', label: 'Front desk', sub: 'In & out board', icon: '◇' },
  { id: 'hk', label: 'Housekeeping', sub: 'Floor sync', icon: '▦' },
  { id: 'memory', label: 'Guest memory', sub: 'Prefs + AI notes', icon: '◎' },
  { id: 'revenue', label: 'Revenue', sub: 'Channels + pace', icon: '◆' },
];

const TITLES: Record<HubTab, string> = {
  tonight: 'Tonight · mission control',
  occupancy: 'Occupancy & rooms',
  desk: 'Front desk board',
  hk: 'Housekeeping sync',
  memory: 'Guest memory',
  revenue: 'Revenue & channels',
};

export default function RowOpsHub() {
  const [tab, setTab] = useState<HubTab>('tonight');
  const [tickerIdx, setTickerIdx] = useState(0);
  const [checkedIn, setCheckedIn] = useState<Record<string, boolean>>({});
  const [appliedPrefs, setAppliedPrefs] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const id = window.setInterval(() => {
      setTickerIdx((n) => (n + 1) % VIP_TICKER.length);
    }, 3400);
    return () => window.clearInterval(id);
  }, []);

  const vip = VIP_TICKER[tickerIdx];
  const gauge = TONIGHT_STATS.occupancyPct;
  const gaugeDeg = Math.round((gauge / 100) * 270);

  return (
    <div className="rh-ops">
      <aside className="rh-ops__nav">
        <div className="rh-ops__brand">
          <RowLogo className="rh-ops__logo" />
          <div>
            <strong>Row Ops</strong>
            <span>Hospitality OS</span>
          </div>
        </div>
        <nav aria-label="Ops navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? 'rh-ops__nav-btn rh-ops__nav-btn--on' : 'rh-ops__nav-btn'}
              onClick={() => setTab(item.id)}
            >
              <span className="rh-ops__nav-icon" aria-hidden>{item.icon}</span>
              <span className="rh-ops__nav-text">
                <span>{item.label}</span>
                <em>{item.sub}</em>
              </span>
            </button>
          ))}
        </nav>
        <div className="rh-ops__nav-foot">
          <span className="rh-ops__live-dot" />
          Live · Fri service
        </div>
      </aside>

      <main className="rh-ops__main">
        <div className="rh-ops__topbar">
          <div>
            <p className="rh-ops__eyebrow">{HOTEL.name} · {HOTEL.address}</p>
            <h1>{TITLES[tab]}</h1>
          </div>
          <div className="rh-ops__topbar-meta">
            <span className="rh-ops__pulse">
              <span className="rh-ops__live-dot" />
              Live
            </span>
            <span className="rh-ops__clock">3:42 PM</span>
          </div>
        </div>

        <div className="rh-ops__ticker" aria-live="polite">
          <span className="rh-ops__ticker-label">VIP arrivals</span>
          <div key={vip.guest} className="rh-ops__ticker-item">
            <strong>{vip.guest}</strong>
            <span>#{vip.room} · {vip.eta}</span>
            <em>{vip.note}</em>
          </div>
        </div>

        <div className="rh-ops__revstrip">
          {REVENUE_METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'rh-ops__kpi rh-ops__kpi--accent' : 'rh-ops__kpi'}>
              <span>{m.label}</span>
              <strong>{m.value}</strong>
              <em>{m.sub}</em>
            </article>
          ))}
        </div>

        {tab === 'tonight' && (
          <div className="rh-ops__panel">
            <div className="rh-ops__tonight-grid">
              <section className="rh-ops__card rh-ops__card--gauge">
                <div className="rh-ops__card-head">
                  <h2>Live occupancy</h2>
                  <span>{TONIGHT_STATS.roomsOccupied}/{TONIGHT_STATS.roomsTotal} rooms</span>
                </div>
                <div
                  className="rh-ops__gauge"
                  style={{ '--rh-gauge': `${gaugeDeg}deg` } as CSSProperties}
                  role="img"
                  aria-label={`${gauge}% occupied`}
                >
                  <div className="rh-ops__gauge-ring">
                    <strong>{gauge}%</strong>
                    <span>Tonight</span>
                  </div>
                </div>
                <div className="rh-ops__gauge-foot">
                  <div>
                    <strong>{TONIGHT_STATS.roomsToSell}</strong>
                    <span>Rooms to sell</span>
                  </div>
                  <div>
                    <strong>{TONIGHT_STATS.walkInPace}</strong>
                    <span>Walk-in pace</span>
                  </div>
                </div>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Mission stack</h2>
                  <span className="rh-ops__pill">Priority</span>
                </div>
                <ul className="rh-ops__stack">
                  <li>
                    <strong>{TONIGHT_STATS.vipArrivals} VIP arrival</strong>
                    <span>Penthouse 504 · prefs auto-staged</span>
                  </li>
                  <li>
                    <strong>{TONIGHT_STATS.conciergeOpen} concierge open</strong>
                    <span>Chat + memory pre-arrival queues</span>
                  </li>
                  <li>
                    <strong>{TONIGHT_STATS.arrivals} arrivals · {TONIGHT_STATS.departures} departures</strong>
                    <span>2 rooms still cleaning for ETA</span>
                  </li>
                  <li>
                    <strong>{TONIGHT_STATS.lateCheckouts} late checkouts</strong>
                    <span>AI approved · HK board synced</span>
                  </li>
                </ul>
              </section>

              <section className="rh-ops__card rh-ops__card--wide">
                <div className="rh-ops__card-head">
                  <h2>Concierge queue</h2>
                  <span>{CONCIERGE_QUEUE.filter((c) => c.status === 'open').length} open</span>
                </div>
                <ul className="rh-ops__queue">
                  {CONCIERGE_QUEUE.map((c) => (
                    <li key={c.id} className={`rh-ops__queue-item rh-ops__queue-item--${c.status}`}>
                      <div>
                        <strong>{c.guest}</strong>
                        <p>{c.request}</p>
                      </div>
                      <div className="rh-ops__queue-meta">
                        <em>{c.channel}</em>
                        <span>{c.eta}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Next arrivals</h2>
                  <button type="button" className="rh-ops__link-btn" onClick={() => setTab('desk')}>
                    Front desk →
                  </button>
                </div>
                <ul className="rh-ops__mini-list">
                  {TODAY_ARRIVALS.map((a) => (
                    <li key={a.id} className={a.vip ? 'rh-ops__mini-list-vip' : undefined}>
                      <strong>{a.time}</strong>
                      <span>{a.guest}{a.vip ? ' · VIP' : ''}</span>
                      <em>#{a.room}</em>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        )}

        {tab === 'occupancy' && (
          <div className="rh-ops__panel">
            <div className="rh-ops__occ-grid">
              <section className="rh-ops__card rh-ops__card--wide">
                <div className="rh-ops__card-head">
                  <h2>This week</h2>
                  <span>Occupancy % · Fri peak</span>
                </div>
                <div className="rh-ops__bars">
                  {OCCUPANCY_BARS.map((bar) => (
                    <div key={bar.day} className="rh-ops__bar-col">
                      <span className="rh-ops__bar-val">{bar.pct}%</span>
                      <div className="rh-ops__bar-track">
                        <div
                          className={`rh-ops__bar-fill ${bar.pct >= 90 ? 'rh-ops__bar-fill--hot' : ''} ${bar.day === 'Fri' ? 'rh-ops__bar-fill--today' : ''}`}
                          style={{ height: `${bar.pct}%` }}
                        />
                      </div>
                      <span className="rh-ops__bar-day">{bar.day}</span>
                    </div>
                  ))}
                </div>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Floor heat</h2>
                  <span>Live</span>
                </div>
                <div className="rh-ops__floors">
                  {FLOOR_HEAT.map((f) => (
                    <article key={f.floor} className="rh-ops__floor">
                      <div className="rh-ops__floor-top">
                        <strong>Floor {f.floor}</strong>
                        <span>{f.occ}% occ</span>
                      </div>
                      <div className="rh-ops__heat-bar" aria-hidden>
                        <i style={{ width: `${f.occ}%` }} />
                      </div>
                      <div className="rh-ops__floor-chips">
                        <span className="rh-ops__chip rh-ops__chip--dirty">{f.dirty} dirty</span>
                        <span className="rh-ops__chip rh-ops__chip--cleaning">{f.cleaning} cleaning</span>
                        <span className="rh-ops__chip rh-ops__chip--ready">{f.ready} ready</span>
                        <span className="rh-ops__chip">{f.occupied} in-house</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Room-type mix</h2>
                  <span>Tonight sell</span>
                </div>
                <ul className="rh-ops__mix">
                  {ROOM_TYPE_MIX.map((r) => (
                    <li key={r.type}>
                      <div className="rh-ops__mix-head">
                        <strong>{r.type}</strong>
                        <em>{r.adr}</em>
                      </div>
                      <div className="rh-ops__mix-bar">
                        <span style={{ width: `${r.pct}%` }} />
                      </div>
                      <small>{r.sold}/{r.total} · {r.pct}%</small>
                    </li>
                  ))}
                </ul>
              </section>
            </div>
          </div>
        )}

        {tab === 'desk' && (
          <div className="rh-ops__panel">
            <div className="rh-ops__desk-grid">
              <section className="rh-ops__card rh-ops__card--wide">
                <div className="rh-ops__card-head">
                  <h2>Arrivals</h2>
                  <span>{TODAY_ARRIVALS.length} expected</span>
                </div>
                <div className="rh-ops__desk-list">
                  {TODAY_ARRIVALS.map((a) => {
                    const done = checkedIn[a.id];
                    return (
                      <article
                        key={a.id}
                        className={`rh-ops__desk-row ${a.vip ? 'rh-ops__desk-row--vip' : ''} ${done ? 'rh-ops__desk-row--done' : ''}`}
                      >
                        <div className="rh-ops__desk-time">
                          <strong>{a.time}</strong>
                          {a.vip && <span className="rh-ops__vip">VIP</span>}
                        </div>
                        <div className="rh-ops__desk-main">
                          <strong>{a.guest}</strong>
                          <p>
                            {a.type} · {a.nights} night{a.nights > 1 ? 's' : ''}
                            {a.returning ? ' · returning' : ''}
                          </p>
                          {a.prefs && (
                            <em className="rh-ops__ai-pref">
                              <span>AI</span> {a.prefs}
                            </em>
                          )}
                        </div>
                        <div className="rh-ops__desk-room">
                          <label>
                            Room
                            <select defaultValue={a.room} aria-label={`Assign room for ${a.guest}`}>
                              <option value={a.room}>{a.room}</option>
                              <option value="403">403</option>
                              <option value="502">502</option>
                              <option value="504">504</option>
                              <option value="605">605</option>
                            </select>
                          </label>
                          <span className={a.roomReady ? 'rh-ops__ready' : 'rh-ops__wait'}>
                            {a.roomReady ? 'Inspected' : 'HK pending'}
                          </span>
                        </div>
                        <button
                          type="button"
                          className={done ? 'rh-ops__action rh-ops__action--done' : 'rh-ops__action'}
                          onClick={() => setCheckedIn((s) => ({ ...s, [a.id]: true }))}
                          disabled={done}
                        >
                          {done ? 'Checked in' : 'Check in'}
                        </button>
                      </article>
                    );
                  })}
                </div>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Departures</h2>
                  <span>{TODAY_DEPARTURES.length} today</span>
                </div>
                <div className="rh-ops__desk-list rh-ops__desk-list--compact">
                  {TODAY_DEPARTURES.map((d) => (
                    <article key={d.id} className="rh-ops__desk-row rh-ops__desk-row--out">
                      <div className="rh-ops__desk-time">
                        <strong>{d.time}</strong>
                      </div>
                      <div className="rh-ops__desk-main">
                        <strong>{d.guest}</strong>
                        <p>Room {d.room} · checkout</p>
                        {d.prefs && <em className="rh-ops__ai-pref"><span>AI</span> {d.prefs}</em>}
                      </div>
                      <span className="rh-ops__out-badge">Out</span>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          </div>
        )}

        {tab === 'hk' && (
          <div className="rh-ops__panel">
            <div className="rh-ops__hk-banner">
              <span className="rh-ops__live-dot" />
              Desk ↔ HK live · {HOUSEKEEPING_SUMMARY.syncNote}
            </div>
            <div className="rh-ops__hk-counts">
              {([
                ['dirty', HOUSEKEEPING_SUMMARY.dirty, 'Dirty'],
                ['cleaning', HOUSEKEEPING_SUMMARY.cleaning, 'Cleaning'],
                ['clean', HOUSEKEEPING_SUMMARY.clean, 'Clean'],
                ['inspected', HOUSEKEEPING_SUMMARY.inspected, 'Inspected'],
                ['occupied', HOUSEKEEPING_SUMMARY.occupied, 'Occupied'],
              ] as const).map(([key, count, label]) => (
                <article key={key} className={`rh-ops__hk-stat rh-ops__hk-stat--${key}`}>
                  <strong>{count}</strong>
                  <span>{label}</span>
                </article>
              ))}
            </div>
            <div className="rh-ops__hk-grid">
              <section className="rh-ops__card rh-ops__card--wide">
                <div className="rh-ops__card-head">
                  <h2>Floor chips</h2>
                  <span>Open the housekeeping board for full grid</span>
                </div>
                <div className="rh-ops__floors rh-ops__floors--row">
                  {FLOOR_HEAT.map((f) => (
                    <article key={f.floor} className="rh-ops__floor">
                      <div className="rh-ops__floor-top">
                        <strong>Floor {f.floor}</strong>
                        <span>{f.ready} ready · {f.dirty + f.cleaning} open</span>
                      </div>
                      <div className="rh-ops__floor-chips">
                        <span className="rh-ops__chip rh-ops__chip--dirty">{f.dirty} dirty</span>
                        <span className="rh-ops__chip rh-ops__chip--cleaning">{f.cleaning} cleaning</span>
                        <span className="rh-ops__chip rh-ops__chip--ready">{f.ready} ready</span>
                        <span className="rh-ops__chip">{f.occupied} in-house</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>VIP / flags</h2>
                  <span className="rh-ops__pill">{HOUSEKEEPING_SUMMARY.vipReady} VIP ready</span>
                </div>
                <ul className="rh-ops__stack">
                  <li>
                    <strong>504 Penthouse inspected</strong>
                    <span>Claire Dubois · hypoallergenic staged</span>
                  </li>
                  <li>
                    <strong>405 late checkout held</strong>
                    <span>Turndown deferred · board flagged</span>
                  </li>
                  <li>
                    <strong>401 still dirty</strong>
                    <span>Departure · M. Reyes assigned</span>
                  </li>
                </ul>
              </section>
            </div>
          </div>
        )}

        {tab === 'memory' && (
          <div className="rh-ops__panel">
            <p className="rh-ops__memory-intro">
              Returning prefs sync from Concierge AI to front desk and housekeeping before arrival — one tap to auto-apply.
            </p>
            <div className="rh-ops__memory-grid">
              {GUEST_MEMORIES.map((g) => {
                const applied = appliedPrefs[g.name];
                return (
                  <article key={g.name} className="rh-ops__memory-card">
                    <div className="rh-ops__memory-head">
                      <div>
                        <strong>{g.name}</strong>
                        <span>{g.loyalty}</span>
                      </div>
                      <em>{g.stays} stays · last {g.lastStay}</em>
                    </div>
                    {g.room && (
                      <p className="rh-ops__memory-stay">
                        Tonight · #{g.room} · {g.nights} night{(g.nights ?? 1) > 1 ? 's' : ''}
                      </p>
                    )}
                    <div className="rh-ops__memory-prefs">
                      {g.prefs.map((p) => (
                        <span key={p} className="rh-ops__pref-chip">{p}</span>
                      ))}
                    </div>
                    {g.history && (
                      <ul className="rh-ops__history">
                        {g.history.map((h) => (
                          <li key={h}>{h}</li>
                        ))}
                      </ul>
                    )}
                    {g.aiNote && (
                      <p className="rh-ops__ai-note">
                        <span>Concierge AI</span>
                        {g.aiNote}
                      </p>
                    )}
                    <button
                      type="button"
                      className={applied ? 'rh-ops__action rh-ops__action--done' : 'rh-ops__action'}
                      onClick={() => setAppliedPrefs((s) => ({ ...s, [g.name]: true }))}
                      disabled={applied}
                    >
                      {applied ? 'Prefs applied · HK + desk' : 'Auto-apply prefs'}
                    </button>
                  </article>
                );
              })}
            </div>
          </div>
        )}

        {tab === 'revenue' && (
          <div className="rh-ops__panel">
            <div className="rh-ops__rev-grid">
              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Channel mix</h2>
                  <span>Tonight nights</span>
                </div>
                <ul className="rh-ops__channels">
                  {CHANNEL_MIX.map((c) => (
                    <li key={c.channel}>
                      <div className="rh-ops__channel-head">
                        <strong>{c.channel}</strong>
                        <em>{c.pct}%</em>
                      </div>
                      <div className="rh-ops__channel-bar">
                        <span className={`rh-ops__channel-fill rh-ops__channel-fill--${c.color}`} style={{ width: `${c.pct}%` }} />
                      </div>
                      <small>{c.nights} nights · {c.revenue}</small>
                    </li>
                  ))}
                </ul>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Tonight pace</h2>
                  <span>{REVENUE_PACE.tonight.pace}</span>
                </div>
                <div className="rh-ops__pace">
                  <div className="rh-ops__pace-meter">
                    <div
                      className="rh-ops__pace-fill"
                      style={{ width: `${(REVENUE_PACE.tonight.sold / REVENUE_PACE.tonight.target) * 100}%` }}
                    />
                  </div>
                  <p>
                    <strong>{REVENUE_PACE.tonight.sold}</strong> / {REVENUE_PACE.tonight.target} rooms sold
                  </p>
                  <div className="rh-ops__pace-stats">
                    <div>
                      <strong>{REVENUE_PACE.week.rev}</strong>
                      <span>Week revenue</span>
                    </div>
                    <div>
                      <strong>{REVENUE_PACE.week.vsPrior}</strong>
                      <span>vs prior week</span>
                    </div>
                  </div>
                </div>
              </section>

              <section className="rh-ops__card">
                <div className="rh-ops__card-head">
                  <h2>Upsell attach</h2>
                  <span className="rh-ops__pill">{REVENUE_PACE.upsellAttach.rate}</span>
                </div>
                <p className="rh-ops__upsell-copy">
                  Tonight attach: {REVENUE_PACE.upsellAttach.tonight}
                </p>
                <ul className="rh-ops__stack">
                  <li>
                    <strong>Late checkout</strong>
                    <span>6 AI-approved · $180 incremental</span>
                  </li>
                  <li>
                    <strong>Breakfast upgrade</strong>
                    <span>11 attached · front desk prompt</span>
                  </li>
                  <li>
                    <strong>Spa packages</strong>
                    <span>3 pending on VIP arrivals</span>
                  </li>
                </ul>
              </section>

              <section className="rh-ops__card rh-ops__card--wide">
                <div className="rh-ops__card-head">
                  <h2>Pickup · direct vs OTA</h2>
                  <span>Nights booked this week</span>
                </div>
                <div className="rh-ops__pickup">
                  {REVENUE_PACE.pickup.map((d) => {
                    const max = 16;
                    return (
                      <div key={d.day} className="rh-ops__pickup-col">
                        <div className="rh-ops__pickup-stack" style={{ height: '6.5rem' }}>
                          <div
                            className="rh-ops__pickup-ota"
                            style={{ height: `${(d.ota / max) * 100}%` }}
                            title={`OTA ${d.ota}`}
                          />
                          <div
                            className="rh-ops__pickup-direct"
                            style={{ height: `${(d.direct / max) * 100}%` }}
                            title={`Direct ${d.direct}`}
                          />
                        </div>
                        <span>{d.day}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="rh-ops__pickup-legend">
                  <span><i className="rh-ops__leg--direct" /> Direct</span>
                  <span><i className="rh-ops__leg--ota" /> OTA</span>
                </div>
              </section>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
