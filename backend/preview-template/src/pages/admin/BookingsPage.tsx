/**
 * DESIGN DRAFT — Bookings, rebuilt as the true calendar view (matches the
 * reference: mini month calendar, week schedule, selected-booking detail
 * drawer with an AI suggestion). This is the calendar page.
 */
import { useState } from 'react';
import { AdminShell, Card, Badge, StatCard, IMG } from '../_adminKit';
import { ChevronLeft, ChevronRight, Users2, Sparkles } from 'lucide-react';

type Row = {
  time: string; client: string | null; phone: string | null; service: string | null;
  dur: string; staff: string | null; avatar: number; status: 'confirmed' | 'risk' | 'open';
  note?: string;
};

const SCHEDULE: Row[] = [
  { time: '9:00 AM', client: 'Maya D.', phone: '+961 71 123 456', service: 'Signature cut & finish', dur: '60 min', staff: 'Maya', avatar: 0, status: 'confirmed' },
  { time: '10:30 AM', client: 'Farah S.', phone: '+961 70 234 567', service: 'Balayage / Lived-in color', dur: '90 min', staff: 'Rania', avatar: 1, status: 'confirmed' },
  { time: '12:00 PM', client: 'Karim B.', phone: '+961 76 345 678', service: 'Fades & barbering', dur: '75 min', staff: 'Karim', avatar: 2, status: 'confirmed' },
  { time: '1:30 PM', client: null, phone: null, service: 'Great time for a color service', dur: '60 min', staff: null, avatar: -1, status: 'open' },
  { time: '3:00 PM', client: null, phone: null, service: 'Great for treatments & services', dur: '60 min', staff: null, avatar: -1, status: 'open' },
  { time: '4:30 PM', client: 'Lea M.', phone: '+961 71 555 121', service: 'Balayage / Lived-in color', dur: '90 min', staff: 'Rania', avatar: 0, status: 'confirmed' },
  { time: '6:00 PM', client: 'Nour K.', phone: '+961 76 888 999', service: 'Keratin smoothing', dur: '120 min', staff: 'Maya', avatar: 1, status: 'confirmed' },
  { time: '7:30 PM', client: 'Yara T.', phone: '+961 70 111 222', service: 'Blowout', dur: '40 min', staff: 'Maya', avatar: 2, status: 'risk' },
];

const WAITLIST = [
  { name: 'Jana H.', note: 'Balayage / Lived-in color', time: '12:00 PM' },
  { name: 'Rami T.', note: 'Fade & beard', time: '1:30 PM' },
  { name: 'Sama M.', note: 'Keratin smoothing', time: '4:00 PM' },
];

const MONTH_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);
const LEAD_BLANKS = 2; // July 2025 starts on a Tuesday

