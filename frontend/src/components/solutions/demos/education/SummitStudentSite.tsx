import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import {
  SUMMIT,
  SUBJECTS,
  matchTutors,
  BOOKING_SLOTS,
  slotsForSubject,
  getTutor,
  prepDeliveryLabel,
  tutorMatchReasons,
  matchScoreBreakdown,
  PREP_PREVIEW,
  type SessionSlot,
  type Tutor,
  type Subject,
} from './summitData.ts';
import SummitStudentChat from './SummitStudentChat.tsx';
import { SummitLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { onSummitImageError } from './summitImageFallback.ts';

type Page = 'home' | 'subjects' | 'match';
type MatchPhase = 'idle' | 'scanning' | 'results';

const JOURNEY = [
  { step: '1', title: 'Subject + level', desc: 'AI pairs students with tutors by expertise — not whoever has an open slot.' },
  { step: '2', title: 'Prep pack delivered', desc: 'Worksheets, videos, and quizzes land in family inbox 24h before each session.' },
  { step: '3', title: 'Session + progress', desc: 'Tutors teach. Parents get weekly reports. Packages renew automatically.' },
];

const AI_SURFACES = [
  {
    title: 'Tutor match score',
    copy: 'Expertise, scheduling fit, and outcomes broken down before you book.',
    tag: 'Matching',
  },
  {
    title: 'Prep automation',
    copy: 'Material packs assemble the moment a session is confirmed.',
    tag: 'Prep',
  },
  {
    title: 'Parent report teaser',
    copy: 'Weekly progress lands in the family inbox — zero manual emails.',
    tag: 'Reports',
  },
];

const REVIEWS = [
  { name: 'Sarah M.', text: 'Ava matched with Elena in one click — prep packs arrive before every algebra session.', stars: 5 },
  { name: 'David K.', text: 'Noah\'s chemistry tutor sends lab prep automatically. We stopped chasing homework.', stars: 5 },
  { name: 'Lisa T.', text: 'Weekly parent reports without us writing a single email. Worth every penny.', stars: 5 },
];

interface Props {
  onBookSession: (slot: SessionSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'sm-site__pane' : 'sm-site__pane sm-site__pane--hidden'}>
      {children}
    </div>
  );
}

function TutorMatchCard({
  tutor,
  level,
  selected,
  onSelect,
  index,
}: {
  tutor: Tutor;
  level: string;
  selected: boolean;
  onSelect: () => void;
  index: number;
}) {
  const reasons = tutorMatchReasons(tutor, level);
  const breakdown = matchScoreBreakdown(tutor);

  return (
    <article
      className={`sm-site__match-card ${selected ? 'sm-site__match-card--on' : ''}`}
      style={{ animationDelay: `${index * 90}ms` }}
    >
      <div className="sm-site__match-score" aria-label={`${tutor.matchScore}% match`}>
        <strong>{tutor.matchScore}%</strong>
        <span>match</span>
      </div>
      <div className="sm-site__match-media">
        <img
          src={tutor.imageUrl}
          alt={tutor.name}
          loading="lazy"
          onError={(e) => onSummitImageError(e, tutor.photoInitial)}
        />
      </div>
      <div className="sm-site__match-body">
        <h3>{tutor.name}</h3>
        <p className="sm-site__match-title">{tutor.title}</p>
        <p className="sm-site__match-bio">{tutor.bio}</p>
        <div className="sm-site__match-meta">
          <span>★ {tutor.rating}</span>
          <span>{tutor.sessionsThisWeek} sessions/wk</span>
        </div>
        <ul className="sm-site__match-why">
          {reasons.map((r) => (
            <li key={r}>
              <IconSparkle className="sm-site__why-icon" />
              {r}
            </li>
          ))}
        </ul>
        <div className="sm-site__match-breakdown" aria-label="Match score breakdown">
          {breakdown.map((b) => (
            <div key={b.label} className="sm-site__breakdown-row">
              <span>{b.label}</span>
              <div className="sm-site__breakdown-track">
                <div style={{ width: `${(b.value / 40) * 100}%` }} />
              </div>
              <em>{b.value}</em>
            </div>
          ))}
        </div>
        <div className="sm-site__match-specs">
          {tutor.specialties.slice(0, 3).map((s) => (
            <span key={s}>{s}</span>
          ))}
        </div>
        <button type="button" className="sm-site__btn sm-site__btn--primary sm-site__btn--sm" onClick={onSelect}>
          {selected ? 'Selected' : 'Select tutor'}
        </button>
      </div>
    </article>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="sm-site__footer">
      <div className="sm-site__footer-grid">
        <div>
          <p className="sm-site__footer-brand">{SUMMIT.brand}</p>
          <p className="sm-site__footer-muted">{SUMMIT.tagline}</p>
          <p className="sm-site__footer-muted">{SUMMIT.address}</p>
          <p className="sm-site__footer-muted">{SUMMIT.city}</p>
        </div>
        <div>
          <p className="sm-site__footer-heading">Hours</p>
          {SUMMIT.hours.map((h) => (
            <p key={h.days} className="sm-site__footer-muted">
              <span>{h.days}</span> {h.time}
            </p>
          ))}
        </div>
        <div>
          <p className="sm-site__footer-heading">Explore</p>
          <button type="button" className="sm-site__footer-link" onClick={() => onNavigate('subjects')}>Subjects</button>
          <button type="button" className="sm-site__footer-link" onClick={() => onNavigate('match')}>Find a tutor</button>
          <button type="button" className="sm-site__footer-link" onClick={() => onNavigate('home')}>Home</button>
        </div>
        <div>
          <p className="sm-site__footer-heading">Contact</p>
          <p className="sm-site__footer-muted">{SUMMIT.phone}</p>
          <p className="sm-site__footer-muted">{SUMMIT.email}</p>
          <p className="sm-site__footer-legal">Privacy · Terms · Parent portal</p>
        </div>
      </div>
      <p className="sm-site__footer-copy">© 2026 {SUMMIT.name}. All rights reserved.</p>
    </footer>
  );
}

