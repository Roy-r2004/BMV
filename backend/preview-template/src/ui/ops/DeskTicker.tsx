import { cn } from '../lib/cn';

export type DeskTickerItem = {
  id: string;
  label: string;
  value: string;
  delta?: string;
};

export type DeskTickerProps = {
  items?: DeskTickerItem[];
  className?: string;
};

const DEFAULT_ITEMS: DeskTickerItem[] = [
  { id: '1', label: 'Day P&L', value: '+$1.24M', delta: '+0.41%' },
  { id: '2', label: 'Gross', value: '62%', delta: 'lim 75%' },
  { id: '3', label: 'Net', value: '38%', delta: 'lim 45%' },
  { id: '4', label: 'Working', value: '18', delta: '+3' },
  { id: '5', label: 'Fills', value: '41', delta: '9 names' },
  { id: '6', label: 'Breach', value: '1 soft', delta: 'Tech sleeve' },
];

/** Trading signature — horizontal desk ticker under the header. */
export function DeskTicker({ items = DEFAULT_ITEMS, className }: DeskTickerProps) {
  return (
    <div
      className={cn(
        'overflow-hidden rounded-[var(--radius-ui)] border border-white/10',
        'bg-[#050d18] shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]',
        className,
      )}
      aria-label="Desk ticker"
    >
      <div className="desk-ticker-track flex gap-0 whitespace-nowrap py-2.5">
        {[...items, ...items].map((item, idx) => {
          const up = item.delta?.startsWith('+');
          const down = item.delta?.startsWith('-') || item.value.startsWith('-');
          return (
            <div
              key={`${item.id}-${idx}`}
              className="mx-4 inline-flex items-baseline gap-2 border-r border-white/10 pr-4 last:border-r-0"
            >
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
                {item.label}
              </span>
              <span className="font-mono text-sm font-semibold tabular-nums text-white">
                {item.value}
              </span>
              {item.delta ? (
                <span
                  className={cn(
                    'font-mono text-[11px] tabular-nums',
                    up && 'text-emerald-400',
                    down && !up && 'text-rose-400',
                    !up && !down && 'text-cyan-300/80',
                  )}
                >
                  {item.delta}
                </span>
              ) : null}
            </div>
          );
        })}
      </div>
      <style>{`
        @keyframes desk-ticker {
          0% { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .desk-ticker-track {
          animation: desk-ticker 28s linear infinite;
          width: max-content;
        }
        @media (prefers-reduced-motion: reduce) {
          .desk-ticker-track { animation: none; }
        }
      `}</style>
    </div>
  );
}