export default function BookingsPage() {
  const [selected, setSelected] = useState<Row>(SCHEDULE[0]);
  const [view, setView] = useState<'Day' | 'Week' | 'Agenda'>('Week');

  return (
    <AdminShell active="/owner/bookings" pageTitle="Bookings" pageSubtitle="Your week, one glance">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard label="Weekly bookings" value={42} delta="15% vs last week" sparkline={[28, 31, 35, 33, 38, 40, 42]} />
        <StatCard label="Confirmed revenue" value={18640} prefix="$" delta="18% vs last week" sparkline={[12, 14, 13, 16, 17, 18, 18.6]} />
        <StatCard label="Open gaps" value={6} suffix=" · 12.5 hrs" />
        <StatCard label="Waitlist coverage" value={87} suffix="%" gauge={87} />
        <StatCard label="No-show risk" value={1240} prefix="$" suffix=" · 6 bookings" deltaGood={false} />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-[16rem_1fr_20rem]">
        {/* Mini month calendar + waitlist */}
        <div className="space-y-6">
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <p className="font-display text-base">July 2025</p>
              <div className="flex gap-1">
                <button className="rounded-lg p-1 text-white/40 hover:bg-white/[0.06] hover:text-white"><ChevronLeft className="h-3.5 w-3.5" /></button>
                <button className="rounded-lg p-1 text-white/40 hover:bg-white/[0.06] hover:text-white"><ChevronRight className="h-3.5 w-3.5" /></button>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-7 gap-y-1.5 text-center text-[11px] text-white/30">
              {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => <span key={d + i}>{d}</span>)}
              {Array.from({ length: LEAD_BLANKS }).map((_, i) => <span key={'b' + i} />)}
              {MONTH_DAYS.map((d) => (
                <span
                  key={d}
                  className={
                    'flex h-6 w-6 items-center justify-center justify-self-center rounded-full text-xs ' +
                    (d === 22 ? 'bg-[var(--color-brand)] font-semibold text-black' : 'text-white/60 hover:bg-white/[0.06]')
                  }
                >
                  {d}
                </span>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Today · Tue 22</p>
            <div className="mt-3 flex items-center gap-4">
              <div className="relative h-14 w-14 rounded-full" style={{ background: 'conic-gradient(#c9a464 280.8deg, rgba(255,255,255,0.08) 0deg)' }}>
                <div className="absolute inset-[3px] flex items-center justify-center rounded-full bg-[#0c0b0a] text-sm font-semibold">78%</div>
              </div>
              <div>
                <p className="text-sm">Occupancy</p>
                <p className="text-xs text-white/40">9.5 / 12 hrs booked</p>
              </div>
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center gap-2">
              <Users2 className="h-3.5 w-3.5 text-white/40" />
              <p className="text-sm font-medium">Waitlist opportunities</p>
            </div>
            <p className="text-xs text-white/40">{WAITLIST.length} clients · 6+ bookings</p>
            <div className="mt-3 space-y-2.5">
              {WAITLIST.map((w) => (
                <div key={w.name} className="flex items-center justify-between text-sm">
                  <div className="min-w-0"><p className="truncate font-medium">{w.name}</p><p className="truncate text-xs text-white/40">{w.note}</p></div>
                  <span className="shrink-0 text-xs text-white/40">{w.time}</span>
                </div>
              ))}
            </div>
            <a href="#" className="mt-3 inline-block text-xs font-medium text-[var(--color-brand)]">View waitlist →</a>
          </Card>
        </div>

        {/* Schedule */}
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.08] px-6 py-4">
            <div className="flex gap-1 rounded-xl border border-white/10 p-1">
              {(['Day', 'Week', 'Agenda'] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={'rounded-lg px-3 py-1.5 text-xs transition ' + (view === v ? 'bg-white/[0.08] font-medium text-white' : 'text-white/40 hover:text-white/70')}
                >
                  {v}
                </button>
              ))}
            </div>
            <div className="flex gap-2 text-xs text-white/40">
              <span className="rounded-lg border border-white/10 px-2.5 py-1.5">All status</span>
              <span className="hidden rounded-lg border border-white/10 px-2.5 py-1.5 sm:inline">All stylists</span>
              <span className="hidden rounded-lg border border-white/10 px-2.5 py-1.5 lg:inline">All services</span>
            </div>
          </div>
          <div>
            {SCHEDULE.map((r, i) => (
              <button
                key={r.time}
                onClick={() => setSelected(r)}
                className={
                  'flex w-full items-center gap-4 border-b border-white/[0.06] px-6 py-3.5 text-left text-sm transition last:border-b-0 hover:bg-white/[0.02] ' +
                  (selected.time === r.time ? 'bg-[var(--color-brand)]/[0.06]' : '') +
                  (r.status === 'risk' ? ' bg-amber-400/[0.04]' : '')
                }
              >
                <span className="w-20 shrink-0 tabular-nums text-white/50">{r.time}</span>
                {r.avatar === -1 ? (
                  <>
                    <span className="flex-1 text-white/35">{r.service}</span>
                    <span className="shrink-0 rounded-lg border border-[var(--color-brand)]/35 bg-[var(--color-brand)]/10 px-3 py-1.5 text-xs text-[var(--color-brand)]">
                      Fill from waitlist
                    </span>
                  </>
                ) : (
                  <>
                    <span className="h-7 w-7 shrink-0 overflow-hidden rounded-full">
                      <img src={IMG.team[r.avatar]} alt="" className="h-full w-full object-cover" />
                    </span>
                    <span className="w-24 shrink-0 truncate font-medium">{r.client}</span>
                    <span className="hidden flex-1 truncate text-white/55 sm:block">{r.service}</span>
                    <span className="hidden shrink-0 rounded-full border border-white/15 px-2.5 py-1 text-xs text-white/50 md:inline-block">{r.staff}</span>
                    <Badge tone={r.status === 'confirmed' ? 'good' : 'warn'}>{r.status === 'confirmed' ? 'Confirmed' : 'At risk'}</Badge>
                  </>
                )}
              </button>
            ))}
          </div>
        </Card>

        {/* Selected booking detail */}
        <Card className="h-fit p-6">
          {selected.avatar === -1 ? (
            <p className="text-sm text-white/40">Select a booking to see details, or fill this slot from the waitlist.</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Selected booking</p>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <span className="h-11 w-11 shrink-0 overflow-hidden rounded-full">
                  <img src={IMG.team[selected.avatar]} alt="" className="h-full w-full object-cover" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-lg">{selected.client}</p>
                  <p className="text-xs text-white/40">Returning client</p>
                </div>
                <Badge tone={selected.status === 'confirmed' ? 'good' : 'warn'}>{selected.status === 'confirmed' ? 'Confirmed' : 'At risk'}</Badge>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3 border-y border-white/[0.08] py-4 text-xs">
                <div><p className="text-white/35">Tue, Jul 22</p><p className="mt-0.5 font-medium">{selected.time}</p></div>
                <div><p className="text-white/35">Duration</p><p className="mt-0.5 font-medium">{selected.dur}</p></div>
                <div><p className="text-white/35">Location</p><p className="mt-0.5 font-medium">Chair 1</p></div>
              </div>

              <div className="mt-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Service</p>
                <p className="mt-1 text-sm">{selected.service} · <span className="text-[var(--color-brand)]">$85</span></p>
              </div>

              <div className="mt-4">
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Client notes</p>
                <p className="mt-1 text-sm text-white/60">Prefers soft layers around face. Loves volume.</p>
              </div>

              <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-[var(--color-brand)]/25 bg-[var(--color-brand)]/[0.06] p-3.5">
                <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--color-brand)]" />
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] font-semibold uppercase tracking-wide text-[var(--color-brand)]">AI suggestion</p>
                  <p className="mt-0.5 text-xs text-white/70">Offer a gloss treatment to boost shine.</p>
                  <button className="mt-2 rounded-lg bg-[var(--color-brand)] px-3 py-1.5 text-xs font-semibold text-black">Add to booking</button>
                </div>
              </div>

              <div className="mt-4 text-xs text-white/50">
                <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/35">Rebooking history</p>
                <p className="mt-1">Every 6–8 weeks · Last visit Jun 3, 2025 · <span className="text-emerald-400">On track</span></p>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-2">
                <button className="rounded-lg border border-white/15 py-2 text-xs text-white/70 transition hover:border-white/35">Reschedule</button>
                <button className="rounded-lg bg-[var(--color-brand)] py-2 text-xs font-semibold text-black">Confirm</button>
              </div>
            </>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}