export default function SummitStudentSite({ onBookSession }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedSubject, setSelectedSubject] = useState('math');
  const [selectedLevel, setSelectedLevel] = useState('Algebra II');
  const [levelPickerFor, setLevelPickerFor] = useState<string | null>(null);
  const [selectedTutor, setSelectedTutor] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [matchPhase, setMatchPhase] = useState<MatchPhase>('idle');
  const scanTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const subject = SUBJECTS.find((s) => s.id === selectedSubject)!;
  const matches = matchTutors(selectedSubject, selectedLevel);
  const slots = selectedTutor
    ? slotsForSubject(selectedSubject, selectedLevel, selectedTutor)
    : [];
  const tutor = selectedTutor ? getTutor(selectedTutor) : null;
  const slot = BOOKING_SLOTS.find((s) => s.id === selectedSlot);
  const matchStep = !selectedTutor ? 1 : !selectedSlot ? 2 : 3;

  const runMatchScan = useCallback(() => {
    if (scanTimer.current) clearTimeout(scanTimer.current);
    setMatchPhase('scanning');
    setSelectedTutor(null);
    setSelectedSlot(null);
    setConfirmed(false);
    scanTimer.current = setTimeout(() => setMatchPhase('results'), 1400);
  }, []);

  useEffect(() => () => {
    if (scanTimer.current) clearTimeout(scanTimer.current);
  }, []);

  const startMatch = (subjectId: string, level: string) => {
    setSelectedSubject(subjectId);
    setSelectedLevel(level);
    setLevelPickerFor(null);
    setSelectedTutor(null);
    setSelectedSlot(null);
    setConfirmed(false);
    nav('match');
    runMatchScan();
  };

  const openSubjectLevels = (s: Subject) => {
    setLevelPickerFor((cur) => (cur === s.id ? null : s.id));
  };

  const confirmSession = () => {
    const s = BOOKING_SLOTS.find((v) => v.id === selectedSlot);
    if (!s) return;
    setConfirmed(true);
    onBookSession(s);
  };

  const goFindTutor = () => {
    nav('subjects');
  };

  return (
    <div className="sm-site">
      <header className="sm-site__header">
        <button type="button" className="sm-site__brand" onClick={() => nav('home')}>
          <SummitLogo className="sm-site__mark" />
          <span className="sm-site__name">{SUMMIT.brand}</span>
        </button>
        <nav className="sm-site__nav" aria-label="Site navigation">
          {(['home', 'subjects', 'match'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`sm-site__nav-link ${page === p ? 'sm-site__nav-link--on' : ''}`}
              onClick={() => {
                if (p === 'match' && matchPhase === 'idle') {
                  runMatchScan();
                }
                nav(p);
              }}
            >
              {p === 'home' ? 'Home' : p === 'subjects' ? 'Subjects' : 'Find tutor'}
            </button>
          ))}
        </nav>
        <button type="button" className="sm-site__nav-cta" onClick={() => setChatOpen(true)}>
          Ask AI
        </button>
      </header>

      <div className="sm-site__scroll" ref={scrollRef}>
        <div className="sm-site__main">
          <SitePane id="home" current={page}>
            <section className="sm-site__hero sm-site__hero--slim">
              <img src={SUMMIT.heroImage} alt="" className="sm-site__hero-bg" onError={onSummitImageError} />
              <div className="sm-site__hero-overlay" />
              <div className="sm-site__hero-grid" aria-hidden />
              <div className="sm-site__hero-grain" aria-hidden />
              <div className="sm-site__hero-content">
                <p className="sm-site__hero-brand">{SUMMIT.brand}</p>
                <h1 className="sm-site__hero-title">The right tutor for every subject.</h1>
                <p className="sm-site__hero-sub">
                  AI matches by subject and level — then preps and reports for every session.
                </p>
                <div className="sm-site__hero-actions">
                  <button type="button" className="sm-site__btn sm-site__btn--primary" onClick={goFindTutor}>
                    Find your tutor
                  </button>
                </div>
              </div>
            </section>

            <section className="sm-site__section sm-site__ai-surfaces">
              <div className="sm-site__section-head">
                <p className="sm-site__eyebrow">Built-in AI</p>
                <h2>Matching, prep, and reports — automated</h2>
              </div>
              <div className="sm-site__ai-grid">
                {AI_SURFACES.map((a) => (
                  <article key={a.title} className="sm-site__ai-card">
                    <span className="sm-site__ai-tag">{a.tag}</span>
                    <h3>{a.title}</h3>
                    <p>{a.copy}</p>
                  </article>
                ))}
              </div>
              <div className="sm-site__prep-strip" aria-label="Prep automation preview">
                <div className="sm-site__prep-strip-label">
                  <IconSparkle className="sm-site__prep-spark" />
                  <strong>Prep pack preview</strong>
                  <span>Auto-built 24h before session</span>
                </div>
                <ul>
                  {PREP_PREVIEW.map((m) => (
                    <li key={m.name}>
                      <span>{m.type}</span>
                      {m.name}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="sm-site__report-teaser">
                <div>
                  <p className="sm-site__eyebrow">Parent report</p>
                  <h3>Weekly progress without writing a thing</h3>
                  <p>Sessions completed · homework status · next-week focus — delivered to the family inbox.</p>
                </div>
                <div className="sm-site__report-mock" aria-hidden>
                  <strong>Ava M. · Algebra II</strong>
                  <span>2 sessions · 4/5 homework · Focus: systems</span>
                  <em>94% parent satisfaction</em>
                </div>
              </div>
            </section>

            <section className="sm-site__section">
              <div className="sm-site__section-head">
                <h2>How Summit works</h2>
              </div>
              <div className="sm-site__journey">
                {JOURNEY.map((j) => (
                  <article key={j.step} className="sm-site__journey-card">
                    <span className="sm-site__journey-step">{j.step}</span>
                    <h3>{j.title}</h3>
                    <p>{j.desc}</p>
                  </article>
                ))}
              </div>
            </section>

            <section className="sm-site__section sm-site__section--muted">
              <div className="sm-site__section-head">
                <h2>Featured Algebra II matches</h2>
                <p>Live pairing from the same matcher families use on the student site.</p>
              </div>
              <div className="sm-site__match-row">
                {matchTutors('math', 'Algebra II').slice(0, 2).map((t, i) => (
                  <TutorMatchCard
                    key={t.id}
                    tutor={t}
                    level="Algebra II"
                    selected={false}
                    index={i}
                    onSelect={() => startMatch('math', 'Algebra II')}
                  />
                ))}
              </div>
            </section>

            <section className="sm-site__section">
              <div className="sm-site__section-head">
                <h2>What families say</h2>
              </div>
              <div className="sm-site__reviews">
                {REVIEWS.map((r) => (
                  <blockquote key={r.name} className="sm-site__review">
                    <p>&ldquo;{r.text}&rdquo;</p>
                    <footer>
                      <strong>{r.name}</strong>
                      <span>{'★'.repeat(r.stars)}</span>
                    </footer>
                  </blockquote>
                ))}
              </div>
            </section>

            <SiteFooter onNavigate={nav} />
          </SitePane>

          <SitePane id="subjects" current={page}>
            <section className="sm-site__subjects-hero">
              <div className="sm-site__subjects-hero-bg" aria-hidden />
              <p className="sm-site__eyebrow">Subject discovery</p>
              <h1>Choose what you need help with</h1>
              <p>Pick a subject, then a level — AI ranks tutors who actually teach that band.</p>
            </section>

            <div className="sm-site__subject-grid">
              {SUBJECTS.map((s) => {
                const open = levelPickerFor === s.id;
                return (
                  <article
                    key={s.id}
                    className={`sm-site__subject-tile ${open ? 'sm-site__subject-tile--open' : ''}`}
                    style={{ '--sm-subject-accent': s.accent } as CSSProperties}
                  >
                    <button
                      type="button"
                      className="sm-site__subject-tile-hit"
                      onClick={() => openSubjectLevels(s)}
                      aria-expanded={open}
                    >
                      <div className="sm-site__subject-art">
                        <img src={s.artUrl} alt="" loading="lazy" onError={onSummitImageError} />
                        <span className="sm-site__subject-icon-badge">{s.icon}</span>
                      </div>
                      <div className="sm-site__subject-copy">
                        <h3>{s.name}</h3>
                        <p>{s.blurb}</p>
                        <span className="sm-site__subject-range">
                          {s.levels[0]} → {s.levels[s.levels.length - 1]}
                        </span>
                      </div>
                    </button>

                    <div className={`sm-site__level-stage ${open ? 'sm-site__level-stage--open' : ''}`}>
                      <p className="sm-site__level-stage-label">Select your level</p>
                      <div className="sm-site__level-pills">
                        {s.levels.map((lvl) => (
                          <button
                            key={lvl}
                            type="button"
                            className="sm-site__level-pill"
                            onClick={() => startMatch(s.id, lvl)}
                          >
                            <strong>{lvl}</strong>
                            <span>Match tutors</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  </article>
                );
              })}
            </div>
            <SiteFooter onNavigate={nav} />
          </SitePane>

          <SitePane id="match" current={page}>
            <section className="sm-site__match-hero">
              <p className="sm-site__eyebrow">Live tutor matching</p>
              <h1>
                {matchPhase === 'scanning'
                  ? `Scanning tutors for ${selectedLevel}…`
                  : `AI matched ${matches.length} tutor${matches.length === 1 ? '' : 's'} for ${selectedLevel}`}
              </h1>
              <p>
                {subject.name} · {selectedLevel} — ranked by expertise, fit, and outcomes.
              </p>
            </section>

            <div className="sm-site__match-flow">
              <div className="sm-site__match-steps" aria-label="Match progress">
                <span className={matchStep >= 1 ? 'sm-site__match-step sm-site__match-step--on' : 'sm-site__match-step'}>1 · Subject</span>
                <span className={matchStep >= 2 ? 'sm-site__match-step sm-site__match-step--on' : 'sm-site__match-step'}>2 · Tutor</span>
                <span className={matchStep >= 3 ? 'sm-site__match-step sm-site__match-step--on' : 'sm-site__match-step'}>3 · Session</span>
              </div>

              <div className="sm-site__match-filters">
                <label>
                  Subject
                  <select
                    value={selectedSubject}
                    onChange={(e) => {
                      const sub = SUBJECTS.find((s) => s.id === e.target.value)!;
                      setSelectedSubject(sub.id);
                      const nextLevel = sub.levels.includes(selectedLevel) ? selectedLevel : sub.levels[0];
                      setSelectedLevel(nextLevel);
                      runMatchScan();
                    }}
                  >
                    {SUBJECTS.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Level
                  <select
                    value={selectedLevel}
                    onChange={(e) => {
                      const lvl = e.target.value;
                      setSelectedLevel(lvl);
                      runMatchScan();
                    }}
                  >
                    {subject.levels.map((lvl) => (
                      <option key={lvl} value={lvl}>{lvl}</option>
                    ))}
                  </select>
                </label>
              </div>

              {matchPhase === 'scanning' && (
                <div className="sm-site__scan" role="status" aria-live="polite">
                  <div className="sm-site__scan-orb" aria-hidden />
                  <div className="sm-site__scan-beam" aria-hidden />
                  <p>
                    <IconSparkle className="sm-site__prep-spark" />
                    Matching tutors for <strong>{selectedLevel}</strong>…
                  </p>
                  <div className="sm-site__scan-bars">
                    <span /><span /><span />
                  </div>
                </div>
              )}

              {matchPhase === 'results' && (
                <>
                  <div className="sm-site__match-banner">
                    <IconSparkle className="sm-site__prep-spark" />
                    <strong>
                      AI matched {matches.length} tutor{matches.length === 1 ? '' : 's'} for {selectedLevel}
                    </strong>
                    <span>Why-this-match reasons + score breakdown on each card</span>
                  </div>

                  {matches.length === 0 ? (
                    <p className="sm-site__slot-empty">No tutors for this level yet — try an adjacent band or ask AI.</p>
                  ) : (
                    <div className="sm-site__match-grid">
                      {matches.map((t, i) => (
                        <TutorMatchCard
                          key={t.id}
                          tutor={t}
                          level={selectedLevel}
                          selected={selectedTutor === t.id}
                          index={i}
                          onSelect={() => {
                            setSelectedTutor(t.id);
                            setSelectedSlot(null);
                            setConfirmed(false);
                          }}
                        />
                      ))}
                    </div>
                  )}

                  <div className="sm-site__prep-strip sm-site__prep-strip--inline">
                    <div className="sm-site__prep-strip-label">
                      <IconSparkle className="sm-site__prep-spark" />
                      <strong>Prep pack will queue on confirm</strong>
                    </div>
                    <ul>
                      {PREP_PREVIEW.map((m) => (
                        <li key={m.name}>
                          <span>{m.type}</span>
                          {m.name}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}

              {selectedTutor && matchPhase === 'results' && (
                <div className="sm-site__slot-panel">
                  <h3>Available sessions with {tutor?.name}</h3>
                  <p className="sm-site__slot-hint">Showing only slots for this tutor · {selectedLevel}</p>
                  {slots.length > 0 ? (
                    <div className="sm-site__slot-list">
                      {slots.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          className={selectedSlot === s.id ? 'sm-site__slot sm-site__slot--on' : 'sm-site__slot'}
                          onClick={() => {
                            setSelectedSlot(s.id);
                            setConfirmed(false);
                          }}
                        >
                          <strong>{s.day} · {s.time}</strong>
                          <span>{s.level} · {s.durationMin} min</span>
                          <small>Prep pack auto-sent {prepDeliveryLabel(s)}</small>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="sm-site__slot-empty">No open slots for this tutor — AI waitlist will notify when one opens.</p>
                  )}
                </div>
              )}

              {selectedSlot && !confirmed && slot && (
                <div className="sm-site__confirm-bar">
                  <div>
                    <strong>{slot.label}</strong>
                    <p>With {tutor?.name} · Prep pack queued for {prepDeliveryLabel(slot)} · Parent report enabled</p>
                  </div>
                  <button type="button" className="sm-site__btn sm-site__btn--primary" onClick={confirmSession}>
                    Confirm session
                  </button>
                </div>
              )}

              {confirmed && slot && (
                <div className="sm-site__confirmed">
                  <strong>Session confirmed ✓</strong>
                  <p>
                    {slot.label} — prep materials will arrive in the family inbox {prepDeliveryLabel(slot)}.
                  </p>
                </div>
              )}
            </div>

            <SiteFooter onNavigate={nav} />
          </SitePane>
        </div>
      </div>

      <SummitStudentChat
        open={chatOpen}
        onOpenChange={setChatOpen}
        onMatchClick={() => {
          setChatOpen(false);
          runMatchScan();
          nav('match');
        }}
      />
    </div>
  );
}
