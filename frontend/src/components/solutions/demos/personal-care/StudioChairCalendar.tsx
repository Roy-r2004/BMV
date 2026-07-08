import { useState, type CSSProperties } from 'react';
import {
  BARBERS,
  TODAY_BOOKINGS,
  type Booking,
} from './studioData.ts';
import { onStudioImageError } from './studioImageFallback.ts';

const WALKINS = [
  { name: 'Sam K.', service: 'Skin fade', wait: '~18 min', position: 1 },
  { name: 'Tyler W.', service: 'Line-up', wait: '~35 min', position: 2 },
];

const BARBER_COLOR: Record<string, string> = {
  marcus: '#c9a227',
  jay: '#7c3aed',
  alex: '#e07a5f',
};

const CHAIR_NUM: Record<string, string> = {
  marcus: '1',
  jay: '2',
  alex: '3',
};

const STATUS: Record<Booking['status'], string> = {
  'checked-in': 'In chair',
  confirmed: 'Confirmed',
  new: 'Just booked',
  open: 'Open',
  pending: 'Pending',
};

const HOUR_BLOCKS = [
  { hour: '11', load: 78 },
  { hour: '12', load: 92 },
  { hour: '1', load: 100 },
  { hour: '2', load: 88, now: true },
  { hour: '3', load: 72 },
  { hour: '4', load: 65 },
];

interface Props {
  highlightClient?: string;
}

