import { useMemo, useState } from 'react';
import { Badge } from '../core/Badge';
import { Button } from '../core/Button';
import { Input } from '../core/Input';
import { cn } from '../lib/cn';

export type AiFeatureItem = {
  id: string;
  name: string;
  description?: string;
  category?: string;
  surface?: string;
};

export type AiFeatureDeckProps = {
  features: AiFeatureItem[];
  brandName?: string;
  className?: string;
};

function categoryLabel(category: string | undefined): string {
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

function FeatureWidget({
  feature,
  brandName,
}: {
  feature: AiFeatureItem;
  brandName: string;
}) {
  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  const [input, setInput] = useState('');
  const [output, setOutput] = useState('');
  const [busy, setBusy] = useState(false);

  const run = () => {
    setBusy(true);
    window.setTimeout(() => {
      const prompt = input.trim() || feature.name;
      if (category === 'chat') {
        setOutput(
          `${brandName} assistant: Based on “${prompt}”, here is a clear next step and what I need from you.`,
        );
      } else if (category === 'scheduling') {
        setOutput(`Suggested: Thu 10:00 · Fri 14:30 · Mon 09:15 — best fit for “${prompt}”.`);
      } else if (category === 'digest') {
        setOutput(`Digest ready: 3 priorities, 1 risk, 1 win related to “${prompt}”.`);
      } else if (category === 'scoring') {
        setOutput(`Score 82/100 for “${prompt}” — high intent, follow up today.`);
      } else if (category === 'ops') {
        setOutput(`Routed “${prompt}” to the right queue with checklist + owner.`);
      } else {
        setOutput(`Automation drafted for “${prompt}” — review → approve → run.`);
      }
      setBusy(false);
    }, 280);
  };

  return (
    <section
      className="rounded-2xl border border-black/10 bg-white/80 p-5 shadow-sm"
      data-ai-feature={feature.id}
      aria-label={feature.name}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Badge variant="secondary">{categoryLabel(category)}</Badge>
        <h3 className="text-base font-semibold tracking-tight text-neutral-900">{feature.name}</h3>
      </div>
      <p className="mb-4 text-sm leading-relaxed text-neutral-600">
        {feature.description || feature.name}
      </p>
      <div className="space-y-3">
        <Input
          label="Try it"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={`Ask ${feature.name.toLowerCase()}…`}
        />
        <Button type="button" onClick={run} disabled={busy}>
          {busy ? 'Running…' : 'Run AI'}
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

export function AiFeatureDeck({ features, brandName = 'Brand', className }: AiFeatureDeckProps) {
  const items = useMemo(
    () => (Array.isArray(features) ? features.filter((f) => f && f.id && f.name) : []),
    [features],
  );

  if (!items.length) {
    return (
      <section className={cn('px-6 py-16', className)}>
        <p className="text-sm text-neutral-500">No AI features in this plan yet.</p>
      </section>
    );
  }

  return (
    <section className={cn('px-6 py-12 sm:px-10', className)} data-ai-feature-deck="">
      <div className="mx-auto max-w-5xl">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-neutral-500">
          AI in your product
        </p>
        <h2 className="mb-2 text-3xl font-semibold tracking-tight text-neutral-950">
          Every AI feature from your plan
        </h2>
        <p className="mb-8 max-w-2xl text-sm leading-relaxed text-neutral-600">
          These are the AI capabilities proposed for {brandName}. Each one is interactive in this
          preview — not just listed in the proposal.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((feature) => (
            <FeatureWidget key={feature.id} feature={feature} brandName={brandName} />
          ))}
        </div>
      </div>
    </section>
  );
}
