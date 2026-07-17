import * as React from 'react';

import { cn } from '../lib/cn';
import { useMotionSafe } from '../motion/presets';

export interface AccentBeamProps {
  children: React.ReactNode;
  className?: string;
}

/** Magic UI BorderBeam-inspired frame — restrained, no open styling API. */
export function AccentBeam({ children, className }: AccentBeamProps) {
  const safe = useMotionSafe();
  return (
    <div className={cn('relative overflow-hidden rounded-[2rem]', className)}>
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-0 rounded-[2rem] bg-[conic-gradient(from_180deg_at_50%_50%,transparent_40%,var(--color-brand)_52%,transparent_64%)] opacity-45 [mask:linear-gradient(#000_0_0)_content-box,linear-gradient(#000_0_0)] [mask-composite:exclude] p-px',
          safe && 'animate-[spin_12s_linear_infinite]'
        )}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-[1px] rounded-[calc(2rem-1px)] bg-[radial-gradient(60%_50%_at_30%_20%,color-mix(in_srgb,var(--color-brand)_12%,transparent),transparent_70%)]"
      />
      <div className="relative">{children}</div>
    </div>
  );
}
