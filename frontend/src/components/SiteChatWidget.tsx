import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { sendSiteChat, type SiteChatMessage } from '../api/siteChat';
import '../styles/site-chat.css';

const WELCOME =
  "Hey — I’m the Build My Version guide. We find the AI your business actually needs, prove it with a free preview, then build it. What kind of business are you running?";

const STARTERS = [
  'I’m a restaurant',
  'How do I start?',
  'What packages do you offer?',
  'Show me solutions',
];

function linkify(text: string) {
  const parts = text.split(/(\/[a-z0-9\-/_]+)/gi);
  return parts.map((part, i) => {
    if (/^\/[a-z0-9\-/_]+$/i.test(part) && part.length > 1) {
      return (
        <Link key={i} to={part} className="site-chat__link">
          {part}
        </Link>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function GuideBot({ active }: { active?: boolean }) {
  return (
    <svg
      viewBox="0 0 64 72"
      className={`site-chat__bot ${active ? 'site-chat__bot--bounce' : ''}`}
      aria-hidden
    >
      <defs>
        <linearGradient id="site-chat-bot-body" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1e3a8a" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="site-chat-bot-face" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <ellipse cx="32" cy="68" rx="14" ry="3" fill="#2563eb" opacity="0.2" />
      <rect
        x="14"
        y="18"
        width="36"
        height="38"
        rx="12"
        fill="url(#site-chat-bot-body)"
        stroke="#38bdf8"
        strokeWidth="1.5"
        opacity="0.9"
      />
      <rect x="22" y="26" width="20" height="16" rx="6" fill="url(#site-chat-bot-face)" />
      <circle cx="28" cy="34" r="2.5" fill="#0f172a" />
      <circle cx="36" cy="34" r="2.5" fill="#0f172a" />
      <path
        d="M27 40 Q32 43 37 40"
        stroke="#0f172a"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <rect x="8" y="30" width="6" height="16" rx="3" fill="#2563eb" />
      <rect x="50" y="30" width="6" height="16" rx="3" fill="#2563eb" />
      <circle cx="32" cy="12" r="5" fill="#22d3ee" className="site-chat__antenna" />
      <line
        x1="32"
        y1="17"
        x2="32"
        y2="20"
        stroke="#67e8f9"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export default function SiteChatWidget() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [messages, setMessages] = useState<SiteChatMessage[]>([
    { role: 'assistant', content: WELCOME },
  ]);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
      inputRef.current?.focus();
    }
  }, [open, messages, busy]);

  if (pathname.startsWith('/admin')) return null;

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;

    const next: SiteChatMessage[] = [...messages, { role: 'user', content: trimmed }];
    setMessages(next);
    setInput('');
    setBusy(true);
    try {
      const reply = await sendSiteChat(next.slice(-8), pathname);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            'I couldn’t reach the guide just now — you can still start free at /submit, browse /demo, or explore /solutions. What are you trying to build?',
        },
      ]);
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(input);
  };

  return (
    <div className={`site-chat ${open ? 'site-chat--open' : ''}`}>
      {open && (
        <section className="site-chat__panel" aria-label="Site guide chat">
          <header className="site-chat__head">
            <div>
              <p className="site-chat__eyebrow">Site guide</p>
              <h2>Build My Version</h2>
            </div>
            <button
              type="button"
              className="site-chat__close"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
            >
              ×
            </button>
          </header>

          <div className="site-chat__messages">
            {messages.map((m, i) => (
              <div
                key={`${m.role}-${i}`}
                className={`site-chat__bubble site-chat__bubble--${m.role}`}
              >
                {linkify(m.content)}
              </div>
            ))}
            {busy && (
              <div className="site-chat__bubble site-chat__bubble--assistant site-chat__typing">
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={endRef} />
          </div>

          {!busy && messages.length < 3 && (
            <div className="site-chat__starters">
              {STARTERS.map((s) => (
                <button key={s} type="button" onClick={() => void ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          )}

          <form className="site-chat__form" onSubmit={onSubmit}>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about plans, solutions…"
              maxLength={800}
              disabled={busy}
              aria-label="Message"
            />
            <button type="submit" disabled={busy || !input.trim()}>
              Send
            </button>
          </form>
        </section>
      )}

      <button
        type="button"
        className={`site-chat__fab ${open ? 'site-chat__fab--open' : ''}`}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={open ? 'Close site guide' : 'Open site guide'}
      >
        {open ? <span className="site-chat__fab-x">×</span> : <GuideBot active={!open} />}
      </button>
    </div>
  );
}
