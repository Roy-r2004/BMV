/** DESIGN DRAFT — reports. Not shown in the reference screenshots, so designed to match their density and language rather than copied from one. */
import { AreaChart, Area, BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Cell } from 'recharts';
import { AdminShell, Card, StatCard, IMG } from '../_adminKit';
import { Download } from 'lucide-react';

const REVENUE_TREND = [
  { week: 'Wk 1', revenue: 9200 },
  { week: 'Wk 2', revenue: 8600 },
  { week: 'Wk 3', revenue: 10400 },
  { week: 'Wk 4', revenue: 11800 },
  { week: 'Wk 5', revenue: 10900 },
  { week: 'Wk 6', revenue: 12840 },
];

const BY_CATEGORY = [
  { label: 'Color & dimension', value: 6420 },
  { label: 'Cut & style', value: 3180 },
  { label: 'Treatments', value: 2340 },
  { label: 'Bridal & occasion', value: 900 },
];

const TOP_SERVICES = [
  { name: 'Balayage / Lived-in color', bookings: 34, revenue: 4760 },
  { name: 'Signature cut & finish', bookings: 41, revenue: 1845 },
  { name: 'Keratin smoothing', bookings: 12, revenue: 2160 },
  { name: 'The Noor ritual', bookings: 18, revenue: 1710 },
  { name: 'Full color / root refresh', bookings: 15, revenue: 1275 },
];

const TEAM = [
  { name: 'Rania', avatar: 0, revenue: 4280, pct: 100 },
  { name: 'Maya', avatar: 1, revenue: 3450, pct: 80 },
  { name: 'Karim', avatar: 2, revenue: 2910, pct: 68 },
];

function RevenueTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.12] bg-[#141210] px-4 py-3 text-xs shadow-xl">
      <p className="font-semibold text-white/85">{label}</p>
      <p className="mt-1 text-[var(--color-brand)]">${payload[0].value.toLocaleString()}</p>
    </div>
  );
}

export default function ReportsPage() {
  return (
    <AdminShell active="/owner/reports" pageTitle="Reports" pageSubtitle="Performance across your business, at a glance.">
      <div className="mb-5 flex justify-end">
        <button className="flex items-center gap-1.5 rounded-full border border-white/15 px-4 py-2 text-sm text-white/70 transition hover:border-white/35">
          <Download className="h-3.5 w-3.5" /> Export report
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Revenue (6 weeks)" value={63740} prefix="$" delta="14% vs prior period" sparkline={[9.2, 8.6, 10.4, 11.8, 10.9, 12.8]} />
        <StatCard label="Total bookings" value={248} delta="9% vs prior period" />
        <StatCard label="Average ticket" value={97} prefix="$" delta="5% vs prior period" />
        <StatCard label="New clients" value={36} delta="12% vs prior period" />
      </div>

      <Card className="mt-6 p-6">
        <p className="font-display text-lg">Revenue trend</p>
        <p className="text-xs text-white/40">Last 6 weeks</p>
        <div className="mt-4 h-56">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={REVENUE_TREND} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="revFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#c9a464" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#c9a464" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
              <XAxis dataKey="week" stroke="rgba(255,255,255,0.35)" fontSize={12} tickLine={false} axisLine={false} />
              <YAxis stroke="rgba(255,255,255,0.25)" fontSize={12} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => `$${v / 1000}k`} />
              <Tooltip content={<RevenueTooltip />} />
              <Area type="monotone" dataKey="revenue" stroke="#c9a464" fill="url(#revFill)" strokeWidth={2.5} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <p className="font-display text-lg">Revenue by category</p>
          <p className="text-xs text-white/40">This month</p>
          <div className="mt-4 h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={BY_CATEGORY} layout="vertical" margin={{ top: 0, right: 16, left: 0, bottom: 0 }}>
                <XAxis type="number" hide />
                <YAxis type="category" dataKey="label" stroke="rgba(255,255,255,0.5)" fontSize={12} tickLine={false} axisLine={false} width={130} />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                  content={({ active, payload }: any) =>
                    active && payload?.length ? (
                      <div className="rounded-xl border border-white/[0.12] bg-[#141210] px-4 py-2.5 text-xs shadow-xl">
                        ${payload[0].value.toLocaleString()}
                      </div>
                    ) : null
                  }
                />
                <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={18}>
                  {BY_CATEGORY.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? '#c9a464' : 'rgba(201,164,100,0.45)'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card className="p-6">
          <p className="font-display text-lg">Team revenue</p>
          <p className="text-xs text-white/40">This month</p>
          <div className="mt-5 space-y-4">
            {TEAM.map((t) => (
              <div key={t.name}>
                <div className="flex items-center gap-3">
                  <span className="h-8 w-8 shrink-0 overflow-hidden rounded-full">
                    <img src={IMG.team[t.avatar]} alt="" className="h-full w-full object-cover" />
                  </span>
                  <p className="flex-1 text-sm font-medium">{t.name}</p>
                  <p className="text-sm tabular-nums text-white/70">${t.revenue.toLocaleString()}</p>
                </div>
                <div className="ml-11 mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-[var(--color-brand)]" style={{ width: `${t.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card className="mt-6 p-6">
        <p className="font-display text-lg">Top services</p>
        <p className="text-xs text-white/40">By revenue, this month</p>
        <div className="mt-3 divide-y divide-white/[0.06]">
          {TOP_SERVICES.sort((a, b) => b.revenue - a.revenue).map((s, i) => (
            <div key={s.name} className="flex items-center gap-4 py-3.5 text-sm">
              <span className="w-5 text-white/35">{i + 1}</span>
              <p className="flex-1 truncate font-medium">{s.name}</p>
              <span className="text-white/40">{s.bookings} bookings</span>
              <span className="w-20 text-right tabular-nums text-white/80">${s.revenue.toLocaleString()}</span>
            </div>
          ))}
        </div>
      </Card>
    </AdminShell>
  );
}
