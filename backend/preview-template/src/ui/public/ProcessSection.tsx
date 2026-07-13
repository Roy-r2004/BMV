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
    <section className={cn('px-6 py-20 text-background lg:px-10 lg:py-24', className)}>
      <div className="mx-auto w-full max-w-7xl">
        <h2 className="max-w-2xl font-display text-3xl tracking-[-0.03em] sm:text-4xl">{heading}</h2>
        {description ? <p className="mt-4 max-w-2xl text-base leading-7 text-background/65">{description}</p> : null}
        <ol className="mt-12 grid gap-8 md:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="relative border-t border-white/15 pt-6">
              <p className="text-xs font-semibold tracking-[0.2em] text-brand uppercase">Step {index + 1}</p>
              <h3 className="mt-3 text-xl font-semibold">{step.title}</h3>
              <p className="mt-3 text-sm leading-7 text-background/65">{step.description}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
