import * as React from 'react';

import { MotionHover } from '../motion';
import { cn } from '../lib/cn';

export interface CardProps {
  children: React.ReactNode;
  title?: string;
  description?: string;
  className?: string;
  /** Soft brand glow behind the card. */
  atmosphere?: boolean;
  /** Disable hover lift (forms / dense panels). */
  static?: boolean;
}

export function Card({
  atmosphere = true,
  children,
  className,
  description,
  static: isStatic = false,
  title,
}: CardProps) {
  const body = (
    <div
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-border-subtle bg-card p-6 shadow-[var(--shadow-ui)]',
        className
      )}
    >
      {atmosphere ? (
        <div
          aria-hidden
          className="pointer-events-none absolute -right-10 -top-12 h-36 w-36 rounded-full bg-[color-mix(in_srgb,var(--color-brand)_12%,transparent)] blur-3xl"
        />
      ) : null}
      <div className="relative">
        {title ? (
          <h3 className="font-display text-lg font-semibold tracking-tight text-foreground">{title}</h3>
        ) : null}
        {description ? <p className="mt-1 text-sm leading-6 text-muted">{description}</p> : null}
        <div className={title || description ? 'mt-4' : undefined}>{children}</div>
      </div>
    </div>
  );

  if (isStatic) return body;
  return <MotionHover>{body}</MotionHover>;
}
