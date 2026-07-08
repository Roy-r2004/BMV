import { useState } from 'react';
import { IconSparkle, MetroLogo } from '../shared/ShowcaseChatIcons.tsx';
import { BAYS, STATUS_TIMELINE, TECHS, type Bay } from './metroData.ts';

const STATUS_LABEL: Record<Bay['status'], string> = {
  open: 'Open',
  active: 'Active',
  hold: 'On hold',
  wash: 'Wash bay',
};

interface Props {
  highlightBay?: number;
}

export default function MetroBayBoard({ highlightBay }: Props) {
  const [selected, setSelected] = useState<number>(highlightBay ?? 1);
  const bay = BAYS.find((b) => b.id === selected)!;
  const tech = bay.techId ? TECHS.find((t) => t.id === bay.techId) : null;

  return (
    <div className="mt-bays">
      <header className="mt-bays__head">
        <div className="mt-bays__brand">
          <MetroLogo className="mt-bays__logo" />
          <div>
            <h2>Bay / lift board</h2>
            <span>Status lights · floor view — not a week calendar</span>
          </div>
        </div>
        <div className="mt-bays__ai-strip">
          <IconSparkle className="mt-bays__sparkle" />
          <span>Progress stream synced to Status Bot SMS</span>
        </div>
      </header>

      <div className="mt-bays__legend" aria-label="Status legend">
        {(
          [
            ['active', 'Active'],
            ['hold', 'Hold'],
            ['open', 'Open'],
            ['wash', 'Wash'],
          ] as const
        ).map(([k, label]) => (
          <span key={k} className={`mt-bays__legend-item mt-bays__legend-item--${k}`}>
            <i aria-hidden />
            {label}
          </span>
        ))}
      </div>

      <div className="mt-bays__grid">
        {BAYS.map((b) => {
          const t = b.techId ? TECHS.find((x) => x.id === b.techId) : null;
          return (
            <button
              key={b.id}
              type="button"
              className={`mt-bays__bay mt-bays__bay--${b.status} ${selected === b.id ? 'mt-bays__bay--on' : ''} ${highlightBay === b.id ? 'mt-bays__bay--pulse' : ''}`}
              onClick={() => setSelected(b.id)}
            >
              <div className="mt-bays__bay-top">
                <span className={`mt-bays__light mt-bays__light--${b.status}`} aria-hidden />
                <strong>{b.label}</strong>
                <em>{STATUS_LABEL[b.status]}</em>
              </div>
              <p className="mt-bays__lift">{b.lift}</p>
              {b.customer ? (
                <>
                  <strong className="mt-bays__customer">{b.customer}</strong>
                  <span className="mt-bays__vehicle">{b.vehicle}</span>
                  <span className="mt-bays__service">{b.service}</span>
                  <div className="mt-bays__progress" aria-hidden>
                    <span style={{ width: `${b.progress}%` }} />
                  </div>
                  <div className="mt-bays__bay-foot">
                    <em>{t?.name ?? '—'}</em>
                    <span>{b.eta}</span>
                  </div>
                </>
              ) : (
                <p className="mt-bays__empty">Lift open — ready for next job</p>
              )}
            </button>
          );
        })}
      </div>

      <aside className="mt-bays__detail">
        <div className="mt-bays__detail-main">
          <span className={`mt-bays__light mt-bays__light--${bay.status} mt-bays__light--lg`} aria-hidden />
          <div>
            <h3>{bay.label} · {bay.lift}</h3>
            <p>{bay.customer ? `${bay.customer} — ${bay.vehicle}` : 'No active vehicle'}</p>
          </div>
          {tech && (
            <div className="mt-bays__tech">
              <span>{tech.initials}</span>
              <div>
                <em>{tech.name}</em>
                <span>{tech.specialty}</span>
              </div>
            </div>
          )}
        </div>

        {bay.customer && (
          <>
            <div className="mt-bays__stage">
              <strong>{bay.stage}</strong>
              <span>{bay.progress}% · ETA {bay.eta}</span>
            </div>
            <ol className="mt-bays__timeline">
              {STATUS_TIMELINE.map((s) => (
                <li key={s.stage} className={s.done ? 'mt-bays__tl mt-bays__tl--done' : 'mt-bays__tl'}>
                  <i aria-hidden />
                  <strong>{s.stage}</strong>
                  <time>{s.time}</time>
                </li>
              ))}
            </ol>
            <p className="mt-bays__sms-note">
              <IconSparkle className="mt-bays__sparkle" />
              Customer receives live SMS at each checkbox — zero “is my car ready?” calls.
            </p>
          </>
        )}
      </aside>
    </div>
  );
}
