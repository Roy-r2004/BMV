import { useEffect, useState } from 'react';
import { BrightFixLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { ACTIVE_JOBS, TECHS, type ActiveJob } from './brightfixData.ts';

const ZONES = [
  { id: 'north', label: 'North', x: 28, y: 22, w: 38, h: 32 },
  { id: 'central', label: 'Central', x: 38, y: 38, w: 32, h: 28 },
  { id: 'south', label: 'South', x: 48, y: 58, w: 40, h: 34 },
  { id: 'east', label: 'East', x: 68, y: 42, w: 28, h: 38 },
];

const STATUS_LABEL: Record<ActiveJob['status'], string> = {
  'en-route': 'En route',
  'in-progress': 'In progress',
  done: 'Done',
};

const STATUS_TICKER = [
  'Mike R. · ETA 8 min · Oak Hill burst pipe',
  'Sara L. · on-site · Congress Ave drain clear',
  'Carlos D. · camera run · East / Manor sewer',
  'Amy K. · closed · Burnet Rd water heater · review queued',
];

interface Props {
  highlightJobId?: string;
}

export default function BrightFixDispatch({ highlightJobId }: Props) {
  const [selected, setSelected] = useState<string | null>(highlightJobId ?? 'a1');
  const [zoneFilter, setZoneFilter] = useState<string | null>(null);
  const [tickerIdx, setTickerIdx] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTickerIdx((i) => (i + 1) % STATUS_TICKER.length), 2800);
    return () => window.clearInterval(id);
  }, []);

  const jobs = zoneFilter ? ACTIVE_JOBS.filter((j) => j.zone === zoneFilter) : ACTIVE_JOBS;
  const job = ACTIVE_JOBS.find((j) => j.id === selected);
  const tech = job ? TECHS.find((t) => t.id === job.techId) : null;

  return (
    <div className="bf-dispatch">
      <aside className="bf-dispatch__sidebar">
        <header className="bf-dispatch__head">
          <BrightFixLogo className="bf-dispatch__logo" />
          <div>
            <h2>Route board</h2>
            <span>Live pins · zone view</span>
          </div>
        </header>

        <div className="bf-dispatch__ai-strip">
          <IconSparkle className="bf-dispatch__sparkle" />
          <span>Auto dispatch routes by skill + proximity</span>
        </div>

        <div className="bf-dispatch__ticker" aria-live="polite">
          <span className="bf-dispatch__ticker-dot" aria-hidden />
          <span key={tickerIdx} className="bf-dispatch__ticker-text">
            {STATUS_TICKER[tickerIdx]}
          </span>
        </div>

        <div className="bf-dispatch__zone-filters">
          <button
            type="button"
            className={!zoneFilter ? 'bf-dispatch__zone-btn bf-dispatch__zone-btn--on' : 'bf-dispatch__zone-btn'}
            onClick={() => setZoneFilter(null)}
          >
            All zones
          </button>
          {ZONES.map((z) => (
            <button
              key={z.id}
              type="button"
              className={zoneFilter === z.id ? 'bf-dispatch__zone-btn bf-dispatch__zone-btn--on' : 'bf-dispatch__zone-btn'}
              onClick={() => setZoneFilter(z.id)}
            >
              {z.label}
            </button>
          ))}
        </div>

        <ul className="bf-dispatch__job-list">
          {jobs.map((j) => {
            const t = TECHS.find((tech) => tech.id === j.techId);
            return (
              <li key={j.id}>
                <button
                  type="button"
                  className={selected === j.id ? 'bf-dispatch__job bf-dispatch__job--on' : 'bf-dispatch__job'}
                  onClick={() => setSelected(j.id)}
                >
                  <span className={`bf-dispatch__status bf-dispatch__status--${j.status}`}>{STATUS_LABEL[j.status]}</span>
                  <strong>{j.customer}</strong>
                  <span>{j.jobType}</span>
                  <div className="bf-dispatch__job-foot">
                    <em>{t?.name}</em>
                    {j.eta && <span>ETA {j.eta}</span>}
                  </div>
                </button>
              </li>
            );
          })}
        </ul>
      </aside>

      <main className="bf-dispatch__map-wrap">
        <header className="bf-dispatch__map-head">
          <h3>Austin service map</h3>
          <span className="bf-dispatch__live">Live</span>
        </header>

        <div className="bf-dispatch__map">
          <div className="bf-dispatch__map-grid" aria-hidden />
          {ZONES.map((z) => (
            <div
              key={z.id}
              className={`bf-dispatch__map-zone bf-dispatch__map-zone--${z.id} ${zoneFilter && zoneFilter !== z.id ? 'bf-dispatch__map-zone--dim' : ''}`}
              style={{ left: `${z.x}%`, top: `${z.y}%`, width: `${z.w}%`, height: `${z.h}%` }}
            >
              <span>{z.label}</span>
            </div>
          ))}
          {ACTIVE_JOBS.map((j) => (
            <button
              key={j.id}
              type="button"
              className={`bf-dispatch__pin bf-dispatch__pin--${j.status} ${selected === j.id ? 'bf-dispatch__pin--on' : ''}`}
              style={{ left: `${j.pinX}%`, top: `${j.pinY}%` }}
              onClick={() => setSelected(j.id)}
              aria-label={`${j.customer} — ${STATUS_LABEL[j.status]}`}
            >
              <span />
            </button>
          ))}
        </div>

        {job && tech && (
          <div className="bf-dispatch__detail">
            <div>
              <strong>{job.customer}</strong>
              <p>
                {job.address} · {job.jobType}
              </p>
            </div>
            <div className="bf-dispatch__detail-tech">
              <span className="bf-dispatch__avatar">{tech.initials}</span>
              <div>
                <em>{tech.name}</em>
                <span>
                  {STATUS_LABEL[job.status]}
                  {job.eta ? ` · ${job.eta}` : ''}
                </span>
              </div>
            </div>
            <span className="bf-dispatch__value">{job.value}</span>
          </div>
        )}
      </main>
    </div>
  );
}
