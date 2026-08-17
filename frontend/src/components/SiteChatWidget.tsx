import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { sendSiteChat, type SiteChatMessage } from '../api/siteChat';
import '../styles/site-chat.css';

const WELCOME =
  "Hey — I’m the Build My Version guide. We find the AI your business actually needs, prove it with a free preview, then build it. What kind of business are you running?";

// Lucide-style outline paths, stroked with currentColor.
const ICONS = {
  utensils:
    'M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2 M7 2v20 M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3 M21 15v7',
  rocket:
    'M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z M12 15l-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0 M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5',
  gift: 'M20 12v10H4V12 M2 7h20v5H2z M12 22V7 M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z',
  bulb: 'M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5 M9 18h6 M10 22h4',
  sparkle:
    'M9.9 15.5a2 2 0 0 0-1.4-1.4l-6.1-1.6a.5.5 0 0 1 0-.96L8.5 9.9A2 2 0 0 0 9.9 8.5l1.6-6.1a.5.5 0 0 1 .96 0l1.6 6.1a2 2 0 0 0 1.4 1.4l6.1 1.6a.5.5 0 0 1 0 .96l-6.1 1.6a2 2 0 0 0-1.4 1.4l-1.6 6.1a.5.5 0 0 1-.96 0z M19 3v4 M21 5h-4',
  plane: 'M22 2 11 13 M22 2 15 22l-4-9-9-4z',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d={path} />
    </svg>
  );
}

/** The one robot mark used everywhere — header tile, message avatar, fab:
 *  a speech-bubble head with antenna nubs, eyes and a smile. */
function BotMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden
    >
      <path d="M9 3.5v2M15 3.5v2" />
      <rect x="4.5" y="5.5" width="15" height="12.5" rx="4" />
      <path d="M9.5 10.4v1.7M14.5 10.4v1.7" />
      <path d="M9.6 15q2.4 1.7 4.8 0" />
      <path d="M8.5 18v3l3-3" />
    </svg>
  );
}

const STARTERS = [
  { label: 'I’m a restaurant', icon: ICONS.utensils },
  { label: 'How do I start?', icon: ICONS.rocket },
  { label: 'What packages do you offer?', icon: ICONS.gift },
  { label: 'Show me solutions', icon: ICONS.bulb },
] as const;

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

  // Keep dense product pages light — no fixed chat fighting thumbs
  if (
    pathname.startsWith('/admin') ||
    pathname.startsWith('/submit') ||
    pathname.startsWith('/demo') ||
    pathname.startsWith('/studio') ||
    pathname.startsWith('/result') ||
    pathname.startsWith('/share') ||
    pathname.startsWith('/login') ||
    pathname.startsWith('/signup')
  ) {
    return null;
  }

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
            <span className="site-chat__tile" aria-hidden>
              <BotMark className="site-chat__tile-bot" />
            </span>
            <div className="site-chat__headtext">
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
            {messages.map((m, i) =>
              m.role === 'assistant' ? (
                <div key={`a-${i}`} className="site-chat__row">
                  <span className="site-chat__avatar" aria-hidden>
                    <BotMark className="site-chat__avatar-bot" />
                  </span>
                  <div className="site-chat__bubble site-chat__bubble--assistant">
                    {linkify(m.content)}
                  </div>
                </div>
              ) : (
                <div key={`u-${i}`} className="site-chat__bubble site-chat__bubble--user">
                  {linkify(m.content)}
                </div>
              ),
            )}
            {busy && (
              <div className="site-chat__row">
                <span className="site-chat__avatar" aria-hidden>
                  <BotMark className="site-chat__avatar-bot" />
                </span>
                <div className="site-chat__bubble site-chat__bubble--assistant site-chat__typing">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {!busy && messages.length < 3 && (
            <div className="site-chat__starters">
              {STARTERS.map((s) => (
                <button key={s.label} type="button" onClick={() => void ask(s.label)}>
                  <Icon path={s.icon} className="site-chat__chip-icon" />
                  {s.label}
                </button>
              ))}
            </div>
          )}

          <form className="site-chat__form" onSubmit={onSubmit}>
            <div className="site-chat__inputwrap">
              <Icon path={ICONS.sparkle} className="site-chat__spark" />
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask about plans, solutions…"
                maxLength={800}
                disabled={busy}
                aria-label="Message"
              />
            </div>
            <button type="submit" disabled={busy || !input.trim()}>
              Send
              <Icon path={ICONS.plane} className="site-chat__plane" />
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
        {open ? <span className="site-chat__fab-x">×</span> : <BotMark className="site-chat__fab-bot" />}
      </button>
    </div>
  );
}
