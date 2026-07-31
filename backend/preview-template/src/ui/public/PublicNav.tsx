import * as React from 'react';
import { useLocation } from 'react-router-dom';

import { recipeNavVariant, type NavVariant } from '../../lib/recipe';
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
  /** Recipe-driven layout — defaults from the active design recipe. */
  variant?: NavVariant;
}

function pathMatches(pathname: string, href: string): boolean {
  if (!href.startsWith('/')) return false;
  if (pathname === href) return true;
  if (href !== '/' && pathname.startsWith(`${href}/`)) return true;
  return false;
}

function useActiveHref(items: PublicNavItem[] | undefined) {
  const { pathname } = useLocation();
  const [hashActive, setHashActive] = React.useState('');
  const safeItems = Array.isArray(items) ? items : [];

  React.useEffect(() => {
    const ids = safeItems
      // A nav item without an href would crash the *shell*, taking every page
      // with it — the one crash a preview can least afford.
      .map((item) => {
        const href = String(item?.href ?? '');
        return href.startsWith('#') ? href.slice(1) : '';
      })
      .filter(Boolean);

    const update = () => {
      let current = '';
      for (const id of ids) {
        const el = document.getElementById(id);
        if (!el) continue;
        const top = el.getBoundingClientRect().top;
        if (top <= 120) current = `#${id}`;
      }
      setHashActive(current);
    };

    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('hashchange', update);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('hashchange', update);
    };
  }, [safeItems]);

  return React.useMemo(() => {
    const pathHit = safeItems.find((item) => pathMatches(pathname, item.href));
    if (pathHit) return pathHit.href;
    if (hashActive) return hashActive;
    return safeItems[0]?.href ?? '';
  }, [safeItems, pathname, hashActive]);
}

/** Catalogue public navigation — pages never invent nav chrome. */
export function PublicNav({
  className,
  cta,
  inverted = false,
  items,
  variant: variantProp,
}: PublicNavProps) {
  const variant = variantProp ?? recipeNavVariant();
  const active = useActiveHref(items);
  const [open, setOpen] = React.useState(false);
  const list = Array.isArray(items) ? items : [];

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const linkClass = (isActive: boolean) => {
    if (variant === 'minimal') {
      return cn(
        'rounded-sm px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] transition-colors',
        inverted
          ? isActive
            ? 'text-white'
            : 'text-white/55 hover:text-white'
          : isActive
            ? 'text-foreground'
            : 'text-muted hover:text-foreground'
      );
    }
    if (variant === 'stacked') {
      return cn(
        'rounded-none px-3 py-2 text-sm font-medium tracking-[0.04em] transition-colors',
        inverted
          ? isActive
            ? 'text-white'
            : 'text-white/65 hover:text-white'
          : isActive
            ? 'text-foreground'
            : 'text-muted hover:text-foreground'
      );
    }
    return cn(
      'group relative rounded-md px-3 py-2 text-[13px] font-medium tracking-[-0.01em] transition-colors',
      inverted
        ? isActive
          ? 'text-white'
          : 'text-white/70 hover:text-white'
        : isActive
          ? 'text-foreground'
          : 'text-muted hover:text-foreground'
    );
  };

  // default links need positioning hooks for the underline span
  const withGroup = (isActive: boolean) =>
    variant === 'default' ? cn('group relative', linkClass(isActive)) : linkClass(isActive);

  return (
    <div
      className={cn(
        'relative flex w-full items-center gap-3',
        variant === 'stacked' ? 'justify-center md:justify-end' : 'justify-end',
        className
      )}
      data-nav-variant={variant}
    >
      <nav
        className={cn(
          'hidden items-center md:flex',
          variant === 'minimal' ? 'gap-0.5' : variant === 'stacked' ? 'gap-5' : 'gap-1'
        )}
        aria-label="Primary"
      >
        {list.map((item) => {
          const isActive = active === item.href;
          return (
            <AppLink
              key={item.href}
              href={item.href}
              className={withGroup(isActive)}
              aria-current={isActive ? 'page' : undefined}
            >
              {item.label}
              {variant === 'default' ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    'absolute inset-x-3 -bottom-0.5 h-px origin-left scale-x-0 bg-current transition-transform duration-300 group-hover:scale-x-100',
                    isActive && 'scale-x-100'
                  )}
                />
              ) : null}
              {variant === 'stacked' ? (
                <span
                  aria-hidden="true"
                  className={cn(
                    'mt-1 block h-0.5 w-full origin-left scale-x-0 bg-brand transition-transform duration-300',
                    isActive && 'scale-x-100',
                    inverted && 'bg-white'
                  )}
                />
              ) : null}
            </AppLink>
          );
        })}
      </nav>

      {cta ? (
        variant === 'minimal' ? (
          <AppLink
            href={cta.href}
            className={cn(
              'text-[11px] font-semibold uppercase tracking-[0.16em]',
              inverted ? 'text-white' : 'text-brand'
            )}
          >
            {cta.label}
          </AppLink>
        ) : (
          <Button
            href={cta.href}
            size="sm"
            className={cn(
              'inline-flex',
              inverted &&
                'border-white/35 bg-white text-foreground shadow-none hover:bg-white/92 hover:text-foreground'
            )}
          >
            {cta.label}
          </Button>
        )
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
            {list.map((item) => (
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
