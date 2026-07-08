import { useState } from 'react';
import {
  ROOMS,
  PRACTITIONERS,
  TREATMENTS,
  TODAY_APPOINTMENTS,
  getPractitioner,
  getRoom,
} from './harborData';
import { StaffPageHeader } from './HarborPageChrome';

type AdminPage = 'overview' | 'services' | 'rooms' | 'staff' | 'inquiries' | 'patients' | 'automations';

const METRICS = [
  { label: 'Appointments today', value: '12', change: '+2 vs yesterday', trend: 'up', accent: true },
  { label: 'AI-resolved inquiries', value: '78%', change: '32 threads this week', trend: 'up' },
  { label: 'New patients', value: '8', change: '+3 this week', trend: 'up' },
  { label: 'No-show rate', value: '4%', change: '↓ 38% with reminders', trend: 'down' },
];

const INQUIRIES = [
  { name: 'Sarah M.', source: 'Instagram', service: 'Botox consult', score: 92, status: 'Booked', time: '2m ago' },
  { name: 'Priya N.', source: 'Google', service: 'New patient', score: 84, status: 'Hot', time: '18m ago' },
  { name: 'Emma R.', source: 'Web chat', service: 'Facial package', score: 71, status: 'Warm', time: '1h ago' },
  { name: 'Alex W.', source: 'WhatsApp', service: 'Insurance Q', score: 58, status: 'Nurture', time: '2h ago' },
];

const ACTIVITY = [
  { text: 'Sarah M. booked via website', detail: 'Thu 2:30 PM · Consult Suite A', type: 'booking' },
  { text: 'Maya R. updated room equipment', detail: 'Treatment Room 2', type: 'admin' },
  { text: 'AI resolved FAQ', detail: 'Laser downtime · Emma R.', type: 'ai' },
  { text: 'Intake form completed', detail: 'David P. · ready for 10:30 AM', type: 'form' },
  { text: 'Reminder sent', detail: 'Maria K. · 9:00 AM visit', type: 'auto' },
];

const PATIENTS = [
  { name: 'Maria K.', last: 'Today · Hydrafacial', forms: 'Complete', next: '—', tag: 'VIP' },
  { name: 'Sarah M.', last: 'New patient', forms: 'Complete', next: 'Thu 2:30 PM', tag: 'New' },
  { name: 'David P.', last: 'Today · Consult', forms: 'Complete', next: '—', tag: '' },
  { name: 'James L.', last: 'May 12', forms: 'Pending', next: 'Today 5:30 PM', tag: '' },
];

const AUTOMATIONS = [
  { id: 'intake', title: 'Patient intake AI', desc: '24/7 chat · escalates 22% to staff', on: true },
  { id: 'reminders', title: 'Appointment reminders', desc: 'SMS + email · 24h & 2h before', on: true },
  { id: 'chase', title: 'Intake form chase', desc: 'Auto-nudge after 6 hours idle', on: true },
  { id: 'digest', title: 'Daily clinic digest', desc: '7:00 AM to front desk email', on: true },
  { id: 'winback', title: 'No-show win-back', desc: 'Offer rebook slot after missed visit', on: true },
  { id: 'waitlist', title: 'Waitlist backfill', desc: 'Fills cancellations within 15 min', on: true },
];

const NAV: { id: AdminPage; label: string; icon: string; group?: string }[] = [
  { id: 'overview', label: 'Overview', icon: '◫' },
  { id: 'services', label: 'Services', icon: '◇', group: 'Clinic setup' },
  { id: 'rooms', label: 'Rooms', icon: '▣', group: 'Clinic setup' },
  { id: 'staff', label: 'Staff', icon: '◉', group: 'Clinic setup' },
  { id: 'inquiries', label: 'Inquiries', icon: '◎' },
  { id: 'patients', label: 'Patients', icon: '◈' },
  { id: 'automations', label: 'Automations', icon: '⚡' },
];

const ROOM_UTIL = [
  { id: 'room-1', pct: 92 },
  { id: 'room-2', pct: 78 },
  { id: 'room-3', pct: 64 },
];

