import * as React from 'react';

import { cn } from '../lib/cn.js';

type NavItem = {
  label?: React.ReactNode;
  path?: string;
  href?: string;
  to?: string;
};

export interface PublicShellProps extends React.HTMLAttributes<HTMLDivElement> {
  brandName: string;
  /** React node OR AI-friendly `[{ path, label }]` list */
  nav?: React.ReactNode | NavItem[];
  footer?: React.ReactNode;
  mainClassName?: string;
  footerClassName?: string;
  backgroundClassName?: string;
  /** AI often invents this — accepted and rendered as a header CTA when present */
  cta?: NavItem | React.ReactNode;
}

function renderNav(nav: PublicShellProps['nav']) {
  if (nav == null) return null;
  if (Array.isArray(nav)) {
    return (
      <nav className="flex flex-wrap items-center justify-end gap-4 text-sm text-white/75">
        {nav.map((item, i) => {
          const href = item.href || item.to || item.path || '#';
          return (
            <a key={`${href}-${i}`} href={href} className="transition hover:text-white">
              {item.label ?? href}
            </a>
          );
        })}
      </nav>
    );
  }
  if (React.isValidElement(nav) || typeof nav === 'string' || typeof nav === 'number') {
    return nav;
  }
  return null;
}

function renderCta(cta: PublicShellProps['cta']) {
  if (cta == null) return null;
  if (React.isValidElement(cta) || typeof cta === 'string' || typeof cta === 'number') {
    return cta;
  }
  if (typeof cta === 'object' && cta !== null) {
    const item = cta as NavItem;
    const href = item.href || item.to || item.path || '#';
    return (
      <a
        href={href}
        className="inline-flex h-9 items-center rounded-xl bg-brand px-3.5 text-sm font-semibold text-white"
      >
        {item.label ?? 'Get started'}
      </a>
    );
  }
  return null;
}

export function PublicShell({
  backgroundClassName,
  brandName,
  children,
  className,
  cta,
  footer,
  footerClassName,
  mainClassName,
  nav,
  ...props
}: PublicShellProps) {
  const navNode = renderNav(nav);
  const ctaNode = renderCta(cta);

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
            <div className="flex min-w-0 flex-1 items-center justify-end gap-4">
              {navNode}
              {ctaNode}
            </div>
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
