import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  CONSULT_SLOTS,
  DOC_CHECKLIST,
  FIRM,
  PARTNERS,
  PRACTICE_AREAS,
  getPartner,
  getPractice,
  slotsForPractice,
  type ConsultSlot,
} from './apexData.ts';
import ApexClientChat from './ApexClientChat.tsx';
import ApexCounselLive from './ApexCounselLive.tsx';
import { ApexLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { onApexImageError } from './apexImageFallback.ts';

type Page = 'home' | 'practice' | 'matter';
type MatterStep = 1 | 2 | 3 | 4;

const TRUST = ['AmLaw 200 counsel', 'SOC2 Type II vault', 'NY & NJ bar'];

const AI_MAGNETS = [
  { id: 'conflict', title: 'Conflict scan', desc: 'Instant clearance before consult' },
  { id: 'clause', title: 'Clause review', desc: 'Risk flags in uploaded contracts' },
  { id: 'vault', title: 'Vault chaser', desc: 'Auto-reminders until files land' },
  { id: 'engage', title: 'Engagement draft', desc: 'Letter pre-filled from matter data' },
];

const UPLOAD_DOCS = [
  { name: 'Entity charter', done: true },
  { name: 'Vendor agreement draft', done: true },
  { name: 'Cap table summary', done: false },
  { name: 'Signer ID', done: false },
];

interface Props {
  onBookConsult: (slot: ConsultSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'ax-site__pane' : 'ax-site__pane ax-site__pane--hidden'}>
      {children}
    </div>
  );
}

