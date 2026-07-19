import { MotionReveal } from '../motion';
import { cn } from '../lib/cn';
import { AiFeatureStage, type AiFeatureItem } from './AiFeatureStage';

export type AiFeaturePanelProps = {
  feature: AiFeatureItem;
  brandName?: string;
  className?: string;
  compact?: boolean;
};

export function AiFeaturePanel({
  feature,
  brandName = 'Brand',
  className,
  compact = false,
}: AiFeaturePanelProps) {
  return (
    <MotionReveal>
      <section
        className={cn(
          'my-8 overflow-hidden rounded-[1.5rem] border border-black/[0.07] bg-[color-mix(in_srgb,var(--color-background)_70%,white)] p-4 shadow-[0_28px_70px_-48px_rgba(20,16,12,0.65)] sm:p-5',
          compact && 'my-5 p-3.5',
          className,
        )}
        data-ai-feature={feature.id}
        data-ai-feature-context={feature.placement_path || ''}
        aria-label={`${feature.name} in context`}
      >
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3 px-0.5">
          <div className="min-w-0">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-[color:var(--color-brand)]">
              {feature.placement_label || 'AI on this page'}
            </p>
            <h3 className="mt-1.5 font-display text-[clamp(1.55rem,2.4vw,2rem)] italic leading-tight tracking-tight text-foreground">
              {feature.name}
            </h3>
            <p className="mt-1.5 max-w-xl text-sm leading-relaxed text-neutral-600">
              {feature.description || feature.name}
            </p>
          </div>
          <a
            href="/ai-features"
            className="shrink-0 text-xs font-semibold text-neutral-600 underline-offset-4 transition hover:text-foreground hover:underline"
          >
            All AI features →
          </a>
        </div>
        <AiFeatureStage feature={feature} brandName={brandName} compact />
      </section>
    </MotionReveal>
  );
}
