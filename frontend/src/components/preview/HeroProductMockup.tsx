import { motion } from 'framer-motion';
import type { VisualDemo } from '../../types/request';
import { hexAlpha } from './liveSiteTheme';

const ease = [0.22, 1, 0.36, 1] as const;

const DEFAULT_STATS = [
  { title: 'New leads', value: '12', delta: '+4 today' },
  { title: 'Booked', value: '8', delta: '67% rate' },
  { title: 'Revenue', value: '$2.4k', delta: 'this week' },
];

interface Props {
  demo: VisualDemo;
  primary: string;
  secondary: string;
  businessName?: string;
}

export default function HeroProductMockup({ demo, primary, secondary, businessName }: Props) {
  const cards = normalizeCards(demo);
  const activity = demo.admin_dashboard_preview?.recent_activity?.length
    ? demo.admin_dashboard_preview.recent_activity
    : [
        'Sarah booked — Botox consultation',
        'New DM from Instagram',
        'Reminder sent via WhatsApp',
      ];

  return (
    <div className="relative">
      {/* Glow */}
      <div
        className="absolute -inset-6 rounded-[2rem] blur-3xl opacity-70 pointer-events-none"
        style={{ background: `linear-gradient(135deg, ${hexAlpha(primary, 0.35)}, ${hexAlpha(secondary, 0.25)})` }}
      />

      {/* Floating notifications */}
      <motion.div
        initial={{ opacity: 0, x: 20, y: -10 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        transition={{ delay: 0.5, duration: 0.6, ease }}
        className="absolute -right-2 sm:right-0 top-8 z-20 w-44 sm:w-52 rounded-2xl border border-white/80 bg-white/95 backdrop-blur-xl shadow-2xl shadow-slate-300/40 p-3"
      >
        <div className="flex items-center gap-2 mb-2">
          <span className="w-7 h-7 rounded-full bg-gradient-to-br from-pink-500 to-purple-600 flex items-center justify-center text-white text-[10px] font-bold">IG</span>
          <div className="min-w-0">
            <p className="text-[10px] font-semibold text-slate-900 truncate">New Instagram DM</p>
            <p className="text-[9px] text-slate-400">Just now</p>
          </div>
        </div>
        <p className="text-[10px] text-slate-600 leading-snug">&ldquo;Hi! Any slots for a facial this week?&rdquo;</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, x: -20, y: 20 }}
        animate={{ opacity: 1, x: 0, y: 0 }}
        transition={{ delay: 0.7, duration: 0.6, ease }}
        className="absolute -left-2 sm:left-0 bottom-16 z-20 w-48 rounded-2xl border border-emerald-200 bg-emerald-50 shadow-xl shadow-emerald-200/40 p-3"
      >
        <div className="flex items-center gap-2">
          <span className="w-8 h-8 rounded-full bg-emerald-500 text-white flex items-center justify-center text-sm">✓</span>
          <div>
            <p className="text-[11px] font-bold text-emerald-900">Booking confirmed</p>
            <p className="text-[9px] text-emerald-700">Thu 2pm · WhatsApp sent</p>
          </div>
        </div>
      </motion.div>

      {/* Main app window */}
      <motion.div
        initial={{ opacity: 0, y: 24, rotateX: 8 }}
        animate={{ opacity: 1, y: 0, rotateX: 0 }}
        transition={{ duration: 0.85, ease }}
        className="relative z-10 rounded-2xl border border-slate-200/90 bg-white shadow-2xl shadow-slate-300/50 overflow-hidden"
        style={{ perspective: 1200 }}
      >
        <div className="px-4 py-2.5 border-b border-slate-100 flex items-center gap-2 bg-slate-50/90">
          <span className="w-2.5 h-2.5 rounded-full bg-red-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
          <span className="flex-1 text-center text-[10px] text-slate-500 font-medium">
            {demo.product_name.toLowerCase().replace(/\s/g, '')}.app
          </span>
          <span className="text-[9px] font-semibold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">Live</span>
        </div>

        <div
          className="p-5 sm:p-6 space-y-4"
          style={{ background: `linear-gradient(165deg, ${hexAlpha(primary, 0.07)} 0%, white 45%, ${hexAlpha(secondary, 0.04)} 100%)` }}
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Dashboard</p>
              <p className="text-xl font-bold text-slate-900 mt-0.5">
                {businessName ? `${businessName}` : 'Your clinic'}
              </p>
              <p className="text-xs text-slate-500 mt-0.5">Today&apos;s performance</p>
            </div>
            <div className="flex -space-x-2">
              {['S', 'M', 'J'].map((l, i) => (
                <span
                  key={l}
                  className="w-7 h-7 rounded-full border-2 border-white text-[10px] font-bold text-white flex items-center justify-center"
                  style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})`, opacity: 1 - i * 0.12 }}
                >
                  {l}
                </span>
              ))}
              <span className="w-7 h-7 rounded-full border-2 border-white bg-slate-100 text-[9px] font-semibold text-slate-600 flex items-center justify-center">
                +9
              </span>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {cards.map((c, i) => (
              <motion.div
                key={c.title}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 + i * 0.1, ease }}
                className="rounded-xl bg-white border border-slate-100 p-3 shadow-sm"
              >
                <p className="text-[9px] text-slate-500 font-medium">{c.title}</p>
                <p className="text-xl font-bold mt-0.5 tabular-nums" style={{ color: primary }}>
                  {c.value}
                </p>
                <p className="text-[9px] text-emerald-600 font-medium mt-0.5">{c.delta}</p>
              </motion.div>
            ))}
          </div>

          {/* Mini inbox */}
          <div className="rounded-xl border border-slate-100 bg-white p-3 shadow-sm space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-bold text-slate-700 uppercase tracking-wide">Inbox</p>
              <span className="text-[9px] px-2 py-0.5 rounded-full font-semibold text-white" style={{ backgroundColor: primary }}>
                3 new
              </span>
            </div>
            {[
              { from: 'Instagram', msg: 'Availability for lip filler?', time: '2m' },
              { from: 'WhatsApp', msg: 'Can I reschedule to Friday?', time: '8m' },
            ].map((row) => (
              <div key={row.msg} className="flex items-center gap-2 rounded-lg bg-slate-50 px-2.5 py-2">
                <span className="w-6 h-6 rounded-full shrink-0 text-[8px] font-bold text-white flex items-center justify-center" style={{ backgroundColor: primary }}>
                  {row.from.charAt(0)}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-medium text-slate-800 truncate">{row.msg}</p>
                </div>
                <span className="text-[9px] text-slate-400 shrink-0">{row.time}</span>
              </div>
            ))}
          </div>

          {/* Activity + chart */}
          <div className="grid grid-cols-5 gap-2">
            <div className="col-span-2 rounded-xl border border-slate-100 bg-white p-2.5 space-y-1.5">
              <p className="text-[9px] font-semibold text-slate-500">Activity</p>
              {activity.slice(0, 2).map((item) => (
                <div key={item.slice(0, 30)} className="flex items-center gap-1.5">
                  <span className="w-1 h-1 rounded-full bg-emerald-400 shrink-0" />
                  <p className="text-[9px] text-slate-600 truncate">{item}</p>
                </div>
              ))}
            </div>
            <div className="col-span-3 rounded-xl p-2.5 flex items-end gap-1" style={{ backgroundColor: hexAlpha(primary, 0.06) }}>
              {[42, 68, 55, 82, 61, 94, 78, 88].map((h, i) => (
                <motion.div
                  key={i}
                  initial={{ height: 0 }}
                  animate={{ height: `${h}%` }}
                  transition={{ delay: 0.4 + i * 0.05, duration: 0.5, ease }}
                  className="flex-1 rounded-t-md min-h-[4px]"
                  style={{
                    background: `linear-gradient(180deg, ${primary}, ${hexAlpha(secondary, 0.7)})`,
                    opacity: 0.55 + i * 0.05,
                  }}
                />
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </div>
  );
}

function normalizeCards(demo: VisualDemo) {
  const raw = demo.admin_dashboard_preview?.cards ?? [];
  const filled = raw.map((c, i) => ({
    title: c.title || DEFAULT_STATS[i]?.title || 'Metric',
    value: c.value?.trim() || DEFAULT_STATS[i]?.value || '—',
    delta: c.description?.trim() || DEFAULT_STATS[i]?.delta || '',
  }));
  while (filled.length < 3) {
    filled.push(DEFAULT_STATS[filled.length]);
  }
  return filled.slice(0, 3);
}
