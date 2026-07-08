import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  CLASS_SLOTS,
  COACHES,
  PROGRAMS,
  PROGRAM_SECTIONS,
  STUDIO,
  getCoach,
  getProgram,
  slotsForProgram,
  type ClassSlot,
  type Program,
} from './peakformData.ts';
import PeakFormMemberChat from './PeakFormMemberChat.tsx';
import { PeakFormLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { onPeakformImageError } from './peakformImageFallback.ts';

type Page = 'home' | 'programs' | 'book';

const HERO_STATS = [
  { label: 'Active members', value: '142' },
  { label: 'Class fill', value: '89%' },
  { label: 'Avg streak', value: '18 days' },
];

const JOURNEY = [
  { step: '1', title: 'Pick your program', desc: 'HIIT, strength, recovery — every class on one schedule, no app hopping.' },
  { step: '2', title: 'Adherence coach', desc: 'Coach AI reschedules classes, logs PRs, and nudges you before streaks break.' },
  { step: '3', title: 'Track progress', desc: 'Check-ins, PRs, and streaks — coaches see adherence before renewals slip.' },
];

const REVIEWS = [
  { name: 'Jordan K.', text: 'Moved my HIIT to Thursday in the app — coach had my program updated before I walked in.', stars: 5 },
  { name: 'Sam L.', text: 'Free trial felt premium, not a sales trap. Derek fixed my squat on day two.', stars: 5 },
  { name: 'Priya M.', text: 'Streak notifications actually work. Haven\'t missed a week in two months.', stars: 5 },
];

interface Props {
  onBookClass: (slot: ClassSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'pf-site__pane' : 'pf-site__pane pf-site__pane--hidden'}>
      {children}
    </div>
  );
}

function ProgramCard({ program, onBook }: { program: Program; onBook: (id: string) => void }) {
  const coach = getCoach(program.coachId);
  return (
    <article className={`pf-site__program-card ${program.tag ? 'pf-site__program-card--featured' : ''}`}>
      <div className="pf-site__program-media">
        <img src={program.imageUrl} alt={program.name} loading="lazy" onError={(e) => onPeakformImageError(e, program.name)} />
        <div className="pf-site__program-shade" aria-hidden />
        {program.tag && <span className="pf-site__program-badge">{program.tag}</span>}
        <span className="pf-site__program-price">{program.price}</span>
      </div>
      <div className="pf-site__program-body">
        <h3>{program.name}</h3>
        <p className="pf-site__program-cat">{program.category} · {program.duration}</p>
        <p>{program.desc}</p>
        {coach && <span className="pf-site__program-coach">With {coach.name}</span>}
        <button type="button" className="pf-site__btn pf-site__btn--primary pf-site__btn--sm" onClick={() => onBook(program.id)}>
          Book class
        </button>
      </div>
    </article>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="pf-site__footer">
      <div className="pf-site__footer-grid">
        <div>
          <p className="pf-site__footer-brand">{STUDIO.name}</p>
          <p className="pf-site__footer-muted">{STUDIO.tagline}</p>
          <p className="pf-site__footer-muted">{STUDIO.address}</p>
          <p className="pf-site__footer-muted">{STUDIO.city}</p>
        </div>
        <div>
          <p className="pf-site__footer-heading">Train</p>
          <button type="button" className="pf-site__footer-link" onClick={() => onNavigate('programs')}>Programs</button>
          <button type="button" className="pf-site__footer-link" onClick={() => onNavigate('book')}>Book a class</button>
          <button type="button" className="pf-site__footer-link" onClick={() => onNavigate('home')}>Home</button>
        </div>
        <div>
          <p className="pf-site__footer-heading">Contact</p>
          <p className="pf-site__footer-muted">{STUDIO.phone}</p>
          <p className="pf-site__footer-muted">{STUDIO.email}</p>
          <p className="pf-site__footer-legal">Privacy · Terms · Waiver</p>
        </div>
      </div>
      <p className="pf-site__footer-copy">© 2026 {STUDIO.name}. All rights reserved.</p>
    </footer>
  );
}

