/** DESIGN DRAFT — client directory + detail drawer. Matches the reference mockup. */
import { useState } from 'react';
import { AdminShell, Card, Badge, StatCard, IMG } from '../_adminKit';
import { Search, X, Phone, MessageSquare, Mail, MoreHorizontal, Sparkles } from 'lucide-react';

type Tier = 'vip' | 'new' | 'risk' | 'none';
type Client = {
  name: string; phone: string; avatar: number; tier: Tier; lastVisit: string; ltv: number; visits: number;
  favorite: string; stylist: number; frequency: string; action: string; actionTone: 'brand' | 'good' | 'risk';
};

const CLIENTS: Client[] = [
  { name: 'Lea M.', phone: '+961 70 123 456', avatar: 0, tier: 'vip', lastVisit: '3 days ago · Jul 19', ltv: 1280, visits: 12, favorite: 'Balayage / Lived-in Color', stylist: 1, frequency: 'Every 5 weeks', action: 'Book follow-up · due in 9 days', actionTone: 'good' },
  { name: 'Nour K.', phone: '+961 71 234 567', avatar: 1, tier: 'vip', lastVisit: '1 week ago · Jul 15', ltv: 920, visits: 9, favorite: 'Keratin Smoothing', stylist: 1, frequency: 'Every 6 weeks', action: 'Recommend · due in 6 days', actionTone: 'brand' },
  { name: 'Sami H.', phone: '+961 76 345 678', avatar: 2, tier: 'vip', lastVisit: '2 weeks ago · Jul 8', ltv: 1740, visits: 22, favorite: 'The Noor Ritual', stylist: 2, frequency: 'Every 3 weeks', action: 'Book follow-up · due in 5 days', actionTone: 'good' },
  { name: 'Farah S.', phone: '+961 78 456 789', avatar: 0, tier: 'new', lastVisit: 'Today · Jul 22', ltv: 350, visits: 3, favorite: 'Balayage / Gloss Treatment', stylist: 1, frequency: 'Every 6 weeks', action: 'Send care plan · due in 2 days', actionTone: 'brand' },
  { name: 'Karim B.', phone: '+961 81 567 890', avatar: 2, tier: 'vip', lastVisit: 'Today · Jul 22', ltv: 2100, visits: 31, favorite: 'Fades / Beard Grooming', stylist: 2, frequency: 'Every 2 weeks', action: 'Recommend · due in 4 days', actionTone: 'brand' },
  { name: 'Reem A.', phone: '+961 70 654 321', avatar: 1, tier: 'risk', lastVisit: '2 months ago · May 20', ltv: 680, visits: 5, favorite: 'Bridal Trial / Updo', stylist: 1, frequency: 'Every 8 weeks', action: 'Win-back · due in 3 days', actionTone: 'risk' },
  { name: 'Dana K.', phone: '+961 71 987 654', avatar: 0, tier: 'vip', lastVisit: '5 days ago · Jul 17', ltv: 1050, visits: 6, favorite: 'Full Color / Root Refresh', stylist: 1, frequency: 'Every 6 weeks', action: 'Book follow-up · due in 15 days', actionTone: 'good' },
  { name: 'Lina T.', phone: '+961 76 111 222', avatar: 2, tier: 'new', lastVisit: '1 week ago · Jul 15', ltv: 290, visits: 2, favorite: 'Haircut / Blowout', stylist: 1, frequency: '—', action: 'Send care plan · due in 1 day', actionTone: 'brand' },
];

const TIER_META: Record<Tier, { label: string; tone: 'brand' | 'good' | 'risk' } | null> = {
  vip: { label: 'VIP', tone: 'brand' },
  new: { label: 'NEW', tone: 'good' },
  risk: { label: 'AT RISK', tone: 'risk' },
  none: null,
};

const TABS = [
  { id: 'all', label: 'All clients', count: 842 },
  { id: 'new', label: 'New this month', count: 36 },
  { id: 'vip', label: 'VIPs', count: 128 },
  { id: 'risk', label: 'At risk', count: 47 },
];

