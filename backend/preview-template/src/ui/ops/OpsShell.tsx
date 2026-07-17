import * as React from 'react';
import { useLocation } from 'react-router-dom';

import { AppLink } from '../lib/AppLink';
import { cn } from '../lib/cn';

export interface OpsShellNavItem {
  id: string;
  label: string;
  href?: string;
  active?: boolean;
}

function pathMatches(pathname: string, href?: string): boolean {
  if (!href || !href.startsWith('/')) return false;
  if (pathname === href) return true;
  if (href !== '/' && pathname.startsWith(`${href}/`)) return true;
  return false;
}

export type OpsShellAppearance = 'soft' | 'floor';

export interface OpsShellProps {
  brandName: string;
  navItems: OpsShellNavItem[];
  children: React.ReactNode;
  topbar?: React.ReactNode;
  /** Right context column (activity / profile). Stacks under main below xl. */
  rail?: React.ReactNode;
  /** Soft branded workspace (default) or dark floor control. */
  appearance?: OpsShellAppearance;
  className?: string;
  adjustableSidebar?: boolean;
  defaultSidebarWidth?: number;
  defaultSidebarCollapsed?: boolean;
}

const MIN_WIDTH = 176;
const MAX_WIDTH = 320;
const DEFAULT_WIDTH = 264;

