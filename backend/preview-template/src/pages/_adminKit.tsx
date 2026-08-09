/**
 * DESIGN DRAFT — shared shell + primitives for the owner-facing admin pages,
 * v2 (matches the reference mockups: logo lockup, date/location/search
 * topbar, sparklines/gauges/donuts on stat cards). Sibling to `_kit.tsx`
 * (the public site). Restored to the dark-editorial register per the
 * approved reference — richer surfaces than draft-2's flat dark, closer to
 * the public site's depth (gradients, glow borders).
 */
import { useEffect, useRef, useState, type ReactNode, type CSSProperties } from 'react';
import {
  LayoutGrid, CalendarDays, Users, MessageSquare, Settings, Bell, Sparkles,
  ChevronDown, MapPin, Search, Command,
} from 'lucide-react';
import { FONT_LINK, IMG, GlobalStyles } from './_kit';

export { FONT_LINK, IMG, GlobalStyles };

export const ADMIN_THEME_VARS = {
  '--font-display': '"Fraunces", Georgia, serif',
  '--font-sans': '"Inter", "Segoe UI", system-ui, sans-serif',
  '--color-brand': '#c9a464',
  '--color-brand-dark': '#b08d4f',
  '--ease-out': 'cubic-bezier(0.22, 0.61, 0.36, 1)',
} as CSSProperties;

export const ADMIN_NAV = [
  { icon: LayoutGrid, label: 'Overview', href: '/owner' },
  { icon: CalendarDays, label: 'Bookings', href: '/owner/bookings' },
  { icon: Users, label: 'Clients', href: '/owner/clients' },
  { icon: Sparkles, label: 'AI Front Desk', href: '/owner/ai' },
  { icon: Users, label: 'Team', href: '/owner/settings?tab=team' },
  { icon: LayoutGrid, label: 'Reports', href: '/owner/reports' },
  { icon: Settings, label: 'Settings', href: '/owner/settings' },
];

function LogoLockup() {
  return (
    <a href="/" className="block">
      <div className="relative flex h-16 w-16 items-center justify-center">
        <Sparkles className="absolute right-0 top-0 h-3.5 w-3.5 text-[var(--color-brand)]" />
        <span className="font-display text-3xl italic text-[var(--color-brand)]">MN</span>
      </div>
      <p className="mt-1 font-display text-lg italic tracking-wide">Maison Noor</p>
      <p className="text-[10px] font-semibold uppercase tracking-[0.32em] text-white/35">Beirut</p>
    </a>
  );
}

function TopBar() {
  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] px-8 py-4">
      <div className="min-w-0">
        <p className="font-display text-2xl font-light">Good evening, Noor.</p>
        <p className="text-sm text-white/40">Tuesday, July 22, 2025</p>
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        <button className="flex items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.03] px-3.5 py-2 text-xs text-white/70 transition hover:border-white/25">
          <CalendarDays className="h-3.5 w-3.5" /> Jul 22 – Jul 28 <ChevronDown className="h-3 w-3 text-white/40" />
        </button>
        <button className="hidden items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.03] px-3.5 py-2 text-xs text-white/70 transition hover:border-white/25 sm:flex">
          <MapPin className="h-3.5 w-3.5" /> Gemmayze, Beirut <ChevronDown className="h-3 w-3 text-white/40" />
        </button>
        <div className="hidden items-center gap-2 rounded-xl border border-white/[0.1] bg-white/[0.03] px-3.5 py-2 text-xs text-white/40 md:flex">
          <Search className="h-3.5 w-3.5" />
          <span>Search clients, bookings…</span>
          <span className="ml-3 flex items-center gap-0.5 rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] text-white/30">
            <Command className="h-2.5 w-2.5" />K
          </span>
        </div>
        <button className="relative rounded-xl border border-white/[0.1] bg-white/[0.03] p-2.5 text-white/60 transition hover:border-white/25">
          <Bell className="h-4 w-4" strokeWidth={1.6} />
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[var(--color-brand)]" />
        </button>
        <a
          href="/owner/bookings"
          className="rounded-xl bg-[var(--color-brand)] px-4 py-2.5 text-xs font-semibold text-black transition hover:brightness-110"
        >
          + New Booking
        </a>
      </div>
    </header>
  );
}