export default function HarborClinicAdmin() {
  const [page, setPage] = useState<AdminPage>('overview');
  const [automations, setAutomations] = useState(AUTOMATIONS);

  const liveServices = TREATMENTS.filter((t) => t.published).length;

  const toggleAuto = (id: string) => {
    setAutomations((items) => items.map((a) => (a.id === id ? { ...a, on: !a.on } : a)));
  };

  return (
    <div className="hc-admin hc-admin--pro">
      <aside className="hc-admin__nav">
        <div className="hc-admin__brand">
          <span>H</span>
          <div>
            <p>Harbor Care</p>
            <small>Practice admin</small>
          </div>
        </div>
        {NAV.map((item, i) => {
          const showGroup = item.group && (i === 0 || NAV[i - 1]?.group !== item.group);
          return (
            <div key={item.id}>
              {showGroup && <p className="hc-admin__nav-group">{item.group}</p>}
              <button
                type="button"
                className={`hc-admin__nav-btn ${page === item.id ? 'hc-admin__nav-btn--active' : ''}`}
                onClick={() => setPage(item.id)}
              >
                <span className="hc-admin__nav-icon" aria-hidden>{item.icon}</span>
                {item.label}
              </button>
            </div>
          );
        })}
        <div className="hc-admin__nav-foot">
          <p>Synced with patient site & calendar</p>
        </div>
      </aside>

      <div className="hc-admin__body">
        <header className="hc-admin__topbar">
          <div className="hc-admin__search">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3-3" /></svg>
            <input type="search" placeholder="Search patients, services, rooms…" aria-label="Search admin" />
          </div>
          <div className="hc-admin__topbar-actions">
            <button type="button" className="hc-admin__topbar-btn" aria-label="Notifications">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0" /></svg>
              <span className="hc-admin__topbar-badge">3</span>
            </button>
            <div className="hc-admin__user">
              <span className="hc-admin__user-avatar">MR</span>
              <div>
                <strong>Maya R.</strong>
                <small>Office Manager</small>
              </div>
            </div>
          </div>
        </header>

        <nav className="hc-admin__mobile-nav" aria-label="Admin sections">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'hc-admin__mobile-nav-btn hc-admin__mobile-nav-btn--active' : 'hc-admin__mobile-nav-btn'}
              onClick={() => setPage(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <main className="hc-admin__main">
          {page === 'overview' && (
            <>
              <StaffPageHeader
                role="admin"
                title="Good morning, Maya"
                subtitle={`${ROOMS.length} rooms · ${liveServices} services live · ${PRACTITIONERS.length} providers`}
              />
              <div className="hc-admin__sync-bar">
                <span className="hc-admin__sync"><span className="hc-pulse" /> Live · synced just now</span>
                <div className="hc-admin__quick-actions">
                  <button type="button" className="hc-admin__action hc-admin__action--primary">+ New appointment</button>
                  <button type="button" className="hc-admin__action">Add room</button>
                </div>
              </div>

              <div className="hc-admin__metrics hc-admin__metrics--pro">
                {METRICS.map((m) => (
                  <div key={m.label} className={`hc-admin__metric ${m.accent ? 'hc-admin__metric--accent' : ''}`}>
                    <p>{m.label}</p>
                    <span className="hc-admin__metric-val">{m.value}</span>
                    <small className={m.trend === 'down' ? 'hc-admin__metric-trend--down' : ''}>{m.change}</small>
                  </div>
                ))}
              </div>

              <div className="hc-admin__overview-grid">
                <section className="hc-admin__panel hc-admin__panel--chart">
                  <div className="hc-admin__panel-head">
                    <h3>Room utilization · today</h3>
                    <span className="hc-admin__panel-tag">From calendar</span>
                  </div>
                  <div className="hc-admin__util-bars">
                    {ROOM_UTIL.map((u) => {
                      const room = getRoom(u.id);
                      return (
                        <div key={u.id} className="hc-admin__util-row">
                          <span>{room?.name}</span>
                          <div className="hc-admin__util-track"><span style={{ width: `${u.pct}%` }} /></div>
                          <strong>{u.pct}%</strong>
                        </div>
                      );
                    })}
                  </div>
                  <p className="hc-admin__panel-foot">Peak block 2–4 PM · 1 open slot at 3:30 PM</p>
                </section>

                <section className="hc-admin__panel">
                  <div className="hc-admin__panel-head">
                    <h3>AI-scored inquiries</h3>
                    <button type="button" className="hc-admin__action" onClick={() => setPage('inquiries')}>View all</button>
                  </div>
                  <div className="hc-admin__lead-list">
                    {INQUIRIES.slice(0, 3).map((r) => (
                      <article key={r.name} className="hc-admin__lead">
                        <div className="hc-admin__lead-main">
                          <span className="hc-admin__lead-avatar">{r.name.charAt(0)}</span>
                          <div>
                            <strong>{r.name}</strong>
                            <span>{r.service} · {r.source}</span>
                          </div>
                        </div>
                        <span className="hc-admin__score">{r.score}</span>
                        <span className={`hc-admin__lead-status hc-admin__lead-status--${r.status.toLowerCase()}`}>{r.status}</span>
                      </article>
                    ))}
                  </div>
                </section>

                <section className="hc-admin__panel hc-admin__panel--wide">
                  <div className="hc-admin__panel-head">
                    <h3>Live activity</h3>
                  </div>
                  <ul className="hc-admin__activity hc-admin__activity--pro">
                    {ACTIVITY.map((a) => (
                      <li key={a.text} className={`hc-admin__activity-item hc-admin__activity-item--${a.type}`}>
                        <span className="hc-admin__activity-dot" />
                        <div>
                          <strong>{a.text}</strong>
                          <span>{a.detail}</span>
                        </div>
                        <small>Just now</small>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="hc-admin__panel">
                  <div className="hc-admin__panel-head">
                    <h3>Today&apos;s schedule</h3>
                    <button type="button" className="hc-admin__action">Open calendar</button>
                  </div>
                  <ul className="hc-admin__mini-schedule">
                    {TODAY_APPOINTMENTS.filter((a) => a.patient !== '—').slice(0, 4).map((a) => (
                      <li key={a.patient + a.time}>
                        <span>{a.time}</span>
                        <div>
                          <strong>{a.patient}</strong>
                          <small>{a.service} · {getRoom(a.roomId)?.name}</small>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              </div>
            </>
          )}

          {page === 'services' && (
            <>
              <StaffPageHeader role="admin" title="Services catalog" subtitle="Published services appear on harborwellness.com · linked to providers and rooms" />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <div className="hc-admin__panel-top">
                  <div className="hc-admin__panel-filters">
                    <button type="button" className="hc-admin__filter hc-admin__filter--on">All</button>
                    <button type="button" className="hc-admin__filter">Live on website</button>
                    <button type="button" className="hc-admin__filter">Draft</button>
                  </div>
                  <button type="button" className="hc-admin__action hc-admin__action--primary">+ Add service</button>
                </div>
                <div className="hc-admin__service-list">
                  {TREATMENTS.map((t) => (
                    <article key={t.id} className="hc-admin__service-row">
                      <span className="hc-admin__service-icon" aria-hidden>{t.icon}</span>
                      <div className="hc-admin__service-main">
                        <strong>{t.name}</strong>
                        <span>{t.duration} · {t.tag}</span>
                      </div>
                      <span className="hc-admin__service-price">{t.price}</span>
                      <span className="hc-admin__service-meta">{t.practitionerIds.map((id) => getPractitioner(id)?.name.split(' ').slice(-1)[0]).join(', ')}</span>
                      <span className="hc-admin__service-meta">{t.roomIds.map((id) => getRoom(id)?.name).join(', ')}</span>
                      <span className={`hc-admin__pill ${t.published ? 'hc-admin__pill--on' : ''}`}>{t.published ? 'Live' : 'Draft'}</span>
                      <button type="button" className="hc-admin__action">Edit</button>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}

          {page === 'rooms' && (
            <>
              <StaffPageHeader role="admin" title="Rooms & resources" subtitle="Rooms configured here drive calendar columns and online booking locations" />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <div className="hc-admin__panel-top">
                  <p className="hc-admin__panel-hint">3 active · synced to clinic calendar</p>
                  <button type="button" className="hc-admin__action hc-admin__action--primary">+ Add room</button>
                </div>
                <div className="hc-admin__room-grid hc-admin__room-grid--pro">
                  {ROOMS.map((room) => {
                    const util = ROOM_UTIL.find((u) => u.id === room.id)?.pct ?? 0;
                    return (
                      <article key={room.id} className={`hc-admin__room-card hc-admin__room-card--pro ${room.status === 'maintenance' ? 'hc-admin__room-card--maint' : ''}`}>
                        <div className="hc-admin__room-head">
                          <div>
                            <h4>{room.name}</h4>
                            <p className="hc-admin__room-purpose">{room.purpose}</p>
                          </div>
                          <span className={`hc-admin__pill ${room.status === 'active' ? 'hc-admin__pill--on' : ''}`}>{room.status}</span>
                        </div>
                        <div className="hc-admin__room-util">
                          <span>Today&apos;s utilization</span>
                          <div className="hc-admin__util-track"><span style={{ width: `${util}%` }} /></div>
                          <strong>{util}%</strong>
                        </div>
                        <ul className="hc-admin__room-equip">
                          {room.equipment.map((e) => (
                            <li key={e}>{e}</li>
                          ))}
                        </ul>
                        <p className="hc-admin__room-meta">Created by {room.createdBy} · {room.createdAt}</p>
                        <div className="hc-admin__room-actions">
                          <button type="button" className="hc-admin__action">Edit room</button>
                          <button type="button" className="hc-admin__action">View calendar</button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            </>
          )}

          {page === 'staff' && (
            <>
              <StaffPageHeader role="admin" title="Staff & providers" subtitle='Providers marked "visible on website" appear on the public team page' />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <div className="hc-admin__panel-top">
                  <p className="hc-admin__panel-hint">{PRACTITIONERS.filter((p) => p.visibleOnWebsite).length} visible on website</p>
                  <button type="button" className="hc-admin__action hc-admin__action--primary">+ Invite staff</button>
                </div>
                <div className="hc-admin__staff-grid hc-admin__staff-grid--pro">
                  {PRACTITIONERS.map((p) => (
                    <article key={p.id} className="hc-admin__staff-card hc-admin__staff-card--pro">
                      <div className="hc-admin__staff-head">
                        <img src={p.imageUrl} alt={p.name} className="hc-admin__staff-photo" loading="lazy" />
                        <div>
                          <h4>{p.name}</h4>
                          <p>{p.title}</p>
                          <span className={`hc-admin__pill ${p.visibleOnWebsite ? 'hc-admin__pill--on' : ''}`}>
                            {p.visibleOnWebsite ? 'On website' : 'Hidden'}
                          </span>
                        </div>
                      </div>
                      <p className="hc-admin__staff-spec">{p.specialties.join(' · ')}</p>
                      <div className="hc-admin__staff-schedule">
                        <span>Today</span>
                        <strong>{TODAY_APPOINTMENTS.filter((a) => a.practitionerId === p.id && a.patient !== '—').length} appointments</strong>
                      </div>
                      <button type="button" className="hc-admin__action">Manage profile</button>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}

          {page === 'inquiries' && (
            <>
              <StaffPageHeader role="admin" title="All inquiries" subtitle="AI-ranked leads · avg first response 28 seconds" />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <div className="hc-admin__inquiry-grid">
                  {INQUIRIES.map((r) => (
                    <article key={r.name} className="hc-admin__inquiry-card">
                      <div className="hc-admin__inquiry-top">
                        <span className="hc-admin__lead-avatar">{r.name.charAt(0)}</span>
                        <div>
                          <strong>{r.name}</strong>
                          <span>{r.source} · {r.time}</span>
                        </div>
                        <span className="hc-admin__score">{r.score}</span>
                      </div>
                      <p>{r.service}</p>
                      <div className="hc-admin__inquiry-foot">
                        <span className={`hc-admin__lead-status hc-admin__lead-status--${r.status.toLowerCase()}`}>{r.status}</span>
                        <button type="button" className="hc-admin__action">Open thread</button>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}

          {page === 'patients' && (
            <>
              <StaffPageHeader role="admin" title="Patient records" subtitle="Forms, visit history, and upcoming appointments" />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <table className="hc-admin__table hc-admin__table--pro">
                  <thead>
                    <tr><th>Patient</th><th>Last visit</th><th>Forms</th><th>Next appt</th><th></th></tr>
                  </thead>
                  <tbody>
                    {PATIENTS.map((p) => (
                      <tr key={p.name}>
                        <td>
                          <div className="hc-admin__patient-cell">
                            <span className="hc-admin__lead-avatar">{p.name.charAt(0)}</span>
                            <div>
                              <strong>{p.name}</strong>
                              {p.tag && <span className="hc-admin__patient-tag">{p.tag}</span>}
                            </div>
                          </div>
                        </td>
                        <td>{p.last}</td>
                        <td><span className={`hc-admin__pill ${p.forms === 'Complete' ? 'hc-admin__pill--on' : ''}`}>{p.forms}</span></td>
                        <td>{p.next}</td>
                        <td><button type="button" className="hc-admin__action">Open chart</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </>
          )}

          {page === 'automations' && (
            <>
              <StaffPageHeader role="admin" title="Automations" subtitle="Patients never see these — staff and AI run them behind the scenes" />
              <section className="hc-admin__panel hc-admin__panel--full hc-admin__panel--flush">
                <div className="hc-admin__auto-grid hc-admin__auto-grid--pro">
                  {automations.map((a) => (
                    <article key={a.id} className={`hc-admin__auto-card hc-admin__auto-card--pro ${a.on ? 'hc-admin__auto-card--on' : ''}`}>
                      <div className="hc-admin__auto-top">
                        <div>
                          <strong>{a.title}</strong>
                          <p>{a.desc}</p>
                        </div>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={a.on}
                          className={`hc-admin__toggle ${a.on ? 'hc-admin__toggle--on' : ''}`}
                          onClick={() => toggleAuto(a.id)}
                        >
                          <span />
                        </button>
                      </div>
                      <button type="button" className="hc-admin__action">Configure rules</button>
                    </article>
                  ))}
                </div>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
