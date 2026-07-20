import * as React from 'react';

import { MotionReveal, MotionStagger, MotionStaggerItem } from '../motion';
import { cn } from '../lib/cn';

export interface ProcessStep {
  title: string;
  description: string;
}

export interface ProcessSectionProps {
  heading: string;
  steps: ProcessStep[];
  description?: string;
  className?: string;
}

/**
 * Journey timeline — intentionally NOT the same silhouette as FeatureBento rows.
 * Horizontal chapters on desktop; stacked cards with a brand spine on mobile.
 */
export function ProcessSection({
  className,
  description,
  heading,
  steps: stepsProp = [],
}: ProcessSectionProps) {
  const steps = Array.isArray(stepsProp) ? stepsProp : [];
  return (
    <section
      className={cn(
        'relative overflow-hidden bg-[color-mix(in_srgb,var(--color-brand)_5%,var(--color-background))] px-6 py-28 lg:px-12 lg:py-36',
        className
      )}
      data-section="process"
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_50%_at_90%_0%,color-mix(in_srgb,var(--color-brand)_16%,transparent),transparent_60%)]"
      />
      <div className="relative mx-auto w-full max-w-[92rem]">
        <MotionReveal className="max-w-3xl">
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-brand">The path</p>
          <h2 className="mt-4 font-display text-[clamp(2.75rem,5.5vw,4.75rem)] leading-[0.95] tracking-[-0.035em] text-foreground">
            {heading}
          </h2>
          {description ? <p className="mt-5 max-w-md text-base leading-8 text-muted">{description}</p> : null}
        </MotionReveal>

        <MotionStagger
          className="relative mt-16 grid gap-6 md:grid-cols-2 xl:grid-cols-4"
          role="list"
        >
          {/* Desktop connector line */}
          <div
            aria-hidden
            className="pointer-events-none absolute left-[8%] right-[8%] top-10 hidden h-px bg-gradient-to-r from-transparent via-brand/35 to-transparent xl:block"
          />
          {steps.map((step, index) => (
            <MotionStaggerItem key={step.title} role="listitem">
              <article className="group relative flex h-full flex-col rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card p-6 shadow-[var(--shadow-ui)] transition duration-500 hover:-translate-y-1 hover:border-brand/30 sm:p-7">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand text-sm font-semibold text-white shadow-[0_12px_28px_-12px_color-mix(in_srgb,var(--color-brand)_70%,transparent)]">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
                    Step {index + 1}
                  </span>
                </div>
                <h3 className="mt-6 font-display text-[clamp(1.35rem,2vw,1.75rem)] leading-tight tracking-tight text-foreground">
                  {step.title}
                </h3>
                <p className="mt-3 flex-1 text-sm leading-7 text-muted">{step.description}</p>
                {index < steps.length - 1 ? (
                  <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.18em] text-brand/50 transition group-hover:text-brand">
                    Next →
                  </p>
                ) : (
                  <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.18em] text-brand/50">
                    You arrive
                  </p>
                )}
              </article>
            </MotionStaggerItem>
          ))}
        </MotionStagger>
      </div>
    </section>
  );
}