export function AdminShell({
  active, pageTitle, pageSubtitle, children,
}: { active: string; pageTitle?: string; pageSubtitle?: string; children: ReactNode }) {
  return (
    <div
      style={ADMIN_THEME_VARS}
      className="flex min-h-screen bg-[#0c0b0a] font-sans text-white"
    >
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />

      <aside className="hidden w-64 shrink-0 flex-col border-r border-white/[0.08] px-6 py-7 md:flex">
        <LogoLockup />
        <nav className="mt-8 space-y-1">
          {ADMIN_NAV.map((n) => (
            <a
              key={n.href}
              href={n.href}
              className={
                'flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm transition ' +
                (active === n.href
                  ? 'bg-[var(--color-brand)]/[0.12] font-medium text-[var(--color-brand)]'
                  : 'text-white/50 hover:bg-white/[0.04] hover:text-white')
              }
            >
              <n.icon className="h-4 w-4" strokeWidth={1.6} />
              {n.label}
            </a>
          ))}
        </nav>
        <a
          href="/owner/bookings"
          className="mt-6 rounded-xl bg-[var(--color-brand)] py-2.5 text-center text-sm font-semibold text-black transition hover:brightness-110"
        >
          + New Booking
        </a>
        <div className="mt-auto space-y-3 border-t border-white/[0.08] pt-5">
          <div className="flex items-center gap-3">
            <span className="h-9 w-9 overflow-hidden rounded-full">
              <img src={IMG.team[0]} alt="" className="h-full w-full object-cover" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">Noor Badawi</p>
              <p className="text-xs text-white/40">Owner</p>
            </div>
          </div>
          <p className="text-xs leading-relaxed text-white/30">Maison Noor – Gemmayze<br />Beirut, Lebanon</p>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <TopBar />
        <div className="px-8 py-7">
          {pageTitle && (
            <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="font-display text-3xl font-light">{pageTitle}</p>
                {pageSubtitle && <p className="mt-1 text-sm text-white/45">{pageSubtitle}</p>}
              </div>
            </div>
          )}
          {children}
        </div>
      </div>
    </div>
  );
}

export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return (
    <div className={'rounded-2xl border border-white/[0.08] bg-white/[0.015] ' + className}>
      {children}
    </div>
  );
}

export function Badge({ tone = 'neutral', children }: { tone?: 'neutral' | 'brand' | 'good' | 'risk' | 'warn'; children: ReactNode }) {
  const tones: Record<string, string> = {
    neutral: 'border-white/15 text-white/55',
    brand: 'border-[var(--color-brand)]/35 bg-[var(--color-brand)]/10 text-[var(--color-brand)]',
    good: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-400',
    risk: 'border-rose-400/30 bg-rose-400/10 text-rose-400',
    warn: 'border-amber-400/30 bg-amber-400/10 text-amber-400',
  };
  return (
    <span className={'inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium ' + tones[tone]}>
      {children}
    </span>
  );
}

export function Toggle({ on, onChange, label, note }: { on: boolean; onChange: (v: boolean) => void; label: string; note?: string }) {
  return (
    <button onClick={() => onChange(!on)} className="flex w-full items-center justify-between gap-4 py-3 text-left">
      <div>
        <p className="text-sm font-medium text-white/90">{label}</p>
        {note && <p className="mt-0.5 text-xs text-white/40">{note}</p>}
      </div>
      <span className={'relative h-6 w-11 shrink-0 rounded-full transition ' + (on ? 'bg-[var(--color-brand)]' : 'bg-white/15')}>
        <span className={'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ' + (on ? 'translate-x-[22px]' : 'translate-x-0.5')} />
      </span>
    </button>
  );
}

/** Tiny inline trend line for stat cards — no axes, just a felt shape. */
export function Sparkline({ data, color = '#c9a464' }: { data: number[]; color?: string }) {
  const w = 88, h = 28;
  const max = Math.max(...data), min = Math.min(...data);
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * h;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** A clean ring gauge via conic-gradient — matches the mockup's occupancy rings. */
export function RingGauge({ pct, size = 56, color = '#c9a464' }: { pct: number; size?: number; color?: string }) {
  return (
    <div
      className="relative rounded-full"
      style={{
        width: size, height: size,
        background: `conic-gradient(${color} ${pct * 3.6}deg, rgba(255,255,255,0.08) 0deg)`,
      }}
    >
      <div className="absolute inset-[3px] flex items-center justify-center rounded-full bg-[#0c0b0a] text-xs font-semibold">
        {pct}%
      </div>
    </div>
  );
}

export function useCountUp(to: number, duration = 1100) {
  const [n, setN] = useState(0);
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') { setN(to); return; }
    const io = new IntersectionObserver((entries) => {
      if (!entries.some((e) => e.isIntersecting)) return;
      io.disconnect();
      const start = performance.now();
      let raf = 0;
      const tick = (now: number) => {
        const p = Math.min(1, (now - start) / duration);
        setN(Math.round(to * (1 - Math.pow(1 - p, 3))));
        if (p < 1) raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [to, duration]);
  return { ref, n };
}

export function StatCard({
  label, value, prefix = '', suffix = '', delta, deltaGood = true, sparkline, gauge,
}: {
  label: string; value: number; prefix?: string; suffix?: string;
  delta?: string; deltaGood?: boolean; sparkline?: number[]; gauge?: number;
}) {
  const { ref, n } = useCountUp(value);
  return (
    <Card className="p-5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/40">{label}</p>
      <div className="mt-3 flex items-end justify-between gap-3">
        <div>
          <p className="font-display text-3xl font-light">
            <span ref={ref}>{prefix}{n.toLocaleString()}{suffix}</span>
          </p>
          {delta && (
            <p className={'mt-1.5 text-xs ' + (deltaGood ? 'text-emerald-400' : 'text-rose-400')}>
              {deltaGood ? '↑' : '↓'} {delta}
            </p>
          )}
        </div>
        {sparkline && <Sparkline data={sparkline} />}
        {gauge !== undefined && <RingGauge pct={gauge} />}
      </div>
    </Card>
  );
}
