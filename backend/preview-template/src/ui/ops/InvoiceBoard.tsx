import { Badge } from '../core/Badge';
import { cn } from '../lib/cn';

export type InvoiceBoardCard = {
  id: string;
  number: string;
  customer: string;
  amount: string;
  due?: string;
};

export type InvoiceBoardColumn = {
  id: string;
  title: string;
  tone?: 'draft' | 'sent' | 'overdue' | 'paid';
  cards: InvoiceBoardCard[];
};

export type InvoiceBoardProps = {
  heading?: string;
  columns?: InvoiceBoardColumn[];
  className?: string;
};

const COL_TONE: Record<NonNullable<InvoiceBoardColumn['tone']>, string> = {
  draft: 'border-slate-200 bg-slate-50/80',
  sent: 'border-sky-200 bg-sky-50/70',
  overdue: 'border-rose-200 bg-rose-50/80',
  paid: 'border-emerald-200 bg-emerald-50/70',
};

const DEFAULT_COLUMNS: InvoiceBoardColumn[] = [
  {
    id: 'draft',
    title: 'Draft',
    tone: 'draft',
    cards: [
      { id: 'd1', number: 'INV-1040', customer: 'Harbor Dental', amount: '$1,120', due: '—' },
      { id: 'd2', number: 'INV-1038', customer: 'Peak Studio', amount: '$640', due: '—' },
    ],
  },
  {
    id: 'sent',
    title: 'Sent',
    tone: 'sent',
    cards: [
      { id: 's1', number: 'INV-1042', customer: 'Northwind Co', amount: '$2,480', due: 'Jul 28' },
      { id: 's2', number: 'INV-1037', customer: 'Lumen Labs', amount: '$990', due: 'Jul 30' },
    ],
  },
  {
    id: 'overdue',
    title: 'Overdue',
    tone: 'overdue',
    cards: [
      { id: 'o1', number: 'INV-1041', customer: 'Bright Labs', amount: '$890', due: 'Jul 12' },
    ],
  },
  {
    id: 'paid',
    title: 'Paid',
    tone: 'paid',
    cards: [
      { id: 'p1', number: 'INV-1039', customer: 'Peak Studio', amount: '$1,450', due: 'Jul 08' },
    ],
  },
];

/** Accounting signature — invoice pipeline as a status board, not a plain table. */
export function InvoiceBoard({
  heading = 'Invoice pipeline',
  columns = DEFAULT_COLUMNS,
  className,
}: InvoiceBoardProps) {
  return (
    <section className={cn('space-y-3', className)} aria-label={heading}>
      <div className="flex items-end justify-between gap-3">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">{heading}</h2>
        <p className="text-xs text-muted">Drag mentally — status is the product</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {columns.map((col) => (
          <div
            key={col.id}
            className={cn(
              'rounded-[calc(var(--radius-ui)+0.35rem)] border p-3',
              COL_TONE[col.tone || 'draft'],
            )}
          >
            <div className="mb-3 flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-foreground/80">
                {col.title}
              </p>
              <Badge variant="secondary">{col.cards.length}</Badge>
            </div>
            <div className="space-y-2">
              {col.cards.map((card) => (
                <article
                  key={card.id}
                  className="rounded-[var(--radius-ui)] border border-white/70 bg-white/90 px-3 py-2.5 shadow-sm"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-foreground">{card.number}</p>
                      <p className="text-xs text-muted">{card.customer}</p>
                    </div>
                    <p className="text-sm font-semibold tabular-nums text-foreground">
                      {card.amount}
                    </p>
                  </div>
                  {card.due ? (
                    <p className="mt-2 text-[11px] font-medium text-muted">Due {card.due}</p>
                  ) : null}
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
