import { Badge } from '../core/Badge';
import { cn } from '../lib/cn';

export type ExpenseQueueItem = {
  id: string;
  merchant: string;
  category: string;
  amount: string;
  status: 'Needs review' | 'Categorized' | 'Receipt missing';
  when?: string;
};

export type ExpenseQueueProps = {
  heading?: string;
  items?: ExpenseQueueItem[];
  className?: string;
};

const DEFAULT_ITEMS: ExpenseQueueItem[] = [
  { id: 'e1', merchant: 'Adobe Creative', category: 'Software', amount: '$54.99', status: 'Needs review', when: 'Jul 17' },
  { id: 'e2', merchant: 'Uber', category: 'Travel', amount: '$38.20', status: 'Categorized', when: 'Jul 16' },
  { id: 'e3', merchant: 'WeWork', category: 'Office', amount: '$420.00', status: 'Needs review', when: 'Jul 15' },
  { id: 'e4', merchant: 'AWS', category: 'Software', amount: '$186.40', status: 'Receipt missing', when: 'Jul 14' },
  { id: 'e5', merchant: 'Sweetgreen', category: 'Meals', amount: '$24.10', status: 'Categorized', when: 'Jul 14' },
  { id: 'e6', merchant: 'Staples', category: 'Office', amount: '$67.55', status: 'Needs review', when: 'Jul 13' },
];

const STATUS_TONE: Record<ExpenseQueueItem['status'], string> = {
  'Needs review': 'border-amber-200 bg-amber-50 text-amber-900',
  Categorized: 'border-emerald-200 bg-emerald-50 text-emerald-900',
  'Receipt missing': 'border-rose-200 bg-rose-50 text-rose-900',
};

/** Accounting signature — expense triage cards, not a plain table. */
export function ExpenseQueue({
  heading = 'Expense queue',
  items = DEFAULT_ITEMS,
  className,
}: ExpenseQueueProps) {
  const needsReview = items.filter((i) => i.status !== 'Categorized').length;
  return (
    <section className={cn('space-y-3', className)} aria-label={heading}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-foreground">{heading}</h2>
          <p className="mt-1 text-sm text-muted">
            {needsReview} need attention · tap to categorize
          </p>
        </div>
        <Badge variant="secondary">{items.length} open</Badge>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <article
            key={item.id}
            className="flex items-start justify-between gap-3 rounded-[calc(var(--radius-ui)+0.25rem)] border border-border-subtle bg-card px-3.5 py-3 shadow-[var(--shadow-ui)]"
          >
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">{item.merchant}</p>
              <p className="mt-0.5 text-xs text-muted">
                {item.category}
                {item.when ? ` · ${item.when}` : ''}
              </p>
              <span
                className={cn(
                  'mt-2 inline-flex rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
                  STATUS_TONE[item.status],
                )}
              >
                {item.status}
              </span>
            </div>
            <p className="shrink-0 text-sm font-semibold tabular-nums text-foreground">
              {item.amount}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
