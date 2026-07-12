import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface PublicShellProps extends React.HTMLAttributes<HTMLDivElement> {
  brandName: string;
  nav?: React.ReactNode;
  footer?: React.ReactNode;
  mainClassName?: string;
  footerClassName?: string;
  backgroundClassName?: string;
}

export function PublicShell({
  backgroundClassName,
  brandName,
  children,
  className,
  footer,
  footerClassName,
  mainClassName,
  nav,
  ...props
}: PublicShellProps) {
  return (
    <div
      className={cn(
        'relative min-h-screen overflow-hidden bg-slate-950 text-white',
        'before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-[34rem] before:bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.14),transparent_55%)] before:content-[""]',
        className
      )}
      {...props}
    >
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(255,255,255,0.04)_0%,rgba(2,6,23,0.75)_48%,rgba(2,6,23,1)_100%)]',
          backgroundClassName
        )}
      />
      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/65 backdrop-blur-xl">
          <div className="mx-auto flex min-h-18 w-full max-w-7xl items-center justify-between gap-6 px-6 py-4 lg:px-10">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold uppercase tracking-[0.28em] text-white/55">{brandName}</p>
            </div>
            <div className="flex min-w-0 flex-1 justify-end">{nav}</div>
          </div>
        </header>

        <main className={cn('relative flex-1', mainClassName)}>{children}</main>

        <footer className={cn('relative border-t border-white/10 bg-white/5', footerClassName)}>
          <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-10 lg:px-10">
            {footer ?? (
              <>
                <p className="text-lg font-semibold">{brandName}</p>
                <p className="max-w-2xl text-sm leading-6 text-white/60">
                  Premium, AI-native customer experiences designed to turn curiosity into booked revenue.
                </p>
              </>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

export default PublicShell;
