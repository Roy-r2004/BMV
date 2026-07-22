import { Button } from '../core/Button';
import { cn } from '../lib/cn';

export type ReconLine = {
  id: string;
  label: string;
  amount: string;
  meta?: string;
};

export type ReconSplitProps = {
  heading?: string;
  bankLabel?: string;
  booksLabel?: string;
  bankLines?: ReconLine[];
  bookLines?: ReconLine[];
  matchedHint?: string;
  className?: string;
};

const DEFAULT_BANK: ReconLine[] = [
  { id: 'b1', label: 'ACH · Northwind', amount: '+$2,480.00', meta: 'Chase *4491 · Jul 18' },
  { id: 'b2', label: 'Card · Adobe', amount: '-$54.99', meta: 'Chase *4491 · Jul 17' },
  { id: 'b3', label: 'Wire · Unknown', amount: '+$1,200.00', meta: 'Needs match' },
];

const DEFAULT_BOOKS: ReconLine[] = [
  { id: 'k1', label: 'INV-1042 payment', amount: '+$2,480.00', meta: 'Suggested 98%' },
  { id: 'k2', label: 'Expense · Software', amount: '-$54.99', meta: 'Suggested 94%' },
  { id: 'k3', label: 'Uncategorized deposit', amount: '+$1,200.00', meta: 'Review' },
];

/** Accounting signature — bank feed vs books, match-first. */
export function ReconSplit({
  heading = 'Bank reconciliation',
  bankLabel = 'Bank feed',
  booksLabel = 'Books',
  bankLines = DEFAULT_BANK,
  bookLines = DEFAULT_BOOKS,
  matchedHint = 'AI suggested 2 high-confidence matches · review to clear 12 unmatched',
  className,
}: ReconSplitProps) {
  return (
    <section className={cn('space-y-3', className)} aria-label={heading}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">{heading}</h2>
          <p className="mt-1 text-sm text-muted">{matchedHint}</p>
        </div>
        <Button size="sm">Match selected</Button>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <Pane title={bankLabel} lines={bankLines} accent="bank" />
        <Pane title={booksLabel} lines={bookLines} accent="books" />
      </div>
    </section>
  );
}

function Pane({
  title,
  lines,
  accent,
}: {
  title: string;
  lines: ReconLine[];
  accent: 'bank' | 'books';
}) {
  return (
    <div
      className={cn(
        'rounded-[calc(var(--radius-ui)+0.4rem)] border border-border-subtle bg-card p-3 shadow-[var(--shadow-ui)]',
        accent === 'bank'
          ? 'bg-[color-mix(in_srgb,var(--color-brand)_4%,var(--color-card))]'
          : 'bg-[color-mix(in_srgb,var(--color-accent)_5%,var(--color-card))]',
      )}
    >
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
        {title}
      </p>
      <ul className="space-y-2">
        {lines.map((line) => (
          <li
            key={line.id}
            className="flex items-start justify-between gap-3 rounded-[var(--radius-ui)] border border-border-subtle/80 bg-background/80 px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-foreground">{line.label}</p>
              {line.meta ? <p className="mt-0.5 text-xs text-muted">{line.meta}</p> : null}
            </div>
            <p
              className={cn(
                'shrink-0 text-sm font-semibold tabular-nums',
                line.amount.startsWith('+') ? 'text-emerald-700' : 'text-foreground',
              )}
            >
              {line.amount}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}