export default function PeakFormMemberSite({ onBookClass }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedProgram, setSelectedProgram] = useState<string>('hiit');
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const startBooking = (programId: string) => {
    setSelectedProgram(programId);
    setSelectedSlot(null);
    setConfirmed(false);
    nav('book');
  };

  const slots = slotsForProgram(selectedProgram);
  const program = getProgram(selectedProgram);
  const slot = CLASS_SLOTS.find((s) => s.id === selectedSlot);
  const bookStep = !selectedSlot ? 1 : 2;

  const confirmBooking = () => {
    const s = CLASS_SLOTS.find((v) => v.id === selectedSlot);
    if (!s) return;
    setConfirmed(true);
    onBookClass(s);
  };

  return (
    <div className="pf-site">
      <header className="pf-site__header">
        <button type="button" className="pf-site__brand" onClick={() => nav('home')}>
          <PeakFormLogo className="pf-site__mark" />
          <span className="pf-site__name">{STUDIO.name}</span>
        </button>
        <nav className="pf-site__nav" aria-label="Site navigation">
          {(['home', 'programs', 'book'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`pf-site__nav-link ${page === p ? 'pf-site__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Home' : p === 'programs' ? 'Programs' : 'Book class'}
            </button>
          ))}
        </nav>
        <button type="button" className="pf-site__nav-cta" onClick={() => setChatOpen(true)}>
          Ask AI
        </button>
      </header>

      <div className="pf-site__scroll" ref={scrollRef}>
        <div className="pf-site__main">
          <SitePane id="home" current={page}>
            <section className="pf-site__hero">
              <img src={STUDIO.heroImage} alt="" className="pf-site__hero-bg" onError={onPeakformImageError} />
              <div className="pf-site__hero-overlay" />
              <div className="pf-site__hero-grain" aria-hidden />
              <div className="pf-site__hero-content">
                <p className="pf-site__hero-eyebrow">SoHo · Small-group coaching · AI check-ins</p>
                <div className="pf-site__ai-chips" aria-label="AI capabilities">
                  <span>Class fit AI</span>
                  <span>Streak keeper</span>
                  <span>Churn alerts</span>
                </div>
                <h1 className="pf-site__hero-title">
                  Stop losing members
                  <span>to silent churn.</span>
                </h1>
                <p className="pf-site__hero-sub">
                  Adherence coach AI saves streaks, reschedules in one tap, and flags who needs a nudge before they cancel.
                </p>
                <div className="pf-site__ai-magnet" aria-label="AI proof">
                  <div><strong>89%</strong><span>30-day retain</span></div>
                  <div><strong>12</strong><span>day avg streak</span></div>
                  <div><strong>18d</strong><span>early churn warn</span></div>
                </div>
                <div className="pf-site__hero-actions">
                  <button type="button" className="pf-site__btn pf-site__btn--primary" onClick={() => nav('book')}>
                    Start free trial
                  </button>
                  <button type="button" className="pf-site__btn pf-site__btn--ghost" onClick={() => setChatOpen(true)}>
                    Talk to coach AI
                  </button>
                </div>
              </div>
            </section>

            <div className="pf-site__hero-stats">
              {HERO_STATS.map((s) => (
                <div key={s.label} className="pf-site__stat">
                  <strong>{s.value}</strong>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>

            <section className="pf-site__journey">
              <div className="pf-site__section-inner">
                <h2 className="pf-site__section-title">From signup to streak</h2>
                <div className="pf-site__journey-grid">
                  {JOURNEY.map((step) => (
                    <article key={step.step} className="pf-site__journey-card">
                      <span className="pf-site__journey-num">{step.step}</span>
                      <h3>{step.title}</h3>
                      <p>{step.desc}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="pf-site__featured">
              <div className="pf-site__section-inner">
                <div className="pf-site__featured-head">
                  <div>
                    <p className="pf-site__section-eyebrow">This week</p>
                    <h2 className="pf-site__section-title">Popular classes</h2>
                  </div>
                  <button type="button" className="pf-site__link-btn" onClick={() => nav('programs')}>
                    All programs
                    <IconArrowRight className="pf-site__link-icon" />
                  </button>
                </div>
                <div className="pf-site__program-scroll">
                  {PROGRAMS.slice(0, 3).map((p) => (
                    <article key={p.id} className="pf-site__scroll-card">
                      <div className="pf-site__scroll-media">
                        <img src={p.imageUrl} alt={p.name} loading="lazy" onError={(e) => onPeakformImageError(e, p.name)} />
                        {p.tag && <span className="pf-site__scroll-tag">{p.tag}</span>}
                      </div>
                      <div className="pf-site__scroll-body">
                        <h3>{p.name}</h3>
                        <p>{p.desc}</p>
                        <div className="pf-site__scroll-foot">
                          <strong>{p.price}</strong>
                          <button type="button" onClick={() => startBooking(p.id)}>Book</button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="pf-site__home-programs">
              <div className="pf-site__section-inner">
                <p className="pf-site__section-eyebrow">Full schedule</p>
                <h2 className="pf-site__section-title">Every program on one page</h2>
                <p className="pf-site__home-programs-lead">Scroll the full catalog — book direct, no third-party apps.</p>
                {PROGRAM_SECTIONS.map((section) => (
                  <div key={section.id} className="pf-site__home-programs-section">
                    <h3>{section.title}</h3>
                    <div className="pf-site__program-grid">
                      {section.items.map((p) => (
                        <ProgramCard key={p.id} program={p} onBook={startBooking} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="pf-site__coaches">
              <div className="pf-site__section-inner">
                <p className="pf-site__section-eyebrow">Your coaches</p>
                <h2 className="pf-site__section-title">People who push (and protect)</h2>
                <div className="pf-site__coaches-grid">
                  {COACHES.map((c) => (
                    <article key={c.id} className="pf-site__coach-card">
                      <div className="pf-site__coach-photo">
                        <img src={c.imageUrl} alt={c.name} loading="lazy" onError={(e) => onPeakformImageError(e, c.photoInitial)} />
                      </div>
                      <h3>{c.name}</h3>
                      <p className="pf-site__coach-title">{c.title}</p>
                      <div className="pf-site__coach-tags">
                        {c.specialties.map((t) => <span key={t}>{t}</span>)}
                      </div>
                      <button type="button" className="pf-site__btn pf-site__btn--outline pf-site__btn--sm" onClick={() => nav('book')}>
                        Train with {c.name.split(' ')[0]}
                      </button>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="pf-site__trial-cta">
              <img src={STUDIO.trialImage} alt="" className="pf-site__trial-photo" onError={onPeakformImageError} />
              <div className="pf-site__trial-shade" aria-hidden />
              <div className="pf-site__trial-inner">
                <p className="pf-site__section-eyebrow pf-site__section-eyebrow--light">Free trial</p>
                <h2>Your first week is on us</h2>
                <p>Unlimited classes · coach intro · no card required.</p>
                <button type="button" className="pf-site__btn pf-site__btn--primary" onClick={() => nav('book')}>
                  Claim free week
                </button>
              </div>
            </section>

            <section className="pf-site__reviews">
              <div className="pf-site__section-inner">
                <h2 className="pf-site__section-title">What members say</h2>
                <div className="pf-site__review-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="pf-site__review">
                      <p>&ldquo;{r.text}&rdquo;</p>
                      <footer>{'★'.repeat(r.stars)} · {r.name}</footer>
                    </blockquote>
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="programs" current={page}>
            <section className="pf-site__programs-page">
              <header className="pf-site__page-hero">
                <img src={STUDIO.programsHeroImage} alt="" className="pf-site__page-hero-photo" onError={onPeakformImageError} />
                <div className="pf-site__page-hero-bg" aria-hidden />
                <div className="pf-site__page-hero-inner">
                  <p className="pf-site__section-eyebrow pf-site__section-eyebrow--light">Live schedule</p>
                  <h1>Programs</h1>
                  <p>{PROGRAMS.length} class types · updated daily</p>
                </div>
              </header>
              <div className="pf-site__section-inner">
                {PROGRAM_SECTIONS.map((section) => (
                  <div key={section.id} className="pf-site__home-programs-section">
                    <h3>{section.title}</h3>
                    <div className="pf-site__program-grid">
                      {section.items.map((p) => (
                        <ProgramCard key={p.id} program={p} onBook={startBooking} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </SitePane>

          <SitePane id="book" current={page}>
            <section className="pf-site__book-page">
              <div className="pf-site__book-layout">
                <aside className="pf-site__book-aside">
                  <img src={program?.imageUrl || STUDIO.heroImage} alt="" className="pf-site__book-photo" onError={onPeakformImageError} />
                  <div className="pf-site__book-aside-shade" aria-hidden />
                  <div className="pf-site__book-aside-inner">
                    <PeakFormLogo className="pf-site__book-mark" />
                    <p className="pf-site__section-eyebrow pf-site__section-eyebrow--light">Book a class</p>
                    <h1>Grab your spot</h1>
                    <p>Live coach calendars — instant confirm + progress tracking.</p>
                    {program && (
                      <div className="pf-site__book-program-pick">
                        <strong>{program.name}</strong>
                        <span>{program.price} · {program.duration}</span>
                      </div>
                    )}
                  </div>
                </aside>
                <div className="pf-site__book-main">
                  <div className="pf-site__book-panel">
                    {!confirmed ? (
                      <>
                        <header className="pf-site__book-panel-head">
                          <div>
                            <h2>Pick your time</h2>
                            <p>Live class availability</p>
                          </div>
                          <div className="pf-site__book-steps">
                            <span className={bookStep >= 1 ? 'pf-site__step pf-site__step--on' : 'pf-site__step'}>Program</span>
                            <span className="pf-site__step-line" aria-hidden />
                            <span className={bookStep >= 2 ? 'pf-site__step pf-site__step--on' : 'pf-site__step'}>Time</span>
                          </div>
                        </header>
                        <label className="pf-site__book-label">Which program?</label>
                        <div className="pf-site__book-programs">
                          {PROGRAMS.map((p) => (
                            <button
                              key={p.id}
                              type="button"
                              className={`pf-site__book-program-btn ${selectedProgram === p.id ? 'pf-site__book-program-btn--on' : ''}`}
                              onClick={() => { setSelectedProgram(p.id); setSelectedSlot(null); }}
                            >
                              <strong>{p.name}</strong>
                              <span>{p.price}</span>
                            </button>
                          ))}
                        </div>
                        <label className="pf-site__book-label">Available classes</label>
                        <div className="pf-site__book-slots">
                          {slots.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              className={`pf-site__book-slot ${selectedSlot === s.id ? 'pf-site__book-slot--on' : ''}`}
                              onClick={() => setSelectedSlot(s.id)}
                            >
                              <strong>{s.time}</strong>
                              <span>{s.day}</span>
                              <small>{getCoach(s.coachId)?.name}</small>
                            </button>
                          ))}
                        </div>
                        {selectedSlot && (
                          <div className="pf-site__book-confirm-bar">
                            <div>
                              <p>Your class</p>
                              <strong>{slot?.label}</strong>
                            </div>
                            <button type="button" className="pf-site__btn pf-site__btn--primary" onClick={confirmBooking}>
                              Confirm
                              <IconArrowRight className="pf-site__btn-icon" />
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="pf-site__confirmed">
                        <span className="pf-site__confirmed-ring" aria-hidden />
                        <PeakFormLogo className="pf-site__confirmed-logo" />
                        <h2>Class booked.</h2>
                        <p className="pf-site__confirmed-slot">{slot?.label}</p>
                        <p className="pf-site__confirmed-note">Calendar invite sent · coach briefed · see you Thursday</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </section>
          </SitePane>
        </div>
        <SiteFooter onNavigate={nav} />
      </div>

      <PeakFormMemberChat open={chatOpen} onOpenChange={setChatOpen} onBookClick={() => nav('book')} />
    </div>
  );
}
