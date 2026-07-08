import { useMemo, useState, type CSSProperties } from 'react';
import {
  ROOMS,
  PRACTITIONERS,
  TODAY_APPOINTMENTS,
  getPractitioner,
  getRoom,
  type Appointment,
} from './harborData';
import HarborSubNav from './HarborSubNav';
import { StaffPageHeader } from './HarborPageChrome';

type SchedulePage = 'today' | 'week' | 'waitlist' | 'checkin';
type FilterType = 'all' | 'practitioner' | 'room';
type TodayView = 'timeline' | 'list';

const WAITLIST = [
  { patient: 'Tom H.', service: 'Botox consult', requested: 'Thu PM', since: '2 days', match: 94 },
  { patient: 'Nina C.', service: 'Hydrafacial', requested: 'Any Fri', since: '1 day', match: 88 },
  { patient: 'Keira W.', service: 'IV therapy', requested: 'Wed AM', since: '4 hours', match: 76 },
];

const WEEK_DAYS = [
  { label: 'Mon', date: '7', count: 10, load: 83 },
  { label: 'Tue', date: '8', count: 12, load: 100, today: true },
  { label: 'Wed', date: '9', count: 9, load: 75 },
  { label: 'Thu', date: '10', count: 14, load: 92 },
  { label: 'Fri', date: '11', count: 8, load: 67 },
];

const CAL_START = 8;
const CAL_END = 18;
const PX_PER_HOUR = 56;
const NOW_MINUTES = 14 * 60 + 15; // demo "now" = 2:15 PM

const STATUS_LABEL: Record<Appointment['status'], string> = {
  'checked-in': 'Checked in',
  confirmed: 'Confirmed',
  new: 'New booking',
  open: 'Available',
  pending: 'Pending',
};

const ROOM_TINT: Record<string, string> = {
  'room-1': '#0e7490',
  'room-2': '#7c3aed',
  'room-3': '#059669',
};

function timeToMinutes(time: string) {
  const [h, m = '0'] = time.split(':');
  return Number(h) * 60 + Number(m);
}

function formatTime12(time: string) {
  const mins = timeToMinutes(time);
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const period = h >= 12 ? 'PM' : 'AM';
  const hour = h % 12 || 12;
  return m ? `${hour}:${String(m).padStart(2, '0')} ${period}` : `${hour} ${period}`;
}

interface Props {
  highlightPatient?: string;
}

