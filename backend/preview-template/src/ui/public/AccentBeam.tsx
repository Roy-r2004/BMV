import * as React from 'react';

import { cn } from '../lib/cn';

export interface AccentBeamProps {
  children: React.ReactNode;
  className?: string;
}

/** Magic UI BorderBeam-inspired frame — restrained, no open styling API. */
export function AccentBeam({ children, className }: AccentBeamProps) {
  return (
    <div className={cn('relative overflow-hidden rounded-[2rem]', className)}>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 rounded-[2rem] bg-[conic-gradient(from_180deg_at_50%_50%,transparent_40%,var(--color-brand)_52%,transparent_64%)] opacity-40 [mask:linear-gradient(#000_0_0)_content-box,linear-gradient(#000_0_0)] [mask-composite:exclude] p-px"
      />
      <div className="relative">{children}</div>
    </div>
  );
}
