import { cn } from '../lib/cn';

export type BlotterTapeRow = {
  id: string;
  time: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  qty: string;
  px: string;
  status: string;
  desk?: string;
};

export type BlotterTapeProps = {
  heading?: string;
  rows?: BlotterTapeRow[];
  className?: string;
};

const DEFAULT_ROWS: BlotterTapeRow[] = [
  { id: '1', time: '15:42:11', symbol: 'AAPL', side: 'BUY', qty: '25,000', px: '214.30', status: 'Working', desk: 'Core' },
  { id: '2', time: '15:41:58', symbol: 'MSFT', side: 'SELL', qty: '12,000', px: '448.10', status: 'Partial', desk: 'Core' },
  { id: '3', time: '15:40:22', symbol: 'NVDA', side: 'BUY', qty: '8,000', px: '905.00', status: 'Working', desk: 'Growth' },
  { id: '4', time: '15:38:09', symbol: 'META', side: 'BUY', qty: '4,500', px: '512.40', status: 'Filled', desk: 'Core' },
  { id: '5', time: '15:36:44', symbol: 'TSLA', side: 'SELL', qty: '6,200', px: '248.75', status: 'Working', desk: 'Tactical' },
  { id: '6', time: '15:35:01', symbol: 'AMZN', side: 'BUY', qty: '9,100', px: '186.20', status: 'Filled', desk: 'Core' },
];

/** Trading signature — dense live blotter tape. */
export function BlotterTape({
  heading = 'Working blotter',
  rows = DEFAULT_ROWS,
  className,
}: BlotterTapeProps) {
  return (
    <section
      className={cn(
        'overflow-hidden rounded-[calc(var(--radius-ui)+0.35rem)] border border-white/10',
        'bg-[#07111f] text-slate-100 shadow-[0_24px_48px_-28px_rgba(0,0,0,0.65)]',
        className,
      )}
      aria-label={heading}
    >
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/70 opacity-70" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-400" />
          </span>
          <h2 className="text-sm font-semibold tracking-wide text-white">{heading}</h2>
        </div>
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-cyan-300/80">
          Tape · live
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left text-[12px]">
          <thead className="bg-white/[0.03] font-mono text-[10px] uppercase tracking-[0.14em] text-slate-400">
            <tr>
              <th className="px-3 py-2 font-medium">Time</th>
              <th className="px-3 py-2 font-medium">Sym</th>
              <th className="px-3 py-2 font-medium">Side</th>
              <th className="px-3 py-2 font-medium">Qty</th>
              <th className="px-3 py-2 font-medium">Px</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Desk</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {rows.map((row, i) => (
              <tr
                key={row.id}
                className={cn(
                  'border-t border-white/5 transition-colors hover:bg-white/[0.04]',
                  i === 0 && 'bg-cyan-400/[0.06]',
                )}
              >
                <td className="px-3 py-2 text-slate-400">{row.time}</td>
                <td className="px-3 py-2 font-semibold text-white">{row.symbol}</td>
                <td
                  className={cn(
                    'px-3 py-2 font-bold',
                    row.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400',
                  )}
                >
                  {row.side}
                </td>
                <td className="px-3 py-2 text-slate-200">{row.qty}</td>
                <td className="px-3 py-2 text-slate-200">{row.px}</td>
                <td className="px-3 py-2">
                  <span
                    className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                      row.status === 'Filled' && 'bg-emerald-500/15 text-emerald-300',
                      row.status === 'Partial' && 'bg-amber-500/15 text-amber-200',
                      row.status === 'Working' && 'bg-sky-500/15 text-sky-200',
                    )}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-slate-400">{row.desk || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