export default function StudioChairCalendar({ highlightClient }: Props) {
  const [selectedBarber, setSelectedBarber] = useState<string | null>(null);

  return (
    <div className="sn-board">
      <header className="sn-board__head">
        <div className="sn-board__head-title">
          <span className="sn-board__head-badge">Live</span>
          <h1>The board</h1>
          <p>Thursday · Jul 9 · 3 chairs · synced with shop site & DMs</p>
        </div>
        <div className="sn-board__head-stats">
          <div className="sn-board__stat">
            <strong>18</strong>
            <span>Bookings</span>
            <small>+3 vs yesterday</small>
          </div>
          <div className="sn-board__stat">
            <strong>91%</strong>
            <span>Utilization</span>
            <small>Peak 5–7 PM</small>
          </div>
          <div className="sn-board__stat sn-board__stat--accent">
            <strong>2</strong>
            <span>Walk-ins</span>
            <small>~25 min wait</small>
          </div>
          <div className="sn-board__stat sn-board__stat--rev">
            <strong>$1.8k</strong>
            <span>Revenue</span>
            <small>Today</small>
          </div>
        </div>
        <button type="button" className="sn-board__add">+ Walk-in</button>
      </header>

      <div className="sn-board__hour-chart" aria-hidden>
        {HOUR_BLOCKS.map((b) => (
          <div key={b.hour} className={`sn-board__hour ${b.now ? 'sn-board__hour--now' : ''}`}>
            <div className="sn-board__hour-bar"><span style={{ height: `${b.load}%` }} /></div>
            <span>{b.hour}</span>
          </div>
        ))}
      </div>

      <div className="sn-board__layout">
        <div className="sn-board__main">
          <div className="sn-board__now">
            <span className="sn-board__now-dot" />
            <span>2:15 PM</span>
            <strong>Jordan P.</strong> in Jay&apos;s chair · Cut + beard · ~35 min left
          </div>

          <div className="sn-board__lanes">
            {BARBERS.map((barber) => {
              const appts = TODAY_BOOKINGS.filter((b) => b.barberId === barber.id);
              const current = appts.find((a) => a.status === 'checked-in');
              const color = BARBER_COLOR[barber.id];
              const upcoming = appts.filter((a) => a.status !== 'checked-in').length;

              return (
                <div key={barber.id} className="sn-board__lane" style={{ '--barber-color': color } as CSSProperties}>
                  <header className="sn-board__lane-head">
                    <img src={barber.imageUrl} alt={barber.name} onError={(e) => onStudioImageError(e, barber.photoInitial)} />
                    <div>
                      <strong>{barber.name}</strong>
                      <span>{barber.title}</span>
                    </div>
                    <div className="sn-board__lane-meta">
                      <span className="sn-board__lane-chair">Chair {CHAIR_NUM[barber.id]}</span>
                      <span className="sn-board__lane-count">{upcoming} queued</span>
                    </div>
                  </header>

                  {current ? (
                    <div className="sn-board__current">
                      <div className="sn-board__current-top">
                        <span className="sn-board__current-label">In chair now</span>
                        <span className="sn-board__current-time">{current.time}</span>
                      </div>
                      <strong>{current.client}</strong>
                      <span>{current.service}</span>
                      <div className="sn-board__current-bar"><span style={{ width: '65%' }} /></div>
                      <small>~25 min remaining</small>
                    </div>
                  ) : (
                    <div className="sn-board__current sn-board__current--empty">
                      <span>Chair open</span>
                      <small>Next booking soon</small>
                    </div>
                  )}

                  <div className="sn-board__queue">
                    {appts.filter((a) => a.status !== 'checked-in').map((a, i) => (
                      <div
                        key={`${a.time}-${i}`}
                        className={`sn-board__appt sn-board__appt--${a.status} ${highlightClient && a.client === highlightClient ? 'sn-board__appt--highlight' : ''}`}
                      >
                        <span className="sn-board__appt-time">{a.time}</span>
                        <div className="sn-board__appt-body">
                          <strong>{a.client}</strong>
                          <span>{a.service}</span>
                          <div className="sn-board__appt-dur" style={{ width: `${Math.min(a.durationMin / 60 * 100, 100)}%` }} />
                        </div>
                        <em>{STATUS[a.status]}</em>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="sn-board__filter">
            <span>Focus:</span>
            <button type="button" className={!selectedBarber ? 'sn-board__filter-btn sn-board__filter-btn--on' : 'sn-board__filter-btn'} onClick={() => setSelectedBarber(null)}>All chairs</button>
            {BARBERS.map((b) => (
              <button
                key={b.id}
                type="button"
                className={selectedBarber === b.id ? 'sn-board__filter-btn sn-board__filter-btn--on' : 'sn-board__filter-btn'}
                onClick={() => setSelectedBarber(selectedBarber === b.id ? null : b.id)}
                style={selectedBarber === b.id ? { borderColor: BARBER_COLOR[b.id], background: BARBER_COLOR[b.id], color: '#14110f' } : undefined}
              >
                {b.name.split(' ')[0]}
              </button>
            ))}
          </div>
        </div>

        <aside className="sn-board__walkins">
          <header className="sn-board__walkins-head">
            <h2>Walk-in queue</h2>
            <span className="sn-board__walkins-live">2 waiting</span>
          </header>
          <p className="sn-board__walkins-sub">Alex on Chair 3 · estimates from check-in</p>

          {WALKINS.map((w) => (
            <article key={w.name} className="sn-board__walkin-card">
              <span className="sn-board__walkin-pos">#{w.position}</span>
              <div>
                <strong>{w.name}</strong>
                <span>{w.service}</span>
              </div>
              <em>{w.wait}</em>
              <button type="button">Seat now</button>
            </article>
          ))}

          <div className="sn-board__walkins-open">
            <p>Next open slot</p>
            <strong>3:00 PM</strong>
            <span>Alex · Chair 3 · 45 min</span>
            <button type="button">Fill from waitlist</button>
          </div>

          <div className="sn-board__next-up">
            <h3>Next up · all chairs</h3>
            <ul>
              <li className={highlightClient === 'Mike T.' ? 'sn-board__next--highlight' : ''}>
                <span>5:15</span>
                <div><strong>Mike T.</strong><small>Jay · Skin fade</small></div>
              </li>
              <li>
                <span>4:30</span>
                <div><strong>Chris D.</strong><small>Marcus · VIP</small></div>
              </li>
              <li>
                <span>3:00</span>
                <div><strong>Open</strong><small>Alex · Chair 3</small></div>
              </li>
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}
