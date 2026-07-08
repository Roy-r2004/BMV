import { useMemo, useState } from 'react';
import { SummitLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { TUTORS, STUDENTS, PACKAGES, SUMMIT, getPackage, type Student } from './summitData.ts';
import { onSummitImageError } from './summitImageFallback.ts';

type HubPage = 'roster' | 'progress' | 'billing';

const METRICS = [
  { label: 'Active students', value: '320', sub: '+14 this month', accent: true },
  { label: 'Sessions this week', value: '186', sub: '94% fill rate' },
  { label: 'Prep packs sent', value: '47', sub: 'Auto 24h before' },
  { label: 'Renewals due', value: '5', sub: 'Auto-reminders on' },
];

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'roster', label: 'Tutor roster', sub: 'Team & load' },
  { id: 'progress', label: 'Student progress', sub: 'Rings & goals' },
  { id: 'billing', label: 'Payments', sub: 'Packages' },
];

function ProgressRing({ value, size = 48 }: { value: number; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (value / 100) * c;
  return (
    <svg className="sm-hub__ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <circle className="sm-hub__ring-bg" cx={size / 2} cy={size / 2} r={r} />
      <circle
        className="sm-hub__ring-fill"
        cx={size / 2}
        cy={size / 2}
        r={r}
        strokeDasharray={c}
        strokeDashoffset={offset}
      />
      <text x={size / 2} y={size / 2 + 4} textAnchor="middle" className="sm-hub__ring-text">{value}%</text>
    </svg>
  );
}

export default function SummitTutorHub() {
  const [page, setPage] = useState<HubPage>('roster');

  const renewalDue = useMemo(() => PACKAGES.filter((p) => p.status === 'renewal-due'), []);

  return (
    <div className="sm-hub">
      <aside className="sm-hub__nav">
        <div className="sm-hub__brand">
          <SummitLogo className="sm-hub__brand-logo" />
          <div>
            <strong>Summit Hub</strong>
            <span>Tutor dashboard</span>
          </div>
        </div>
        <nav aria-label="Hub navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'sm-hub__nav-btn sm-hub__nav-btn--on' : 'sm-hub__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="sm-hub__nav-label">{item.label}</span>
              <span className="sm-hub__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className="sm-hub__nav-foot">
          <span className="sm-hub__nav-live" />
          Center live
        </div>
      </aside>

      <main className="sm-hub__main">
        <div className="sm-hub__hero-strip">
          <img src={SUMMIT.studyImage} alt="" onError={onSummitImageError} />
          <div className="sm-hub__hero-shade" aria-hidden />
          <div className="sm-hub__hero-copy">
            <p>Thursday session block</p>
            <strong>320 students · 186 sessions this week</strong>
          </div>
        </div>

        <header className="sm-hub__head">
          <div>
            <p className="sm-hub__head-eyebrow">{SUMMIT.name}</p>
            <h1>{page === 'roster' ? 'Tutor roster' : page === 'progress' ? 'Student progress' : 'Payment strip'}</h1>
            <p>Thursday · 4:30 PM block · 6 tutors on floor</p>
          </div>
          <span className="sm-hub__live">Live</span>
        </header>

        <div className="sm-hub__metrics">
          {METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'sm-hub__metric sm-hub__metric--accent' : 'sm-hub__metric'}>
              <strong>{m.value}</strong>
              <span>{m.label}</span>
              <small>{m.sub}</small>
            </article>
          ))}
        </div>

        {page === 'roster' && (
          <div className="sm-hub__roster">
            {TUTORS.map((t) => (
              <article key={t.id} className="sm-hub__tutor-card">
                <img
                  src={t.imageUrl}
                  alt={t.name}
                  onError={(e) => onSummitImageError(e, t.photoInitial)}
                />
                <div>
                  <div className="sm-hub__tutor-top">
                    <strong>{t.name}</strong>
                    <span>★ {t.rating}</span>
                  </div>
                  <p className="sm-hub__tutor-title">{t.title}</p>
                  <div className="sm-hub__tutor-tags">
                    {t.specialties.slice(0, 3).map((s) => (
                      <span key={s}>{s}</span>
                    ))}
                  </div>
                  <div className="sm-hub__tutor-load">
                    <div className="sm-hub__load-bar">
                      <div style={{ width: `${Math.min(100, t.sessionsThisWeek * 5)}%` }} />
                    </div>
                    <span>{t.sessionsThisWeek} sessions this week</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {page === 'progress' && (
          <div className="sm-hub__progress-grid">
            {STUDENTS.map((s: Student) => {
              const pkg = getPackage(s.packageId);
              const tutor = TUTORS.find((t) => t.id === s.tutorId);
              return (
                <article key={s.id} className="sm-hub__student-card">
                  <ProgressRing value={s.progress} />
                  <div>
                    <strong>{s.name}</strong>
                    <span className="sm-hub__student-grade">{s.grade} · {s.subjects.join(', ')}</span>
                    <p>{tutor?.name} · {s.sessionsCompleted} sessions</p>
                    <span className="sm-hub__student-pkg">{pkg?.name}</span>
                  </div>
                </article>
              );
            })}
          </div>
        )}

        {page === 'billing' && (
          <>
            <div className="sm-hub__ai-banner">
              <div>
                <strong>
                  <IconSparkle className="sm-hub__sparkle" />
                  Auto billing — {renewalDue.length} renewals due this week
                </strong>
                <p>Invoices queued · one-tap pay links · parent SMS reminders sent 7 days before expiry</p>
              </div>
              <span className="sm-hub__ai-banner-tag">$3,600 pending</span>
            </div>

            <div className="sm-hub__payment-strip">
              {PACKAGES.map((pkg) => {
                const students = STUDENTS.filter((s) => s.packageId === pkg.id);
                return (
                  <article key={pkg.id} className={`sm-hub__pkg-card sm-hub__pkg-card--${pkg.status}`}>
                    <div className="sm-hub__pkg-top">
                      <strong>{pkg.name}</strong>
                      <span className={`sm-hub__pkg-status sm-hub__pkg-status--${pkg.status}`}>
                        {pkg.status === 'renewal-due' ? 'Renewal due' : pkg.status === 'active' ? 'Active' : 'Expired'}
                      </span>
                    </div>
                    <p className="sm-hub__pkg-price">{pkg.price}</p>
                    <p className="sm-hub__pkg-students">{students.map((s) => s.name).join(' · ') || '—'}</p>
                    {pkg.renewsOn && (
                      <footer>
                        <span>Renews {pkg.renewsOn}</span>
                        {pkg.status === 'renewal-due' && (
                          <button type="button" className="sm-hub__pkg-btn">Send reminder</button>
                        )}
                      </footer>
                    )}
                  </article>
                );
              })}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
