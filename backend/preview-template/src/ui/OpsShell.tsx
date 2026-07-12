import * as React from 'react';

import { cn } from '../lib/cn.js';

export interface OpsShellNavItem {
  id: string;
  label: string;
  href?: string;
  icon?: React.ReactNode;
  active?: boolean;
}

export interface OpsShellProps extends React.HTMLAttributes<HTMLDivElement> {
  brandName: string;
  navItems: OpsShellNavItem[];
  topbar?: React.ReactNode;
}

function NavItemContent({ icon, label }: Pick<OpsShellNavItem, 'icon' | 'label'>) {
  return (
    <>
      {icon ? <span className="text-slate-400">{icon}</span> : null}
      <span className="truncate">{label}</span>
    </>
  );
}

export function OpsShell({ brandName, children, className, navItems, topbar, ...props }: OpsShellProps) {
  return (
    <div className={cn('flex min-h-screen bg-slate-100 text-slate-900', className)} {...props}>
      <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white xl:flex xl:flex-col">
        <div className="border-b border-slate-200 px-6 py-7">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">Operations</p>
          <p className="mt-2 text-xl font-semibold tracking-[-0.02em] text-slate-950">{brandName}</p>
        </div>
        <nav className="flex flex-1 flex-col gap-1.5 p-4">
          {navItems.map((item) => {
            const itemClassName = cn(
              'flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition',
              item.active
                ? 'bg-slate-950 text-white shadow-sm shadow-slate-950/15'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            );

            if (item.href) {
              return (
                <a key={item.id} href={item.href} className={itemClassName} aria-current={item.active ? 'page' : undefined}>
                  <NavItemContent icon={item.icon} label={item.label} />
                </a>
              );
            }

            return (
              <div key={item.id} className={itemClassName} aria-current={item.active ? 'page' : undefined}>
                <NavItemContent icon={item.icon} label={item.label} />
              </div>
            );
          })}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/95 backdrop-blur">
          <div className="flex min-h-18 items-center justify-between gap-4 px-5 py-4 sm:px-6 lg:px-8">{topbar}</div>
        </header>
        <main className="flex-1 px-5 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

export default OpsShell;
