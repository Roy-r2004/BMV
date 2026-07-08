import { useState } from 'react';
import { getRoom, type TimeSlot } from './harborData';
import HarborSubNav from './HarborSubNav';
import { StaffPageHeader } from './HarborPageChrome';

type IntakePage = 'inbox' | 'escalations' | 'playbooks' | 'analytics' | 'settings';

const CONVERSATIONS = [
  { id: '0', name: 'Sarah M.', channel: 'Instagram', preview: 'Botox consult this week?', time: '2m', unread: true },
  { id: '1', name: 'James L.', channel: 'WhatsApp', preview: 'Reschedule to Friday?', time: '18m', unread: false },
  { id: '2', name: 'Emma R.', channel: 'Web chat', preview: 'Facial package details?', time: '1h', unread: false },
  { id: '3', name: 'Alex W.', channel: 'Web chat', preview: 'Insurance question', time: '2h', unread: false },
];

const THREADS: Record<string, { role: 'user' | 'ai'; text: string }[]> = {
  '0': [
    { role: 'user', text: 'Hi — do you have availability for a Botox consult this Thursday?' },
    { role: 'ai', text: 'Hello Sarah! Yes — Dr. Chen has 2:30 PM or 4:00 PM open for consults. Both include a digital intake form sent before your visit.' },
    { role: 'user', text: '2:30 works. What do I need to bring?' },
    { role: 'ai', text: 'Perfect — you\'re confirmed for Thu 2:30 PM. I\'ve sent the intake form to your email. Just bring a valid ID. Reminder goes out tomorrow at 10 AM.' },
  ],
  '1': [
    { role: 'user', text: 'Can I move my Hydrafacial to Friday afternoon?' },
    { role: 'ai', text: `Hi James — Friday has 1:15 PM or 3:45 PM in ${getRoom('room-2')?.name}. Want me to move your booking?` },
  ],
  '2': [
    { role: 'user', text: 'What\'s included in the signature facial package?' },
    { role: 'ai', text: 'Our signature package is 75 min: cleanse, enzyme peel, LED therapy, and hydration mask — $265. I can book you this week if you\'d like.' },
  ],
  '3': [
    { role: 'user', text: 'Do you accept my insurance for consults?' },
    { role: 'ai', text: 'I\'m escalating this to our billing team — they\'ll reply within 30 minutes during business hours.' },
  ],
};

const ESCALATIONS = [
  { patient: 'Alex W.', reason: 'Insurance / billing', wait: '12 min', priority: 'high' },
  { patient: 'Priya N.', reason: 'Complex medical history', wait: '28 min', priority: 'medium' },
];

const PLAYBOOKS = [
  { name: 'New patient intake', triggers: 'First message · Web chat', rate: '94% auto-resolved' },
  { name: 'Booking & rescheduling', triggers: 'Availability keywords', rate: '89% auto-resolved' },
  { name: 'Treatment FAQ', triggers: 'Pricing · downtime · prep', rate: '91% auto-resolved' },
  { name: 'Post-visit follow-up', triggers: '24h after appointment', rate: '100% automated' },
];

interface Props {
  bookedSlot: TimeSlot | null;
  onClearBooking: () => void;
}

