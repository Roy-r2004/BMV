import { useState } from 'react';
import { EmberLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type ReservationSlot } from './emberData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Birthday party', handle: 'Website', channel: 'web' as const, preview: 'Party of 8 Saturday — private patio?', time: '3m', unread: true, avatar: '8', covers: 8 },
  { id: '1', name: 'Tom H.', handle: '+1 718…', channel: 'whatsapp' as const, preview: 'Is truffle pasta still on tonight?', time: '22m', unread: false, avatar: 'T', covers: 2 },
  { id: '2', name: 'Nina R.', handle: '@nina.eats', channel: 'instagram' as const, preview: 'Gluten-free options for group of 4?', time: '45m', unread: false, avatar: 'N', covers: 4 },
  { id: '3', name: 'Delivery #1841', handle: 'App order', channel: 'web' as const, preview: 'Where is my order?', time: '1h', unread: false, avatar: 'D', covers: 0 },
];

type ThreadMsg = { role: 'user' | 'ai'; text: string; time?: string };

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'user', text: 'Hi — birthday dinner for 8 this Saturday around 7:30. Any private area?', time: '6:41 PM' },
    { role: 'ai', text: 'We can do the patio section at 7:45 — set menu link attached. Candle + cake add-on available.', time: '6:41 PM' },
    { role: 'user', text: 'Perfect. 7:45 patio works.', time: '6:42 PM' },
    { role: 'ai', text: 'Reserved ✓ Sat 7:45 PM · Patio (8). Deposit waived for returning guests. See you then!', time: '6:42 PM' },
  ],
  '1': [
    { role: 'user', text: 'Is the truffle tagliatelle still on the menu tonight?', time: '6:18 PM' },
    { role: 'ai', text: 'Yes — chef just fired a fresh batch. Want pickup at 7:15 or dine-in bar seating?', time: '6:18 PM' },
  ],
  '2': [
    { role: 'user', text: 'Group of 4 — any solid gluten-free mains?', time: '5:55 PM' },
    { role: 'ai', text: 'Cedar salmon and burrata plate are GF. I can note allergies on your reservation.', time: '5:55 PM' },
  ],
  '3': [
    { role: 'user', text: 'Order #1841 — any update?', time: '5:30 PM' },
    { role: 'ai', text: 'Just plated — driver assigned. ETA 12 min to your address.', time: '5:30 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  instagram: 'Instagram',
  whatsapp: 'WhatsApp',
  web: 'Web / App',
};

interface Props {
  bookedSlot: ReservationSlot | null;
  onClearBooking: () => void;
}

export default function EmberGuestInbox({ bookedSlot, onClearBooking }: Props) {
  const [active, setActive] = useState('0');
  const [channelFilter, setChannelFilter] = useState<'all' | 'instagram' | 'whatsapp' | 'web'>('all');
  const [input, setInput] = useState('');
  const [extra, setExtra] = useState<ThreadMsg[]>([]);

  const convo = CONVERSATIONS.find((c) => c.id === active)!;
  const messages = [...(THREADS[active] || []), ...extra];

  const filteredConvos = CONVERSATIONS.filter((c) => {
    if (channelFilter === 'all') return true;
    return c.channel === channelFilter;
  });

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setExtra((m) => [...m, { role: 'user', text, time: 'Now' }, { role: 'ai', text: 'Checking with the floor team…', time: 'Now' }]);
    setInput('');
  };

  return (
    <div className="eo-inbox">
      <aside className="eo-inbox__sidebar">
        <header className="eo-inbox__sidebar-head">
          <div className="eo-inbox__sidebar-brand">
            <EmberLogo className="eo-inbox__sidebar-logo" />
            <div>
              <h2>Guest inbox</h2>
              <span className="eo-inbox__count">{CONVERSATIONS.length} active threads</span>
            </div>
          </div>
          <span className="eo-inbox__ai-pill">
            <IconSparkle className="eo-inbox__sparkle" />
            Menu AI
          </span>
        </header>

        <div className="eo-inbox__ai-strip">
          <span>Saves 30% fees</span>
          <span>Allergen trust</span>
          <span>Party → patio</span>
        </div>

        <div className="eo-inbox__sidebar-stats">
          <div><strong>14</strong><span>Dietary Qs</span></div>
          <div><strong>6</strong><span>Parties booked</span></div>
          <div><strong>8</strong><span>Orders routed</span></div>
        </div>

        {bookedSlot && (
          <div className="eo-inbox__booking-alert">
            <span className="eo-inbox__booking-alert-icon" aria-hidden>
              <EmberLogo className="eo-inbox__booking-logo" />
            </span>
            <div>
              <strong>Reservation confirmed</strong>
              <p>{bookedSlot.label}</p>
            </div>
            <button type="button" className="eo-inbox__booking-dismiss" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="eo-inbox__icon" />
            </button>
          </div>
        )}

        <div className="eo-inbox__filters">
          {(['all', 'web', 'whatsapp', 'instagram'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={channelFilter === f ? 'eo-inbox__filter eo-inbox__filter--on' : 'eo-inbox__filter'}
              onClick={() => setChannelFilter(f)}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <ul className="eo-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`eo-inbox__convo ${active === c.id ? 'eo-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`eo-inbox__avatar eo-inbox__avatar--${c.channel}`}>{c.avatar}</span>
                <div className="eo-inbox__convo-body">
                  <div className="eo-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="eo-inbox__channel">{CHANNEL_LABEL[c.channel]}</span>
                </div>
                {c.unread && <span className="eo-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="eo-inbox__thread">
        <header className="eo-inbox__thread-head">
          <div className="eo-inbox__thread-guest">
            <span className={`eo-inbox__avatar eo-inbox__avatar--${convo.channel} eo-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{convo.handle} · {CHANNEL_LABEL[convo.channel]}</span>
            </div>
          </div>
          <div className="eo-inbox__thread-actions">
            <button type="button">Send set menu</button>
            <button type="button" className="eo-inbox__thread-action--primary">Flag allergies</button>
          </div>
        </header>

        <div className="eo-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`eo-inbox__msg eo-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="eo-inbox__msg-label">
                  <IconSparkle className="eo-inbox__sparkle" />
                  Menu & table AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="eo-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Reply or let AI handle it…"
            aria-label="Reply"
          />
          <button type="button" onClick={send}>Send</button>
        </div>
      </main>

      <aside className="eo-inbox__ctx">
        <p className="eo-inbox__ctx-eyebrow">Guest card</p>
        <h4>{convo.name}</h4>
        <dl>
          <div><dt>Party</dt><dd>{convo.covers || '—'} covers · patio zone</dd></div>
          <div><dt>Dietary</dt><dd>GF main available · AI noted</dd></div>
          <div><dt>Status</dt><dd className={convo.unread ? 'eo-inbox__ctx-hot' : ''}>{convo.unread ? 'Set menu sent' : 'Kitchen synced'}</dd></div>
        </dl>
        <div className="eo-inbox__ctx-notes">
          <p>Concierge notes</p>
          <span>Birthday · patio 7:45 · set menu link attached · candle add-on offered</span>
        </div>
        <button type="button" className="eo-inbox__ctx-btn">Open table planner</button>
      </aside>
    </div>
  );
}
