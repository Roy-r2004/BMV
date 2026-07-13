import * as React from 'react';

import { cn } from '../lib/cn';

export interface PublicShellProps {
  brandName: string;
  children: React.ReactNode;
  nav?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function PublicShell({ brandName, children, className, footer, nav }: PublicShellProps) {
  return (
    <div className={cn('relative min-h-screen overflow-hidden bg-foreground text-background', className)}>
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[30rem] bg-[radial-gradient(circle_at_top,var(--glow-atmosphere),transparent_58%)]"
      />
      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="sticky top-0 z-20 border-b border-white/10 bg-foreground/80 backdrop-blur-xl">
          <div className="mx-auto flex min-h-16 w-full max-w-7xl items-center justify-between gap-6 px-6 py-4 lg:px-10">
            <p className="font-display text-lg tracking-tight text-background">{brandName}</p>
            <nav className="flex min-w-0 flex-1 justify-end">{nav}</nav>
          </div>
        </header>
        <main className="relative flex-1">{children}</main>
        {footer}
      </div>
    </div>
  );
}
