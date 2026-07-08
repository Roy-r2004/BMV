import { useState } from 'react';
import { RowLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type BookingHold, GUEST_MEMORIES } from './rowData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Claire Dubois', handle: 'Returning · 7 stays', channel: 'web' as const, preview: 'Late checkout + hypoallergenic?', time: '2m', unread: true, avatar: 'C', room: '504' },
  { id: '1', name: 'James Walsh', handle: '+1 312…', channel: 'whatsapp' as const, preview: 'Corner Suite still open Fri?', time: '18m', unread: false, avatar: 'J', room: '—' },
  { id: '2', name: 'Sofia Kim', handle: '@sofia.k', channel: 'instagram' as const, preview: 'Quiet floor + sparkling water again', time: '41m', unread: false, avatar: 'S', room: '605' },
  { id: '3', name: 'Marcus Lee', handle: 'App chat', channel: 'web' as const, preview: 'Local dinner near the river?', time: '1h', unread: false, avatar: 'M', room: '502' },
];

type ThreadMsg = { role: 'user' | 'ai'; text: string; time?: string };

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'user', text: 'Hi — arriving today. Can I get late checkout and hypoallergenic bedding again?', time: '2:41 PM' },
    { role: 'ai', text: 'Welcome back, Claire. Guest memory loaded: hypoallergenic bedding + still water. Late checkout until 1 PM approved — housekeeping board updated for 504.', time: '2:41 PM' },
    { role: 'user', text: 'Perfect. Any quiet table tip for dinner?', time: '2:42 PM' },
    { role: 'ai', text: 'Avec at 7:30 — walking distance. I can hold under Dubois if you like.', time: '2:42 PM' },
  ],
  '1': [
    { role: 'user', text: 'Is Corner Suite available Friday–Sunday?', time: '2:20 PM' },
    { role: 'ai', text: 'Yes — $778 direct (OTA would be ~$890 after fees). I can hold 15 min at your best rate.', time: '2:20 PM' },
  ],
  '2': [
    { role: 'user', text: 'Same as last stay — high floor quiet wing?', time: '1:55 PM' },
    { role: 'ai', text: 'Sofia · 4 stays remembered. Assigned 605 quiet wing; sparkling water on arrival. Front desk notified.', time: '1:55 PM' },
  ],
  '3': [
    { role: 'user', text: 'Dinner nearby with jazz?', time: '1:30 PM' },
    { role: 'ai', text: 'Untitled Supper Club from 9 PM — 8-minute walk. Want a note on your folios?', time: '1:30 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  instagram: 'Instagram',
  whatsapp: 'WhatsApp',
  web: 'Web / App',
};

interface Props {
  bookedHold: BookingHold | null;
  onClearBooking: () => void;
}

export default function RowGuestInbox({ bookedHold, onClearBooking }: Props) {
  const [active, setActive] = useState('0');
  const [channelFilter, setChannelFilter] = useState<'all' | 'instagram' | 'whatsapp' | 'web'>('all');
  const [input, setInput] = useState('');
  const [extra, setExtra] = useState<ThreadMsg[]>([]);

  const convo = CONVERSATIONS.find((c) => c.id === active)!;
  const messages = [...(THREADS[active] || []), ...extra];
  const memory = GUEST_MEMORIES.find((g) => g.name === convo.name);

  const filteredConvos = CONVERSATIONS.filter((c) => {
    if (channelFilter === 'all') return true;
    return c.channel === channelFilter;
  });

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setExtra((m) => [
      ...m,
      { role: 'user', text, time: 'Now' },
      { role: 'ai', text: 'Checking prefs + room board… synced with housekeeping.', time: 'Now' },
    ]);
    setInput('');
  };

  return (
    <div className="rh-inbox">
      <aside className="rh-inbox__sidebar">
        <header className="rh-inbox__sidebar-head">
          <div className="rh-inbox__sidebar-brand">
            <RowLogo className="rh-inbox__sidebar-logo" />
            <div>
              <h2>Guest inbox</h2>
              <span className="rh-inbox__count">{CONVERSATIONS.length} threads · memory live</span>
            </div>
          </div>
          <span className="rh-inbox__ai-pill">
            <IconSparkle className="rh-inbox__sparkle" />
            Concierge AI
          </span>
        </header>

        <div className="rh-inbox__ai-strip">
          <span>Late checkout</span>
          <span>Local recs</span>
          <span>Guest memory</span>
        </div>

        <div className="rh-inbox__sidebar-stats">
          <div><strong>11</strong><span>Prefs applied</span></div>
          <div><strong>6</strong><span>Late C/O</span></div>
          <div><strong>9</strong><span>Direct holds</span></div>
        </div>

        {bookedHold && (
          <div className="rh-inbox__booking-alert">
            <span className="rh-inbox__booking-alert-icon" aria-hidden>
              <RowLogo className="rh-inbox__booking-logo" />
            </span>
            <div>
              <strong>Direct booking confirmed</strong>
              <p>{bookedHold.label}</p>
            </div>
            <button type="button" className="rh-inbox__booking-dismiss" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="rh-inbox__icon" />
            </button>
          </div>
        )}

        <div className="rh-inbox__filters">
          {(['all', 'web', 'whatsapp', 'instagram'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={channelFilter === f ? 'rh-inbox__filter rh-inbox__filter--on' : 'rh-inbox__filter'}
              onClick={() => setChannelFilter(f)}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <ul className="rh-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`rh-inbox__convo ${active === c.id ? 'rh-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`rh-inbox__avatar rh-inbox__avatar--${c.channel}`}>{c.avatar}</span>
                <div className="rh-inbox__convo-body">
                  <div className="rh-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="rh-inbox__channel">{CHANNEL_LABEL[c.channel]}</span>
                </div>
                {c.unread && <span className="rh-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="rh-inbox__thread">
        <header className="rh-inbox__thread-head">
          <div className="rh-inbox__thread-guest">
            <span className={`rh-inbox__avatar rh-inbox__avatar--${convo.channel} rh-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{convo.handle} · {CHANNEL_LABEL[convo.channel]}</span>
            </div>
          </div>
          <div className="rh-inbox__thread-actions">
            <button type="button">Send local picks</button>
            <button type="button" className="rh-inbox__thread-action--primary">Apply prefs</button>
          </div>
        </header>

        <div className="rh-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`rh-inbox__msg rh-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="rh-inbox__msg-label">
                  <IconSparkle className="rh-inbox__sparkle" />
                  Concierge AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="rh-inbox__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Reply or let Concierge AI handle it…"
            aria-label="Reply"
          />
          <button type="button" onClick={send}>Send</button>
        </div>
      </main>

      <aside className="rh-inbox__ctx">
        <p className="rh-inbox__ctx-eyebrow">Guest card</p>
        <h4>{convo.name}</h4>
        <dl>
          <div><dt>Room</dt><dd>{convo.room}</dd></div>
          <div><dt>Channel</dt><dd>{CHANNEL_LABEL[convo.channel]}</dd></div>
          <div>
            <dt>Status</dt>
            <dd className={convo.unread ? 'rh-inbox__ctx-hot' : ''}>
              {convo.unread ? 'Late C/O syncing' : 'Handled by AI'}
            </dd>
          </div>
        </dl>
        {memory && (
          <div className="rh-inbox__ctx-memory">
            <p>Guest memory · {memory.stays} stays</p>
            <ul>
              {memory.prefs.map((p) => <li key={p}>{p}</li>)}
            </ul>
            <span>Last stay {memory.lastStay}</span>
          </div>
        )}
        {!memory && (
          <div className="rh-inbox__ctx-notes">
            <p>Concierge notes</p>
            <span>New guest · collect prefs on pre-arrival · offer direct rebook</span>
          </div>
        )}
        <button type="button" className="rh-inbox__ctx-btn">Open housekeeping board</button>
      </aside>
    </div>
  );
}
