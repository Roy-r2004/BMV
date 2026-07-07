import type { VisualDemo } from '../../../types/request';
import { resolvePreviewContent, type DemoContext } from '../demoContent';
import type { AppShellConfig } from '../industryBranding';

interface Props extends DemoContext {
  demo: VisualDemo;
  shell: AppShellConfig;
  primary: string;
  secondary: string;
}

const HABITS = [
  { label: 'Meals logged', done: 18, total: 24, pct: 75 },
  { label: 'Workouts completed', done: 20, total: 24, pct: 83 },
  { label: 'Weigh-in submitted', done: 22, total: 24, pct: 92 },
  { label: 'Progress photos', done: 14, total: 24, pct: 58 },
];

const CLIENT_PROGRESS = [
  { name: 'Jamie R.', adherence: 87, meals: '6/7', workout: 'Done', photos: 'Due Fri' },
  { name: 'Taylor S.', adherence: 72, meals: '5/7', workout: 'Skipped', photos: 'Uploaded' },
  { name: 'Jordan P.', adherence: 94, meals: '7/7', workout: 'Done', photos: 'Uploaded' },
];

export default function ProgressView({ demo, businessName, industry, previewFeatures, shell, primary, secondary }: Props) {
  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });
  const features = demo.feature_cards?.slice(0, 4) || [];

  return (
    <div className="min-h-full overflow-x-hidden" style={{ backgroundColor: '#fffbeb' }}>
      <div className="max-w-5xl mx-auto p-3 sm:p-6 lg:p-8">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900">{shell.schedule.title}</h1>
            <p className="text-sm text-slate-500 mt-0.5">{shell.schedule.subtitle}</p>
          </div>
          <button
            type="button"
            className="px-4 py-2 rounded-xl text-white text-sm font-semibold shadow-md self-start"
            style={{ backgroundColor: primary }}
          >
            {shell.schedule.addButton}
          </button>
        </div>

        <div className="grid lg:grid-cols-3 gap-5">
          <div className="lg:col-span-2 space-y-4">
            <div className="rounded-2xl border border-orange-100 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">{shell.schedule.slotsLabel}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {HABITS.map((h) => (
                  <div key={h.label} className="rounded-xl border border-slate-100 p-4 bg-slate-50/50">
                    <div className="flex justify-between items-center mb-2">
                      <p className="text-sm font-semibold text-slate-800">{h.label}</p>
                      <span className="text-xs font-bold" style={{ color: primary }}>{h.pct}%</span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${h.pct}%`, backgroundColor: secondary }} />
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1.5">{h.done}/{h.total} clients this week</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">Client snapshot</p>
              <div className="space-y-3">
                {CLIENT_PROGRESS.map((c) => (
                  <div key={c.name} className="flex items-center gap-4 p-3 rounded-xl hover:bg-slate-50 transition-colors">
                    <div
                      className="w-11 h-11 rounded-full shrink-0 flex items-center justify-center text-white text-sm font-bold"
                      style={{ backgroundColor: primary }}
                    >
                      {c.name.charAt(0)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-center">
                        <p className="font-semibold text-slate-900 text-sm">{c.name}</p>
                        <span className="text-xs font-bold" style={{ color: secondary }}>{c.adherence}% adherence</span>
                      </div>
                      <div className="flex gap-3 mt-1 text-[10px] text-slate-500">
                        <span>Meals {c.meals}</span>
                        <span>·</span>
                        <span>Workout {c.workout}</span>
                        <span>·</span>
                        <span>Photos {c.photos}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">{shell.schedule.todayLabel}</p>
              <div className="space-y-3">
                {content.appointments.map((apt) => (
                  <div key={apt.time} className="flex gap-3 items-start">
                    <span className="text-xs font-bold text-slate-400 w-10 shrink-0 pt-0.5">{apt.time}</span>
                    <div className="flex-1 rounded-xl px-3 py-2.5 border border-slate-100 bg-white">
                      <p className="text-sm font-semibold text-slate-900">{apt.client}</p>
                      <p className="text-xs text-slate-500">{apt.service}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl p-5 text-white" style={{ background: `linear-gradient(135deg, ${primary}, ${secondary})` }}>
              <p className="text-xs font-semibold opacity-90">This week</p>
              <p className="text-3xl font-bold mt-1">{content.weekStat}</p>
              <p className="text-sm opacity-90">{content.weekDetail}</p>
            </div>

            {features.length > 0 && (
              <div className="rounded-2xl border border-orange-100 bg-white p-5 shadow-sm">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Platform modules</p>
                <div className="space-y-2">
                  {features.map((f) => (
                    <div key={f.title} className="flex items-center gap-2 text-xs text-slate-700">
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: secondary }} />
                      {f.title}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
