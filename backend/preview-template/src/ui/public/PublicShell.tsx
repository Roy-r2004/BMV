import * as React from 'react';

import { cn } from '../lib/cn';

export interface PublicShellProps {
  brandName: string;
  children: React.ReactNode;
  nav?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  chrome?: 'solid' | 'immersive';
  /** Sticky thumb-zone CTA for small screens (e.g. Book). */
  mobileDock?: React.ReactNode;
}

export function PublicShell({
  brandName,
  children,
  className,
  chrome = 'solid',
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

  return (
    <div className={cn('relative min-h-screen bg-background text-foreground', className)}>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-md focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow-[var(--shadow-ui)]"
      >
        Skip to content
      </a>

      <div className="relative z-10 flex min-h-screen flex-col">
        <header
          className={cn(
            'z-40 transition-[background-color,border-color,box-shadow,backdrop-filter] duration-300',
            immersive || scrolled ? 'fixed inset-x-0 top-0' : 'sticky top-0',
            scrolled
              ? 'border-b border-border-subtle/80 bg-background/80 shadow-[0_10px_30px_-24px_rgb(18_22_26_/0.45)] backdrop-blur-xl'
              : immersive
                ? 'border-b border-transparent bg-transparent'
                : 'border-b border-border-subtle/60 bg-background/90 backdrop-blur-xl'
          )}
        >
          <div className="mx-auto flex min-h-[4.25rem] w-full max-w-[92rem] items-center justify-between gap-6 px-6 py-2.5 lg:px-12">
            <a
              href="#top"
              className="font-display text-[1.7rem] italic leading-none tracking-[-0.03em] text-foreground transition-opacity hover:opacity-80"
            >
              {brandName}
            </a>
            <div className="flex min-w-0 flex-1 items-center justify-end">{nav}</div>
          </div>
          <div
            aria-hidden="true"
            className="h-px w-full origin-left bg-brand transition-transform duration-150 ease-out"
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
