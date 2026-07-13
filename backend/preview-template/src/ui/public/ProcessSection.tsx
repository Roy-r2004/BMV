import * as React from 'react';

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

export function ProcessSection({ className, description, heading, steps }: ProcessSectionProps) {
  return (
    <section className={cn('px-6 py-24 lg:px-10 lg:py-28', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <div className="max-w-2xl">
          <h2 className="font-display text-[clamp(2.25rem,4vw,3.4rem)] leading-[1.05] tracking-[-0.03em] text-foreground">
            {heading}
          </h2>
          {description ? <p className="mt-5 text-base leading-7 text-muted sm:text-lg">{description}</p> : null}
        </div>
        <ol className="mt-14 grid gap-8 md:grid-cols-3 md:gap-6">
          {steps.map((step, index) => (
            <li key={step.title} className="relative rounded-[1.5rem] border border-border-subtle bg-card p-7 shadow-[var(--shadow-ui)]">
              <p className="font-display text-5xl leading-none text-brand/35">{String(index + 1).padStart(2, '0')}</p>
              <h3 className="mt-6 text-xl font-semibold tracking-tight text-foreground">{step.title}</h3>
              <p className="mt-3 text-sm leading-7 text-muted">{step.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