export function OpsShell({
  adjustableSidebar = false,
  appearance = 'soft',
  brandName,
  children,
  className,
  defaultSidebarCollapsed = false,
  defaultSidebarWidth = DEFAULT_WIDTH,
  navItems,
  rail,
  topbar,
}: OpsShellProps) {
  const soft = appearance === 'soft';
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = React.useState(defaultSidebarCollapsed);
  const [width, setWidth] = React.useState(
    Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, defaultSidebarWidth))
  );
  const dragging = React.useRef(false);

  const resolvedNav = React.useMemo(
    () =>
      navItems.map((item) => ({
        ...item,
        active: pathMatches(pathname, item.href) || Boolean(item.active && !item.href),
      })),
    [navItems, pathname]
  );

  React.useEffect(() => {
    if (!adjustableSidebar) return;

    const onMove = (event: MouseEvent) => {
      if (!dragging.current || collapsed) return;
      setWidth(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, event.clientX)));
    };
    const onUp = () => {
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      dragging.current = false;
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [adjustableSidebar, collapsed]);

  const sidebarWidth = collapsed ? 72 : width;

  return (
    <div
      className={cn(
        'relative flex min-h-screen text-foreground',
        soft
          ? 'bg-[color-mix(in_srgb,var(--color-brand)_5%,var(--color-background))]'
          : 'bg-[#1a1814]',
        className
      )}
      data-ops-appearance={appearance}
    >
      {soft ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-90"
          style={{
            background:
              'radial-gradient(70% 50% at 0% 0%, color-mix(in srgb, var(--color-brand) 16%, transparent), transparent 55%), radial-gradient(55% 40% at 100% 0%, color-mix(in srgb, var(--color-accent) 10%, transparent), transparent 50%)',
          }}
        />
      ) : null}

      <aside
        className={cn(
          'relative z-[1] hidden shrink-0 xl:flex xl:flex-col',
          soft
            ? 'border-r border-border-subtle/80 bg-card/90 shadow-[var(--shadow-ui)] backdrop-blur-md'
            : 'bg-[#141210] text-[#f4f0ea]'
        )}
        style={adjustableSidebar ? { width: sidebarWidth } : { width: soft ? '15.5rem' : '16.5rem' }}
      >
        <div className={cn('px-4 py-5', soft ? 'border-b border-border-subtle/70' : 'border-b border-white/10')}>
          <div className="flex items-start justify-between gap-2">
            <div className={cn('min-w-0', collapsed && 'sr-only')}>
              <p
                className={cn(
                  'font-display tracking-[-0.03em]',
                  soft ? 'text-xl font-semibold not-italic text-foreground' : 'text-2xl font-medium italic'
                )}
              >
                {brandName}
              </p>
              <p
                className={cn(
                  'mt-1 text-[11px] font-medium tracking-[0.14em] uppercase',
                  soft ? 'text-muted' : 'text-white/45'
                )}
              >
                {soft ? 'Workspace' : 'Floor control'}
              </p>
            </div>
            {adjustableSidebar ? (
              <button
                type="button"
                onClick={() => setCollapsed((value) => !value)}
                className={cn(
                  'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition',
                  soft
                    ? 'text-muted hover:bg-[color-mix(in_srgb,var(--color-brand)_8%,var(--color-background))] hover:text-foreground'
                    : 'text-white/55 hover:bg-white/8 hover:text-white'
                )}
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                title={collapsed ? 'Expand' : 'Collapse'}
              >
                {collapsed ? '»' : '«'}
              </button>
            ) : null}
          </div>
          {collapsed ? (
            <p
              className={cn('font-display text-xl leading-none', soft ? 'font-semibold' : 'italic')}
              aria-hidden="true"
            >
              {brandName.slice(0, 1)}
            </p>
          ) : null}
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-2.5" aria-label="Operations">
          {resolvedNav.map((item) => {
            const itemClassName = cn(
              'rounded-[calc(var(--radius-ui)+0.35rem)] px-3 py-2.5 text-sm font-medium transition',
              soft
                ? item.active
                  ? 'bg-[color-mix(in_srgb,var(--color-brand)_16%,white)] text-[color:var(--color-brand-dark,var(--color-brand))] shadow-sm'
                  : 'text-muted hover:bg-[color-mix(in_srgb,var(--color-brand)_7%,var(--color-background))] hover:text-foreground'
                : item.active
                  ? 'bg-white/12 text-white'
                  : 'text-white/55 hover:bg-white/6 hover:text-white',
              collapsed && 'flex items-center justify-center px-0 text-center text-xs tracking-wide'
            );
            const label = collapsed ? item.label.slice(0, 1) : item.label;
            if (item.href) {
              return (
                <AppLink
                  key={item.id}
                  href={item.href}
                  className={itemClassName}
                  aria-current={item.active ? 'page' : undefined}
                  title={item.label}
                >
                  {label}
                </AppLink>
              );
            }
            return (
              <div
                key={item.id}
                className={itemClassName}
                aria-current={item.active ? 'page' : undefined}
                title={item.label}
              >
                {label}
              </div>
            );
          })}
        </nav>

        <div
          className={cn(
            'px-4 py-4 text-[11px]',
            soft ? 'border-t border-border-subtle/70 text-muted' : 'border-t border-white/10 text-white/40',
            collapsed && 'text-center'
          )}
        >
          {collapsed ? 'Live' : soft ? 'Live workspace' : 'Live · three studios'}
        </div>

        {adjustableSidebar && !collapsed ? (
          <div
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize sidebar"
            title="Drag to resize"
            onMouseDown={() => {
              dragging.current = true;
              document.body.style.cursor = 'col-resize';
              document.body.style.userSelect = 'none';
            }}
            className={cn(
              'absolute inset-y-0 right-0 z-10 w-1.5 cursor-col-resize bg-transparent',
              soft ? 'hover:bg-brand/25' : 'hover:bg-white/15'
            )}
          />
        ) : null}
      </aside>

      <div className="relative z-[1] flex min-w-0 flex-1 flex-col">
        <div
          className={cn(
            'border-b px-4 py-2 xl:hidden',
            soft ? 'border-border-subtle/80 bg-card/95 backdrop-blur' : 'border-border-subtle bg-card'
          )}
        >
          <nav className="flex gap-2 overflow-x-auto" aria-label="Operations mobile">
            {resolvedNav.map((item) => (
              <AppLink
                key={item.id}
                href={item.href ?? '#'}
                className={cn(
                  'shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold',
                  item.active
                    ? soft
                      ? 'bg-[color-mix(in_srgb,var(--color-brand)_18%,white)] text-[color:var(--color-brand-dark,var(--color-brand))]'
                      : 'bg-foreground text-background'
                    : soft
                      ? 'bg-[color-mix(in_srgb,var(--color-brand)_6%,var(--color-background))] text-muted'
                      : 'bg-background text-muted'
                )}
              >
                {item.label}
              </AppLink>
            ))}
          </nav>
        </div>
        {topbar ? (
          <header
            className={cn(
              'sticky top-0 z-10 border-b backdrop-blur-md',
              soft
                ? 'border-border-subtle/70 bg-card/85'
                : 'border-border-subtle/80 bg-[#f3efe9]/90'
            )}
          >
            <div className="flex min-h-12 items-center justify-between gap-4 px-5 py-2.5 sm:px-6 lg:px-7">
              {topbar}
            </div>
          </header>
        ) : null}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col xl:flex-row">
          <main className="min-w-0 flex-1 px-5 py-5 sm:px-6 lg:px-8">{children}</main>
          {rail ? (
            <aside
              className={cn(
                'w-full shrink-0 px-5 pb-5 sm:px-6 lg:px-7 xl:w-[22rem] xl:border-l xl:py-5',
                soft
                  ? 'border-border-subtle/80 xl:bg-[color-mix(in_srgb,var(--color-brand)_4%,var(--color-background))]'
                  : 'border-border-subtle'
              )}
              data-ops-rail=""
            >
              {rail}
            </aside>
          ) : null}
        </div>
      </div>
    </div>
  );
}
