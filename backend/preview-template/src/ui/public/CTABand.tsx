import * as React from 'react';

import { Button } from '../core/Button';
import { MotionReveal } from '../motion';
import { cn } from '../lib/cn';

export interface CTALink {
  label: string;
  href: string;
}

export interface CTABandProps {
  heading: string;
  primaryCta: CTALink;
  description?: string;
  secondaryCta?: CTALink;
  /**
   * Small caps line above the heading. Pass business copy; the default is
   * deliberately plain rather than a slogan.
   *
   * This was a hardcoded two-word phrase that `safety/copy_hygiene._BANNED_COPY`
   * has banned since it was written — and the ban could never take effect. The
   * guard rewrites the file, then `restore_template_owned_files` restores it from
   * the template, `src/ui/**` being template-owned on every catalogue workspace.
   * So the guard logged "template jargon replaced" on every run while the banned
   * phrase — in caps, because of the `uppercase` class below — shipped above the
   * CTA of every generated site.
   *
   * The ownership rule is right and stays; the kit simply must not ship a string
   * the pipeline bans. A prop with a default is the pattern the rest of the kit
   * already uses — see `ConfirmStage`'s `eyebrow = 'Confirmed'`.
   *
   * (The banned phrase is not repeated here on purpose: `scripts/preview-qa.sh`
   * greps this tree, and a comment quoting it is a false positive forever.)
   */
  eyebrow?: string;
  className?: string;
}

export function CTABand({
  className,
  description,
  eyebrow = 'What comes next',
  heading,
  primaryCta,
  secondaryCta,
}: CTABandProps) {
  // Keep ink readable even when callers pass light `bg-*` / `text-*` overrides.
  return (
    <section
      className={cn(
        'relative isolate overflow-hidden bg-foreground px-6 py-28 text-background lg:px-12 lg:py-32',
        className
      )}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_80%_at_80%_20%,color-mix(in_srgb,var(--color-brand)_42%,transparent),transparent_60%)]" />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -left-20 bottom-0 h-72 w-72 rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-brand)_28%,transparent),transparent_70%)] blur-2xl"
      />
      <div className="ui-mesh opacity-40" />
      <div className="ui-film-grain opacity-[0.14]" />
      <div className="ui-noise opacity-30" />
      <MotionReveal>
        <div className="relative mx-auto flex w-full max-w-[92rem] flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl text-inherit">
            {eyebrow ? (
              <p className="text-[11px] font-semibold tracking-[0.28em] text-current/45 uppercase">
                {eyebrow}
              </p>
            ) : null}
            <h2 className="mt-4 font-display text-[clamp(2.75rem,5.5vw,5.25rem)] leading-[0.92] tracking-[-0.04em] text-current">
              {heading}
            </h2>
            {description ? (
              <p className="mt-5 max-w-lg text-base leading-8 text-current/55">{description}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-3">
            <Button
              href={primaryCta.href}
              size="lg"
              className="border-transparent bg-white text-foreground shadow-[0_0_40px_-8px_color-mix(in_srgb,var(--color-brand)_55%,transparent)] hover:bg-white/92 hover:text-foreground"
            >
              {primaryCta.label}
            </Button>
            {secondaryCta ? (
              <Button
                href={secondaryCta.href}
                size="lg"
                variant="outline"
                className="border-current/35 bg-current/5 text-current hover:bg-current/12 hover:text-current"
              >
                {secondaryCta.label}
              </Button>
            ) : null}
          </div>
        </div>
      </MotionReveal>
    </section>
  );
}