export default function HarborAIIntake({ bookedSlot, onClearBooking }: Props) {
  const [page, setPage] = useState<IntakePage>('inbox');
  const [active, setActive] = useState('0');
  const [input, setInput] = useState('');
  const [extraMessages, setExtraMessages] = useState<{ role: 'user' | 'ai'; text: string }[]>([]);

  const base = THREADS[active] || [];
  const messages = [...base, ...extraMessages];
  const convo = CONVERSATIONS.find((c) => c.id === active)!;

  const sendMessage = () => {
    const text = input.trim();
    if (!text) return;
    setExtraMessages((m) => [
      ...m,
      { role: 'user', text },
      { role: 'ai', text: 'Checking live calendar… I\'ll confirm in a moment.' },
    ]);
    setInput('');
  };

  const navItems = [
    { id: 'inbox' as const, label: 'Inbox', badge: 2 },
    { id: 'escalations' as const, label: 'Escalations', badge: 2 },
    { id: 'playbooks' as const, label: 'AI playbooks' },
    { id: 'analytics' as const, label: 'Analytics' },
    { id: 'settings' as const, label: 'Settings' },
  ];

  return (
    <div className="hc-intake-app">
      <HarborSubNav items={navItems} active={page} onChange={setPage} className="hc-subnav--staff" />

      {page === 'inbox' && (
        <div className="hc-intake">
          <aside className="hc-intake__sidebar">
            <div className="hc-intake__sidebar-head">
              <h2>All channels</h2>
              <p>Instagram · WhatsApp · Web chat</p>
            </div>
            {bookedSlot && (
              <div className="hc-intake__banner">
                <strong>New web booking</strong>
                <span>{bookedSlot.label}</span>
                <button type="button" onClick={onClearBooking}>Dismiss</button>
              </div>
            )}
            <div className="hc-intake__list">
              {CONVERSATIONS.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => { setActive(c.id); setExtraMessages([]); }}
                  className={`hc-intake__convo ${active === c.id ? 'hc-intake__convo--active' : ''}`}
                >
                  <div className="hc-intake__avatar">{c.name.charAt(0)}</div>
                  <div className="hc-intake__convo-body">
                    <div className="hc-intake__convo-top">
                      <span>{c.name}</span>
                      <span>{c.time}</span>
                    </div>
                    <p>{c.preview}</p>
                    <span className="hc-intake__channel">{c.channel}</span>
                  </div>
                  {c.unread && <span className="hc-intake__dot" />}
                </button>
              ))}
            </div>
          </aside>
          <div className="hc-intake__main">
            <header className="hc-intake__header">
              <div>
                <p className="hc-intake__header-name">{convo.name}</p>
                <p className="hc-intake__header-status">
                  <span className="hc-pulse" /> AI agent active · {convo.channel}
                </p>
              </div>
              <div className="hc-intake__patient-ctx">
                <span>Intake: complete</span>
                <span>Next: Thu 2:30 PM</span>
              </div>
              <div className="hc-intake__header-actions">
                <button type="button" className="hc-intake__chip">Send intake form</button>
                <button type="button" className="hc-intake__chip">Escalate to staff</button>
              </div>
            </header>
            <div className="hc-intake__messages">
              {messages.map((msg, i) => (
                <div key={i} className={`hc-intake__msg hc-intake__msg--${msg.role}`}>
                  {msg.role === 'ai' && (
                    <span className="hc-intake__ai-label">
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
                      Harbor AI
                    </span>
                  )}
                  {msg.text}
                </div>
              ))}
            </div>
            <div className="hc-intake__quick">
              {['Offer Thu 2:30pm', 'Send pricing PDF', 'Confirm visit'].map((q) => (
                <button key={q} type="button" className="hc-intake__quick-btn" onClick={() => setInput(q)}>{q}</button>
              ))}
            </div>
            <div className="hc-intake__composer">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
                placeholder="Staff override — type a reply..."
                className="hc-intake__input"
              />
              <button type="button" className="hc-intake__send" onClick={sendMessage}>Send</button>
            </div>
          </div>
        </div>
      )}

      {page === 'escalations' && (
        <div className="hc-intake-page">
          <StaffPageHeader role="intake" title="Escalation queue" subtitle="Cases AI flagged for human review · SLA 30 min" />
          <div className="hc-intake-page--pad">
          <div className="hc-intake-page__cards">
            {ESCALATIONS.map((e) => (
              <article key={e.patient} className="hc-intake-page__card">
                <div className="hc-intake-page__card-top">
                  <strong>{e.patient}</strong>
                  <span className={`hc-intake-page__prio hc-intake-page__prio--${e.priority}`}>{e.priority}</span>
                </div>
                <p>{e.reason}</p>
                <small>Waiting {e.wait}</small>
                <button type="button" className="hc-intake__chip">Take over thread</button>
              </article>
            ))}
          </div>
          </div>
        </div>
      )}

      {page === 'playbooks' && (
        <div className="hc-intake-page">
          <StaffPageHeader role="intake" title="AI playbooks" subtitle="Automated flows — edit triggers and escalation rules" />
          <div className="hc-intake-page--pad">
          <div className="hc-intake-page__table-wrap">
            <table className="hc-admin__table">
              <thead>
                <tr><th>Playbook</th><th>Triggers</th><th>Resolution rate</th><th></th></tr>
              </thead>
              <tbody>
                {PLAYBOOKS.map((p) => (
                  <tr key={p.name}>
                    <td><strong>{p.name}</strong></td>
                    <td>{p.triggers}</td>
                    <td><span className="hc-admin__score">{p.rate}</span></td>
                    <td><button type="button" className="hc-admin__action">Edit</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </div>
        </div>
      )}

      {page === 'analytics' && (
        <div className="hc-intake-page">
          <StaffPageHeader role="intake" title="AI performance" subtitle="Resolution rates, response times, channel breakdown" />
          <div className="hc-intake-page--pad">
          <div className="hc-intake-page__metrics">
            {[
              ['78%', 'Auto-resolved', '↑ 12% this month'],
              ['28s', 'Avg first response', '↓ 40% vs manual'],
              ['4.9', 'Patient satisfaction', 'Post-chat survey'],
              ['22%', 'Escalation rate', 'Mostly billing'],
            ].map(([val, label, sub]) => (
              <div key={label} className="hc-intake-page__metric">
                <span className="hc-intake-page__metric-val">{val}</span>
                <span>{label}</span>
                <small>{sub}</small>
              </div>
            ))}
          </div>
          <div className="hc-intake-page__chart">
            <p>Conversations by channel — last 7 days</p>
            <div className="hc-intake-page__bars">
              {[['Web chat', 68], ['Instagram', 42], ['WhatsApp', 31]].map(([ch, pct]) => (
                <div key={ch as string} className="hc-intake-page__bar-row">
                  <span>{ch}</span>
                  <div className="hc-intake-page__bar"><span style={{ width: `${pct}%` }} /></div>
                  <span>{pct}</span>
                </div>
              ))}
            </div>
          </div>
          </div>
        </div>
      )}

      {page === 'settings' && (
        <div className="hc-intake-page">
          <StaffPageHeader role="intake" title="Intake settings" subtitle="Tone, languages, channels, and handoff rules" />
          <div className="hc-intake-page--pad">
          <div className="hc-intake-page__settings">
            {[
              ['AI tone', 'Warm, clinical, concise'],
              ['Business hours handoff', 'Escalate billing after 6 PM'],
              ['Languages', 'English · Spanish (beta)'],
              ['Connected channels', 'Web chat · Instagram · WhatsApp'],
            ].map(([k, v]) => (
              <div key={k} className="hc-intake-page__setting">
                <span>{k}</span>
                <strong>{v}</strong>
                <button type="button" className="hc-admin__action">Edit</button>
              </div>
            ))}
          </div>
          </div>
        </div>
      )}
    </div>
  );
}
