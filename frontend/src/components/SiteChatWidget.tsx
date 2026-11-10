import axios from 'axios';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { sendSiteChat, type SiteChatMessage } from '../api/siteChat';
import { SCENES } from '../film/scenes';
import '../styles/site-chat.css';

const WELCOME =
  'Ask me anything. I can talk through your idea or your business, explain how we work, or help with any other question.';

/** One plain speech mark, for the launcher. */
function SpeechMark({ className }: { className?: string }) {
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
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.6A8 8 0 1 1 21 12z" />
    </svg>
  );
}

const STARTERS = [
  'I have an idea I want built',
  'I already run a business',
  'How does a consultation work?',
  'What does it cost?',
] as const;

// Only the site's real pages become links, so "and/or" and "24/7" stay plain text.
const PAGES = ['/demo', ...SCENES.map((s) => s.path).filter((p) => p !== '/')];
const PAGE_LINK = new RegExp(`(?<![\\w/.:-])(${PAGES.join('|')})(?![\\w/-])`, 'g');

/** An answer's text: the site's pages as links, and **words** in bold. */
function renderAnswer(text: string) {
  return text.split(PAGE_LINK).map((part, i) => {
    if (i % 2 === 1) {
      return (
        <Link key={i} to={part} className="site-chat__link">
          {part}
        </Link>
      );
    }
    return (
      <span key={i}>
        {part.split(/\*\*(.+?)\*\*/g).map((bit, k) => (k % 2 === 1 ? <strong key={k}>{bit}</strong> : bit))}
      </span>
    );
  });
}

/** What to tell the visitor when a message did not get through. */
function failureMessage(err: unknown): string {
  const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
  if (typeof detail === 'string' && detail) return detail;
  return 'Sorry, I couldn’t get an answer just now. Please ask again in a moment, or write to consulting@buildmyversion.com.';
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
  const inputRef = useRef<HTMLTextAreaElement>(null);

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
    // A consultation in progress, or its package: the bubble sat on top of
    // the reviewers' notes in the diagnosis margin.
    pathname.startsWith('/engagements/') ||
    pathname.startsWith('/result') ||
    pathname.startsWith('/share') ||
    pathname.startsWith('/for/') ||
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
      const reply = await sendSiteChat(next.slice(-20), pathname);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: failureMessage(err) }]);
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
        <section className="site-chat__panel" role="dialog" aria-label="Ask Build My Version">
          <header className="site-chat__head">
            <div>
              <h2>Ask Build My Version</h2>
              <p>An AI assistant. Ask it anything.</p>
            </div>
            <button type="button" className="site-chat__close" onClick={() => setOpen(false)} aria-label="Close">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
                <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
              </svg>
            </button>
          </header>

          <div className="site-chat__messages" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`site-chat__msg site-chat__msg--${m.role}`}>
                {m.role === 'assistant' ? <span className="site-chat__who">Build My Version</span> : null}
                <p dir="auto">{m.role === 'assistant' ? renderAnswer(m.content) : m.content}</p>
              </div>
            ))}
            {busy && (
              <div className="site-chat__msg site-chat__msg--assistant">
                <span className="site-chat__who">Build My Version</span>
                <p className="site-chat__typing" aria-label="Writing a reply">
                  <span />
                  <span />
                  <span />
                </p>
              </div>
            )}
            {!busy && messages.length < 3 && (
              <ul className="site-chat__starters">
                {STARTERS.map((q) => (
                  <li key={q}>
                    <button type="button" onClick={() => void ask(q)}>
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div ref={endRef} />
          </div>

          <form className="site-chat__form" onSubmit={onSubmit}>
            <label htmlFor="site-chat-input" className="sr-only">
              Your question
            </label>
            <textarea
              id="site-chat-input"
              ref={inputRef}
              dir="auto"
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void ask(input);
                }
              }}
              placeholder="Ask anything"
              maxLength={2000}
              disabled={busy}
            />
            <button type="submit" disabled={busy || !input.trim()}>
              Send
            </button>
          </form>
        </section>
      )}

      {!open && (
        <button type="button" className="site-chat__launch" onClick={() => setOpen(true)} aria-label="Ask a question">
          <SpeechMark className="site-chat__launch-icon" />
          <span className="site-chat__launch-text">Ask a question</span>
        </button>
      )}
    </div>
  );
}
