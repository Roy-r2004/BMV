/**
 * The pilot, tracked in the same terms it was planned in.
 *
 * The plan names what to measure and where each measure starts — only ever
 * one of their own figures, or "measure it in week 1". This is where they log
 * each week against it, and see which way it is moving. At the end the
 * decision rule, written before the pilot began, says what the result means;
 * nobody gets to decide what "worked" after seeing the numbers.
 */
import { useMemo, useState } from 'react';

import type { ActionPlan, CapacityPicture, PilotEntry } from '../../api/consultant';
import WeekGrid from './WeekGrid';
import { fmt } from '../../utils/week';

function trend(watch: 'up' | 'down' | 'hold', from: number, to: number) {
  const diff = to - from;
  const steady = Math.abs(diff) <= Math.max(0.02 * Math.abs(from), 0.0001);
  const good = watch === 'hold' ? steady : watch === 'up' ? diff > 0 : diff < 0;
  const text = steady ? 'Steady' : `${diff > 0 ? 'Up' : 'Down'} from ${fmt(from)}`;
  return { text, good: good || (steady && watch !== 'hold' ? null : good) };
}

export default function Tracker({ plan, log, capacity, canEdit, onSave }: {
  plan: ActionPlan;
  log: PilotEntry[];
  capacity: CapacityPicture | null;
  canEdit: boolean;
  onSave?: (week: number, values: Record<string, number>, note: string) => Promise<void>;
}) {
  const measures = plan.measures ?? [];
  const weeks = plan.weeks ?? 6;
  const latestWeek = log.reduce((m, e) => Math.max(m, e.week), 0);
  const [week, setWeek] = useState(Math.min(latestWeek + 1, weeks));
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const byWeek = useMemo(() => new Map(log.map((e) => [e.week, e])), [log]);
  const latestOf = (id: string): { week: number; value: number } | null => {
    for (let w = weeks + 6; w >= 1; w--) {
      const v = byWeek.get(w)?.values?.[id];
      if (v != null) return { week: w, value: v };
    }
    return null;
  };
  const firstOf = (id: string): number | null => {
    for (let w = 1; w <= weeks + 6; w++) {
      const v = byWeek.get(w)?.values?.[id];
      if (v != null) return v;
    }
    return null;
  };

  if (!measures.length) return null;

  return (
    <div className="cx-card p-7 sm:p-8">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h3 className="cx-h3">
          {latestWeek ? `Your pilot, week ${latestWeek}` : `Your ${weeks}-week pilot starts Monday`}
        </h3>
        <span className="cx-faint cx-small">{latestWeek ? `${weeks - latestWeek > 0 ? `${weeks - latestWeek} to go` : 'Finished — read the decision rule'}` : 'Log one week at a time'}</span>
      </div>
      <p className="cx-muted mt-1 text-[15px]">Each measure against where you started. The rule for what it means was written before you began.</p>

      <div className="mt-5 grid gap-4" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(170px, 1fr))` }}>
        {measures.map((m) => {
          const latest = latestOf(m.id);
          const start = m.baseline ?? firstOf(m.id);
          const t = latest && start != null && latest.value !== start ? trend(m.watch, start, latest.value) : null;
          return (
            <div className="cx-kpi" key={m.id}>
              <span className="cx-small cx-muted">{m.name}</span>
              <b>{latest ? fmt(latest.value) : start != null ? fmt(start) : '—'}</b>
              <small className={`text-[12.5px] font-semibold ${t ? (t.good ? 'text-[var(--cx-green)]' : t.good === false ? 'text-[var(--cx-red)]' : 'text-[var(--cx-blue)]') : 'text-[var(--cx-blue)]'}`}>
                {t ? t.text : latest ? 'Week ' + latest.week : start != null ? 'Where you start' : 'Measure it in week 1'}
              </small>
              {m.unit ? <span className="cx-faint block text-[12px]">{m.unit}</span> : null}
            </div>
          );
        })}
      </div>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full min-w-[520px] text-[14px]">
          <thead>
            <tr className="cx-faint text-left">
              <th className="py-2 pr-3 font-medium">Measure</th>
              <th className="py-2 pr-3 font-medium">Start</th>
              {Array.from({ length: weeks }, (_, i) => (
                <th key={i} className="py-2 pr-3 font-medium">W{i + 1}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {measures.map((m) => (
              <tr key={m.id} className="border-t border-[var(--cx-line)]">
                <td className="py-2 pr-3">{m.name}</td>
                <td className="py-2 pr-3 cx-muted">{m.baseline != null ? fmt(m.baseline) : '—'}</td>
                {Array.from({ length: weeks }, (_, i) => {
                  const v = byWeek.get(i + 1)?.values?.[m.id];
                  return <td key={i} className="py-2 pr-3 font-semibold">{v != null ? fmt(v) : ''}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {plan.decision_rule ? (
        <p className="cx-tint mt-6 px-5 py-4 text-[15.5px]"><b>At the end:</b> {plan.decision_rule}</p>
      ) : null}

      {canEdit && onSave ? (
        <form
          className="mt-6 border-t border-[var(--cx-line)] pt-6"
          onSubmit={async (e) => {
            e.preventDefault();
            const values: Record<string, number> = {};
            for (const m of measures) {
              const raw = (draft[m.id] ?? '').replace(/[,$\s]/g, '');
              if (raw !== '' && !Number.isNaN(Number(raw))) values[m.id] = Number(raw);
            }
            if (!Object.keys(values).length) {
              setError('Enter at least one number for this week.');
              return;
            }
            setSaving(true);
            setError(null);
            try {
              await onSave(week, values, note);
              setDraft({});
              setNote('');
              setWeek((w) => Math.min(w + 1, weeks));
            } catch {
              setError('That week could not be saved just now. Try again in a moment.');
            } finally {
              setSaving(false);
            }
          }}
        >
          <div className="flex flex-wrap items-center gap-3">
            <p className="font-semibold">Log week</p>
            <select className="cx-input h-10 w-auto" value={week} onChange={(e) => setWeek(Number(e.target.value))} aria-label="Week">
              {Array.from({ length: weeks }, (_, i) => (
                <option key={i} value={i + 1}>Week {i + 1}{byWeek.has(i + 1) ? ' (logged)' : ''}</option>
              ))}
            </select>
          </div>
          <div className="mt-4 grid gap-3" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
            {measures.map((m) => (
              <label key={m.id} className="block">
                <span className="cx-small cx-muted">{m.name}</span>
                <input
                  className="cx-input mt-1 h-11 w-full"
                  inputMode="decimal"
                  value={draft[m.id] ?? ''}
                  placeholder={byWeek.get(week)?.values?.[m.id] != null ? fmt(byWeek.get(week)!.values[m.id]) : m.unit || 'number'}
                  onChange={(e) => setDraft((d) => ({ ...d, [m.id]: e.target.value }))}
                />
              </label>
            ))}
          </div>
          <input className="cx-input mt-3 w-full" value={note} onChange={(e) => setNote(e.target.value)} placeholder="A note on this week (optional)" maxLength={400} />
          <div className="mt-4 flex items-center gap-4">
            <button type="submit" className="cx-btn cx-btn--blue cx-btn--sm" disabled={saving}>{saving ? 'Saving…' : 'Save this week'}</button>
            {error ? <span className="cx-error">{error}</span> : null}
          </div>
        </form>
      ) : null}

      {capacity ? (
        <div className="mt-8 border-t border-[var(--cx-line)] pt-6">
          <p className="cx-small cx-muted mb-3">The week you started with</p>
          <WeekGrid picture={capacity} mini />
        </div>
      ) : null}
    </div>
  );
}
