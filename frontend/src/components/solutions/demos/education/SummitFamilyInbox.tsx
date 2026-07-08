import { useState } from 'react';
import { SummitLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type SessionSlot } from './summitData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Sarah M.', role: 'parent' as const, preview: 'Weekly report received — thanks!', time: '12m', unread: true, avatar: 'S', subject: 'Ava · Math', channel: 'email' as const },
  { id: '1', name: 'Ava M.', role: 'student' as const, preview: 'Prep pack for Thursday ready?', time: '28m', unread: false, avatar: 'A', subject: 'Algebra II', channel: 'app' as const },
  { id: '2', name: 'David K.', role: 'parent' as const, preview: 'Can we renew the 8-pack?', time: '1h', unread: false, avatar: 'D', subject: 'Noah · Science', channel: 'sms' as const },
  { id: '3', name: 'Mia T.', role: 'student' as const, preview: 'Finished the vocab quiz — 18/20', time: '2h', unread: false, avatar: 'M', subject: 'SAT verbal', channel: 'app' as const },
];

type ThreadMsg = {
  role: 'user' | 'ai';
  text: string;
  time?: string;
  prepPack?: { title: string; items: string[] };
};

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'ai', text: 'Weekly progress report for Ava M. — Algebra II with Dr. Elena Ruiz', time: '8:00 AM' },
    {
      role: 'ai',
      text: '',
      time: '8:00 AM',
      prepPack: {
        title: 'Parent report · Week of Mar 3',
        items: ['Sessions: 2 completed', 'Homework: 4/5 submitted', 'Focus next week: systems of equations', 'Package: 8 of 12 sessions remaining'],
      },
    },
    { role: 'user', text: 'Weekly report received — thanks!', time: '9:14 AM' },
    { role: 'ai', text: 'Glad it helped! Ava\'s Thursday prep pack will arrive Wednesday evening.', time: '9:14 AM' },
  ],
  '1': [
    { role: 'user', text: 'Is my prep pack for Thursday ready?', time: '3:40 PM' },
    {
      role: 'ai',
      text: '',
      time: '3:40 PM',
      prepPack: {
        title: 'Prep pack · Thu Algebra II',
        items: ['Systems of equations worksheet', 'Graphing shortcuts video (12 min)', 'Practice quiz — 10 problems'],
      },
    },
    { role: 'ai', text: 'All set — complete the quiz before session for best results.', time: '3:40 PM' },
  ],
  '2': [
    { role: 'user', text: 'Can we renew Noah\'s 8-session pack?', time: '11:20 AM' },
    { role: 'ai', text: 'Renewal invoice $720 queued — due Mar 14. One-tap pay link sent. 2 sessions left on current pack.', time: '11:20 AM' },
  ],
  '3': [
    { role: 'user', text: 'Finished the vocab quiz — got 18/20', time: '2:05 PM' },
    { role: 'ai', text: 'Logged ✓ 18/20 · SAT verbal. Priya noted strong inference skills — timed passage drill added to next prep pack.', time: '2:05 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  app: 'Student app',
  email: 'Parent email',
  sms: 'SMS',
};

const ROLE_LABEL: Record<string, string> = {
  parent: 'Parent',
  student: 'Student',
};

interface Props {
  bookedSlot: SessionSlot | null;
  onClearBooking: () => void;
}

export default function SummitFamilyInbox({ bookedSlot, onClearBooking }: Props) {
  const [active, setActive] = useState('1');
  const [roleFilter, setRoleFilter] = useState<'all' | 'parent' | 'student'>('all');
  const [input, setInput] = useState('');
  const [extra, setExtra] = useState<ThreadMsg[]>([]);

  const convo = CONVERSATIONS.find((c) => c.id === active)!;
  const messages = [...(THREADS[active] || []), ...extra];

  const filteredConvos = CONVERSATIONS.filter((c) => {
    if (roleFilter === 'all') return true;
    return c.role === roleFilter;
  });

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setExtra((m) => [
      ...m,
      { role: 'user', text, time: 'Now' },
      { role: 'ai', text: 'Checking prep status and tutor notes…', time: 'Now' },
    ]);
    setInput('');
  };

  return (
    <div className="sm-inbox">
      <aside className="sm-inbox__sidebar">
        <header className="sm-inbox__sidebar-head">
          <div className="sm-inbox__sidebar-brand">
            <SummitLogo className="sm-inbox__sidebar-logo" />
            <div>
              <h2>Family inbox</h2>
              <span className="sm-inbox__count">{CONVERSATIONS.length} threads</span>
            </div>
          </div>
          <span className="sm-inbox__ai-pill">
            <IconSparkle className="sm-inbox__sparkle" />
            Prep + reports
          </span>
        </header>

        <div className="sm-inbox__ai-strip">
          <span>Prep packs</span>
          <span>Parent reports</span>
          <span>Match alerts</span>
          <span>Auto billing</span>
        </div>

        <div className="sm-inbox__sidebar-stats">
          <div><strong>47</strong><span>Prep packs sent</span></div>
          <div><strong>38</strong><span>Reports delivered</span></div>
          <div><strong>5</strong><span>Renewals due</span></div>
        </div>

        {bookedSlot && (
          <div className="sm-inbox__booking-alert">
            <span className="sm-inbox__booking-alert-icon" aria-hidden>
              <SummitLogo className="sm-inbox__booking-logo" />
            </span>
            <div>
              <strong>Session confirmed</strong>
              <p>{bookedSlot.label}</p>
              <small>Prep pack queued for delivery</small>
            </div>
            <button type="button" className="sm-inbox__booking-dismiss" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="sm-inbox__icon" />
            </button>
          </div>
        )}

        <div className="sm-inbox__filters">
          {(['all', 'parent', 'student'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={roleFilter === f ? 'sm-inbox__filter sm-inbox__filter--on' : 'sm-inbox__filter'}
              onClick={() => setRoleFilter(f)}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1) + 's'}
            </button>
          ))}
        </div>

        <ul className="sm-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`sm-inbox__convo ${active === c.id ? 'sm-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`sm-inbox__avatar sm-inbox__avatar--${c.role}`}>{c.avatar}</span>
                <div className="sm-inbox__convo-body">
                  <div className="sm-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="sm-inbox__channel">{ROLE_LABEL[c.role]} · {c.subject}</span>
                </div>
                {c.unread && <span className="sm-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="sm-inbox__thread">
        <header className="sm-inbox__thread-head">
          <div className="sm-inbox__thread-guest">
            <span className={`sm-inbox__avatar sm-inbox__avatar--${convo.role} sm-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{ROLE_LABEL[convo.role]} · {CHANNEL_LABEL[convo.channel]} · {convo.subject}</span>
            </div>
          </div>
          <div className="sm-inbox__thread-actions">
            <button type="button">Send prep pack</button>
            <button type="button" className="sm-inbox__thread-action--primary">Parent report</button>
          </div>
        </header>

        <div className="sm-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`sm-inbox__msg sm-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="sm-inbox__msg-label">
                  <IconSparkle className="sm-inbox__sparkle" />
                  Summit AI
                </span>
              )}
              {msg.prepPack ? (
                <div className="sm-inbox__prep-pack">
                  <strong>{msg.prepPack.title}</strong>
                  <ul>
                    {msg.prepPack.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : msg.text ? (
                <p>{msg.text}</p>
              ) : null}
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="sm-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Message family or ask about prep…"
            aria-label="Message"
          />
          <button type="button" className="sm-inbox__send" onClick={send} aria-label="Send">
            Send
          </button>
        </div>
      </main>
    </div>
  );
}
