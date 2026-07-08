import { PROGRAMS, STUDIO, TODAY_CLASSES, WEEKLY_PROGRESS } from './peakformData.ts';
import { onPeakformImageError } from './peakformImageFallback.ts';

interface Props {
  highlightMember?: string;
}

export default function PeakFormProgress({ highlightMember = 'Jordan K.' }: Props) {
  const completed = WEEKLY_PROGRESS.filter((d) => d.workouts >= d.goal).length;
  const weekPct = Math.round((completed / WEEKLY_PROGRESS.length) * 100);

  return (
    <div className="pf-progress">
      <div className="pf-progress__grain" aria-hidden />
      <header className="pf-progress__head">
        <div>
          <p className="pf-progress__eyebrow">This week · Member adherence</p>
          <h2>Progress tracker</h2>
          <p className="pf-progress__sub">{weekPct}% weekly goal · live check-ins</p>
        </div>
        <div className="pf-progress__stats">
          <article><strong>87%</strong><span>Check-ins</span></article>
          <article><strong>12</strong><span>Day streak</span></article>
          <article><strong>3</strong><span>PRs logged</span></article>
        </div>
      </header>

      <div className="pf-progress__hero-strip">
        <img src={STUDIO.floorImage} alt="" onError={onPeakformImageError} />
        <div className="pf-progress__hero-shade" aria-hidden />
        <div className="pf-progress__hero-copy">
          <p>Jordan K. · HIIT pass</p>
          <strong>2 of 3 workouts done — Thursday closes the week</strong>
        </div>
      </div>

      <div className="pf-progress__week">
        {WEEKLY_PROGRESS.map((d) => (
          <div key={d.day} className={`pf-progress__day ${d.active ? 'pf-progress__day--active' : ''} ${d.workouts >= d.goal ? 'pf-progress__day--done' : ''}`}>
            <span>{d.day}</span>
            <div className="pf-progress__day-bar">
              <span style={{ width: `${Math.min(100, (d.workouts / d.goal) * 100)}%` }} />
            </div>
            <small>{d.workouts}/{d.goal}</small>
          </div>
        ))}
      </div>

      <div className="pf-progress__layout">
        <section className="pf-progress__schedule">
          <h3>Today&apos;s classes</h3>
          <ul className="pf-progress__list">
            {TODAY_CLASSES.map((c) => {
              const highlighted = c.member === highlightMember;
              const program = PROGRAMS.find((p) => p.name === c.program);
              return (
                <li key={`${c.time}-${c.program}`}>
                  <article className={`pf-progress__card ${highlighted ? 'pf-progress__card--highlight' : ''} pf-progress__card--${c.status}`}>
                    <div className="pf-progress__card-time">
                      <time>{c.time}</time>
                      <span className={`pf-progress__status pf-progress__status--${c.status}`}>{c.status}</span>
                    </div>
                    <div className="pf-progress__card-body">
                      <strong>{c.member}</strong>
                      <p>{c.program}</p>
                      <span className="pf-progress__coach">{c.coach}</span>
                    </div>
                    {program && (
                      <div className="pf-progress__card-thumb">
                        <img src={program.imageUrl} alt="" loading="lazy" onError={(e) => onPeakformImageError(e, program.name)} />
                      </div>
                    )}
                    {highlighted && <span className="pf-progress__new-badge">Just booked</span>}
                  </article>
                </li>
              );
            })}
          </ul>
        </section>

        <aside className="pf-progress__metrics">
          <h3>Member metrics</h3>
          <div className="pf-progress__metric-cards">
            <article>
              <strong>HIIT Burn</strong>
              <div className="pf-progress__bar"><span style={{ width: '92%' }} /></div>
              <small>92% attendance</small>
            </article>
            <article>
              <strong>Strength Lab</strong>
              <div className="pf-progress__bar"><span style={{ width: '78%' }} /></div>
              <small>78% attendance</small>
            </article>
            <article>
              <strong>Flow & Recover</strong>
              <div className="pf-progress__bar"><span style={{ width: '65%' }} /></div>
              <small>65% attendance</small>
            </article>
          </div>

          <h3>Recent PRs</h3>
          <ul className="pf-progress__prs">
            <li><strong>Deadlift</strong> 225 lb · Priya M.</li>
            <li><strong>5K row</strong> 19:42 · Jordan K.</li>
            <li><strong>Bench</strong> 185 lb · Sam L.</li>
          </ul>
        </aside>
      </div>
    </div>
  );
}
