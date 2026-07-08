import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  HarborLogo,
  EmberLogo,
  IconArrowRight,
  IconChat,
  IconClose,
  IconSend,
  IconSparkle,
  StudioNineLogo,
  NorthlineLogo,
  PeakFormLogo,
  ApexLogo,
  LumenLogo,
  SummitLogo,
  BrightFixLogo,
  HarborFundLogo,
  RowLogo,
  MetroLogo,
} from './ShowcaseChatIcons.tsx';

export type ChatTheme =
  | 'harbor'
  | 'studio'
  | 'ember'
  | 'northline'
  | 'peakform'
  | 'apex'
  | 'lumen'
  | 'summit'
  | 'brightfix'
  | 'harborfund'
  | 'row'
  | 'metro';

type Msg = { role: 'user' | 'ai'; text: string };

const LOGOS: Record<ChatTheme, ReactNode> = {
  harbor: <HarborLogo className="sc-chat__logo-svg" />,
  studio: <StudioNineLogo className="sc-chat__logo-svg" />,
  ember: <EmberLogo className="sc-chat__logo-svg" />,
  northline: <NorthlineLogo className="sc-chat__logo-svg" />,
  peakform: <PeakFormLogo className="sc-chat__logo-svg" />,
  apex: <ApexLogo className="sc-chat__logo-svg" />,
  lumen: <LumenLogo className="sc-chat__logo-svg" />,
  summit: <SummitLogo className="sc-chat__logo-svg" />,
  brightfix: <BrightFixLogo className="sc-chat__logo-svg" />,
  harborfund: <HarborFundLogo className="sc-chat__logo-svg" />,
  row: <RowLogo className="sc-chat__logo-svg" />,
  metro: <MetroLogo className="sc-chat__logo-svg" />,
};

interface Props {
  theme: ChatTheme;
  brandName: string;
  aiLabel: string;
  statusText: string;
  greeting: string;
  quickReplies: string[];
  fabLabel: string;
  fabBadge?: string;
  placeholder?: string;
  poweredByText?: string;
  capabilityChips?: string[];
  /** One-line social proof that makes the AI feel irresistible */
  hookProof?: string;
  ctaLabel?: string;
  onCtaClick?: () => void;
  onReply: (text: string) => string;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  ariaLabel?: string;
}

export default function ShowcaseChatWidget({
  theme,
  brandName,
  aiLabel,
  statusText,
  greeting,
  quickReplies,
  fabLabel,
  fabBadge = 'AI',
  placeholder = 'Ask anything…',
  poweredByText = 'AI-powered · replies in seconds',
  capabilityChips,
  hookProof,
  ctaLabel,
  onCtaClick,
  onReply,
  open: controlledOpen,
  onOpenChange,
  ariaLabel,
}: Props) {
  const [internalOpen, setInternalOpen] = useState(false);
  const open = controlledOpen ?? internalOpen;
  const setOpen = (v: boolean | ((o: boolean) => boolean)) => {
    const next = typeof v === 'function' ? v(open) : v;
    onOpenChange?.(next);
    if (controlledOpen === undefined) setInternalOpen(next);
  };

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Msg[]>([{ role: 'ai', text: greeting }]);
  const [typing, setTyping] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, typing]);

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || typing) return;
    setMessages((m) => [...m, { role: 'user', text: trimmed }]);
    setInput('');
    setTyping(true);
    window.setTimeout(() => {
      setMessages((m) => [...m, { role: 'ai', text: onReply(trimmed) }]);
      setTyping(false);
    }, 520);
  };

  return (
    <div className={`sc-chat-wrap sc-chat-wrap--${theme}`}>
      {open && (
        <div className="sc-chat" role="dialog" aria-label={ariaLabel ?? `Chat with ${brandName}`}>
          <header className="sc-chat__head">
            <div className="sc-chat__brand">
              <span className="sc-chat__avatar">{LOGOS[theme]}</span>
              <div className="sc-chat__brand-text">
                <strong>{brandName}</strong>
                <span className="sc-chat__status">
                  <span className="sc-chat__dot" aria-hidden />
                  {statusText}
                </span>
              </div>
            </div>
            <button type="button" className="sc-chat__close" onClick={() => setOpen(false)} aria-label="Close chat">
              <IconClose className="sc-chat__icon" />
            </button>
          </header>

          {capabilityChips && capabilityChips.length > 0 && (
            <div className="sc-chat__caps" aria-label="AI capabilities">
              {capabilityChips.map((chip) => (
                <span key={chip} className="sc-chat__cap">{chip}</span>
              ))}
            </div>
          )}

          {hookProof && (
            <div className="sc-chat__hook" role="status">
              <IconSparkle className="sc-chat__sparkle" />
              <span>{hookProof}</span>
            </div>
          )}

          <div className="sc-chat__body" ref={bodyRef}>
            {messages.map((msg, i) => (
              <div key={i} className={`sc-chat__msg sc-chat__msg--${msg.role}`}>
                {msg.role === 'ai' && (
                  <span className="sc-chat__ai-label">
                    <IconSparkle className="sc-chat__sparkle" />
                    {aiLabel}
                  </span>
                )}
                <p>{msg.text}</p>
              </div>
            ))}
            {typing && (
              <div className="sc-chat__msg sc-chat__msg--ai sc-chat__msg--typing" aria-live="polite">
                <span className="sc-chat__ai-label">
                  <IconSparkle className="sc-chat__sparkle" />
                  {aiLabel}
                </span>
                <span className="sc-chat__dots">
                  <span /><span /><span />
                </span>
              </div>
            )}
          </div>

          <div className="sc-chat__quick">
            {quickReplies.map((q) => (
              <button key={q} type="button" onClick={() => send(q)} disabled={typing}>
                {q}
              </button>
            ))}
          </div>

          <div className="sc-chat__composer">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && send(input)}
              placeholder={placeholder}
              aria-label="Message"
              disabled={typing}
            />
            <button
              type="button"
              className="sc-chat__send"
              onClick={() => send(input)}
              aria-label="Send message"
              disabled={typing || !input.trim()}
            >
              <IconSend className="sc-chat__icon" />
            </button>
          </div>

          {onCtaClick && ctaLabel && (
            <button type="button" className="sc-chat__cta" onClick={onCtaClick}>
              <span>{ctaLabel}</span>
              <IconArrowRight className="sc-chat__icon" />
            </button>
          )}

          <p className="sc-chat__powered">
            <IconSparkle className="sc-chat__sparkle sc-chat__sparkle--sm" />
            {poweredByText}
          </p>
        </div>
      )}

      {!open && (
        <button type="button" className="sc-chat__fab" onClick={() => setOpen(true)} aria-label={`Open ${fabLabel}`}>
          <span className="sc-chat__fab-pulse" aria-hidden />
          <span className="sc-chat__fab-icon">
            <IconChat className="sc-chat__icon" />
          </span>
          <span className="sc-chat__fab-label">{fabLabel}</span>
          <span className="sc-chat__fab-badge">{fabBadge}</span>
        </button>
      )}
    </div>
  );
}