export default function HarborSchedule({ highlightPatient }: Props) {
  const [page, setPage] = useState<SchedulePage>('today');
  const [todayView, setTodayView] = useState<TodayView>('list');
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [filterId, setFilterId] = useState<string>('all');
  const [checkedIn, setCheckedIn] = useState<string[]>(['Maria K.']);
  const [selected, setSelected] = useState<Appointment | null>(null);

  const activeRooms = ROOMS.filter((r) => r.status === 'active');

  const rows = TODAY_APPOINTMENTS.filter((a) => {
    if (filterType === 'all' || filterId === 'all') return true;
    if (filterType === 'practitioner') return a.practitionerId === filterId;
    return a.roomId === filterId;
  });

  const timelineHeight = (CAL_END - CAL_START) * PX_PER_HOUR;
  const nowTop = ((NOW_MINUTES - CAL_START * 60) / 60) * PX_PER_HOUR;

  const hours = useMemo(
    () => Array.from({ length: CAL_END - CAL_START + 1 }, (_, i) => CAL_START + i),
    [],
  );

  const navItems = [
    { id: 'today' as const, label: 'Today' },
    { id: 'week' as const, label: 'Week view' },
    { id: 'waitlist' as const, label: 'Waitlist', badge: WAITLIST.length },
    { id: 'checkin' as const, label: 'Check-in' },
  ];

  const renderStatus = (status: Appointment['status']) => (
    <span className={`hc-schedule__status hc-schedule__status--${status}`}>{STATUS_LABEL[status]}</span>
  );

  return (
    <div className="hc-schedule-app">
      <HarborSubNav items={navItems} active={page} onChange={setPage} className="hc-subnav--schedule" />

      {page === 'today' && (
        <div className="hc-schedule hc-schedule--pro">
          <StaffPageHeader
            role="schedule"
            title="Clinic calendar"
            subtitle="Tuesday, July 8 · rooms & providers synced from Practice admin"
          />

          <div className="hc-schedule__command">
            <div className="hc-schedule__command-left">
              <div className="hc-schedule__date-nav">
                <button type="button" aria-label="Previous day">‹</button>
                <span>Today · Jul 8</span>
                <button type="button" aria-label="Next day">›</button>
              </div>
              <div className="hc-schedule__view-toggle">
                <button
                  type="button"
                  className={todayView === 'timeline' ? 'hc-schedule__view-btn hc-schedule__view-btn--on' : 'hc-schedule__view-btn'}
                  onClick={() => setTodayView('timeline')}
                >
                  Timeline
                </button>
                <button
                  type="button"
                  className={todayView === 'list' ? 'hc-schedule__view-btn hc-schedule__view-btn--on' : 'hc-schedule__view-btn'}
                  onClick={() => setTodayView('list')}
                >
                  List
                </button>
              </div>
            </div>
            <div className="hc-schedule__command-right">
              <button type="button" className="hc-schedule__btn-ghost">Print day sheet</button>
              <button type="button" className="hc-schedule__add">+ New appointment</button>
            </div>
          </div>

          <div className="hc-schedule__stats hc-schedule__stats--pro">
            {[
              { val: '12', label: 'Appointments', sub: '+2 vs yesterday', accent: true },
              { val: '3', label: 'In next hour', sub: 'Sarah · Lisa · open slot' },
              { val: '87%', label: 'Room utilization', sub: 'Peak 2–4 PM' },
              { val: '4%', label: 'No-show rate', sub: '↓ 38% with AI reminders' },
            ].map((s) => (
              <div key={s.label} className={`hc-schedule__stat ${s.accent ? 'hc-schedule__stat--accent' : ''}`}>
                <span className="hc-schedule__stat-val">{s.val}</span>
                <span className="hc-schedule__stat-label">{s.label}</span>
                <small>{s.sub}</small>
              </div>
            ))}
          </div>

          <div className="hc-schedule__filter-bar">
            <span className="hc-schedule__filter-label">Filter</span>
            <div className="hc-schedule__filters">
              {(['all', 'practitioner', 'room'] as FilterType[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  className={`hc-schedule__filter ${filterType === f ? 'hc-schedule__filter--on' : ''}`}
                  onClick={() => { setFilterType(f); setFilterId('all'); }}
                >
                  {f === 'all' ? 'All' : f === 'practitioner' ? 'Provider' : 'Room'}
                </button>
              ))}
            </div>
            {filterType === 'practitioner' && (
              <div className="hc-schedule__filters hc-schedule__filters--sub">
                <button type="button" className={`hc-schedule__filter ${filterId === 'all' ? 'hc-schedule__filter--on' : ''}`} onClick={() => setFilterId('all')}>All</button>
                {PRACTITIONERS.map((p) => (
                  <button key={p.id} type="button" className={`hc-schedule__filter ${filterId === p.id ? 'hc-schedule__filter--on' : ''}`} onClick={() => setFilterId(p.id)}>
                    {p.name.split(' ').slice(-1)[0]}
                  </button>
                ))}
              </div>
            )}
            {filterType === 'room' && (
              <div className="hc-schedule__filters hc-schedule__filters--sub">
                <button type="button" className={`hc-schedule__filter ${filterId === 'all' ? 'hc-schedule__filter--on' : ''}`} onClick={() => setFilterId('all')}>All</button>
                {ROOMS.map((r) => (
                  <button key={r.id} type="button" className={`hc-schedule__filter ${filterId === r.id ? 'hc-schedule__filter--on' : ''}`} onClick={() => setFilterId(r.id)}>{r.name}</button>
                ))}
              </div>
            )}
          </div>

          {todayView === 'timeline' ? (
            <div className="hc-cal-wrap">
              <div className="hc-cal">
                <div className="hc-cal__room-headers">
                  <div className="hc-cal__room-head hc-cal__room-head--empty" aria-hidden />
                  {activeRooms.map((room) => (
                    <div key={room.id} className="hc-cal__room-head" style={{ '--room-color': ROOM_TINT[room.id] } as CSSProperties}>
                      <span className="hc-cal__room-dot" />
                      <div>
                        <strong>{room.name}</strong>
                        <small>{room.purpose}</small>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="hc-cal__scroll">
                  <div className="hc-cal__body">
                    <div className="hc-cal__times" style={{ height: timelineHeight }}>
                      {hours.map((h) => (
                        <div key={h} className="hc-cal__time" style={{ top: (h - CAL_START) * PX_PER_HOUR }}>
                          {h <= 12 ? `${h === 12 ? 12 : h} ${h < 12 ? 'AM' : 'PM'}` : `${h - 12} PM`}
                        </div>
                      ))}
                    </div>
                    <div className="hc-cal__grid" style={{ height: timelineHeight }}>
                      {hours.slice(0, -1).map((h) => (
                        <div key={h} className="hc-cal__grid-line" style={{ top: (h - CAL_START) * PX_PER_HOUR }} />
                      ))}
                      <div className="hc-cal__now" style={{ top: nowTop }}>
                        <span>2:15 PM</span>
                      </div>
                      {activeRooms.map((room) => {
                        const roomAppts = rows.filter((a) => a.roomId === room.id);
                        return (
                          <div key={room.id} className="hc-cal__col">
                            {roomAppts.map((a, i) => {
                              const top = ((timeToMinutes(a.time) - CAL_START * 60) / 60) * PX_PER_HOUR;
                              const height = Math.max((a.durationMin / 60) * PX_PER_HOUR - 6, 32);
                              const isHighlight = highlightPatient && a.patient === highlightPatient;
                              const isSelected = selected?.patient === a.patient && selected?.time === a.time;
                              return (
                                <button
                                  key={`${a.time}-${i}`}
                                  type="button"
                                  className={`hc-cal__block hc-cal__block--${a.status} ${isHighlight ? 'hc-cal__block--highlight' : ''} ${isSelected ? 'hc-cal__block--selected' : ''}`}
                                  style={{ top, height, '--room-color': ROOM_TINT[room.id] } as CSSProperties}
                                  onClick={() => setSelected(a)}
                                >
                                  <span className="hc-cal__block-time">{formatTime12(a.time)}</span>
                                  <strong>{a.patient}</strong>
                                  <span>{a.service}</span>
                                  <small>{getPractitioner(a.practitionerId)?.name.split(' ').slice(-1)[0]}</small>
                                </button>
                              );
                            })}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {selected && (
                <aside className="hc-cal-detail">
                  <button type="button" className="hc-cal-detail__close" onClick={() => setSelected(null)} aria-label="Close">×</button>
                  <p className="hc-cal-detail__eyebrow">{getRoom(selected.roomId)?.name}</p>
                  <h3>{selected.patient === '—' ? 'Open slot' : selected.patient}</h3>
                  <p className="hc-cal-detail__service">{selected.service}</p>
                  <dl className="hc-cal-detail__meta">
                    <div><dt>Time</dt><dd>{formatTime12(selected.time)} · {selected.durationMin} min</dd></div>
                    <div><dt>Provider</dt><dd>{getPractitioner(selected.practitionerId)?.name}</dd></div>
                    <div><dt>Status</dt><dd>{renderStatus(selected.status)}</dd></div>
                    <div><dt>Intake</dt><dd>{selected.status === 'new' ? 'Form sent · pending' : 'Complete'}</dd></div>
                  </dl>
                  <div className="hc-cal-detail__actions">
                    {selected.status === 'open' ? (
                      <button type="button" className="hc-schedule__add">Book from waitlist</button>
                    ) : (
                      <>
                        <button type="button" className="hc-schedule__add">Check in</button>
                        <button type="button" className="hc-schedule__btn-ghost">Message patient</button>
                      </>
                    )}
                  </div>
                </aside>
              )}
            </div>
          ) : (
            <div className="hc-schedule__grid">
              <div className="hc-schedule__grid-head">
                <span>Time</span><span>Patient</span><span>Service</span><span>Provider</span><span>Room</span><span>Status</span>
              </div>
              {rows.map((a, i) => (
                <div
                  key={`${a.time}-${i}`}
                  className={`hc-schedule__row ${highlightPatient && a.patient === highlightPatient ? 'hc-schedule__row--highlight' : ''} ${a.status === 'open' ? 'hc-schedule__row--open' : ''}`}
                >
                  <span className="hc-schedule__time">{formatTime12(a.time)}</span>
                  <span className="hc-schedule__patient">{a.patient}</span>
                  <span>{a.service}</span>
                  <span>{getPractitioner(a.practitionerId)?.name ?? '—'}</span>
                  <span className="hc-schedule__room">{getRoom(a.roomId)?.name ?? '—'}</span>
                  {renderStatus(a.status)}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {page === 'week' && (
        <div className="hc-schedule-page">
          <StaffPageHeader role="schedule" title="Week of July 7–11" subtitle="Capacity planning · click a day to open in Today view" />
          <div className="hc-schedule-page--pad">
            <div className="hc-week-summary">
              {WEEK_DAYS.map((d) => (
                <button
                  key={d.label}
                  type="button"
                  className={`hc-week-summary__day ${d.today ? 'hc-week-summary__day--today' : ''}`}
                >
                  <span className="hc-week-summary__label">{d.label}</span>
                  <span className="hc-week-summary__date">{d.date}</span>
                  <span className="hc-week-summary__count">{d.count} appts</span>
                  <div className="hc-week-summary__bar"><span style={{ width: `${d.load}%` }} /></div>
                  <small>{d.load}% capacity</small>
                </button>
              ))}
            </div>
            <div className="hc-week-grid">
              <div className="hc-week-grid__head">
                <span />
                {WEEK_DAYS.map((d) => (
                  <span key={d.label} className={d.today ? 'hc-week-grid__today' : ''}>{d.label} {d.date}</span>
                ))}
              </div>
              {['Morning', 'Afternoon', 'Evening'].map((block, bi) => (
                <div key={block} className="hc-week-grid__row">
                  <span className="hc-week-grid__block-label">{block}</span>
                  {WEEK_DAYS.map((d) => {
                    const n = Math.max(1, Math.floor(d.count / 3) + (bi === 1 ? 1 : 0));
                    return (
                      <div key={d.label} className={`hc-week-grid__cell ${d.today ? 'hc-week-grid__cell--today' : ''}`}>
                        {Array.from({ length: Math.min(n, 4) }).map((_, i) => (
                          <span key={i} className="hc-week-grid__pill" style={{ opacity: 1 - i * 0.15 }} />
                        ))}
                        <small>{n} slots</small>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
            <p className="hc-schedule-page__note">Online bookings sync in real time · waitlist auto-fills cancellations</p>
          </div>
        </div>
      )}

      {page === 'waitlist' && (
        <div className="hc-schedule-page">
          <StaffPageHeader role="schedule" title="Waitlist" subtitle="AI matches patients to open slots · average fill time 15 min" />
          <div className="hc-schedule-page--pad">
            <div className="hc-waitlist-stats">
              <div><strong>{WAITLIST.length}</strong><span>Active requests</span></div>
              <div><strong>15m</strong><span>Avg fill time</span></div>
              <div><strong>2</strong><span>Matched today</span></div>
            </div>
            {WAITLIST.map((w) => (
              <article key={w.patient} className="hc-waitlist-card">
                <div className="hc-waitlist-card__main">
                  <div className="hc-waitlist-card__avatar">{w.patient.charAt(0)}</div>
                  <div>
                    <strong>{w.patient}</strong>
                    <span>{w.service}</span>
                    <small>Prefers {w.requested} · waiting {w.since}</small>
                  </div>
                </div>
                <div className="hc-waitlist-card__match">
                  <span className="hc-waitlist-card__score">{w.match}%</span>
                  <small>AI match</small>
                </div>
                <div className="hc-waitlist-card__actions">
                  <button type="button" className="hc-schedule__add">Offer slot</button>
                  <button type="button" className="hc-schedule__btn-ghost">View chat</button>
                </div>
              </article>
            ))}
          </div>
        </div>
      )}

      {page === 'checkin' && (
        <div className="hc-schedule-page">
          <StaffPageHeader role="schedule" title="Front desk check-in" subtitle="Digital intake on file · one tap to seat in room" />
          <div className="hc-schedule-page--pad">
            <div className="hc-checkin-progress">
              <div className="hc-checkin-progress__bar"><span style={{ width: `${(checkedIn.length / 5) * 100}%` }} /></div>
              <p>{checkedIn.length} of 5 checked in · {5 - checkedIn.length} arriving soon</p>
            </div>
            <div className="hc-checkin-grid">
              {TODAY_APPOINTMENTS.filter((a) => a.patient !== '—').map((a) => {
                const done = checkedIn.includes(a.patient);
                const practitioner = getPractitioner(a.practitionerId);
                return (
                  <article key={a.patient + a.time} className={`hc-checkin-card ${done ? 'hc-checkin-card--done' : ''} ${highlightPatient === a.patient ? 'hc-checkin-card--highlight' : ''}`}>
                    <div className="hc-checkin-card__top">
                      <span className="hc-checkin-card__time">{formatTime12(a.time)}</span>
                      {renderStatus(done ? 'checked-in' : a.status)}
                    </div>
                    <div className="hc-checkin-card__patient">
                      <span className="hc-checkin-card__avatar">{a.patient.charAt(0)}</span>
                      <div>
                        <strong>{a.patient}</strong>
                        <span>{a.service}</span>
                      </div>
                    </div>
                    <div className="hc-checkin-card__meta">
                      <span>{getRoom(a.roomId)?.name}</span>
                      <span>{practitioner?.name}</span>
                    </div>
                    <div className="hc-checkin-card__forms">
                      <span className="hc-checkin-card__form hc-checkin-card__form--done">Intake ✓</span>
                      <span className={`hc-checkin-card__form ${a.status === 'pending' ? '' : 'hc-checkin-card__form--done'}`}>ID {a.status === 'pending' ? '…' : '✓'}</span>
                    </div>
                    {done ? (
                      <p className="hc-checkin-card__seated">Seated · room notified</p>
                    ) : (
                      <button type="button" className="hc-schedule__add hc-checkin-card__btn" onClick={() => setCheckedIn((c) => [...c, a.patient])}>
                        Check in now
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
