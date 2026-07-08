import { useState } from 'react';
import { HarborFundLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type Donation, INBOX_THREADS } from './harborFundData.ts';

type ThreadMsg = {
  role: 'user' | 'ai';
  text: string;
  time?: string;
  receipt?: { title: string; items: string[] };
};

const CONVERSATIONS = INBOX_THREADS.map((t) => ({
  ...t,
}));

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'ai', text: 'Gift received — Bridge the Gap 2026 · $50 Neighbor tier', time: '9:02 AM' },
    {
      role: 'ai',
      text: '',
      time: '9:02 AM',
      receipt: {
        title: 'Personalized thank-you · Maya Chen',
        items: [
          'Amount: $50 one-time',
          'Impact: 1 week of tutoring supplies',
          'Story: Meals @ the pier kitchen · 3,200 meals',
          'Tax receipt PDF attached · EIN on file',
        ],
      },
    },
    { role: 'user', text: 'Thank you — receipt arrived!', time: '9:10 AM' },
    { role: 'ai', text: 'Glad it landed. Want a monthly upgrade? Same impact story, auto every cycle.', time: '9:10 AM' },
  ],
  '1': [
    { role: 'user', text: 'I have kitchen + logistics skills — any Saturday shifts?', time: '8:40 AM' },
    { role: 'ai', text: 'Matched: Pier kitchen shift Sat 9 AM–1 PM — 94% skill fit. 4 spots left. Confirmation + reminder SMS queued.', time: '8:40 AM' },
    { role: 'user', text: 'Matched to pier kitchen Sat', time: '8:41 AM' },
  ],
  '2': [
    { role: 'user', text: 'Can I make this monthly?', time: '11:05 AM' },
    { role: 'ai', text: 'Yes — converting your $100 Anchor gift to monthly. Impact story: Youth mentorship hours · 612 hours this quarter. Pay link texted.', time: '11:05 AM' },
  ],
  '3': [
    { role: 'ai', text: 'After-school tutoring Tue/Thu confirmed — literacy pack attached.', time: '2:00 PM' },
    {
      role: 'ai',
      text: '',
      time: '2:00 PM',
      receipt: {
        title: 'Volunteer thank-you · Chris Park',
        items: ['Shift: Tutoring 3:30–5:30 PM', 'Skill match: 88%', 'Hours logged toward Summer Youth Lab'],
      },
    },
    { role: 'user', text: 'Tutoring confirmation received', time: '2:12 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  app: 'Volunteer app',
  email: 'Email',
  sms: 'SMS',
};

const ROLE_LABEL: Record<string, string> = {
  donor: 'Donor',
  volunteer: 'Volunteer',
};

interface Props {
  donation: Donation | null;
  onClearDonation: () => void;
}

export default function HarborDonorInbox({ donation, onClearDonation }: Props) {
  const [active, setActive] = useState('0');
  const [roleFilter, setRoleFilter] = useState<'all' | 'donor' | 'volunteer'>('all');
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
      { role: 'ai', text: 'Thank-you bot drafting personalized receipt + impact story…', time: 'Now' },
    ]);
    setInput('');
  };

  return (
    <div className="hg-inbox">
      <aside className="hg-inbox__sidebar">
        <header className="hg-inbox__sidebar-head">
          <div className="hg-inbox__sidebar-brand">
            <HarborFundLogo className="hg-inbox__sidebar-logo" />
            <div>
              <h2>Donor inbox</h2>
              <span className="hg-inbox__count">{CONVERSATIONS.length} threads · thank-yous live</span>
            </div>
          </div>
          <span className="hg-inbox__ai-pill">
            <IconSparkle className="hg-inbox__sparkle" />
            Thank-you bot
          </span>
        </header>

        <div className="hg-inbox__ai-strip">
          <span>Smart receipts</span>
          <span>Volunteer match</span>
          <span>Impact stories</span>
        </div>

        <div className="hg-inbox__sidebar-stats">
          <div><strong>186</strong><span>Thank-yous sent</span></div>
          <div><strong>42</strong><span>Shifts matched</span></div>
          <div><strong>18</strong><span>Monthly upgrades</span></div>
        </div>

        {donation && (
          <div className="hg-inbox__booking-alert">
            <span className="hg-inbox__booking-alert-icon" aria-hidden>
              <HarborFundLogo className="hg-inbox__booking-logo" />
            </span>
            <div>
              <strong>Gift confirmed</strong>
              <p>
                {donation.donorName} · ${donation.amount}
                {donation.recurring ? '/mo' : ''} · {donation.tier}
              </p>
              <small>Personalized receipt queued</small>
            </div>
            <button type="button" className="hg-inbox__booking-dismiss" onClick={onClearDonation} aria-label="Dismiss">
              <IconClose className="hg-inbox__icon" />
            </button>
          </div>
        )}

        <div className="hg-inbox__filters">
          {(['all', 'donor', 'volunteer'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={roleFilter === f ? 'hg-inbox__filter hg-inbox__filter--on' : 'hg-inbox__filter'}
              onClick={() => setRoleFilter(f)}
            >
              {f === 'all' ? 'All' : f === 'donor' ? 'Donors' : 'Volunteers'}
            </button>
          ))}
        </div>

        <ul className="hg-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`hg-inbox__convo ${active === c.id ? 'hg-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`hg-inbox__avatar hg-inbox__avatar--${c.role}`}>{c.avatar}</span>
                <div className="hg-inbox__convo-body">
                  <div className="hg-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="hg-inbox__channel">{ROLE_LABEL[c.role]} · {c.topic}</span>
                </div>
                {c.unread && <span className="hg-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="hg-inbox__thread">
        <header className="hg-inbox__thread-head">
          <div className="hg-inbox__thread-guest">
            <span className={`hg-inbox__avatar hg-inbox__avatar--${convo.role} hg-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{ROLE_LABEL[convo.role]} · {CHANNEL_LABEL[convo.channel]} · {convo.topic}</span>
            </div>
          </div>
          <div className="hg-inbox__thread-actions">
            <button type="button">Impact story</button>
            <button type="button" className="hg-inbox__thread-action--primary">Send receipt</button>
          </div>
        </header>

        <div className="hg-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`hg-inbox__msg hg-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="hg-inbox__msg-label">
                  <IconSparkle className="hg-inbox__sparkle" />
                  Harbor thank-you bot
                </span>
              )}
              {msg.receipt ? (
                <div className="hg-inbox__prep-pack">
                  <strong>{msg.receipt.title}</strong>
                  <ul>
                    {msg.receipt.items.map((item) => (
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

        <div className="hg-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Message donor or volunteer…"
            aria-label="Message"
          />
          <button type="button" className="hg-inbox__send" onClick={send} aria-label="Send">
            Send
          </button>
        </div>
      </main>
    </div>
  );
}
