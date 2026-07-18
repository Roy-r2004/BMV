import { useMemo, useState } from 'react';
import { Badge } from '../core/Badge';
import { Button } from '../core/Button';
import { Input } from '../core/Input';
import { cn } from '../lib/cn';
import type { AiFeatureItem } from './AiFeatureDeck';

export type AiFeaturePanelProps = {
  feature: AiFeatureItem;
  brandName?: string;
  className?: string;
  compact?: boolean;
};

function runDemo(category: string, brandName: string, prompt: string, featureName: string): string {
  const text = prompt.trim() || featureName;
  switch ((category || 'automation').toLowerCase()) {
    case 'chat':
      return `${brandName}: “${text}” — here’s the clear answer, what to do next, and when a human should jump in.`;
    case 'scheduling':
      return `Best fits for “${text}”: Thu 10:00 · Fri 14:30 · Mon 09:15. Tap one to hold the seat.`;
    case 'digest':
      return `Daily brief for “${text}”: 3 priorities · 1 risk · 1 win. Owners can act in under a minute.`;
    case 'scoring':
      return `Score 84/100 for “${text}” — high intent. Suggested next step: call within 2 hours.`;
    case 'ops':
      return `Routed “${text}” → queue + owner + checklist. Status set to In progress.`;
    default:
      return `Automation for “${text}”: drafted → ready to approve → will run on confirm.`;
  }
}

export function AiFeaturePanel({
  feature,
  brandName = 'Brand',
  className,
  compact = false,
}: AiFeaturePanelProps) {
  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  const prompts = useMemo(() => {
    const list = Array.isArray(feature.demo_prompts) ? feature.demo_prompts : [];
    return list.filter(Boolean).slice(0, 3) as string[];
  }, [feature.demo_prompts]);
  const [input, setInput] = useState(prompts[0] || '');
  const [output, setOutput] = useState('');
  const [busy, setBusy] = useState(false);

  const run = (prompt?: string) => {
    const next = (prompt ?? input).trim();
    if (prompt) setInput(prompt);
    setBusy(true);
    window.setTimeout(() => {
      setOutput(runDemo(category, brandName, next, feature.name));
      setBusy(false);
    }, 220);
  };

  return (
    <section
      className={cn(
        'my-6 rounded-2xl border border-black/10 bg-gradient-to-br from-neutral-50 to-white p-5 shadow-sm',
        compact && 'my-4 p-4',
        className,
      )}
      data-ai-feature={feature.id}
      data-ai-feature-context={feature.placement_path || ''}
      aria-label={`${feature.name} in context`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{feature.placement_label || 'AI'}</Badge>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-neutral-500">
          Try this AI in context
        </p>
      </div>
      <h3 className="text-lg font-semibold tracking-tight text-neutral-950">{feature.name}</h3>
      <p className="mt-1 text-sm leading-relaxed text-neutral-600">
        {feature.description || feature.name}
      </p>
      {feature.demo_hint ? (
        <p className="mt-3 text-xs font-medium text-neutral-500">{feature.demo_hint}</p>
      ) : null}
      {prompts.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {prompts.map((prompt) => (
            <button
              key={prompt}
              type="button"
              className="rounded-full border border-neutral-200 bg-white px-3 py-1.5 text-left text-xs font-medium text-neutral-700 transition hover:border-neutral-400"
              onClick={() => run(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      ) : null}
      <div className="mt-4 space-y-3">
        <Input
          label="Or type your own"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Try a real request…"
        />
        <Button type="button" onClick={() => run()} disabled={busy}>
          {busy ? 'Running…' : 'Run demo'}
        </Button>
        {output ? (
          <div className="rounded-xl bg-neutral-950 px-4 py-3 text-sm leading-relaxed text-neutral-100">
            {output}
          </div>
        ) : null}
      </div>
    </section>
  );
}
