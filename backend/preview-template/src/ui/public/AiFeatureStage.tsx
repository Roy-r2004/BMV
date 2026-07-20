import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';

import { Button } from '../core/Button';
import { useMotionSafe } from '../motion/presets';
import { cn } from '../lib/cn';

export type AiFeatureItem = {
  id: string;
  name: string;
  description?: string;
  category?: string;
  surface?: string;
  demo_hint?: string;
  demo_prompts?: string[];
  demo_results?: Record<string, string>;
  placement_label?: string;
  placement_path?: string;
  placement_title?: string;
  placement_component?: string;
};

type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
};

export function categoryLabel(category: string | undefined): string {
  const c = (category || 'automation').toLowerCase();
  const map: Record<string, string> = {
    chat: 'Assistant',
    scheduling: 'Scheduling',
    digest: 'Digest',
    scoring: 'Scoring',
    automation: 'Automation',
    ops: 'Ops AI',
  };
  return map[c] || 'AI';
}

export function resolveDemo(feature: AiFeatureItem, brandName: string, prompt: string): string {
  const text = prompt.trim() || feature.name;
  const results = feature.demo_results || {};
  if (results[text]) return results[text];
  const fold = text.toLowerCase();
  const match = Object.entries(results).find(([key]) => {
    const k = key.toLowerCase();
    return k === fold || fold.includes(k) || k.includes(fold);
  });
  if (match) return match[1];

  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  if (category === 'chat') {
    return `${brandName}: “${text}” — here’s the clear answer, what to do next, and when a human should jump in.`;
  }
  if (category === 'scheduling') {
    return `Best fits for “${text}”: Thu 10:00 · Fri 14:30 · Mon 09:15. Tap one to hold the seat.`;
  }
  if (category === 'digest') {
    return `Daily brief for “${text}”: 3 priorities · 1 risk · 1 win. Owners can act in under a minute.`;
  }
  if (category === 'scoring') {
    return `Score 84/100 for “${text}” — high intent. Suggested next step: call within 2 hours.`;
  }
  if (category === 'ops') {
    return `Routed “${text}” → queue + owner + checklist. Status set to In progress.`;
  }
  return `Automation for “${text}”: drafted → ready to approve → will run on confirm.`;
}

function ThinkingDots() {
  return (
    <span className="inline-flex items-center gap-1 px-0.5" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-current opacity-70"
          style={{ animationDelay: `${i * 140}ms` }}
        />
      ))}
    </span>
  );
}

function MessageBlock({
  msg,
  brandName,
  animate,
}: {
  msg: ChatMessage;
  brandName: string;
  animate: boolean;
}) {
  if (msg.role === 'system') {
    const body = (
      <div className="rounded-2xl border border-dashed border-border-subtle bg-card/60 px-3.5 py-3 text-sm leading-relaxed text-muted">
        {msg.text}
      </div>
    );
    if (!animate) return body;
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        {body}
      </motion.div>
    );
  }

  const isUser = msg.role === 'user';
  const bubble = (
    <div className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[92%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed shadow-[var(--shadow-ui)] sm:max-w-[85%]',
          isUser
            ? 'rounded-br-md bg-brand text-white'
            : 'rounded-bl-md border border-border-subtle bg-card text-foreground',
        )}
      >
        {!isUser ? (
          <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
            {brandName}
          </p>
        ) : null}
        {msg.text}
      </div>
    </div>
  );

  if (!animate) return bubble;
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
    >
      {bubble}
    </motion.div>
  );
}

export type AiFeatureStageProps = {
  feature: AiFeatureItem;
  brandName?: string;
  compact?: boolean;
  className?: string;
};

