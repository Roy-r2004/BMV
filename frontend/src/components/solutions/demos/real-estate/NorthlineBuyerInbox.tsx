import { useState } from 'react';
import { NorthlineLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type ViewingSlot } from './northlineData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Alex P.', handle: 'Listing chat', channel: 'web' as const, preview: 'HOA on Oak Lane? Book Sat 10am?', time: '2m', unread: true, avatar: 'A', listing: '22 Oak Lane' },
  { id: '1', name: 'Nina S.', handle: '+1 917…', channel: 'whatsapp' as const, preview: 'Saturday morning viewing still open?', time: '38m', unread: false, avatar: 'N', listing: 'Park View #4' },
  { id: '2', name: 'James L.', handle: '@james.nyc', channel: 'instagram' as const, preview: 'Any investor comps for River Loft?', time: '1h', unread: false, avatar: 'J', listing: 'River Loft' },
  { id: '3', name: 'Priya K.', handle: 'Open house', channel: 'web' as const, preview: 'Cedar Row — rental income breakdown?', time: '2h', unread: false, avatar: 'P', listing: 'Cedar Row' },
];

type ThreadMsg = { role: 'user' | 'ai'; text: string; time?: string };

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'user', text: "What's the HOA fee on 22 Oak Lane?", time: '4:12 PM' },
    { role: 'ai', text: '$240/mo — parking included. Saturday 10am with Sarah is open. Want me to book?', time: '4:12 PM' },
    { role: 'user', text: 'Yes — Sat 10am works.', time: '4:13 PM' },
    { role: 'ai', text: 'Viewing booked ✓ Sat 10:00 AM · 22 Oak Lane. Calendar invite sent — Sarah briefed.', time: '4:13 PM' },
  ],
  '1': [
    { role: 'user', text: 'Can we still tour Park View Saturday morning?', time: '3:40 PM' },
    { role: 'ai', text: '11:30 AM with Elena is open. Corner unit with skyline views — want me to hold it?', time: '3:40 PM' },
  ],
  '2': [
    { role: 'user', text: 'Any investor comps for the River Loft?', time: '2:55 PM' },
    { role: 'ai', text: 'Marcus sent a rental yield sheet — 4.2% gross at current ask. Viewing at 2pm Sat available.', time: '2:55 PM' },
  ],
  '3': [
    { role: 'user', text: 'Does Cedar Row have rental income potential?', time: '1:20 PM' },
    { role: 'ai', text: 'Garden unit rented at $2,400/mo — Sarah can walk you through the numbers Sunday.', time: '1:20 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  instagram: 'Instagram',
  whatsapp: 'WhatsApp',
  web: 'Listing AI',
};

interface Props {
  bookedSlot: ViewingSlot | null;
  onClearBooking: () => void;
}

export default function NorthlineBuyerInbox({ bookedSlot, onClearBooking }: Props) {
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
    setExtra((m) => [...m, { role: 'user', text, time: 'Now' }, { role: 'ai', text: 'Checking with the listing agent…', time: 'Now' }]);
    setInput('');
  };

  return (
    <div className="nr-inbox">
      <aside className="nr-inbox__sidebar">
        <header className="nr-inbox__sidebar-head">
          <div className="nr-inbox__sidebar-brand">
            <NorthlineLogo className="nr-inbox__sidebar-logo" />
            <div>
              <h2>Buyer inbox</h2>
              <span className="nr-inbox__count">{CONVERSATIONS.length} active threads</span>
            </div>
          </div>
          <span className="nr-inbox__ai-pill">
            <IconSparkle className="nr-inbox__sparkle" />
            Lead score AI
          </span>
        </header>

        <div className="nr-inbox__ai-strip">
          <span>Hot-score 94</span>
          <span>Tours, not forms</span>
          <span>Night seller</span>
        </div>

        <div className="nr-inbox__sidebar-stats">
          <div><strong>31</strong><span>Listing Qs</span></div>
          <div><strong>8</strong><span>Tours booked</span></div>
          <div><strong>14</strong><span>Hot leads</span></div>
        </div>

        {bookedSlot && (
          <div className="nr-inbox__booking-alert">
            <span className="nr-inbox__booking-alert-icon" aria-hidden>
              <NorthlineLogo className="nr-inbox__booking-logo" />
            </span>
            <div>
              <strong>Viewing confirmed</strong>
              <p>{bookedSlot.label}</p>
            </div>
            <button type="button" className="nr-inbox__booking-dismiss" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="nr-inbox__icon" />
            </button>
          </div>
        )}

        <div className="nr-inbox__filters">
          {(['all', 'web', 'whatsapp', 'instagram'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={channelFilter === f ? 'nr-inbox__filter nr-inbox__filter--on' : 'nr-inbox__filter'}
              onClick={() => setChannelFilter(f)}
            >
              {f === 'all' ? 'All' : f === 'web' ? 'Listing AI' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <ul className="nr-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`nr-inbox__convo ${active === c.id ? 'nr-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`nr-inbox__avatar nr-inbox__avatar--${c.channel}`}>{c.avatar}</span>
                <div className="nr-inbox__convo-body">
                  <div className="nr-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="nr-inbox__channel">{CHANNEL_LABEL[c.channel]}</span>
                </div>
                {c.unread && <span className="nr-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="nr-inbox__thread">
        <header className="nr-inbox__thread-head">
          <div className="nr-inbox__thread-guest">
            <span className={`nr-inbox__avatar nr-inbox__avatar--${convo.channel} nr-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{convo.handle} · {CHANNEL_LABEL[convo.channel]}</span>
            </div>
          </div>
          <div className="nr-inbox__thread-actions">
            <button type="button">Send comp pack</button>
            <button type="button" className="nr-inbox__thread-action--primary">Assign agent</button>
          </div>
        </header>

        <div className="nr-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`nr-inbox__msg nr-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="nr-inbox__msg-label">
                  <IconSparkle className="nr-inbox__sparkle" />
                  Lead scoring AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="nr-inbox__composer">
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

      <aside className="nr-inbox__ctx">
        <p className="nr-inbox__ctx-eyebrow">Buyer card</p>
        <h4>{convo.name}</h4>
        <dl>
          <div><dt>Listing</dt><dd>{convo.listing}</dd></div>
          <div><dt>Lead score</dt><dd className="nr-inbox__ctx-hot">94 · Hot</dd></div>
          <div><dt>Budget fit</dt><dd>$1.2–1.4M · matched</dd></div>
        </dl>
        <div className="nr-inbox__ctx-notes">
          <p>Listing AI</p>
          <span>Asked HOA + tour · pre-approved · Saturday preference · nurture paused</span>
        </div>
        <button type="button" className="nr-inbox__ctx-btn">View on schedule</button>
      </aside>
    </div>
  );
}
