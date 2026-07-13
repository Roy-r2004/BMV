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
    <div className={cn('flex min-h-screen bg-[#e9eef2] text-foreground', className)}>
      <aside className="hidden w-[17rem] shrink-0 border-r border-border-subtle bg-card xl:flex xl:flex-col">
        <div className="border-b border-border-subtle px-6 py-7">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/12 text-sm font-bold text-brand">
            {brandName.slice(0, 1)}
          </div>
          <p className="mt-4 text-lg font-semibold tracking-tight text-foreground">{brandName}</p>
          <p className="mt-1 text-xs text-muted">Clinic operations</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-3" aria-label="Operations">
          {navItems.map((item) => {
            const itemClassName = cn(
              'rounded-xl px-3 py-2.5 text-sm font-medium transition',
              item.active
                ? 'bg-brand text-white shadow-sm shadow-brand/20'
                : 'text-muted hover:bg-background hover:text-foreground'
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
        <div className="border-b border-border-subtle bg-card px-4 py-2 xl:hidden">
          <nav className="flex gap-2 overflow-x-auto" aria-label="Operations mobile">
            {navItems.map((item) => (
              <a
                key={item.id}
                href={item.href ?? '#'}
                className={cn(
                  'shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold',
                  item.active ? 'bg-brand text-white' : 'bg-background text-muted'
                )}
              >
                {item.label}
              </a>
            ))}
          </nav>
        </div>
        {topbar ? (
          <header className="sticky top-0 z-10 border-b border-border-subtle/80 bg-card/90 backdrop-blur">
            <div className="flex min-h-14 items-center justify-between gap-4 px-5 py-3 sm:px-6 lg:px-8">{topbar}</div>
          </header>
        ) : null}
        <main className="flex-1 px-5 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
