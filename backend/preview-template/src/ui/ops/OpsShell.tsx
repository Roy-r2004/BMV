import * as React from 'react';

import { cn } from '../lib/cn';

export interface OpsShellNavItem {
  id: string;
  label: string;
  href?: string;
  active?: boolean;
}

export interface OpsShellProps {
  brandName: string;
  navItems: OpsShellNavItem[];
  children: React.ReactNode;
  topbar?: React.ReactNode;
  className?: string;
}

export function OpsShell({ brandName, children, className, navItems, topbar }: OpsShellProps) {
  return (
    <div className={cn('flex min-h-screen bg-background text-foreground', className)}>
      <aside className="hidden w-64 shrink-0 border-r border-border-subtle bg-card xl:flex xl:flex-col">
        <div className="border-b border-border-subtle px-6 py-6">
          <p className="text-xs font-semibold tracking-[0.2em] text-muted uppercase">Operations</p>
          <p className="mt-2 text-lg font-semibold tracking-tight text-foreground">{brandName}</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Operations">
          {navItems.map((item) => {
            const itemClassName = cn(
              'rounded-[var(--radius-ui)] px-3 py-2.5 text-sm font-medium transition',
              item.active ? 'bg-foreground text-background' : 'text-muted hover:bg-background hover:text-foreground'
            );
            if (item.href) {
              return (
                <a key={item.id} href={item.href} className={itemClassName} aria-current={item.active ? 'page' : undefined}>
                  {item.label}
                </a>
              );
            }
            return (
              <div key={item.id} className={itemClassName} aria-current={item.active ? 'page' : undefined}>
                {item.label}
              </div>
            );
          })}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        {topbar ? (
          <header className="sticky top-0 z-10 border-b border-border-subtle bg-card/95 backdrop-blur">
            <div className="flex min-h-16 items-center justify-between gap-4 px-5 py-4 sm:px-6 lg:px-8">{topbar}</div>
          </header>
        ) : null}
        <main className="flex-1 px-5 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
