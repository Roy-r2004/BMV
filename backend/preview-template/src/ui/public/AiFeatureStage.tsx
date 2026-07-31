import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
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
  // Partial by construction: the synthesizer writes one entry per demo prompt
  // and the union of prompt sets across features leaves the rest `undefined`,
  // which a `Record<string, string>` rejected (TS2322 on every AI hub).
  demo_results?: Record<string, string | undefined>;
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

export function resolveDemo(
  feature: AiFeatureItem,
  brandName: string,
  prompt?: string | null,
): string {
  // `prompt` is routinely `feature.name`, and a generated feature object need not
  // have one. Request 47's `/admin/paintings/1/edit` rendered the error boundary
  // with "Cannot read properties of undefined (reading 'trim')" for exactly that.
  const text = String(prompt ?? '').trim() || String(feature.name ?? 'this feature');
  // Entries can be `undefined` now that the type admits a partial record, so the
  // lookups below must not hand a `string | undefined` back as the answer.
  const results = feature.demo_results || {};
  const exact = results[text];
  if (exact) return exact;
  const fold = text.toLowerCase();
  const match = Object.entries(results).find(([key, value]) => {
    if (!value) return false;
    const k = key.toLowerCase();
    return k === fold || fold.includes(k) || k.includes(fold);
  });
  if (match && match[1]) return match[1];

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
  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  if (category === 'digest') {
    return <DigestStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  if (category === 'scoring') {
    return <ScorecardStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  if (category === 'ops') {
    return <OpsRouterStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  if (category === 'scheduling') {
    return <SchedulingStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  if (category === 'automation') {
    return <AutomationStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  if (category === 'chat') {
    return <ChatStage feature={feature} brandName={brandName} compact={compact} className={className} />;
  }
  // Unknown categories still get a tool face — never a random chat wall.
  return <AutomationStage feature={feature} brandName={brandName} compact={compact} className={className} />;
}

function AutomationStage({
  feature,
  brandName,
  compact,
  className,
}: AiFeatureStageProps) {
  const steps = [
    { id: '1', label: 'Trigger', text: feature.demo_hint || `${feature.name} detects work` },
    { id: '2', label: 'Draft', text: resolveDemo(feature, brandName || 'Brand', feature.name) },
    { id: '3', label: 'Approve', text: `You confirm — ${brandName} runs it` },
  ];
  return (
    <StageChrome feature={feature} category="automation" compact={!!compact} className={className}>
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
        Workflow · not a chat
      </p>
      <ol className="space-y-2">
        {steps.map((step, i) => (
          <li
            key={step.id}
            className="rounded-[var(--radius-ui)] border border-border-subtle bg-background/80 px-3.5 py-3"
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-brand">
              {String(i + 1).padStart(2, '0')} · {step.label}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground">{step.text}</p>
          </li>
        ))}
      </ol>
      <Button className="mt-4 w-full" size="sm">
        Run once
      </Button>
    </StageChrome>
  );
}

function StageChrome({
  feature,
  category,
  compact,
  className,
  children,
}: {
  feature: AiFeatureItem;
  category: string;
  compact: boolean;
  className?: string;
  children: ReactNode;
}) {
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
      <div className="relative z-[1] flex-1 p-4 sm:p-5">{children}</div>
    </div>
  );
}

function DigestStage({
  feature,
  brandName,
  compact,
  className,
}: AiFeatureStageProps) {
  const cards = [
    { id: 'p1', label: 'Priority', text: `Clear overdue AR before noon — 4 invoices block ${brandName} cash.` },
    { id: 'p2', label: 'Risk', text: 'Bank feed has 12 unmatched lines; 2 look like duplicate payments.' },
    { id: 'p3', label: 'Win', text: feature.demo_hint || `${feature.name} drafted tomorrow’s books brief automatically.` },
  ];
  return (
    <StageChrome feature={feature} category="digest" compact={!!compact} className={className}>
      <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
        Morning brief · not a chat
      </p>
      <div className="space-y-3">
        {cards.map((card) => (
          <article
            key={card.id}
            className="rounded-[var(--radius-ui)] border border-border-subtle bg-background/80 px-3.5 py-3"
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-brand">
              {card.label}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-foreground">{card.text}</p>
          </article>
        ))}
      </div>
      <Button className="mt-5 w-full" size="sm">
        Open action list
      </Button>
    </StageChrome>
  );
}

function ScorecardStage({
  feature,
  brandName,
  compact,
  className,
}: AiFeatureStageProps) {
  const score = 84;
  return (
    <StageChrome feature={feature} category="scoring" compact={!!compact} className={className}>
      <div className="flex flex-col items-center text-center">
        <div className="relative flex h-28 w-28 items-center justify-center rounded-full border-4 border-brand/25 bg-brand/10">
          <span className="font-display text-4xl font-semibold tabular-nums text-foreground">
            {score}
          </span>
        </div>
        <p className="mt-4 text-sm font-semibold text-foreground">
          High intent · {feature.name}
        </p>
        <p className="mt-1 max-w-sm text-sm text-muted">
          {resolveDemo(feature, brandName || 'Brand', feature.name)}
        </p>
        <div className="mt-5 grid w-full grid-cols-3 gap-2 text-center">
          {[
            ['Signal', 'Strong'],
            ['Next', 'Call 2h'],
            ['Owner', 'You'],
          ].map(([k, v]) => (
            <div
              key={k}
              className="rounded-[var(--radius-ui)] border border-border-subtle bg-background/80 px-2 py-2"
            >
              <p className="text-[10px] uppercase tracking-[0.14em] text-muted">{k}</p>
              <p className="mt-1 text-xs font-semibold text-foreground">{v}</p>
            </div>
          ))}
        </div>
      </div>
    </StageChrome>
  );
}

function OpsRouterStage({
  feature,
  brandName,
  compact,
  className,
}: AiFeatureStageProps) {
  const items = [
    { id: '1', title: 'Route unmatched bank lines', owner: 'Books', status: 'Ready' },
    { id: '2', title: `Assign ${feature.name} checklist`, owner: 'Ops', status: 'Queued' },
    { id: '3', title: `${brandName} exception triage`, owner: 'AI', status: 'In progress' },
  ];
  return (
    <StageChrome feature={feature} category="ops" compact={!!compact} className={className}>
      <p className="mb-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted">
        Queue router · tap to assign
      </p>
      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between gap-3 rounded-[var(--radius-ui)] border border-border-subtle bg-background/80 px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">{item.title}</p>
              <p className="text-xs text-muted">{item.owner}</p>
            </div>
            <span className="shrink-0 rounded-full border border-border-subtle px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
              {item.status}
            </span>
          </li>
        ))}
      </ul>
      <Button className="mt-4 w-full" size="sm" variant="secondary">
        Run router
      </Button>
    </StageChrome>
  );
}

function SchedulingStage({
  feature,
  brandName,
  compact,
  className,
}: AiFeatureStageProps) {
  const slots = ['Thu 10:00', 'Fri 14:30', 'Mon 09:15'];
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <StageChrome feature={feature} category="scheduling" compact={!!compact} className={className}>
      <p className="mb-1 text-sm font-medium text-foreground">
        Hold a seat with {feature.name}
      </p>
      <p className="mb-4 text-xs text-muted">
        Best fits for {brandName} — pick one to preview the hold.
      </p>
      <div className="grid gap-2">
        {slots.map((slot) => (
          <button
            key={slot}
            type="button"
            onClick={() => setPicked(slot)}
            className={cn(
              'rounded-[var(--radius-ui)] border px-3.5 py-3 text-left text-sm font-semibold transition',
              picked === slot
                ? 'border-brand bg-brand text-white'
                : 'border-border-subtle bg-background/80 text-foreground hover:border-brand/35',
            )}
          >
            {slot}
          </button>
        ))}
      </div>
      {picked ? (
        <p className="mt-4 text-xs text-muted">Held {picked} · confirmation ready</p>
      ) : null}
    </StageChrome>
  );
}

function ChatStage({
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
