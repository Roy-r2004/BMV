import { useState } from 'react';
import { PeakFormLogo, IconClose, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { type ClassSlot } from './peakformData.ts';

const CONVERSATIONS = [
  { id: '0', name: 'Jordan K.', handle: 'App', channel: 'app' as const, preview: 'Move HIIT to Thursday 6:30?', time: '4m', unread: true, avatar: 'J', program: 'HIIT Burn' },
  { id: '1', name: 'Sam L.', handle: 'Referral', channel: 'app' as const, preview: 'Trial — which class for beginners?', time: '35m', unread: false, avatar: 'S', program: '12-week program' },
  { id: '2', name: 'Priya M.', handle: '@priya.lifts', channel: 'instagram' as const, preview: 'Log my deadlift PR?', time: '1h', unread: false, avatar: 'P', program: 'Strength Lab' },
  { id: '3', name: 'Chris W.', handle: 'SMS', channel: 'sms' as const, preview: 'Missed Monday — still on plan?', time: '2h', unread: false, avatar: 'C', program: 'Unlimited' },
];

type ThreadMsg = { role: 'user' | 'ai'; text: string; time?: string };

const THREADS: Record<string, ThreadMsg[]> = {
  '0': [
    { role: 'user', text: 'Can I move my HIIT slot to Thursday 6:30?', time: '5:12 PM' },
    { role: 'ai', text: 'Thursday 6:30 PM with Maya is open — want me to swap you in?', time: '5:12 PM' },
    { role: 'user', text: 'Yes please.', time: '5:13 PM' },
    { role: 'ai', text: 'Done ✓ Thu 6:30 PM · HIIT Burn. Calendar updated — Maya has your program notes.', time: '5:13 PM' },
  ],
  '1': [
    { role: 'user', text: 'First trial class — HIIT or strength for a beginner?', time: '4:40 PM' },
    { role: 'ai', text: 'Strength Lab Thu 7:30 is great for form foundations — or Friday 6:30 AM flow for mobility.', time: '4:40 PM' },
  ],
  '2': [
    { role: 'user', text: 'Just hit 225 on deadlift — can you log it?', time: '3:55 PM' },
    { role: 'ai', text: 'Logged ✓ PR #225 · Strength Lab. Derek left form notes in your progress feed.', time: '3:55 PM' },
  ],
  '3': [
    { role: 'user', text: 'Missed Monday — am I still on track?', time: '2:20 PM' },
    { role: 'ai', text: 'You\'re 2 of 3 for the week. Thursday HIIT gets you back on streak — book now?', time: '2:20 PM' },
  ],
};

const CHANNEL_LABEL: Record<string, string> = {
  app: 'App',
  instagram: 'Instagram',
  sms: 'SMS',
};

interface Props {
  bookedSlot: ClassSlot | null;
  onClearBooking: () => void;
}

export default function PeakFormMemberInbox({ bookedSlot, onClearBooking }: Props) {
  const [active, setActive] = useState('0');
  const [channelFilter, setChannelFilter] = useState<'all' | 'app' | 'instagram' | 'sms'>('all');
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
    setExtra((m) => [...m, { role: 'user', text, time: 'Now' }, { role: 'ai', text: 'Checking with your coach…', time: 'Now' }]);
    setInput('');
  };

  return (
    <div className="pf-inbox">
      <aside className="pf-inbox__sidebar">
        <header className="pf-inbox__sidebar-head">
          <div className="pf-inbox__sidebar-brand">
            <PeakFormLogo className="pf-inbox__sidebar-logo" />
            <div>
              <h2>Member chat</h2>
              <span className="pf-inbox__count">{CONVERSATIONS.length} active threads</span>
            </div>
          </div>
          <span className="pf-inbox__ai-pill">
            <IconSparkle className="pf-inbox__sparkle" />
            Adherence AI
          </span>
        </header>

        <div className="pf-inbox__ai-strip">
          <span>Saves streaks</span>
          <span>Stops silent churn</span>
          <span>Coach digest</span>
        </div>

        <div className="pf-inbox__sidebar-stats">
          <div><strong>47</strong><span>Reschedules</span></div>
          <div><strong>11</strong><span>Streak saves</span></div>
          <div><strong>3</strong><span>At-risk flagged</span></div>
        </div>

        {bookedSlot && (
          <div className="pf-inbox__booking-alert">
            <span className="pf-inbox__booking-alert-icon" aria-hidden>
              <PeakFormLogo className="pf-inbox__booking-logo" />
            </span>
            <div>
              <strong>Class confirmed</strong>
              <p>{bookedSlot.label}</p>
            </div>
            <button type="button" className="pf-inbox__booking-dismiss" onClick={onClearBooking} aria-label="Dismiss">
              <IconClose className="pf-inbox__icon" />
            </button>
          </div>
        )}

        <div className="pf-inbox__filters">
          {(['all', 'app', 'instagram', 'sms'] as const).map((f) => (
            <button
              key={f}
              type="button"
              className={channelFilter === f ? 'pf-inbox__filter pf-inbox__filter--on' : 'pf-inbox__filter'}
              onClick={() => setChannelFilter(f)}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        <ul className="pf-inbox__list">
          {filteredConvos.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                className={`pf-inbox__convo ${active === c.id ? 'pf-inbox__convo--on' : ''}`}
                onClick={() => { setActive(c.id); setExtra([]); }}
              >
                <span className={`pf-inbox__avatar pf-inbox__avatar--${c.channel}`}>{c.avatar}</span>
                <div className="pf-inbox__convo-body">
                  <div className="pf-inbox__convo-top">
                    <strong>{c.name}</strong>
                    <span>{c.time}</span>
                  </div>
                  <p>{c.preview}</p>
                  <span className="pf-inbox__channel">{CHANNEL_LABEL[c.channel]}</span>
                </div>
                {c.unread && <span className="pf-inbox__unread" aria-label="Unread" />}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <main className="pf-inbox__thread">
        <header className="pf-inbox__thread-head">
          <div className="pf-inbox__thread-guest">
            <span className={`pf-inbox__avatar pf-inbox__avatar--${convo.channel} pf-inbox__avatar--lg`}>{convo.avatar}</span>
            <div>
              <h3>{convo.name}</h3>
              <span>{convo.handle} · {CHANNEL_LABEL[convo.channel]}</span>
            </div>
          </div>
          <div className="pf-inbox__thread-actions">
            <button type="button">Adjust program</button>
            <button type="button" className="pf-inbox__thread-action--primary">Log PR</button>
          </div>
        </header>

        <div className="pf-inbox__messages">
          {messages.map((msg, i) => (
            <div key={i} className={`pf-inbox__msg pf-inbox__msg--${msg.role}`}>
              {msg.role === 'ai' && (
                <span className="pf-inbox__msg-label">
                  <IconSparkle className="pf-inbox__sparkle" />
                  Adherence coach
                </span>
              )}
              <p>{msg.text}</p>
              {msg.time && <time>{msg.time}</time>}
            </div>
          ))}
        </div>

        <div className="pf-inbox__composer">
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

      <aside className="pf-inbox__ctx">
        <p className="pf-inbox__ctx-eyebrow">Member card</p>
        <h4>{convo.name}</h4>
        <dl>
          <div><dt>Program</dt><dd>{convo.program}</dd></div>
          <div><dt>Streak</dt><dd className="pf-inbox__ctx-hot">12 days</dd></div>
          <div><dt>Churn risk</dt><dd>Low · on plan</dd></div>
        </dl>
        <div className="pf-inbox__ctx-notes">
          <p>Coach AI</p>
          <span>Prefers evening HIIT · rescheduled Thu · Maya briefed · renewal in 18 days</span>
        </div>
        <button type="button" className="pf-inbox__ctx-btn">Open progress</button>
      </aside>
    </div>
  );
}
