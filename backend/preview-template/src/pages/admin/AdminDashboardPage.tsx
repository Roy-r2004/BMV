import { brand, stats } from '../../data/mock';

interface StatCard {
  label: string;
  value: string;
  change?: string;
}

/**
 * `mock.ts` is generated, so `stats` is whatever shape the business needed —
 * request 45 shipped `{ chartData: [{ label, value }] }` and this page's
 * `stats.map` became a TS2339 on a page nothing even routed. Read it
 * defensively: a stock page must never fail the build over a data shape it
 * does not own.
 */
function statCards(source: unknown): StatCard[] {
  const rows = Array.isArray(source)
    ? source
    : ((source as { chartData?: unknown[] } | null)?.chartData ?? []);
  return (rows as Array<Record<string, unknown>>)
    .map((row) => ({
      label: String(row?.label ?? row?.name ?? row?.title ?? ''),
      value: String(row?.value ?? row?.count ?? row?.amount ?? ''),
      change: row?.change == null ? undefined : String(row.change),
    }))
    .filter((card) => card.label || card.value);
}

export default function AdminDashboardPage() {
  const cards = statCards(stats);
  // This subtitle used to name the generic placeholder business instead of the
  // real one — template voice on every owner hub, and a leak-check hit once the
  // harness folded case. Bind the brand rather than silence the pattern: named
  // is better copy than generic. Read defensively like `stats` above, because
  // `mock.ts` is generated and owns neither shape.
  // (The banned phrase is deliberately not repeated here — quoting it makes the
  // leak check flag this file forever, exactly as CTABand.tsx notes.)
  const brandName = String((brand as { name?: unknown } | null)?.name ?? '').trim();

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
      <p className="mt-1 text-slate-600">{brandName ? `Overview of ${brandName}` : 'Overview'}</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((s, index) => (
          <div
            key={`${s.label}-${index}`}
            className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm"
          >
            <p className="text-sm text-slate-500">{s.label}</p>
            <p className="mt-2 text-3xl font-bold text-slate-900">{s.value}</p>
            {s.change ? (
              <p className="mt-1 text-sm font-medium text-emerald-600">{s.change}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