export default function ApexClientSite({ onBookConsult }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activePractice, setActivePractice] = useState('corporate');
  const [matterStep, setMatterStep] = useState<MatterStep>(1);
  const [selectedPractice, setSelectedPractice] = useState('corporate');
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const openMatter = (practiceId: string) => {
    setSelectedPractice(practiceId);
    setActivePractice(practiceId);
    setSelectedSlot(null);
    setConfirmed(false);
    setMatterStep(1);
    nav('matter');
  };

  const slots = slotsForPractice(selectedPractice);
  const practiceDetail = getPractice(activePractice);
  const slot = CONSULT_SLOTS.find((s) => s.id === selectedSlot);
  const partner = practiceDetail ? getPartner(practiceDetail.partnerId) : undefined;

  const confirmBooking = () => {
    const s = CONSULT_SLOTS.find((v) => v.id === selectedSlot);
    if (!s) return;
    setConfirmed(true);
    onBookConsult(s);
  };

  return (
    <div className="ax-site ax-site--counsel">
      <header className="ax-site__header ax-site__header--counsel">
        <button type="button" className="ax-site__brand" onClick={() => nav('home')}>
          <ApexLogo className="ax-site__mark" />
          <span className="ax-site__name">{FIRM.name}</span>
        </button>
        <nav className="ax-site__nav" aria-label="Site navigation">
          {(['home', 'practice', 'matter'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`ax-site__nav-link ${page === p ? 'ax-site__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Firm home' : p === 'practice' ? 'Practice areas' : 'Open matter'}
            </button>
          ))}
        </nav>
        <button type="button" className="ax-site__nav-cta" onClick={() => setChatOpen(true)}>
          Ask Counsel AI
        </button>
      </header>

      <div className="ax-site__scroll" ref={scrollRef}>
        <div className="ax-site__main">
          <SitePane id="home" current={page}>
            <section className="ax-counsel-hero">
              <div className="ax-counsel-hero__inner">
                <div className="ax-counsel-hero__copy">
                  <p className="ax-counsel-hero__eyebrow">Counsel AI · not another intake form</p>
                  <h1>
                    Conflict checks, clause review, and vault chasing —
                    <em> before partners bill a minute.</em>
                  </h1>
                  <p className="ax-counsel-hero__sub">
                    Apex runs the admin layer lawyers hate: clearance, document vault, engagement drafts, and partner routing — live in your branded portal.
                  </p>
                  <ul className="ax-counsel-hero__proof">
                    <li><strong>0</strong> conflict surprises</li>
                    <li><strong>55%</strong> less paralegal chase</li>
                    <li><strong>9</strong> billable-ready this week</li>
                  </ul>
                  <div className="ax-counsel-hero__actions">
                    <button type="button" className="ax-site__btn ax-site__btn--gold" onClick={() => openMatter('corporate')}>
                      Run conflict check
                    </button>
                    <button type="button" className="ax-site__btn ax-site__btn--ghost-light" onClick={() => setChatOpen(true)}>
                      Talk to Counsel AI
                    </button>
                  </div>
                  <div className="ax-counsel-hero__trust">
                    {TRUST.map((t) => (
                      <span key={t}>{t}</span>
                    ))}
                  </div>
                </div>
                <ApexCounselLive />
              </div>

              <div className="ax-counsel-hero__magnets">
                {AI_MAGNETS.map((m) => (
                  <article key={m.id} className="ax-counsel-magnet">
                    <span className="ax-counsel-magnet__dot" aria-hidden />
                    <div>
                      <strong>{m.title}</strong>
                      <p>{m.desc}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="ax-counsel-practice">
              <div className="ax-counsel-practice__inner">
                <div className="ax-counsel-practice__nav">
                  <p className="ax-counsel-label">Practice areas</p>
                  <h2>Where Counsel AI qualifies first</h2>
                  <ul>
                    {PRACTICE_AREAS.map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          className={activePractice === p.id ? 'ax-counsel-practice__tab ax-counsel-practice__tab--on' : 'ax-counsel-practice__tab'}
                          onClick={() => setActivePractice(p.id)}
                        >
                          <span>{p.name}</span>
                          <small>{p.fee}</small>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
                {practiceDetail && (
                  <article className="ax-counsel-practice__detail">
                    <img src={practiceDetail.imageUrl} alt="" onError={(e) => onApexImageError(e, practiceDetail.name)} />
                    <div>
                      <span className="ax-counsel-practice__tag">{practiceDetail.category}</span>
                      <h3>{practiceDetail.name}</h3>
                      <p>{practiceDetail.desc}</p>
                      <p className="ax-counsel-practice__partner">Lead partner · {getPartner(practiceDetail.partnerId)?.name}</p>
                      <div className="ax-counsel-practice__ai-note">
                        Counsel AI runs conflict scan + clause review for this practice area automatically.
                      </div>
                      <button type="button" className="ax-site__btn ax-site__btn--gold ax-site__btn--sm" onClick={() => openMatter(practiceDetail.id)}>
                        Open matter
                      </button>
                    </div>
                  </article>
                )}
              </div>
            </section>

            <section className="ax-counsel-vault">
              <div className="ax-counsel-vault__inner">
                <div className="ax-counsel-vault__copy">
                  <p className="ax-counsel-label">Secure vault</p>
                  <h2>Vault chaser AI never lets a file go missing.</h2>
                  <p>Encrypted at rest. Reminders until billable-ready. Partners review complete matters — not attachment hunts.</p>
                </div>
                <div className="ax-counsel-vault__grid">
                  {DOC_CHECKLIST.map((d) => (
                    <div key={d.name} className={`ax-counsel-vault__file ${d.done ? 'ax-counsel-vault__file--done' : 'ax-counsel-vault__file--chase'}`}>
                      <span aria-hidden>{d.done ? '✓' : '◎'}</span>
                      <div>
                        <strong>{d.name}</strong>
                        <small>{d.done ? 'Verified · on file' : 'Vault chaser · reminder live'}</small>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="ax-counsel-partners">
              <p className="ax-counsel-label">Partners</p>
              <h2>Human counsel when AI has done the prep</h2>
              <div className="ax-counsel-partners__row">
                {PARTNERS.map((p) => (
                  <article key={p.id}>
                    <img src={p.imageUrl} alt={p.name} loading="lazy" onError={(e) => onApexImageError(e, p.photoInitial)} />
                    <div>
                      <strong>{p.name}</strong>
                      <span>{p.title}</span>
                      <p>{p.specialties.join(' · ')}</p>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </SitePane>

          <SitePane id="practice" current={page}>
            <section className="ax-counsel-practice ax-counsel-practice--page">
              <header className="ax-counsel-page-head">
                <h1>Practice areas</h1>
                <p>Counsel AI conflict-scans and routes to the right partner.</p>
              </header>
              <div className="ax-counsel-practice-list">
                {PRACTICE_AREAS.map((p) => (
                  <article key={p.id} className="ax-counsel-practice-row">
                    <div>
                      <h3>{p.name}</h3>
                      <p>{p.desc}</p>
                      <span>{p.fee} · {getPartner(p.partnerId)?.name}</span>
                    </div>
                    <button type="button" className="ax-site__btn ax-site__btn--outline-gold ax-site__btn--sm" onClick={() => openMatter(p.id)}>
                      Open matter
                    </button>
                  </article>
                ))}
              </div>
            </section>
          </SitePane>

          <SitePane id="matter" current={page}>
            <section className="ax-counsel-wizard">
              <header className="ax-counsel-wizard__head">
                <h1>Matter onboarding</h1>
                <p>Conflict scan → questionnaire → vault upload → partner consult</p>
              </header>

              <ol className="ax-counsel-wizard__rail">
                {(['Conflict check', 'Matter brief', 'Secure vault', 'Partner consult'] as const).map((label, i) => {
                  const step = (i + 1) as MatterStep;
                  const done = matterStep > step;
                  const active = matterStep === step;
                  return (
                    <li key={label} className={done ? 'ax-counsel-wizard__rail-item--done' : active ? 'ax-counsel-wizard__rail-item--active' : ''}>
                      <span>{step}</span>
                      {label}
                    </li>
                  );
                })}
              </ol>

              <div className="ax-counsel-wizard__layout">
                <div className="ax-counsel-wizard__panel">
                  {!confirmed ? (
                    <>
                      {matterStep === 1 && (
                        <div className="ax-counsel-wizard__step">
                          <h2>Conflict clearance</h2>
                          <p className="ax-counsel-wizard__hint">Counsel AI scans 847 active matters before any consult is offered.</p>
                          <div className="ax-counsel-wizard__scan">
                            <span className="ax-counsel-wizard__scan-pulse" aria-hidden />
                            <div>
                              <strong>Chen LLC · Corporate vendor contract</strong>
                              <p>No conflicts detected · clearance valid 30 days</p>
                            </div>
                          </div>
                          <div className="ax-counsel-wizard__choices">
                            {PRACTICE_AREAS.map((p) => (
                              <button
                                key={p.id}
                                type="button"
                                className={selectedPractice === p.id ? 'ax-counsel-wizard__choice ax-counsel-wizard__choice--on' : 'ax-counsel-wizard__choice'}
                                onClick={() => setSelectedPractice(p.id)}
                              >
                                <strong>{p.name}</strong>
                                <span>{p.desc}</span>
                              </button>
                            ))}
                          </div>
                          <button type="button" className="ax-site__btn ax-site__btn--gold" onClick={() => setMatterStep(2)}>
                            Clearance confirmed — continue
                            <IconArrowRight className="ax-site__btn-icon" />
                          </button>
                        </div>
                      )}

                      {matterStep === 2 && (
                        <div className="ax-counsel-wizard__step">
                          <h2>Matter brief</h2>
                          <div className="ax-counsel-wizard__fields">
                            <label>Client entity<input readOnly value="Chen LLC" /></label>
                            <label>Matter summary<textarea readOnly rows={3} value="Vendor SaaS agreement review — Series A prep. Clause AI will flag indemnity and liability caps." /></label>
                            <label>Timeline<select disabled><option>Within 2 weeks</option></select></label>
                          </div>
                          <div className="ax-counsel-wizard__nav">
                            <button type="button" className="ax-site__btn ax-site__btn--ghost-dark" onClick={() => setMatterStep(1)}>Back</button>
                            <button type="button" className="ax-site__btn ax-site__btn--gold" onClick={() => setMatterStep(3)}>Save &amp; open vault</button>
                          </div>
                        </div>
                      )}

                      {matterStep === 3 && (
                        <div className="ax-counsel-wizard__step">
                          <h2>Secure vault upload</h2>
                          <p className="ax-counsel-wizard__hint">Vault chaser AI reminds until every file is verified.</p>
                          <ul className="ax-counsel-wizard__uploads">
                            {UPLOAD_DOCS.map((d) => (
                              <li key={d.name} className={d.done ? 'ax-counsel-wizard__upload--done' : 'ax-counsel-wizard__upload--chase'}>
                                <span>{d.done ? '✓' : '+'}</span>
                                <div>
                                  <strong>{d.name}</strong>
                                  <small>{d.done ? 'Verified' : 'Vault chaser active'}</small>
                                </div>
                              </li>
                            ))}
                          </ul>
                          <div className="ax-counsel-wizard__nav">
                            <button type="button" className="ax-site__btn ax-site__btn--ghost-dark" onClick={() => setMatterStep(2)}>Back</button>
                            <button type="button" className="ax-site__btn ax-site__btn--gold" onClick={() => setMatterStep(4)}>Continue to consult</button>
                          </div>
                        </div>
                      )}

                      {matterStep === 4 && (
                        <div className="ax-counsel-wizard__step">
                          <h2>Partner consult</h2>
                          <p className="ax-counsel-wizard__hint">{partner?.name} · {getPractice(selectedPractice)?.name}</p>
                          <div className="ax-counsel-wizard__slots">
                            {slots.map((s) => (
                              <button
                                key={s.id}
                                type="button"
                                className={selectedSlot === s.id ? 'ax-counsel-wizard__slot ax-counsel-wizard__slot--on' : 'ax-counsel-wizard__slot'}
                                onClick={() => setSelectedSlot(s.id)}
                              >
                                <strong>{s.day}</strong>
                                <span>{s.time}</span>
                              </button>
                            ))}
                          </div>
                          <div className="ax-counsel-wizard__nav">
                            <button type="button" className="ax-site__btn ax-site__btn--ghost-dark" onClick={() => setMatterStep(3)}>Back</button>
                            <button
                              type="button"
                              className="ax-site__btn ax-site__btn--gold"
                              disabled={!selectedSlot}
                              onClick={confirmBooking}
                            >
                              Confirm matter + book
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="ax-counsel-wizard__done">
                      <ApexLogo className="ax-counsel-wizard__done-logo" />
                      <h2>Matter opened</h2>
                      <p>{slot?.label} · {partner?.name}</p>
                      <span>Conflict cleared · vault active · engagement draft queued</span>
                    </div>
                  )}
                </div>
                <ApexCounselLive compact />
              </div>
            </section>
          </SitePane>
        </div>

        <footer className="ax-site__footer ax-site__footer--counsel">
          <p>© 2026 {FIRM.name} · Attorney advertising · {FIRM.address}</p>
        </footer>
      </div>

      <ApexClientChat open={chatOpen} onOpenChange={setChatOpen} onMatterClick={() => openMatter('corporate')} />
    </div>
  );
}
