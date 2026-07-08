import { useState } from 'react';
import { BOOKING_SLOTS } from './harborData';

type Msg = { role: 'user' | 'ai'; text: string };

const GREETING: Msg = {
  role: 'ai',
  text: 'Hi! I\'m Harbor AI — ask about treatments, pricing, or availability. I can book you in under a minute.',
};

const REPLIES: Record<string, string> = {
  botox: `Botox consults start at $420 with Dr. Elena Chen in Consult Suite A. Next openings: ${BOOKING_SLOTS.filter((s) => s.treatmentId === 'botox').map((s) => s.time).join(' or ')}.`,
  hydra: `Hydrafacial is $189 · 45 min in Treatment Room 2 with Jess Kim, RN. Most popular — want me to hold a slot?`,
  book: 'I can book you now — which treatment interests you? Hydrafacial, Botox consult, IV drip, or laser?',
  hours: 'Mon–Fri 8am–6pm · Sat 9am–2pm · Sun closed. Online booking is 24/7.',
  default: 'Great question — let me check that for you. Average response: under 15 seconds. Want to book or speak with our team?',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('botox')) return REPLIES.botox;
  if (t.includes('hydra') || t.includes('facial')) return REPLIES.hydra;
  if (t.includes('book') || t.includes('appointment') || t.includes('slot')) return REPLIES.book;
  if (t.includes('hour') || t.includes('open')) return REPLIES.hours;
  return REPLIES.default;
}

interface Props {
  onBookClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function HarborPatientChat({ onBookClick, open: controlledOpen, onOpenChange }: Props) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = (v: boolean | ((o: boolean) => boolean)) => {
    const next = typeof v === 'function' ? v(open) : v;
    onOpenChange?.(next);
    if (controlledOpen === undefined) setInternalOpen(next);
  };
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Msg[]>([GREETING]);

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setMessages((m) => [...m, { role: 'user', text: trimmed }, { role: 'ai', text: aiReply(trimmed) }]);
    setInput('');
  };

  return (
    <>
      {open && (
        <div className="hc-chat__panel" role="dialog" aria-label="Chat with Harbor AI">
          <header className="hc-chat__head">
            <div className="hc-chat__head-info">
              <span className="hc-chat__avatar">AI</span>
              <div>
                <p className="hc-chat__name">Harbor AI</p>
                <p className="hc-chat__status"><span className="hc-pulse" /> Online · replies instantly</p>
              </div>
            </div>
            <button type="button" className="hc-chat__close" onClick={() => setOpen(false)} aria-label="Close chat">×</button>
          </header>
          <div className="hc-chat__body">
            {messages.map((msg, i) => (
              <div key={i} className={`hc-chat__msg hc-chat__msg--${msg.role}`}>
                {msg.role === 'ai' && <span className="hc-chat__ai-tag">Harbor AI</span>}
                {msg.text}
              </div>
            ))}
          </div>
          <div className="hc-chat__quick">
            {['Botox pricing?', 'Book Hydrafacial', 'Clinic hours'].map((q) => (
              <button key={q} type="button" onClick={() => send(q)}>{q}</button>
            ))}
          </div>
          <div className="hc-chat__composer">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send(input)}
              placeholder="Ask anything..."
              className="hc-chat__input"
            />
            <button type="button" className="hc-chat__send" onClick={() => send(input)}>Send</button>
          </div>
          {onBookClick && (
            <button type="button" className="hc-chat__book-cta" onClick={onBookClick}>
              Book appointment →
            </button>
          )}
        </div>
      )}
      <button type="button" className={`hc-chat__fab ${open ? 'hc-chat__fab--open' : ''}`} onClick={() => setOpen((o) => !o)}>
        {open ? (
          'Close'
        ) : (
          <>
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>
            Chat with us
          </>
        )}
      </button>
    </>
  );
}

export { aiReply };
