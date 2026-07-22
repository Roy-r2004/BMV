import { cn } from '../lib/cn';

export type CashPulseItem = {
  id: string;
  label: string;
  value: string;
  tone?: 'good' | 'warn' | 'neutral';
};

export type CashPulseBarProps = {
  cashLabel?: string;
  cashValue?: string;
  cashHint?: string;
  items?: CashPulseItem[];
  className?: string;
};

const TONE: Record<NonNullable<CashPulseItem['tone']>, string> = {
  good: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-800',
  warn: 'border-amber-500/30 bg-amber-500/10 text-amber-900',
  neutral: 'border-border-subtle bg-card text-foreground',
};

/** Accounting signature — cash command strip above the books home. */
export function CashPulseBar({
  cashLabel = 'Cash on hand',
  cashValue = '$48,220',
  cashHint = 'Updated just now · operating account',
  items = [
    { id: 'ar', label: 'Collectible AR', value: '$18.4k', tone: 'good' },
    { id: 'due', label: 'Due this week', value: '7 invoices', tone: 'warn' },
    { id: 'bank', label: 'Unmatched bank', value: '12 lines', tone: 'warn' },
    { id: 'burn', label: 'Burn MTD', value: '$12.8k', tone: 'neutral' },
  ],
  className,
}: CashPulseBarProps) {
  return (
    <section
      className={cn(
        'relative overflow-hidden rounded-[calc(var(--radius-ui)+0.55rem)] border border-border-subtle',
        'bg-[linear-gradient(135deg,color-mix(in_srgb,var(--color-brand)_14%,#fff)_0%,#fff_48%,color-mix(in_srgb,var(--color-accent)_10%,#f8fafc)_100%)]',
        'px-5 py-5 shadow-[var(--shadow-ui)] sm:px-6 sm:py-6',
        className,
      )}
      aria-label="Cash pulse"
    >
      <div
        className="pointer-events-none absolute -right-8 -top-10 h-40 w-40 rounded-full opacity-40"
        style={{
          background:
            'radial-gradient(circle, color-mix(in srgb, var(--color-brand) 35%, transparent), transparent 70%)',
        }}
        aria-hidden="true"
      />
      <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-muted">
            {cashLabel}
          </p>
          <p className="mt-1 font-display text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
            {cashValue}
          </p>
          <p className="mt-2 text-sm text-muted">{cashHint}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:max-w-2xl">
          {items.map((item) => (
            <div
              key={item.id}
              className={cn(
                'rounded-[var(--radius-ui)] border px-3 py-2.5',
                TONE[item.tone || 'neutral'],
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] opacity-80">
                {item.label}
              </p>
              <p className="mt-1 text-sm font-semibold tabular-nums">{item.value}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
