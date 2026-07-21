import { useMemo } from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
import { AppLink } from '../lib/AppLink';
import { cn } from '../lib/cn';
import {
  AiFeatureStage,
  categoryLabel,
  type AiFeatureItem,
} from './AiFeatureStage';

export type { AiFeatureItem };

export type AiFeatureDeckProps = {
  features: AiFeatureItem[];
  brandName?: string;
  className?: string;
};

function FeatureStageRow({
  feature,
  brandName,
  index,
}: {
  feature: AiFeatureItem;
  brandName: string;
  index: number;
}) {
  const category = (feature.category || feature.surface || 'automation').toLowerCase();
  const inContext =
    feature.placement_path && feature.placement_path !== '/ai-features'
      ? feature.placement_path
      : null;

  return (
    <MotionStaggerItem>
      <article
        className="grid items-start gap-8 border-t border-border-subtle py-12 first:border-t-0 first:pt-0 lg:grid-cols-[0.9fr_1.1fr] lg:gap-12"
        data-ai-feature={feature.id}
        aria-label={feature.name}
      >
        <div className="max-w-md">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[11px] tabular-nums text-muted">
              {String(index + 1).padStart(2, '0')}
            </span>
            <span className="rounded-full border border-border-subtle bg-card px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-muted">
              {categoryLabel(category)}
            </span>
          </div>
          <h3 className="mt-4 font-display text-[clamp(2rem,3.4vw,2.85rem)] leading-[1.05] tracking-tight text-foreground">
            {feature.name}
          </h3>
          <p className="mt-3 text-sm leading-relaxed text-muted sm:text-[15px]">
            {feature.description || feature.name}
          </p>
          {inContext ? (
            <AppLink
              href={inContext}
              className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-foreground underline-offset-4 transition hover:underline"
            >
              See it in context
              {feature.placement_title ? (
                <span className="font-normal text-muted">· {feature.placement_title}</span>
              ) : null}
              <span aria-hidden="true">→</span>
            </AppLink>
          ) : (
            <p className="mt-6 text-xs font-medium uppercase tracking-[0.16em] text-muted">
              Previewed on this hub
            </p>
          )}
        </div>
        <AiFeatureStage feature={feature} brandName={brandName} />
      </article>
    </MotionStaggerItem>
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
        <p className="text-sm text-muted">No AI features in this plan yet.</p>
      </section>
    );
  }

  return (
    <section
      className={cn('relative isolate overflow-hidden px-6 py-16 sm:px-10 sm:py-20', className)}
      data-ai-feature-deck=""
    >
      <div className="ui-mesh opacity-30" aria-hidden="true" />
      <div className="relative mx-auto max-w-6xl">
        <MotionReveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-brand">
            AI in your product
          </p>
          <h2 className="mt-4 max-w-3xl font-display text-[clamp(2.5rem,5.5vw,4.25rem)] leading-[0.95] tracking-[-0.03em] text-foreground">
            Every AI feature from your plan — live
          </h2>
          <p className="mt-5 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
            These are the capabilities proposed for {brandName}. Open a conversation below, or jump
            into the page where each one actually lives.
          </p>
        </MotionReveal>

        <MotionStagger className="mt-14">
          {items.map((feature, index) => (
            <FeatureStageRow
              key={feature.id}
              feature={feature}
              brandName={brandName}
              index={index}
            />
          ))}
        </MotionStagger>
      </div>
    </section>
  );
}
