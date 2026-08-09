/**
 * DESIGN DRAFT — owner dashboard, draft 4: rebuilt to match the approved
 * reference mockup exactly — AI morning summary with inline stat chips,
 * 4 gauged/sparklined KPIs, bookings-performance chart, "today at a
 * glance", team performance leaderboard, client insights, automation health
 * row. See HomePage.tsx header for the extraction plan.
 */
import { useState } from 'react';
import { AreaChart, Area, ResponsiveContainer, XAxis, Tooltip, CartesianGrid, Line, ComposedChart } from 'recharts';
import { AdminShell, Card, StatCard, IMG } from './_adminKit';
import {
  Sparkles, CalendarDays, Users2, TriangleAlert, DollarSign, Clock, Bell, Repeat, ArrowRight,
} from 'lucide-react';

const CHART_DATA = [
  { day: 'Tue', baseline: 48, ai: 58 },
  { day: 'Wed', baseline: 40, ai: 52 },
  { day: 'Thu', baseline: 52, ai: 66 },
  { day: 'Fri', baseline: 60, ai: 74 },
  { day: 'Sat', baseline: 58, ai: 82 },
  { day: 'Sun', baseline: 46, ai: 60 },
  { day: 'Mon', baseline: 44, ai: 55 },
];

const UP_NEXT = [
  { time: '9:30 AM', name: 'Lea Haddad', note: 'Balayage / Rania', avatar: 0 },
  { time: '11:00 AM', name: 'Nadine Khoury', note: 'Haircut / Maya', avatar: 1 },
  { time: '12:30 PM', name: 'Yara Tabet', note: 'Color / Karim', avatar: 2 },
];

const TEAM = [
  { name: 'Rania', bookings: 17, revenue: 4280, avatar: 0, pct: 100 },
  { name: 'Maya', bookings: 14, revenue: 3450, avatar: 1, pct: 80 },
  { name: 'Karim', bookings: 12, revenue: 2910, avatar: 2, pct: 68 },
];

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-white/[0.12] bg-[#141210] px-4 py-3 text-xs shadow-xl">
      <p className="font-semibold text-white/85">{label}</p>
      <p className="mt-1 text-[var(--color-brand)]">AI-assisted: {payload.find((p: any) => p.dataKey === 'ai')?.value}</p>
      <p className="text-white/45">Baseline: {payload.find((p: any) => p.dataKey === 'baseline')?.value}</p>
    </div>
  );
}