export default function ClientsPage() {
  const [q, setQ] = useState('');
  const [tab, setTab] = useState('all');
  const [selected, setSelected] = useState<Client>(CLIENTS[0]);
  const filtered = CLIENTS.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()) && (tab === 'all' || c.tier === tab));

  return (
    <AdminShell active="/owner/clients" pageTitle="Clients" pageSubtitle="Your client relationships. Personalized care. Lasting loyalty.">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Active clients" value={842} delta="12% vs last month" sparkline={[720, 760, 780, 800, 815, 830, 842]} />
        <StatCard label="VIPs" value={128} delta="8% vs last month" gauge={65} />
        <StatCard label="At risk clients" value={47} delta="23% vs last month" deltaGood={false} />
        <StatCard label="Average spend" value={362} prefix="$" delta="15% vs last month" sparkline={[300, 310, 320, 330, 345, 355, 362]} />
        <StatCard label="Repeat rate" value={68} suffix="%" delta="6pp vs last month" gauge={68} />
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-white/35" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name, phone, or email…"
            className="w-full rounded-full border border-white/10 bg-white/[0.03] py-2.5 pl-11 pr-4 text-sm placeholder:text-white/30 focus:border-[var(--color-brand)] focus:outline-none"
          />
        </div>
        <span className="hidden rounded-full border border-white/10 px-3.5 py-2 text-xs text-white/50 sm:inline">Segment ⌄</span>
        <span className="hidden rounded-full border border-white/10 px-3.5 py-2 text-xs text-white/50 md:inline">Last visit ⌄</span>
      </div>

      <div className="mt-4 flex gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={
              'rounded-full border px-4 py-1.5 text-sm transition ' +
              (tab === t.id
                ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/10 text-[var(--color-brand)]'
                : 'border-white/10 text-white/50 hover:border-white/25')
            }
          >
            {t.label} <span className="text-white/35">{t.count}</span>
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Card>
          {filtered.map((c, i) => {
            const tier = TIER_META[c.tier];
            return (
              <button
                key={c.name}
                onClick={() => setSelected(c)}
                className={
                  'flex w-full items-center gap-4 border-b border-white/[0.06] px-6 py-4 text-left text-sm transition last:border-b-0 hover:bg-white/[0.02] ' +
                  (selected.name === c.name ? 'bg-[var(--color-brand)]/[0.05]' : '')
                }
              >
                <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full">
                  <img src={IMG.team[c.avatar]} alt="" className="h-full w-full object-cover" />
                </span>
                <div className="w-28 shrink-0">
                  <p className="truncate font-medium">{c.name}</p>
                  {tier && <span className="mt-0.5 inline-block"><Badge tone={tier.tone}>{tier.label}</Badge></span>}
                </div>
                <span className="hidden w-24 shrink-0 text-white/40 lg:block">{c.lastVisit.split(' · ')[0]}</span>
                <span className="hidden w-16 shrink-0 tabular-nums text-white/50 md:block">${c.ltv}</span>
                <span className="hidden flex-1 truncate text-white/45 xl:block">{c.favorite}</span>
              </button>
            );
          })}
          {!filtered.length && <p className="px-6 py-10 text-center text-sm text-white/40">No clients match “{q}”.</p>}
          <div className="border-t border-white/[0.06] px-6 py-3 text-xs text-white/35">
            Showing 1 to {filtered.length} of 842 clients
          </div>
        </Card>

        {/* Detail drawer */}
        <Card className="h-fit p-6">
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <span className="h-12 w-12 shrink-0 overflow-hidden rounded-full">
                <img src={IMG.team[selected.avatar]} alt="" className="h-full w-full object-cover" />
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-display text-lg">{selected.name}</p>
                  {TIER_META[selected.tier] && <Badge tone={TIER_META[selected.tier]!.tone}>{TIER_META[selected.tier]!.label}</Badge>}
                </div>
                <p className="text-xs text-white/40">Client since Nov 2023</p>
              </div>
            </div>
            <button className="text-white/30 hover:text-white"><X className="h-4 w-4" /></button>
          </div>

          <div className="mt-4 flex gap-2">
            {[Phone, MessageSquare, Mail, MoreHorizontal].map((Icon, i) => (
              <button key={i} className="rounded-lg border border-white/10 p-2 text-white/50 transition hover:border-white/30 hover:text-white">
                <Icon className="h-3.5 w-3.5" />
              </button>
            ))}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-4 border-y border-white/[0.08] py-4 text-xs">
            <div><p className="text-white/35">Last visit</p><p className="mt-0.5 font-medium">{selected.lastVisit}</p></div>
            <div><p className="text-white/35">Lifetime value</p><p className="mt-0.5 font-medium">${selected.ltv} · {selected.visits} visits</p></div>
            <div><p className="text-white/35">Preferred stylist</p><p className="mt-0.5 font-medium">{['Rania', 'Maya', 'Karim'][selected.stylist]}</p></div>
            <div><p className="text-white/35">Frequency</p><p className="mt-0.5 font-medium">{selected.frequency}</p></div>
          </div>

          <div className="mt-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Favorite services</p>
            <p className="mt-1 text-sm text-white/70">{selected.favorite}</p>
          </div>

          <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-[var(--color-brand)]/25 bg-[var(--color-brand)]/[0.06] p-3.5">
            <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-brand)]" />
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-brand)]">AI recommendation</p>
              <p className="mt-0.5 text-xs text-white/70">{selected.action}</p>
            </div>
          </div>
        </Card>
      </div>
    </AdminShell>
  );
}
