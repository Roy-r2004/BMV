import * as React from 'react';

import { AppLink } from '../lib/AppLink';
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
  /** Allow collapse + drag-resize of the desktop sidebar. */
  adjustableSidebar?: boolean;
  defaultSidebarWidth?: number;
  defaultSidebarCollapsed?: boolean;
}

const MIN_WIDTH = 176;
const MAX_WIDTH = 320;
const DEFAULT_WIDTH = 264;

export function OpsShell({
  adjustableSidebar = false,
  brandName,
  children,
  className,
  defaultSidebarCollapsed = false,
  defaultSidebarWidth = DEFAULT_WIDTH,
  navItems,
  topbar,
}: OpsShellProps) {
  const [collapsed, setCollapsed] = React.useState(defaultSidebarCollapsed);
  const [width, setWidth] = React.useState(
    Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, defaultSidebarWidth))
  );
  const dragging = React.useRef(false);

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
    <div className={cn('flex min-h-screen bg-[#ece8e2] text-foreground', className)}>
      <aside
        className="relative hidden shrink-0 bg-[#1c1916] text-[#f4f0ea] xl:flex xl:flex-col"
        style={adjustableSidebar ? { width: sidebarWidth } : { width: '16.5rem' }}
      >
        <div className="border-b border-white/10 px-4 py-5">
          <div className="flex items-start justify-between gap-2">
            <div className={cn('min-w-0', collapsed && 'sr-only')}>
              <p className="font-display text-2xl font-medium italic tracking-[-0.03em]">{brandName}</p>
              <p className="mt-1 text-[11px] font-medium tracking-[0.16em] text-white/45 uppercase">Floor control</p>
            </div>
            {adjustableSidebar ? (
              <button
                type="button"
                onClick={() => setCollapsed((value) => !value)}
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-white/55 transition hover:bg-white/8 hover:text-white"
                aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
                title={collapsed ? 'Expand' : 'Collapse'}
              >
                {collapsed ? '»' : '«'}
              </button>
            ) : null}
          </div>
          {collapsed ? (
            <p className="font-display text-xl italic leading-none" aria-hidden="true">
              {brandName.slice(0, 1)}
            </p>
          ) : null}
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-2.5" aria-label="Operations">
          {navItems.map((item) => {
            const itemClassName = cn(
              'rounded-lg px-3 py-2.5 text-sm font-medium transition',
              item.active ? 'bg-white/12 text-white' : 'text-white/55 hover:bg-white/6 hover:text-white',
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
              <div key={item.id} className={itemClassName} aria-current={item.active ? 'page' : undefined} title={item.label}>
                {label}
              </div>
            );
          })}
        </nav>

        <div className={cn('border-t border-white/10 px-4 py-4 text-[11px] text-white/40', collapsed && 'text-center')}>
          {collapsed ? 'Live' : 'Live · three studios'}
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
            className="absolute inset-y-0 right-0 z-10 w-1.5 cursor-col-resize bg-transparent hover:bg-white/15"
          />
        ) : null}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-border-subtle bg-card px-4 py-2 xl:hidden">
          <nav className="flex gap-2 overflow-x-auto" aria-label="Operations mobile">
            {navItems.map((item) => (
              <AppLink
                key={item.id}
                href={item.href ?? '#'}
                className={cn(
                  'shrink-0 rounded-md px-3 py-1.5 text-xs font-semibold',
                  item.active ? 'bg-foreground text-background' : 'bg-background text-muted'
                )}
              >
                {item.label}
              </AppLink>
            ))}
          </nav>
        </div>
        {topbar ? (
          <header className="sticky top-0 z-10 border-b border-border-subtle/80 bg-[#f3efe9]/90 backdrop-blur">
            <div className="flex min-h-12 items-center justify-between gap-4 px-5 py-2.5 sm:px-6 lg:px-7">{topbar}</div>
          </header>
        ) : null}
        <main className="flex-1 px-5 py-5 sm:px-6 lg:px-7">{children}</main>
      </div>
    </div>
  );
}