export default function OwnerDashboardPage() {
  const [range] = useState('This week');

  return (
    <AdminShell active="/owner">
      {/* AI morning summary */}
      <Card className="bg-gradient-to-br from-[var(--color-brand)]/[0.08] to-transparent p-7">
        <div className="flex flex-wrap items-center justify-between gap-8">
          <div className="max-w-md">
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-brand)]">
              <Sparkles className="h-3.5 w-3.5" /> AI morning summary
            </p>
            <h2 className="mt-3 font-display text-3xl font-light leading-tight">
              A calm day ahead — <span className="italic text-[var(--color-brand)]">with opportunity.</span>
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-white/55">
              6 bookings today, 2 open gaps, and 3 waitlist matches likely to fill. One at-risk booking detected.
            </p>
            <button className="mt-4 flex items-center gap-1.5 text-sm font-medium text-[var(--color-brand)] transition hover:gap-2.5">
              View full briefing <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="flex flex-wrap gap-8">
            {[
              { icon: CalendarDays, value: '2', label: 'Open gaps', note: '1:30pm, 3:00pm' },
              { icon: Users2, value: '3', label: 'Waitlist matches', note: 'High fit' },
              { icon: TriangleAlert, value: '1', label: 'At-risk booking', note: '4:30pm with Karim' },
              { icon: DollarSign, value: '$1,640', label: 'Est. revenue today', note: '↑ 24% vs baseline', good: true },
            ].map((s) => (
              <div key={s.label} className="text-center">
                <span className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-white/[0.05]">
                  <s.icon className="h-4.5 w-4.5 text-[var(--color-brand)]" strokeWidth={1.6} />
                </span>
                <p className="mt-2 font-display text-xl">{s.value}</p>
                <p className="text-xs text-white/45">{s.label}</p>
                <p className={'text-[11px] ' + (s.good ? 'text-emerald-400' : 'text-white/35')}>{s.note}</p>
              </div>
            ))}
          </div>
        </div>
      </Card>

      {/* KPI row */}
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Recovered revenue (MTD)" value={12840} prefix="$" delta="18% vs baseline" sparkline={[4, 6, 5, 7, 9, 8, 11]} />
        <StatCard label="Chair occupancy" value={78} suffix="%" delta="9pp vs last month" gauge={78} />
        <StatCard label="AI resolution rate" value={93} suffix="%" delta="12pp vs last month" sparkline={[70, 74, 78, 83, 88, 90, 93]} />
        <StatCard label="Returning client rate" value={64} suffix="%" delta="7pp vs last month" gauge={64} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_18rem_16rem]">
        {/* Chart */}
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="font-display text-lg">Bookings performance</p>
              <p className="text-xs text-white/40">Baseline vs AI-assisted recovery</p>
            </div>
            <span className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/60">{range}</span>
          </div>
          <div className="mt-4 h-52">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={CHART_DATA} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
                <XAxis dataKey="day" stroke="rgba(255,255,255,0.35)" fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Line type="monotone" dataKey="baseline" stroke="rgba(255,255,255,0.35)" strokeDasharray="4 4" strokeWidth={1.75} dot={false} />
                <Line type="monotone" dataKey="ai" stroke="#c9a464" strokeWidth={2.5} dot={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex items-center gap-4 text-xs text-white/45">
            <span className="flex items-center gap-1.5"><span className="h-px w-4 border-t border-dashed border-white/40" /> Baseline</span>
            <span className="flex items-center gap-1.5"><span className="h-px w-4 bg-[var(--color-brand)]" /> AI-assisted</span>
          </div>
        </Card>

        {/* Today at a glance */}
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <p className="font-display text-lg">Today at a glance</p>
            <a href="/owner/bookings" className="text-xs font-medium text-[var(--color-brand)]">More details →</a>
          </div>
          <p className="mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Up next</p>
          <div className="mt-2 space-y-3">
            {UP_NEXT.map((u) => (
              <div key={u.time} className="flex items-center gap-2.5 text-sm">
                <span className="w-16 shrink-0 tabular-nums text-white/45">{u.time}</span>
                <span className="h-6 w-6 shrink-0 overflow-hidden rounded-full">
                  <img src={IMG.team[u.avatar]} alt="" className="h-full w-full object-cover" />
                </span>
                <div className="min-w-0">
                  <p className="truncate font-medium">{u.name}</p>
                  <p className="truncate text-xs text-white/40">{u.note}</p>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Open slots</p>
          <div className="mt-2 flex gap-2">
            {['1:30 PM', '3:00 PM', '5:15 PM'].map((s) => (
              <span key={s} className="rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-white/60">{s}</span>
            ))}
          </div>
          <div className="mt-4 flex items-center gap-2.5 rounded-xl border border-rose-400/25 bg-rose-400/[0.06] px-3.5 py-2.5">
            <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-rose-400" />
            <div className="min-w-0 text-xs">
              <p className="font-medium text-rose-300">4:30 PM · Rita Bou Rjeily</p>
              <p className="text-rose-400/70">Highlight / Karim — at risk</p>
            </div>
          </div>
        </Card>

        {/* Team performance */}
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <p className="font-display text-lg">Team</p>
            <a href="/owner/settings?tab=team" className="text-xs font-medium text-[var(--color-brand)]">View all →</a>
          </div>
          <p className="mt-0.5 text-xs text-white/40">This week</p>
          <div className="mt-4 space-y-4">
            {TEAM.map((t, i) => (
              <div key={t.name}>
                <div className="flex items-center gap-2.5">
                  <span className="w-4 text-xs text-white/35">{i + 1}</span>
                  <span className="h-7 w-7 shrink-0 overflow-hidden rounded-full">
                    <img src={IMG.team[t.avatar]} alt="" className="h-full w-full object-cover" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{t.name}</p>
                    <p className="text-xs text-white/40">{t.bookings} bookings</p>
                  </div>
                  <p className="shrink-0 text-sm font-medium tabular-nums">${t.revenue.toLocaleString()}</p>
                </div>
                <div className="ml-[3.4rem] mt-1.5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-[var(--color-brand)]" style={{ width: `${t.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Client insights */}
      <Card className="mt-6 p-6">
        <div className="flex items-center justify-between">
          <p className="font-display text-lg">Client insights</p>
          <a href="/owner/clients" className="text-xs font-medium text-[var(--color-brand)]">See all →</a>
        </div>
        <div className="mt-4 grid gap-8 sm:grid-cols-2">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">VIPs to follow up</p>
            <div className="mt-3 space-y-3">
              {[{ n: 'Lama Achkar', d: '45 days ago' }, { n: 'Joyce El Hajj', d: '38 days ago' }].map((c) => (
                <div key={c.n} className="flex items-center justify-between gap-3 text-sm">
                  <div><p className="font-medium">{c.n}</p><p className="text-xs text-white/40">Last in: {c.d}</p></div>
                  <button className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white/70 transition hover:border-white/35">Message</button>
                </div>
              ))}
            </div>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">At-risk of lapsing</p>
            <div className="mt-3 space-y-3">
              {[{ n: 'Nour Sleiman', d: '73 days ago' }, { n: 'Tatiana Aoun', d: '64 days ago' }].map((c) => (
                <div key={c.n} className="flex items-center justify-between gap-3 text-sm">
                  <div><p className="font-medium">{c.n}</p><p className="text-xs text-white/40">Last in: {c.d}</p></div>
                  <button className="rounded-lg border border-[var(--color-brand)]/35 bg-[var(--color-brand)]/10 px-3 py-1.5 text-xs text-[var(--color-brand)] transition hover:brightness-110">Re-engage</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* Automation & health */}
      <Card className="mt-6 p-6">
        <div className="flex items-center justify-between">
          <p className="font-display text-lg">Automation &amp; health</p>
          <span className="flex items-center gap-1.5 text-xs text-white/40"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> System status</span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-6 sm:grid-cols-4">
          {[
            { icon: Clock, label: 'AI response time', value: '4.3s', delta: '0.8s vs last week', good: true },
            { icon: Bell, label: 'Reminders sent', value: '64', delta: '11% vs last week', good: true },
            { icon: Users2, label: 'Waitlist fills', value: '7', delta: '40% vs last week', good: true },
            { icon: Repeat, label: 'No-shows saved', value: '$980', delta: '22% vs last week', good: true },
          ].map((s) => (
            <div key={s.label}>
              <s.icon className="h-4 w-4 text-white/40" strokeWidth={1.6} />
              <p className="mt-2 font-display text-2xl font-light">{s.value}</p>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-white/35">{s.label}</p>
              <p className="mt-0.5 text-xs text-emerald-400">↑ {s.delta}</p>
            </div>
          ))}
        </div>
      </Card>
    </AdminShell>
  );
}
