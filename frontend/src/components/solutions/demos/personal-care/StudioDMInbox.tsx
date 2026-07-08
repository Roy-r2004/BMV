import { useState } from 'react';
import { type TimeSlot } from './studioData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Mike T.', handle: '@miket_fades', channel: 'instagram' as const, preview: 'Yo any fades Thursday after 5?', time: '2m', unread: true, avatar: 'M', visits: 12 },
  { id: '1', name: 'Chris D.', handle: '+1 718…', channel: 'whatsapp' as const, preview: 'VIP slot Friday?', time: '18m', unread: false, avatar: 'C', visits: 24 },
  { id: '2', name: 'Devon S.', handle: 'Web chat', channel: 'web' as const, preview: 'Kids cut Saturday?', time: '1h', unread: false, avatar: 'D', visits: 3 },
  { id: '3', name: 'Jordan P.', handle: '@jordan.p', channel: 'instagram' as const, preview: 'Can we do 6 instead?', time: '2h', unread: false, avatar: 'J', visits: 8 },
];

type ThreadMsg = { role: 'user' | 'ai'; text: string; time?: string };

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'user', text: 'Yo any fades open Thursday after 5?', time: '4:12 PM' },
    { role: 'ai', text: 'Hey Mike! Jay\'s got 5:15 or 6:00 on Chair 2 — both skin fades. Got your #2 guard saved from last time.', time: '4:12 PM' },
    { role: 'user', text: '5:15. Same as always', time: '4:13 PM' },
    { role: 'ai', text: 'Locked ✂ Thu 5:15 · Jay · Chair 2. Text reminder goes out 2h before. See you!', time: '4:13 PM' },
  ],
  '1': [
    { role: 'user', text: 'Can I grab VIP Friday afternoon?', time: '3:48 PM' },
    { role: 'ai', text: 'Chris! Marcus has 4:30 VIP on Chair 1 — skip the wait, loyalty perk included. Book it?', time: '3:48 PM' },
  ],
  '2': [
    { role: 'user', text: 'Saturday morning kids cut?', time: '2:15 PM' },
    { role: 'ai', text: 'Alex has 9:30 or 11:00 Saturday — 30 min kids cut. First haircut? He\'s great with little ones.', time: '2:15 PM' },
  ],
  '3': [
    { role: 'user', text: 'Can we push cut + beard to 6?', time: '1:02 PM' },
    { role: 'ai', text: 'Checking Jay\'s chair… 6:00 PM is open. Want me to move your booking?', time: '1:02 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  instagram: 'Instagram DM',
  whatsapp: 'WhatsApp',
  web: 'Web chat',
};

interface Props {
  bookedSlot: TimeSlot | null;
  onClearBooking: () => void;
}

export default function StudioDMInbox({ bookedSlot, onClearBooking }: Props) {
  const [active, setActive] = useState('0');
  const [channelFilter, setChannelFilter] = useState<'all' | 'instagram' | 'whatsapp'>('all');
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
    setExtra((m) => [...m, { role: 'user', text, time: 'Now' }, { role: 'ai', text: 'On it — checking the board…', time: 'Now' }]);
    setInput('');
  };

  return (
    <div className="sn-dm">
      <aside className="sn-dm__sidebar">
        <header className="sn-dm__sidebar-head">
          <div>
            <h2>Inbox</h2>
            <span className="sn-dm__count">{CONVERSATIONS.length} active threads</span>
          </div>
          <span className="sn-dm__ai-pill">Style memory</span>
        </header>

        <div className="sn-dm__ai-strip">
          <span>Remembers fade</span>
          <span>Books from IG</span>
          <span>Fills cancels</span>
        </div>

        {bookedSlot && (
          <div className="sn-dm__booking-alert">
            <span className="sn-dm__booking-alert-icon">✂</span>
            <div>
              <strong>New web booking</strong>
              <p>{bookedSlot.label}</p>
            </div>
            <button type="button" onClick={onClearBooking} aria-label="Dismiss">×</button>
          </div>
        )}

        <div className="sn-dm__channels">
          {(['all', 'instagram', 'whatsapp'] as const).map((ch) => (
            <button
              key={ch}
              type="button"
              className={`sn-dm__channel ${channelFilter === ch ? 'sn-dm__channel--on' : ''}`}
              onClick={() => setChannelFilter(ch)}
            >
              {ch === 'all' ? 'All' : ch === 'instagram' ? 'Instagram' : 'WhatsApp'}
            </button>
          ))}
        </div>

        <div className="sn-dm__list">
          {filteredConvos.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`sn-dm__thread ${active === c.id ? 'sn-dm__thread--on' : ''}`}
              onClick={() => { setActive(c.id); setExtra([]); }}
            >
              <span className={`sn-dm__avatar-ring sn-dm__avatar-ring--${c.channel}`}>
                <span className={`sn-dm__avatar sn-dm__avatar--${c.channel}`}>{c.avatar}</span>
              </span>
              <div className="sn-dm__thread-body">
                <div className="sn-dm__thread-top">
                  <strong>{c.name}</strong>
                  <span>{c.time}</span>
                </div>
                <p>{c.preview}</p>
              </div>
              {c.unread && <span className="sn-dm__unread" />}
            </button>
          ))}
        </div>

        <footer className="sn-dm__sidebar-foot">
          <div className="sn-dm__sidebar-stat"><strong>4.2m</strong><span>avg reply</span></div>
          <div className="sn-dm__sidebar-stat"><strong>38</strong><span>booked this week</span></div>
        </footer>
      </aside>

      <div className="sn-dm__chat">
        <header className="sn-dm__chat-head">
          <span className={`sn-dm__avatar-ring sn-dm__avatar-ring--${convo.channel}`}>
            <span className={`sn-dm__avatar sn-dm__avatar--${convo.channel} sn-dm__avatar--lg`}>{convo.avatar}</span>
          </span>
          <div>
            <strong>{convo.name}</strong>
            <span>{CHANNEL_LABEL[convo.channel]} · {convo.handle}</span>
          </div>
          <div className="sn-dm__chat-actions">
            <button type="button" className="sn-dm__chat-action sn-dm__chat-action--primary">Book slot</button>
            <button type="button" className="sn-dm__chat-action">Take over</button>
          </div>
        </header>

        <div className="sn-dm__day-divider"><span>Today</span></div>

        <div className="sn-dm__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`sn-dm__bubble sn-dm__bubble--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="sn-dm__bubble-tag">
                  <svg viewBox="0 0 24 24" width="10" height="10" fill="currentColor" aria-hidden><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
                  Style memory AI
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="sn-dm__quick">
          {['Recall #2 fade', 'Offer Jay 5:15', 'Backfill waitlist'].map((q) => (
            <button key={q} type="button" onClick={() => setInput(q)}>{q}</button>
          ))}
        </div>

        <div className="sn-dm__composer">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Staff reply…"
          />
          <button type="button" className="sn-dm__send" onClick={send}>Send</button>
        </div>
      </div>

      <aside className="sn-dm__ctx">
        <h3>Client card</h3>
        <div className="sn-dm__ctx-profile">
          <span className={`sn-dm__avatar-ring sn-dm__avatar-ring--${convo.channel}`}>
            <span className={`sn-dm__avatar sn-dm__avatar--${convo.channel} sn-dm__avatar--xl`}>{convo.avatar}</span>
          </span>
          <strong>{convo.name}</strong>
          <span>Regular · {convo.visits} visits</span>
        </div>
        <dl className="sn-dm__ctx-meta">
          <div><dt>Style</dt><dd>#2 guard fade · line-up</dd></div>
          <div><dt>Barber</dt><dd>Jay Ortiz</dd></div>
          <div><dt>Loyalty</dt><dd><span className="sn-dm__ctx-stamps">5 / 8 stamps</span></dd></div>
          <div><dt>Next</dt><dd className="sn-dm__ctx-next">Thu 5:15 PM</dd></div>
        </dl>
        <div className="sn-dm__ctx-tags">
          <span>Instagram</span>
          <span>Auto-book</span>
          <span className="sn-dm__ctx-tag--vip">VIP</span>
        </div>
        <button type="button" className="sn-dm__ctx-cta">View full profile</button>
      </aside>
    </div>
  );
}
