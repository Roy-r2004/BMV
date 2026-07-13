import * as React from 'react';

import { Button } from '../core/Button';
import { AppLink } from '../lib/AppLink';
import { cn } from '../lib/cn';

export interface PublicNavItem {
  label: string;
  href: string;
}

export interface PublicNavCta {
  label: string;
  href: string;
}

export interface PublicNavProps {
  items: PublicNavItem[];
  cta?: PublicNavCta;
  className?: string;
  /** When true, use compact inverted styles for dark photo overlays */
  inverted?: boolean;
}

function useActiveHash(items: PublicNavItem[]) {
  const [active, setActive] = React.useState(items[0]?.href ?? '');

  React.useEffect(() => {
    const ids = items
      .map((item) => (item.href.startsWith('#') ? item.href.slice(1) : ''))
      .filter(Boolean);

    const update = () => {
      let current = items[0]?.href ?? '';
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        if (top <= 120) current = `#${id}`;
      }
      setActive(current);
    };

    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('hashchange', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('hashchange', update);
    };
  }, [items]);

  return active;
}

/** Catalogue public navigation — pages never invent nav chrome. */
export function PublicNav({ className, cta, inverted = false, items }: PublicNavProps) {
  const active = useActiveHash(items);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  return (
    <div className={cn('relative flex w-full items-center justify-end gap-3', className)}>
      <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
        {items.map((item) => {
          const isActive = active === item.href;
          return (
            <AppLink
              key={item.href}
              href={item.href}
              className={cn(
                'group relative rounded-md px-3 py-2 text-[13px] font-medium tracking-[-0.01em] transition-colors',
                inverted
                  ? isActive
                    ? 'text-white'
                    : 'text-white/70 hover:text-white'
                  : isActive
                    ? 'text-foreground'
                    : 'text-muted hover:text-foreground'
              )}
              aria-current={isActive ? 'page' : undefined}
            >
              {item.label}
              <span
                aria-hidden="true"
                className={cn(
                  'absolute inset-x-3 -bottom-0.5 h-px origin-left scale-x-0 bg-current transition-transform duration-300 group-hover:scale-x-100',
                  isActive && 'scale-x-100'
                )}
              />
            </AppLink>
          );
        })}
      </nav>

      {cta ? (
        <Button href={cta.href} size="sm" className="hidden sm:inline-flex">
          {cta.label}
        </Button>
      ) : null}

      <button
        type="button"
        className={cn(
          'inline-flex h-9 w-9 items-center justify-center rounded-md border md:hidden',
          inverted ? 'border-white/25 text-white' : 'border-border-subtle text-foreground'
        )}
        aria-expanded={open}
        aria-controls="public-mobile-nav"
        aria-label={open ? 'Close menu' : 'Open menu'}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="sr-only">{open ? 'Close' : 'Menu'}</span>
        <span aria-hidden="true" className="flex w-4 flex-col gap-1">
          <span className={cn('h-px w-full bg-current transition', open && 'translate-y-[5px] rotate-45')} />
          <span className={cn('h-px w-full bg-current transition', open && 'opacity-0')} />
          <span className={cn('h-px w-full bg-current transition', open && '-translate-y-[5px] -rotate-45')} />
        </span>
      </button>

      {open ? (
        <div
          id="public-mobile-nav"
          className="absolute right-0 top-[calc(100%+0.75rem)] z-50 w-[min(18rem,calc(100vw-2rem))] overflow-hidden rounded-[var(--radius-ui)] border border-border-subtle bg-card shadow-[var(--shadow-ui)] md:hidden"
        >
          <nav className="flex flex-col p-2" aria-label="Mobile">
            {items.map((item) => (
              <AppLink
                key={item.href}
                href={item.href}
                className={cn(
                  'rounded-md px-3 py-3 text-sm font-medium',
                  active === item.href ? 'bg-brand/8 text-brand' : 'text-foreground hover:bg-background'
                )}
                onClick={() => setOpen(false)}
              >
                {item.label}
              </AppLink>
            ))}
            {cta ? (
              <div className="border-t border-border-subtle p-2 pt-3">
                <Button href={cta.href} size="sm" className="w-full" onClick={() => setOpen(false)}>
                  {cta.label}
                </Button>
              </div>
            ) : null}
          </nav>
        </div>
      ) : null}
    </div>
  );
}
