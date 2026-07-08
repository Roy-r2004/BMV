import { useState } from 'react';
import { BrightFixLogo } from '../shared/ShowcaseChatIcons.tsx';
import { ACTIVE_JOBS, COMPANY, REVIEW_QUEUE, TECHS, TODAY_METRICS } from './brightfixData.ts';
import { onBrightfixImageError } from './brightfixImageFallback.ts';

type HubTab = 'jobs' | 'roster' | 'reviews';

const STATUS_LABEL = {
  'en-route': 'En route',
  'in-progress': 'In progress',
  done: 'Done',
} as const;

export default function BrightFixOpsHub() {
  const [tab, setTab] = useState<HubTab>('jobs');

  return (
    <div className="bf-ops">
      <aside className="bf-ops__nav">
        <div className="bf-ops__brand">
          <BrightFixLogo className="bf-ops__logo" />
          <div>
            <strong>BrightFix Ops</strong>
            <span>Dispatch hub</span>
          </div>
        </div>
        <nav aria-label="Ops navigation">
          {([
            { id: 'jobs' as const, label: 'Today\'s jobs', sub: 'Live board' },
            { id: 'roster' as const, label: 'Tech roster', sub: 'Availability' },
            { id: 'reviews' as const, label: 'Review bot', sub: 'Post-job' },
          ]).map((item) => (
            <button
              key={item.id}
              type="button"
              className={tab === item.id ? 'bf-ops__nav-btn bf-ops__nav-btn--on' : 'bf-ops__nav-btn'}
              onClick={() => setTab(item.id)}
            >
              <span>{item.label}</span>
              <em>{item.sub}</em>
            </button>
          ))}
        </nav>
        <div className="bf-ops__nav-foot">
          <span className="bf-ops__live-dot" />
          Tuesday service live
        </div>
      </aside>

      <main className="bf-ops__main">
        <div className="bf-ops__hero-strip">
          <img src={COMPANY.techImage} alt="" onError={(e) => onBrightfixImageError(e)} />
          <div className="bf-ops__hero-shade" aria-hidden />
          <p>Field status · 3 active · 2 available</p>
        </div>

        <div className="bf-ops__revenue-strip">
          {TODAY_METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'bf-ops__metric bf-ops__metric--accent' : 'bf-ops__metric'}>
              <span>{m.label}</span>
              <strong>{m.value}</strong>
              <em>{m.sub}</em>
            </article>
          ))}
        </div>

        <header className="bf-ops__head">
          <div>
            <p>BrightFix Dispatch</p>
            <h1>{tab === 'jobs' ? 'Today\'s jobs' : tab === 'roster' ? 'Tech roster' : 'Review bot'}</h1>
          </div>
          <span className="bf-ops__badge">Live</span>
        </header>

        {tab === 'jobs' && (
          <div className="bf-ops__jobs">
            {ACTIVE_JOBS.map((job) => {
              const tech = TECHS.find((t) => t.id === job.techId);
              return (
                <article key={job.id} className={`bf-ops__job bf-ops__job--${job.status}`}>
                  <div className="bf-ops__job-main">
                    <span className={`bf-ops__job-status bf-ops__job-status--${job.status}`}>
                      {STATUS_LABEL[job.status]}
                    </span>
                    <strong>{job.customer}</strong>
                    <p>{job.jobType} · {job.address}</p>
                  </div>
                  <div className="bf-ops__job-tech">
                    <span>{tech?.initials}</span>
                    <em>{tech?.name}</em>
                  </div>
                  <strong className="bf-ops__job-value">{job.value}</strong>
                </article>
              );
            })}
          </div>
        )}

        {tab === 'roster' && (
          <div className="bf-ops__roster">
            {TECHS.map((tech) => (
              <article key={tech.id} className={`bf-ops__tech bf-ops__tech--${tech.status}`}>
                <span className="bf-ops__tech-avatar">{tech.initials}</span>
                <div className="bf-ops__tech-info">
                  <strong>{tech.name}</strong>
                  <span>{tech.skill} · {tech.zone}</span>
                  <em>{tech.jobsToday} jobs today · {tech.rating}★</em>
                </div>
                <span className={`bf-ops__tech-status bf-ops__tech-status--${tech.status}`}>
                  {tech.status.replace('-', ' ')}
                </span>
              </article>
            ))}
          </div>
        )}

        {tab === 'reviews' && (
          <div className="bf-ops__reviews">
            <p className="bf-ops__reviews-intro">
              Review bot sends Google requests 15 min after job close — only when status is done.
            </p>
            {REVIEW_QUEUE.map((r) => (
              <article key={r.customer} className="bf-ops__review">
                <div>
                  <strong>{r.customer}</strong>
                  <span>{r.job}</span>
                </div>
                <em>Sent {r.sent}</em>
                <span className={`bf-ops__review-status bf-ops__review-status--${r.status}`}>{r.status}</span>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