export function AiFeatureStage({
  feature,
  brandName = 'Brand',
  compact = false,
  className,
}: AiFeatureStageProps) {
  const safeMotion = useMotionSafe();
  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  const prompts = useMemo(() => {
    const list = Array.isArray(feature.demo_prompts) ? feature.demo_prompts : [];
    return list.filter(Boolean).slice(0, 3) as string[];
  }, [feature.demo_prompts]);

  const welcome = useMemo(() => {
    if (feature.demo_hint) return feature.demo_hint;
    return `Ask ${feature.name} the way a real ${brandName} customer would.`;
  }, [brandName, feature.demo_hint, feature.name]);

  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: `${feature.id}-sys`, role: 'system', text: welcome },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [activePrompt, setActivePrompt] = useState<string | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  const send = (prompt?: string) => {
    const next = (prompt ?? input).trim();
    if (!next || busy) return;
    setActivePrompt(next);
    setInput('');
    const userId = `${feature.id}-u-${Date.now()}`;
    setMessages((prev) => [...prev, { id: userId, role: 'user', text: next }]);
    setBusy(true);
    window.setTimeout(() => {
      const reply = resolveDemo(feature, brandName, next);
      setMessages((prev) => [
        ...prev,
        { id: `${feature.id}-a-${Date.now()}`, role: 'assistant', text: reply },
      ]);
      setBusy(false);
    }, compact ? 360 : 520);
  };

  return (
    <div
      className={cn(
        'relative flex flex-col overflow-hidden rounded-[calc(var(--radius-ui)+0.85rem)] border border-border-subtle bg-card shadow-[var(--shadow-ui)]',
        compact ? 'min-h-[280px]' : 'min-h-[360px]',
        className,
      )}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-70"
        aria-hidden="true"
        style={{
          background:
            'radial-gradient(80% 55% at 100% 0%, color-mix(in srgb, var(--color-brand) 10%, transparent), transparent 55%)',
        }}
      />

      <header className="relative z-[1] flex items-center justify-between gap-3 border-b border-border-subtle px-4 py-3 sm:px-5">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-brand">
            Live demo · {categoryLabel(category)}
          </p>
          <p className="mt-0.5 truncate text-sm font-medium tracking-tight text-foreground">
            {feature.name}
          </p>
        </div>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border-subtle bg-background/80 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500/70 opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-600" />
          </span>
          Ready
        </span>
      </header>

      <div
        ref={scrollerRef}
        className={cn(
          'relative z-[1] flex-1 space-y-3 overflow-y-auto px-4 py-4 sm:px-5',
          compact ? 'max-h-[220px]' : 'max-h-[280px]',
        )}
        role="log"
        aria-live="polite"
        aria-relevant="additions"
      >
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <MessageBlock key={msg.id} msg={msg} brandName={brandName} animate={safeMotion} />
          ))}
        </AnimatePresence>

        {busy ? (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-md border border-border-subtle bg-card px-3.5 py-2.5 text-sm text-muted shadow-sm">
              <span className="sr-only">Thinking</span>
              <ThinkingDots />
            </div>
          </div>
        ) : null}

        {!busy && messages.length <= 1 && prompts.length > 0 ? (
          <div className="pt-1">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted">
              Try one of these
            </p>
            <div className="flex flex-col gap-2">
              {prompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => send(prompt)}
                  className={cn(
                    'group rounded-2xl border border-border-subtle bg-background/80 px-3.5 py-2.5 text-left text-sm leading-snug text-foreground transition',
                    'hover:border-brand/35 hover:bg-card hover:shadow-[var(--shadow-ui)]',
                    activePrompt === prompt && 'border-brand/40',
                  )}
                >
                  <span className="mr-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted transition group-hover:text-brand">
                    Ask
                  </span>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <form
        className="relative z-[1] border-t border-border-subtle bg-background/70 p-3 backdrop-blur-sm sm:p-4"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        {messages.length > 1 && prompts.length > 0 ? (
          <div className="mb-2.5 flex flex-wrap gap-1.5">
            {prompts.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => send(prompt)}
                disabled={busy}
                className={cn(
                  'rounded-full border px-2.5 py-1 text-left text-[11px] font-medium transition',
                  activePrompt === prompt
                    ? 'border-brand bg-brand text-white'
                    : 'border-border-subtle bg-card text-muted hover:border-brand/30 hover:text-foreground',
                )}
              >
                {prompt}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2">
          <label className="sr-only" htmlFor={`ai-stage-${feature.id}`}>
            Message
          </label>
          <input
            id={`ai-stage-${feature.id}`}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a real customer ask…"
            disabled={busy}
            className="h-11 min-w-0 flex-1 rounded-[var(--radius-ui)] border border-border-subtle bg-card px-3.5 text-sm text-foreground outline-none transition placeholder:text-muted focus:border-brand/40 focus:ring-4 focus:ring-ring/15"
          />
          <Button type="submit" disabled={busy || !input.trim()} size="default">
            {busy ? '…' : 'Send'}
          </Button>
        </div>
      </form>
    </div>
  );
}
