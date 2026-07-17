import * as React from 'react';

import { cn } from '../lib/cn';
import { PublicNav, type PublicNavCta, type PublicNavItem } from './PublicNav';

export interface PublicShellProps {
  brandName: string;
  children: React.ReactNode;
  /** PublicNav element, or a bare nav-item array (AI often forgets the wrapper). */
  nav?: React.ReactNode | PublicNavItem[];
  /** Optional CTA when `nav` is passed as a bare item array. */
  cta?: PublicNavCta;
  footer?: React.ReactNode;
  className?: string;
  chrome?: 'solid' | 'immersive';
  /** Sticky thumb-zone CTA for small screens (e.g. Book). */
  mobileDock?: React.ReactNode;
}

function isNavItemList(value: unknown): value is PublicNavItem[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (item) =>
        typeof item === 'object' &&
        item !== null &&
        !React.isValidElement(item) &&
        typeof (item as PublicNavItem).label === 'string' &&
        typeof (item as PublicNavItem).href === 'string'
    )
  );
}

export function PublicShell({
  brandName,
  children,
  className,
  chrome = 'solid',
  cta,
  footer,
  mobileDock,
  nav,
}: PublicShellProps) {
  const immersive = chrome === 'immersive';
  const [scrolled, setScrolled] = React.useState(false);
  const [progress, setProgress] = React.useState(0);

  React.useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY;
      setScrolled(y > 24);
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, y / max) : 0);
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const overHero = immersive && !scrolled;

  const baseNav = isNavItemList(nav) ? <PublicNav items={nav} cta={cta} /> : nav;

  const resolvedNav =
    React.isValidElement(baseNav) && immersive
      ? React.cloneElement(baseNav as React.ReactElement<{ inverted?: boolean }>, {
          inverted: overHero,
        })
      : baseNav;

  return (
    <div
      className={cn('relative min-h-screen bg-background text-foreground', className)}
      data-public-chrome={chrome}
    >
      <div
        aria-hidden="true"
        className="pointer-events-none fixed inset-0 z-0 overflow-hidden"
      >
        <div className="ui-mesh opacity-[0.45]" />
        <div className="absolute -left-32 top-[18%] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,var(--glow-atmosphere),transparent_68%)]" />
        <div className="absolute -right-24 bottom-[12%] h-[22rem] w-[22rem] rounded-full bg-[radial-gradient(circle,color-mix(in_srgb,var(--color-brand)_12%,transparent),transparent_70%)]" />
      </div>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow-[var(--shadow-ui)]"
      >
        Skip to content
      </a>

      <div className="relative z-10 flex min-h-screen flex-col">
        <header
          className={cn(
            'z-40 transition-[background-color,border-color,box-shadow,backdrop-filter,color] duration-300',
            immersive || scrolled ? 'fixed inset-x-0 top-0' : 'sticky top-0',
            scrolled
              ? 'border-b border-border-subtle/80 bg-background/80 shadow-[0_10px_30px_-24px_rgb(18_22_26_/0.45)] backdrop-blur-xl'
              : immersive
                ? 'border-b border-transparent bg-gradient-to-b from-black/45 to-transparent'
                : 'border-b border-border-subtle/60 bg-background/90 backdrop-blur-xl'
          )}
        >
          <div className="mx-auto flex min-h-[4.5rem] w-full max-w-[92rem] items-center justify-between gap-6 px-6 py-2.5 lg:px-12">
            <a
              href="#top"
              className={cn(
                'font-display text-[1.85rem] leading-none tracking-[-0.03em] transition-colors hover:opacity-80',
                overHero ? 'text-white' : 'text-foreground'
              )}
            >
              {brandName}
            </a>
            <div className="flex min-w-0 flex-1 items-center justify-end">{resolvedNav}</div>
          </div>
          <div
            aria-hidden="true"
            className={cn(
              'h-px w-full origin-left transition-transform duration-150 ease-out',
              overHero ? 'bg-white/70' : 'bg-brand'
            )}
            style={{ transform: `scaleX(${progress})` }}
          />
        </header>

        <main id="main" className={cn('relative flex-1', mobileDock && 'pb-24 md:pb-0')}>
          <div id="top" className="h-0 scroll-mt-0" />
          {children}
        </main>
        {footer}

        {mobileDock ? (
          <div className="fixed inset-x-0 bottom-0 z-50 border-t border-border-subtle/80 bg-background/90 px-4 py-3 backdrop-blur-xl md:hidden">
            <div className="mx-auto max-w-lg">{mobileDock}</div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
