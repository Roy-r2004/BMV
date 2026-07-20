import * as React from 'react';

import { AnimeHeroItem, AnimeReveal } from '../motion';
import { Button } from '../core/Button';
import { cn } from '../lib/cn';

export type ConfirmNextStep = {
  title: string;
  description: string;
  ctaLabel: string;
  href: string;
};

export type ConfirmStageProps = {
  title: string;
  description: string;
  /** Short status line under the title (class name, date, order id). */
  detail?: string;
  eyebrow?: string;
  nextSteps?: ConfirmNextStep[];
  primaryCta?: { label: string; href: string };
  className?: string;
};

/**
 * Manus-clear confirmation surface — centered status, equal next-step columns.
 * Use instead of PageHeader + uneven Card grids on waitlist / booking success.
 */
export function ConfirmStage({
  className,
  description,
  detail,
  eyebrow = 'Confirmed',
  nextSteps = [],
  primaryCta,
  title,
}: ConfirmStageProps) {
  const cols =
    nextSteps.length >= 3 ? 'sm:grid-cols-2 lg:grid-cols-3' : nextSteps.length === 2 ? 'sm:grid-cols-2' : 'grid-cols-1';

  return (
    <section
      data-confirm-stage=""
      className={cn('relative isolate overflow-hidden', className)}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[28rem] bg-[radial-gradient(70%_55%_at_50%_0%,color-mix(in_srgb,var(--color-brand)_14%,transparent),transparent_70%)]"
      />
      <div className="relative mx-auto max-w-5xl px-6 py-16 sm:px-10 sm:py-20 lg:py-24">
        <div className="mx-auto max-w-2xl text-center">
          <AnimeHeroItem index={0}>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-brand">
              {eyebrow}
            </p>
          </AnimeHeroItem>
          <AnimeHeroItem index={1}>
            <h1 className="mt-5 font-display text-[clamp(2.4rem,5.5vw,3.75rem)] leading-[1.05] tracking-[-0.03em] text-foreground">
              {title}
            </h1>
          </AnimeHeroItem>
          {detail ? (
            <AnimeHeroItem index={2}>
              <p className="mt-5 inline-flex max-w-xl rounded-full border border-border-subtle bg-card/80 px-4 py-2 text-sm font-medium text-foreground shadow-[var(--shadow-ui)]">
                {detail}
              </p>
            </AnimeHeroItem>
          ) : null}
          <AnimeHeroItem index={detail ? 3 : 2}>
            <p className="mx-auto mt-6 max-w-xl text-base leading-7 text-muted">{description}</p>
          </AnimeHeroItem>
          {primaryCta ? (
            <AnimeHeroItem index={4}>
              <div className="mt-8 flex justify-center">
                <Button href={primaryCta.href} size="lg">
                  {primaryCta.label}
                </Button>
              </div>
            </AnimeHeroItem>
          ) : null}
        </div>

        {nextSteps.length > 0 ? (
          <AnimeReveal className="mt-14">
            <p className="mb-5 text-center text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
              What you can do next
            </p>
            <div className={cn('grid gap-4', cols)}>
              {nextSteps.map((step) => (
                <a
                  key={step.href + step.title}
                  href={step.href}
                  className="group flex h-full flex-col rounded-[calc(var(--radius-ui)+0.45rem)] border border-border-subtle bg-card p-5 shadow-[var(--shadow-ui)] transition hover:-translate-y-0.5 hover:border-brand/25"
                >
                  <h3 className="font-display text-xl tracking-tight text-foreground">{step.title}</h3>
                  <p className="mt-2 flex-1 text-sm leading-6 text-muted">{step.description}</p>
                  <span className="mt-5 inline-flex items-center gap-1.5 text-sm font-semibold text-brand">
                    {step.ctaLabel}
                    <span aria-hidden className="transition group-hover:translate-x-0.5">
                      →
                    </span>
                  </span>
                </a>
              ))}
            </div>
          </AnimeReveal>
        ) : null}
      </div>
    </section>
  );
}
