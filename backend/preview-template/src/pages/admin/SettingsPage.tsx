/** DESIGN DRAFT — settings, rebuilt with tabs (Business Profile/Team/Services/AI Automations/Notifications). Matches the reference mockup. */
import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { AdminShell, Card, Toggle, IMG } from '../_adminKit';
import { SALON } from '../_kit';
import { Building2, Users2, Sliders, Bell, ListChecks, Plus, Pencil, Trash2, MessageSquare, Mail, Send, ExternalLink } from 'lucide-react';

const TABS = [
  { id: 'profile', label: 'Business Profile', icon: Building2 },
  { id: 'team', label: 'Team', icon: Users2 },
  { id: 'services', label: 'Services', icon: ListChecks },
  { id: 'ai', label: 'AI Automations', icon: Sliders },
  { id: 'notifications', label: 'Notifications', icon: Bell },
];

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-white/35">{label}</label>
      <input
        defaultValue={value}
        className="w-full rounded-xl border border-white/10 bg-white/[0.02] px-4 py-2.5 text-sm focus:border-[var(--color-brand)] focus:outline-none"
      />
    </div>
  );
}

export default function SettingsPage() {
  const [params] = useSearchParams();
  const [tab, setTab] = useState(params.get('tab') === 'team' ? 'team' : 'profile');
  const [staff, setStaff] = useState(SALON.team.map((t, i) => ({ ...t, avatar: i })));
  const [autoBook, setAutoBook] = useState(true);
  const [reminders, setReminders] = useState(true);
  const [escalation, setEscalation] = useState(true);
  const [notifyNew, setNotifyNew] = useState(true);
  const [notifyCancel, setNotifyCancel] = useState(true);
  const [notifyDaily, setNotifyDaily] = useState(false);
  const [notifyWeekly, setNotifyWeekly] = useState(true);

  return (
    <AdminShell active="/owner/settings" pageTitle="Settings" pageSubtitle="Manage your business, team, services and AI assistant preferences.">
      <div className="mb-5 flex justify-end">
        <a href="/booking" target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm font-medium text-[var(--color-brand)]">
          Preview Booking Page <ExternalLink className="h-3.5 w-3.5" />
        </a>
      </div>

      <div className="flex gap-1 overflow-x-auto border-b border-white/[0.08] pb-px">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={
              'flex shrink-0 items-center gap-2 border-b-2 px-4 py-3 text-sm transition ' +
              (tab === t.id ? 'border-[var(--color-brand)] text-[var(--color-brand)]' : 'border-transparent text-white/50 hover:text-white')
            }
          >
            <t.icon className="h-3.5 w-3.5" /> {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'profile' && (
          <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
            <Card className="overflow-hidden">
              <div className="flex aspect-square flex-col items-center justify-center bg-gradient-to-br from-[var(--color-brand)]/[0.12] to-black/40 p-6 text-center">
                <span className="font-display text-3xl italic text-[var(--color-brand)]">MN</span>
                <p className="mt-2 font-display text-lg italic">Maison Noor</p>
                <p className="text-[10px] uppercase tracking-[0.3em] text-white/35">Beirut</p>
              </div>
              <button className="w-full border-t border-white/[0.08] py-3 text-sm text-white/60 transition hover:text-white">Change logo</button>
            </Card>
            <Card className="p-7">
              <div className="flex items-center justify-between">
                <p className="font-display text-lg">Business profile</p>
                <button className="flex items-center gap-1.5 text-xs text-white/50"><Pencil className="h-3.5 w-3.5" /> Edit</button>
              </div>
              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <Field label="Salon name" value={SALON.name} />
                <Field label="WhatsApp number" value={SALON.whatsapp + ' 70 123 456'} />
                <div className="sm:col-span-2"><Field label="Address" value={SALON.address + ', Lebanon'} /></div>
                <Field label="Hours" value={SALON.hours} />
              </div>
              <div className="mt-4">
                <label className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wide text-white/35">Branches</label>
                <div className="flex flex-wrap gap-2">
                  <span className="rounded-full border border-white/15 px-3.5 py-1.5 text-xs text-white/70">Gemmayze</span>
                  <button className="flex items-center gap-1 rounded-full border border-dashed border-white/20 px-3.5 py-1.5 text-xs text-white/40 transition hover:border-white/40 hover:text-white">
                    <Plus className="h-3 w-3" /> Add branch
                  </button>
                </div>
              </div>
            </Card>
          </div>
        )}

        {tab === 'team' && (
          <Card className="p-7">
            <div className="flex items-center justify-between">
              <p className="font-display text-lg">Team</p>
              <button className="flex items-center gap-1.5 rounded-full border border-white/15 px-4 py-2 text-xs text-white/60 transition hover:border-[var(--color-brand)] hover:text-[var(--color-brand)]">
                <Plus className="h-3.5 w-3.5" /> Add staff member
              </button>
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-3">
              {staff.map((t) => (
                <div key={t.name} className="rounded-2xl border border-white/[0.08] p-5">
                  <div className="flex items-center gap-3">
                    <span className="h-11 w-11 shrink-0 overflow-hidden rounded-full">
                      <img src={IMG.team[t.avatar]} alt="" className="h-full w-full object-cover" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{t.name}</p>
                      <p className="text-xs text-white/40">{t.role}</p>
                    </div>
                    <span className="shrink-0 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-400">Active</span>
                  </div>
                  <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-white/35">Specialties</p>
                  <p className="mt-1 text-xs text-white/60">{t.specialties.join(' · ')}</p>
                  <p className="mt-3 text-[10px] font-semibold uppercase tracking-wide text-white/35">Hours</p>
                  <p className="mt-1 text-xs text-white/60">{SALON.hours}</p>
                  <div className="mt-4 flex gap-2 border-t border-white/[0.08] pt-3">
                    <button className="flex items-center gap-1 text-xs text-white/50 hover:text-white"><Pencil className="h-3.5 w-3.5" /></button>
                    <button onClick={() => setStaff((s) => s.filter((x) => x.name !== t.name))} className="flex items-center gap-1 text-xs text-white/50 hover:text-rose-400">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {tab === 'services' && (
          <Card className="p-7">
            <div className="flex items-center justify-between">
              <p className="font-display text-lg">Services</p>
              <button className="text-xs font-medium text-[var(--color-brand)]">Manage services →</button>
            </div>
            <div className="mt-4 divide-y divide-white/[0.06]">
              {SALON.categories.flatMap((c) => c.services).slice(0, 6).map((s) => (
                <div key={s.name} className="flex items-center gap-4 py-3.5 text-sm">
                  <span className="h-10 w-10 shrink-0 overflow-hidden rounded-xl bg-white/5">
                    <img src={SALON.categories[0].image} alt="" className="h-full w-full object-cover" />
                  </span>
                  <div className="flex-1"><p className="font-medium">{s.name}</p><p className="text-xs text-white/40">{s.dur}</p></div>
                  <span className="tabular-nums text-white/70">{s.price}</span>
                  <button className="text-white/40 hover:text-white"><Pencil className="h-3.5 w-3.5" /></button>
                </div>
              ))}
            </div>
            <button className="mt-4 flex items-center gap-1.5 rounded-full border border-dashed border-white/20 px-4 py-2 text-xs text-white/40 transition hover:border-white/40 hover:text-white">
              <Plus className="h-3.5 w-3.5" /> Add new service
            </button>
          </Card>
        )}

        {tab === 'ai' && (
          <Card className="p-7">
            <p className="font-display text-lg">AI Automations</p>
            <p className="text-xs text-white/40">Configure how your AI assistant behaves.</p>
            <div className="mt-4 max-w-xl divide-y divide-white/[0.06]">
              <Toggle on={autoBook} onChange={setAutoBook} label="Auto-booking" note="Allow AI to book appointments directly." />
              <Toggle on={reminders} onChange={setReminders} label="Reminders" note="Send smart reminders to reduce no-shows." />
              <Toggle on={escalation} onChange={setEscalation} label="Escalation" note="Escalate complex requests to a human." />
            </div>
            <div className="mt-5 flex items-center justify-between rounded-xl border border-white/10 px-4 py-3">
              <div><p className="text-sm font-medium">Tone & voice</p><p className="text-xs text-white/40">Calm, warm and luxurious.</p></div>
              <span className="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-white/70">Warm & Luxurious ⌄</span>
            </div>
            <a href="/owner/ai" className="mt-4 inline-block text-xs font-medium text-[var(--color-brand)]">Advanced AI settings →</a>
          </Card>
        )}

        {tab === 'notifications' && (
          <Card className="p-7">
            <p className="font-display text-lg">Notifications</p>
            <p className="text-xs text-white/40">Choose what you want to be notified about.</p>
            <div className="mt-4 max-w-xl divide-y divide-white/[0.06]">
              <Toggle on={notifyNew} onChange={setNotifyNew} label="New bookings" note="Instant alert for any new booking." />
              <Toggle on={notifyCancel} onChange={setNotifyCancel} label="Cancellations" note="Get notified when a booking is cancelled." />
              <Toggle on={notifyDaily} onChange={setNotifyDaily} label="Daily summary" note="Receive a summary every evening." />
              <Toggle on={notifyWeekly} onChange={setNotifyWeekly} label="Weekly performance" note="Insights and performance delivered weekly." />
            </div>
            <p className="mt-5 text-[10px] font-semibold uppercase tracking-wide text-white/35">Notification channels</p>
            <div className="mt-2 flex gap-2">
              {[MessageSquare, Mail, Send].map((Icon, i) => (
                <button key={i} className="rounded-lg border border-white/10 p-2.5 text-white/50 transition hover:border-[var(--color-brand)] hover:text-[var(--color-brand)]">
                  <Icon className="h-4 w-4" />
                </button>
              ))}
            </div>
          </Card>
        )}
      </div>

      <div className="sticky bottom-0 mt-6 flex items-center justify-between rounded-2xl border border-white/[0.08] bg-[#141210]/95 px-6 py-4 backdrop-blur">
        <p className="text-xs text-white/40">✓ All changes saved · Just now</p>
        <div className="flex gap-2">
          <button className="rounded-full border border-white/15 px-4 py-2 text-sm text-white/70 transition hover:border-white/35">Discard changes</button>
          <button className="rounded-full bg-[var(--color-brand)] px-5 py-2 text-sm font-semibold text-black transition hover:brightness-110">Save all changes</button>
        </div>
      </div>
    </AdminShell>
  );
}
