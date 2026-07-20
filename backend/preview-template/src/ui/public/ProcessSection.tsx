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

export function ProcessSection({
  className,
  description,
  heading,
  steps: stepsProp = [],
}: ProcessSectionProps) {
  const steps = Array.isArray(stepsProp) ? stepsProp : [];
  return (
    <section className={cn('relative overflow-hidden px-6 py-28 lg:px-12 lg:py-36', className)}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 w-1/2 bg-[radial-gradient(80%_60%_at_0%_40%,color-mix(in_srgb,var(--color-brand)_14%,transparent),transparent_70%)]"
      />
      <div className="relative mx-auto w-full max-w-[92rem]">
        <MotionReveal className="grid gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-end">
          <h2 className="font-display text-[clamp(2.75rem,5.5vw,4.75rem)] leading-[0.95] tracking-[-0.035em] text-foreground">
            {heading}
          </h2>
          {description ? (
            <p className="max-w-md text-base leading-8 text-muted lg:justify-self-end">{description}</p>
          ) : null}
        </MotionReveal>
        <MotionStagger className="mt-16 border-t border-foreground/12" role="list">
          {steps.map((step, index) => (
            <MotionStaggerItem key={step.title} role="listitem">
              <div className="group grid gap-4 border-b border-foreground/12 py-10 transition-colors md:grid-cols-[5.5rem_1fr_1.4fr] md:items-baseline md:gap-10">
                <p className="font-mono text-sm font-semibold tracking-[0.18em] text-brand/55 transition-colors group-hover:text-brand">
                  {String(index + 1).padStart(2, '0')}
                </p>
                <h3 className="font-display text-[clamp(1.5rem,2.4vw,2.15rem)] tracking-tight text-foreground">
                  {step.title}
                </h3>
                <p className="text-base leading-8 text-muted">{step.description}</p>
              </div>
            </MotionStaggerItem>
          ))}
        </MotionStagger>
      </div>
    </section>
  );
}
