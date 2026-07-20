import * as React from 'react';

import {
  recipeBrandPlacement,
  recipeNavVariant,
  recipeShellChrome,
  type BrandPlacement,
  type ShellChrome,
} from '../../lib/recipe';
import { cn } from '../lib/cn';
import { PublicNav, type PublicNavCta, type PublicNavItem, type PublicNavProps } from './PublicNav';

export interface PublicShellProps {
  brandName: string;
  children: React.ReactNode;
  /** PublicNav element, or a bare nav-item array (AI often forgets the wrapper). */
  nav?: React.ReactNode | PublicNavItem[];
  /** Optional CTA when `nav` is passed as a bare item array. */
  cta?: PublicNavCta;
  footer?: React.ReactNode;
  className?: string;
  chrome?: ShellChrome;
  /** Brand lockup placement — defaults from the active design recipe. */
  brandPlacement?: BrandPlacement;
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
  brandPlacement: brandPlacementProp,
  children,
  className,
  chrome: chromeProp,
  cta,
  footer,
  mobileDock,
  nav,
}: PublicShellProps) {
  const chrome = chromeProp ?? recipeShellChrome();
  const brandPlacement = brandPlacementProp ?? recipeBrandPlacement();
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

  const baseNav = isNavItemList(nav) ? (
    <PublicNav items={nav} cta={cta} variant={recipeNavVariant()} />
  ) : (
    nav
  );

  const resolvedNav =
    React.isValidElement(baseNav)
      ? React.cloneElement(baseNav as React.ReactElement<PublicNavProps>, {
          inverted:
            (baseNav.props as PublicNavProps).inverted ?? overHero,
          variant: (baseNav.props as PublicNavProps).variant ?? recipeNavVariant(),
        })
      : baseNav;

  const centered = brandPlacement === 'center';

  return (
    <div
      className={cn('relative min-h-screen bg-background text-foreground', className)}
      data-public-chrome={chrome}
      data-brand-placement={brandPlacement}
    >
      {!immersive ? (
        <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
          <div className="ui-mesh opacity-[0.28]" />
        </div>
      ) : null}
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
              ? 'border-b border-border-subtle/80 bg-background/85 shadow-[0_10px_30px_-24px_rgb(18_22_26_/0.45)] backdrop-blur-xl'
              : immersive
                ? 'border-b border-transparent bg-gradient-to-b from-black/55 via-black/20 to-transparent'
                : centered
                  ? 'border-b border-border-subtle bg-background/90 backdrop-blur-md'
                  : 'border-b border-border-subtle/70 bg-background/90 backdrop-blur-xl'
          )}
        >
          <div
            className={cn(
              'mx-auto w-full max-w-[92rem] px-6 py-3 lg:px-12',
              centered
                ? 'flex min-h-[4.25rem] flex-col items-center justify-center gap-2 md:min-h-[4.5rem]'
                : 'flex min-h-[3.75rem] items-center justify-between gap-6'
            )}
          >
            <a
              href="#top"
              className={cn(
                'font-display leading-none tracking-[-0.03em] transition-colors hover:opacity-80',
                centered
                  ? 'text-[clamp(1.45rem,2.8vw,1.85rem)]'
                  : 'text-[1.35rem] font-medium',
                overHero ? 'text-white' : 'text-foreground'
              )}
            >
              {brandName}
            </a>
            <div
              className={cn(
                'flex min-w-0 items-center',
                centered ? 'w-full justify-center' : 'flex-1 justify-end'
              )}
            >
              {resolvedNav}
            </div>
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
