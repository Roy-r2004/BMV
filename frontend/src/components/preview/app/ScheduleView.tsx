import { useState } from 'react';
import type { VisualDemo } from '../../../types/request';
import { resolvePreviewContent, type DemoContext } from '../demoContent';
import type { AppShellConfig } from '../industryBranding';

interface Props extends DemoContext {
  demo: VisualDemo;
  shell: AppShellConfig;
  primary: string;
  secondary: string;
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const SLOTS = ['9:00', '10:30', '12:00', '2:00', '3:30', '5:00'];

export default function ScheduleView({ demo, businessName, industry, previewFeatures, shell, primary, secondary }: Props) {
  const content = resolvePreviewContent(demo, { businessName, industry, previewFeatures });
  const [selectedDay, setSelectedDay] = useState(3);
  const [selectedSlot, setSelectedSlot] = useState('2:00');

  return (
    <div className="min-h-full bg-slate-50 overflow-x-hidden">
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

        <div className="grid lg:grid-cols-3 gap-4 sm:gap-5">
          <div className="lg:col-span-2 rounded-2xl border border-slate-200 bg-white shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
              <p className="font-semibold text-slate-900">July 2026</p>
              <div className="flex gap-1">
                <button type="button" className="w-8 h-8 rounded-lg border border-slate-200 text-slate-500 text-sm">‹</button>
                <button type="button" className="w-8 h-8 rounded-lg border border-slate-200 text-slate-500 text-sm">›</button>
              </div>
            </div>
            <div className="p-5">
              <div className="grid grid-cols-7 gap-2 mb-4">
                {DAYS.map((d, i) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setSelectedDay(i)}
                    className={`flex flex-col items-center py-3 rounded-xl transition-all ${
                      selectedDay === i ? 'text-white shadow-md' : 'text-slate-600 hover:bg-slate-50'
                    }`}
                    style={selectedDay === i ? { backgroundColor: primary } : undefined}
                  >
                    <span className="text-[10px] font-medium opacity-80">{d}</span>
                    <span className="text-lg font-bold mt-0.5">{7 + i}</span>
                  </button>
                ))}
              </div>

              <p className="text-sm font-semibold text-slate-700 mb-3">
                {shell.schedule.slotsLabel} — {DAYS[selectedDay]} Jul {7 + selectedDay}
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2">
                {SLOTS.map((slot) => {
                  const booked = slot === '12:00';
                  const selected = slot === selectedSlot;
                  return (
                    <button
                      key={slot}
                      type="button"
                      disabled={booked}
                      onClick={() => setSelectedSlot(slot)}
                      className={`py-2.5 rounded-xl text-sm font-medium transition-all ${
                        booked
                          ? 'bg-slate-100 text-slate-300 cursor-not-allowed line-through'
                          : selected
                            ? 'text-white shadow-md'
                            : 'border border-slate-200 text-slate-700 hover:border-slate-300 bg-white'
                      }`}
                      style={selected && !booked ? { backgroundColor: primary } : undefined}
                    >
                      {slot}
                    </button>
                  );
                })}
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
                    <div
                      className={`flex-1 rounded-xl px-3 py-2.5 border ${
                        apt.status === 'available' ? 'border-dashed border-slate-200 bg-slate-50' : 'border-slate-100 bg-white'
                      }`}
                    >
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
          </div>
        </div>
      </div>
    </div>
  );
}
