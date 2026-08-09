/** DESIGN DRAFT — AI front desk: inbox, control center, funnel, live feed, donut. Matches the reference mockup. */
import { useEffect, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import { AdminShell, Card, Badge, StatCard, IMG } from '../_adminKit';
import { MessageSquare, Camera, Mail, Settings2, Shield, Globe2, Sliders, CalendarDays, ChevronRight } from 'lucide-react';

const CHANNEL_ICON = { whatsapp: MessageSquare, instagram: Camera, email: Mail } as const;

const CONVERSATIONS = [
  { name: 'Lea M.', avatar: 0, msg: 'Saturday we’re fully booked until 4 — but Rania has 4:30 open. Want me to hold it?', status: 'resolved' as const, channel: 'whatsapp' as const, time: '11:42 PM' },
  { name: 'Sami H.', avatar: 2, msg: 'Send a reminder for tomorrow’s appointment at 9:30 with Maya.', status: 'resolved' as const, channel: 'whatsapp' as const, time: '9:15 PM' },
  { name: 'Yara T.', avatar: 2, msg: 'Asking about Saturday availability — replying…', status: 'progress' as const, channel: 'instagram' as const, time: 'Just now' },
  { name: 'Reem A.', avatar: 1, msg: 'Wants a custom bridal package quote — escalated to Rania.', status: 'escalated' as const, channel: 'email' as const, time: 'Yesterday' },
  { name: 'Nour J.', avatar: 0, msg: 'Can I move my appointment to earlier?', status: 'waiting' as const, channel: 'whatsapp' as const, time: 'Yesterday' },
];

const STATUS_META = {
  resolved: { label: 'Resolved by AI', tone: 'good' as const },
  progress: { label: 'In progress', tone: 'brand' as const },
  escalated: { label: 'Escalated', tone: 'risk' as const },
  waiting: { label: 'Waiting', tone: 'warn' as const },
};

const TABS = [
  { id: 'all', label: 'All', count: 24 },
  { id: 'resolved', label: 'Resolved', count: 12 },
  { id: 'progress', label: 'In progress', count: 6 },
  { id: 'escalated', label: 'Escalated', count: 3 },
  { id: 'waiting', label: 'Waiting', count: 3 },
];

const DONUT = [
  { name: 'Resolved by AI', value: 287, color: '#22c55e' },
  { name: 'Escalated', value: 19, color: '#fb7185' },
  { name: 'Waiting', value: 6, color: '#fbbf24' },
];

const FUNNEL = [
  { label: 'Conversations', value: 312, pct: 100 },
  { label: 'Qualified', value: 148, pct: 47 },
  { label: 'Booked', value: 36, pct: 24 },
  { label: 'Completed', value: 24, pct: 67 },
];

const ESCALATIONS = [
  { label: 'Complex request', count: 8 },
  { label: 'Custom quotation', count: 6 },
  { label: 'Service not available', count: 3 },
  { label: 'Multiple requests', count: 2 },
];

const LIVE_SEED = [
  { text: 'Lea M. booked a haircut with Rania', via: 'via WhatsApp', time: '11:43 PM' },
  { text: 'Sami H. received appointment reminder', via: 'via WhatsApp', time: '9:15 PM' },
  { text: 'Yara T. is typing…', via: 'via Instagram', time: 'Just now' },
  { text: 'Reem A. escalated to Rania', via: 'via Email', time: 'Yesterday' },
];

export default function AiFrontDeskPage() {
  const [tab, setTab] = useState('all');
  const [live, setLive] = useState(LIVE_SEED);

  useEffect(() => {
    const t = setTimeout(() => {
      setLive((f) => [{ text: 'Nour J. asked to reschedule — AI proposed 3 new times', via: 'via WhatsApp', time: 'Just now' }, ...f]);
    }, 6000);
    return () => clearTimeout(t);
  }, []);

  const filtered = CONVERSATIONS.filter((c) => tab === 'all' || c.status === tab);

  return (
    <AdminShell active="/owner/ai" pageTitle="AI Front Desk" pageSubtitle="Your always-on receptionist, delivering exceptional care 24/7.">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Messages handled" value={312} delta="28% vs last week" sparkline={[210, 240, 260, 275, 290, 300, 312]} />
        <StatCard label="Avg. response time" value={4} suffix="s" delta="38% vs last week" />
        <StatCard label="Autonomous resolution" value={92} suffix="%" delta="12pp vs last week" gauge={92} />
        <StatCard label="Bookings recovered" value={18} delta="64% vs last week" />
        <StatCard label="No-shows prevented" value={23} delta="36% vs last week" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_20rem]">
        {/* Inbox */}
        <Card>
          <div className="flex items-center justify-between border-b border-white/[0.08] px-6 py-4">
            <div className="flex items-center gap-2">
              <p className="font-display text-lg">Conversation inbox</p>
              <span className="flex items-center gap-1.5 text-xs text-emerald-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" /> Live</span>
            </div>
          </div>
          <div className="flex gap-2 border-b border-white/[0.08] px-6 py-3">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={
                  'rounded-full border px-3.5 py-1.5 text-xs transition ' +
                  (tab === t.id ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/10 text-[var(--color-brand)]' : 'border-white/10 text-white/50 hover:border-white/25')
                }
              >
                {t.label} <span className="text-white/35">{t.count}</span>
              </button>
            ))}
          </div>
          <div>
            {filtered.map((c, i) => {
              const meta = STATUS_META[c.status];
              const ChannelIcon = CHANNEL_ICON[c.channel];
              return (
                <div key={c.name + c.time} className={'flex items-start gap-3 px-6 py-4 ' + (i < filtered.length - 1 ? 'border-b border-white/[0.06]' : '')}>
                  <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full">
                    <img src={IMG.team[c.avatar]} alt="" className="h-full w-full object-cover" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{c.name}</p>
                    <p className="mt-0.5 truncate text-sm text-white/50">{c.msg}</p>
                    <div className="mt-2"><Badge tone={meta.tone}>{meta.label}</Badge></div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5 text-white/35">
                    <ChannelIcon className="h-3.5 w-3.5" />
                    <span className="text-xs">{c.time}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <a href="#" className="block border-t border-white/[0.08] px-6 py-3 text-center text-xs font-medium text-[var(--color-brand)]">View all conversations →</a>
        </Card>

        {/* Control center */}
        <Card className="p-6">
          <div className="flex items-center justify-between">
            <p className="font-display text-lg">Control center</p>
            <span className="flex items-center gap-1.5 text-xs text-white/40"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> System status</span>
          </div>
          <div className="mt-4 space-y-1">
            {[
              { icon: Settings2, label: 'Automation behaviors', note: 'Fine-tune how your AI replies and acts', cta: 'Configure' },
              { icon: Shield, label: 'Escalation thresholds', note: 'When to hand off to your team', cta: 'Configure' },
              { icon: Globe2, label: 'Languages', note: 'Arabic, French, English', cta: 'Manage' },
              { icon: Sliders, label: 'Tone profile', note: 'Warm · Luxury · Reassuring', cta: 'Manage' },
              { icon: CalendarDays, label: 'Booking permissions', note: 'What the AI can do on your behalf', cta: 'Configure' },
            ].map((r) => (
              <button key={r.label} className="flex w-full items-center gap-3 rounded-xl px-2 py-3 text-left transition hover:bg-white/[0.03]">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/[0.05]">
                  <r.icon className="h-4 w-4 text-[var(--color-brand)]" strokeWidth={1.6} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{r.label}</p>
                  <p className="truncate text-xs text-white/40">{r.note}</p>
                </div>
                <ChevronRight className="h-3.5 w-3.5 shrink-0 text-white/25" />
              </button>
            ))}
          </div>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-4">
        {/* Funnel */}
        <Card className="p-6">
          <p className="font-display text-base">Performance funnel</p>
          <p className="text-xs text-white/40">This week</p>
          <div className="mt-5 space-y-2.5">
            {FUNNEL.map((f) => (
              <div key={f.label}>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/60">{f.label}</span>
                  <span className="font-medium">{f.value} {f.label !== 'Conversations' && <span className="text-white/35">({f.pct}%)</span>}</span>
                </div>
                <div className="mt-1 h-2.5 overflow-hidden rounded-full bg-white/[0.06]">
                  <div className="h-full rounded-full bg-[var(--color-brand)]" style={{ width: `${(f.value / FUNNEL[0].value) * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Live feed */}
        <Card className="p-6">
          <div className="flex items-center gap-2">
            <p className="font-display text-base">Live activity</p>
            <span className="flex items-center gap-1.5 text-xs text-emerald-400"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" /> Live</span>
          </div>
          <div className="mt-4 max-h-48 space-y-3 overflow-y-auto">
            {live.map((l, i) => (
              <div key={l.text + i} className="text-xs">
                <p className="text-white/80">{l.text}</p>
                <p className="text-white/35">{l.via} · {l.time}</p>
              </div>
            ))}
          </div>
        </Card>

        {/* Donut */}
        <Card className="p-6">
          <p className="font-display text-base">Conversation insights</p>
          <p className="text-xs text-white/40">This week</p>
          <div className="relative mt-2 h-36">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={DONUT} dataKey="value" innerRadius={42} outerRadius={62} paddingAngle={3} stroke="none">
                  {DONUT.map((d) => <Cell key={d.name} fill={d.color} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
              <p className="font-display text-xl">312</p>
              <p className="text-[10px] text-white/40">Total</p>
            </div>
          </div>
          <div className="mt-2 space-y-1.5 text-xs">
            {DONUT.map((d) => (
              <div key={d.name} className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-white/60"><span className="h-2 w-2 rounded-full" style={{ background: d.color }} /> {d.name}</span>
                <span className="text-white/40">{Math.round((d.value / 312) * 100)}% ({d.value})</span>
              </div>
            ))}
          </div>
        </Card>

        {/* Escalation reasons */}
        <Card className="p-6">
          <p className="font-display text-base">Top escalation reasons</p>
          <p className="text-xs text-white/40">This week</p>
          <div className="mt-4 space-y-3">
            {ESCALATIONS.map((e) => (
              <div key={e.label} className="flex items-center justify-between text-sm">
                <span className="text-white/65">{e.label}</span>
                <span className="rounded-full bg-white/[0.06] px-2.5 py-0.5 text-xs text-white/50">{e.count}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </AdminShell>
  );
}
