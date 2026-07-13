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
    <div className={cn('relative min-h-screen bg-background text-foreground', className)}>
      <div className="relative z-10 flex min-h-screen flex-col">
        <header className="sticky top-0 z-30 border-b border-border-subtle/80 bg-background/80 backdrop-blur-xl">
          <div className="mx-auto flex min-h-[4.25rem] w-full max-w-7xl items-center justify-between gap-6 px-6 py-3 lg:px-10">
            <p className="font-display text-[1.65rem] leading-none tracking-[-0.02em] text-foreground">{brandName}</p>
            <nav className="flex min-w-0 flex-1 items-center justify-end gap-1">{nav}</nav>
          </div>
        </header>
        <main className="relative flex-1">{children}</main>
        {footer}
      </div>
    </div>
  );
}
