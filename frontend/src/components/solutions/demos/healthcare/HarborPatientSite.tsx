import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  CLINIC,
  PUBLISHED_TREATMENTS,
  WEBSITE_TEAM,
  BOOKING_SLOTS,
  slotsForTreatment,
  getPractitioner,
  getRoom,
  type TimeSlot,
} from './harborData';
import HarborPatientChat from './HarborPatientChat';
import { SitePageHeader } from './HarborPageChrome';

type Page = 'home' | 'treatments' | 'providers' | 'about' | 'book' | 'contact' | 'portal' | 'faq';

const FAQ = [
  { q: 'How do I book online?', a: 'Choose a treatment, pick an open slot, and confirm. You\'ll get intake forms by email within minutes.' },
  { q: 'Can I chat before booking?', a: 'Yes — use the chat bubble on any page. Harbor AI answers pricing, availability, and prep questions 24/7.' },
  { q: 'What should I bring?', a: 'A valid ID and completed intake form. No clipboard at check-in — forms are digital.' },
  { q: 'Cancellation policy?', a: 'Free cancellation up to 24 hours before your visit. Reschedule anytime via chat or patient portal.' },
];

const REVIEWS = [
  { name: 'Amanda L.', text: 'Booked online at 10pm, form was done before I arrived. Seamless.', stars: 5 },
  { name: 'Michael T.', text: 'Dr. Chen explained everything clearly. The clinic feels premium but warm.', stars: 5 },
  { name: 'Rachel S.', text: 'Hydrafacial in Treatment Room 2 — spotless, calm, on time.', stars: 5 },
];

interface Props {
  onBook: (slot: TimeSlot) => void;
}

type TeamMember = (typeof WEBSITE_TEAM)[number];

function PractitionerPhoto({ person, size = 'md' }: { person: TeamMember; size?: 'sm' | 'md' | 'lg' | 'xl' }) {
  return (
    <div className={`hc-site__photo hc-site__photo--${size}`}>
      <img src={person.imageUrl} alt={person.name} loading="eager" decoding="async" />
    </div>
  );
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  if (current !== id) return null;
  return <div className="hc-site__pane">{children}</div>;
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="hc-site__footer">
      <div className="hc-site__footer-grid">
        <div>
          <p className="hc-site__footer-brand">{CLINIC.name}</p>
          <p className="hc-site__footer-muted">{CLINIC.tagline}</p>
          <p className="hc-site__footer-muted">{CLINIC.address}</p>
          <p className="hc-site__footer-muted">{CLINIC.city}</p>
        </div>
        <div>
          <p className="hc-site__footer-heading">Hours</p>
          {CLINIC.hours.map((h) => (
            <p key={h.days} className="hc-site__footer-muted">
              <span>{h.days}</span> {h.time}
            </p>
          ))}
        </div>
        <div>
          <p className="hc-site__footer-heading">Explore</p>
          {(['treatments', 'providers', 'about', 'book', 'contact'] as Page[]).map((p) => (
            <button key={p} type="button" className="hc-site__footer-link" onClick={() => onNavigate(p)}>
              {p === 'book' ? 'Book online' : p.charAt(0).toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
        <div>
          <p className="hc-site__footer-heading">Contact</p>
          <p className="hc-site__footer-muted">{CLINIC.phone}</p>
          <p className="hc-site__footer-muted">{CLINIC.email}</p>
          <p className="hc-site__footer-legal">Privacy · Terms · HIPAA notice</p>
        </div>
      </div>
      <p className="hc-site__footer-copy">© 2026 {CLINIC.name}. All rights reserved.</p>
    </footer>
  );
}

export default function HarborPatientSite({ onBook }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedTreatment, setSelectedTreatment] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [expandedTreatment, setExpandedTreatment] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const startBook = (treatmentId: string) => {
    setSelectedTreatment(treatmentId);
    setSelectedSlot(null);
    setConfirmed(false);
    nav('book');
  };

  const confirmBooking = () => {
    const slot = BOOKING_SLOTS.find((s) => s.id === selectedSlot);
    if (!slot) return;
    setConfirmed(true);
    onBook(slot);
  };

  const treatment = PUBLISHED_TREATMENTS.find((t) => t.id === selectedTreatment);
  const availableSlots = selectedTreatment ? slotsForTreatment(selectedTreatment) : BOOKING_SLOTS;
  const featuredDoctor = WEBSITE_TEAM[0];

  const navItems: { id: Page; label: string }[] = [
    { id: 'home', label: 'Home' },
    { id: 'treatments', label: 'Treatments' },
    { id: 'providers', label: 'Our team' },
    { id: 'book', label: 'Book' },
    { id: 'portal', label: 'My portal' },
    { id: 'faq', label: 'FAQ' },
    { id: 'contact', label: 'Contact' },
  ];

  return (
    <div className="hc-site">
      <header className="hc-site__header">
        <button type="button" className="hc-site__brand" onClick={() => nav('home')}>
          <span className="hc-site__logo">H</span>
          <span>{CLINIC.name}</span>
        </button>
        <nav className="hc-site__nav" aria-label="Patient site">
          {navItems.map((item) => (
            <button key={item.id} type="button" onClick={() => nav(item.id)} className={page === item.id ? 'hc-site__nav-link hc-site__nav-link--active' : 'hc-site__nav-link'}>
              {item.label}
            </button>
          ))}
        </nav>
        <button type="button" className="hc-site__cta" onClick={() => nav('book')}>Book now</button>
      </header>

      <div className="hc-site__scroll" ref={scrollRef}>
      <div className="hc-site__main">
        <SitePane id="home" current={page}>
            <section className="hc-site__hero hc-site__hero--cinematic">
              <div className="hc-site__hero-mesh" />
              <div className="hc-site__hero-grid">
                <div>
                  <span className="hc-site__badge">Clinical intake AI · digital forms · 24/7</span>
                  <h1 className="hc-site__hero-title">Patients book at midnight. Your staff wake up ready.</h1>
                  <p className="hc-site__hero-sub">Harbor Intake AI sends forms, checks insurance basics, and locks slots — no hold music, no clipboards.</p>
                  <div className="hc-site__ai-magnet" aria-label="AI proof">
                    <div><strong>38</strong><span>after-hours books</span></div>
                    <div><strong>12s</strong><span>avg AI reply</span></div>
                    <div><strong>−40%</strong><span>phone time</span></div>
                  </div>
                  <div className="hc-site__hero-actions">
                    <button type="button" className="hc-site__btn-primary" onClick={() => nav('book')}>Book appointment</button>
                    <button type="button" className="hc-site__btn-ghost" onClick={() => setChatOpen(true)}>Try intake AI</button>
                  </div>
                  <div className="hc-site__trust"><span>★ 4.9</span><span>380+ patients</span><span>Board-certified</span></div>
                </div>
                <div className="hc-site__hero-aside">
                  <div className="hc-site__hero-media">
                    <img src={featuredDoctor.imageUrl} alt={featuredDoctor.name} className="hc-site__hero-doc" loading="eager" decoding="async" />
                    <img src={CLINIC.clinicImage} alt="Harbor Wellness clinic interior" className="hc-site__hero-clinic" loading="lazy" decoding="async" />
                  </div>
                  <div className="hc-site__hero-card hc-site__hero-card--glass">
                    <div className="hc-site__hero-card-doc">
                      <PractitionerPhoto person={featuredDoctor} size="sm" />
                      <div>
                        <p className="hc-site__hero-card-doc-name">{featuredDoctor.name}</p>
                        <p className="hc-site__hero-card-doc-title">{featuredDoctor.title}</p>
                      </div>
                    </div>
                    <p className="hc-site__hero-card-label">Next availability</p>
                    <p className="hc-site__hero-card-time">Thursday · 2:30 PM</p>
                    <p className="hc-site__hero-card-svc">Botox consult · {featuredDoctor.name}</p>
                    <p className="hc-site__hero-card-room">Consult Suite A</p>
                  </div>
                </div>
              </div>
            </section>
            <section className="hc-site__journey">
              <div className="hc-site__section-inner">
                <h2 className="hc-site__section-title">Your visit, step by step</h2>
                <div className="hc-site__journey-grid">
                  {[
                    ['1', 'Chat or book', 'Ask Harbor Intake AI — slots, pricing, insurance basics in seconds.'],
                    ['2', 'Digital intake', 'Forms emailed before the visit. Arrive ready — no clipboard.'],
                    ['3', 'Walk in calm', 'Reminders sent. Room + provider already matched.'],
                  ].map(([n, t, d]) => (
                    <article key={n} className="hc-site__journey-card">
                      <span className="hc-site__journey-num">{n}</span>
                      <h3>{t}</h3>
                      <p>{d}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>
            <section className="hc-site__section hc-site__section--light">
              <div className="hc-site__section-inner">
                <h2 className="hc-site__section-title">Popular treatments</h2>
                <div className="hc-site__treatment-grid hc-site__treatment-grid--home">
                  {PUBLISHED_TREATMENTS.slice(0, 3).map((t) => (
                    <article key={t.id} className="hc-site__treatment hc-site__treatment--glass">
                      <span className="hc-site__treatment-icon" aria-hidden>{t.icon}</span>
                      <span className="hc-site__treatment-tag">{t.tag}</span>
                      <h3>{t.name}</h3>
                      <p>{t.desc}</p>
                      <div className="hc-site__treatment-meta"><span>{t.duration}</span><span className="hc-site__treatment-price">{t.price}</span></div>
                      <button type="button" className="hc-site__btn-primary hc-site__btn-sm" onClick={() => startBook(t.id)}>Book</button>
                    </article>
                  ))}
                </div>
              </div>
            </section>
            <section className="hc-site__team-section">
              <div className="hc-site__team-section-glow" aria-hidden />
              <div className="hc-site__section-inner">
                <div className="hc-site__team-head">
                  <span className="hc-site__team-eyebrow">Board-certified · same providers every visit</span>
                  <h2 className="hc-site__team-heading">Meet your care team</h2>
                  <p className="hc-site__team-lead">Real faces, real credentials — the people who will be in the room with you.</p>
                </div>
                <div className="hc-site__team-grid hc-site__team-grid--premium">
                  {WEBSITE_TEAM.map((p) => (
                    <article key={p.id} className="hc-site__team-card hc-site__team-card--premium">
                      <div className="hc-site__team-photo-wrap">
                        <img src={p.imageUrl} alt={p.name} loading="lazy" decoding="async" />
                      </div>
                      <div className="hc-site__team-body">
                        <h3>{p.name}</h3>
                        <p className="hc-site__team-title">{p.title}</p>
                        <div className="hc-site__team-tags">
                          {p.specialties.slice(0, 2).map((s) => (
                            <span key={s}>{s}</span>
                          ))}
                        </div>
                        <button type="button" className="hc-site__team-book" onClick={() => nav('book')}>
                          Book with {p.name.split(' ')[0]}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
                <button type="button" className="hc-site__team-cta" onClick={() => nav('providers')}>
                  View full profiles
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
                </button>
              </div>
            </section>
            <section className="hc-site__reviews">
              <div className="hc-site__section-inner">
                <h2 className="hc-site__section-title">What patients say</h2>
                <div className="hc-site__review-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="hc-site__review"><p>&ldquo;{r.text}&rdquo;</p><footer>{'★'.repeat(r.stars)} · {r.name}</footer></blockquote>
                  ))}
                </div>
              </div>
            </section>
        </SitePane>

        <SitePane id="treatments" current={page}>
            <SitePageHeader eyebrow="Services & pricing" title="Treatments" subtitle="Every service includes online booking, prep instructions, and a named provider and room." />
            <div className="hc-site__page--pad">
              <div className="hc-site__treatment-grid">
                {PUBLISHED_TREATMENTS.map((t) => (
                  <article key={t.id} className="hc-site__treatment hc-site__treatment--detail hc-site__treatment--glass">
                    <span className="hc-site__treatment-icon" aria-hidden>{t.icon}</span>
                    <span className="hc-site__treatment-tag">{t.tag}</span>
                    <h3>{t.name}</h3>
                    <p>{expandedTreatment === t.id ? t.longDesc : t.desc}</p>
                    <div className="hc-site__treatment-meta"><span>{t.duration}</span><span className="hc-site__treatment-price">{t.price}</span></div>
                    <p className="hc-site__treatment-where">With {t.practitionerIds.map((id) => getPractitioner(id)?.name).join(' or ')} · {t.roomIds.map((id) => getRoom(id)?.name).join(' or ')}</p>
                    <div className="hc-site__treatment-actions">
                      <button type="button" className="hc-site__btn-ghost hc-site__btn-sm" onClick={() => setExpandedTreatment(expandedTreatment === t.id ? null : t.id)}>{expandedTreatment === t.id ? 'Less' : 'More'}</button>
                      <button type="button" className="hc-site__btn-primary hc-site__btn-sm" onClick={() => startBook(t.id)}>Book</button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
        </SitePane>

        <SitePane id="providers" current={page}>
            <SitePageHeader eyebrow="Who you'll see" title="Your care team" subtitle="Board-certified providers and licensed nurses — the people at your appointment." />
            <div className="hc-site__page--pad">
              <div className="hc-site__provider-list">
                {WEBSITE_TEAM.map((p) => (
                  <article key={p.id} className="hc-site__provider">
                    <div className="hc-site__provider-photo">
                      <img src={p.imageUrl} alt={`${p.name}, ${p.title}`} loading="lazy" decoding="async" />
                    </div>
                    <div className="hc-site__provider-body">
                      <h3>{p.name}</h3>
                      <p className="hc-site__team-title">{p.title}</p>
                      <p className="hc-site__provider-bio">{p.bio}</p>
                      <p className="hc-site__provider-creds">{p.specialties.join(' · ')}</p>
                      <button type="button" className="hc-site__btn-primary hc-site__btn-sm" onClick={() => nav('book')}>Book with {p.name.split(' ')[0]}</button>
                    </div>
                  </article>
                ))}
              </div>
            </div>
        </SitePane>

        <SitePane id="about" current={page}>
            <SitePageHeader eyebrow="Our clinic" title={`About ${CLINIC.name}`} subtitle="Medical-grade aesthetics in a calm, private setting." />
            <div className="hc-site__page--pad hc-site__about">
              <div className="hc-site__about-hero">
                <img src={CLINIC.clinicImage} alt="Harbor Wellness clinic" loading="lazy" decoding="async" />
                <div className="hc-site__about-hero-copy">
                  <h3>Where care meets comfort</h3>
                  <p>Private suites, natural light, and a team led by {featuredDoctor.name}.</p>
                </div>
              </div>
              <div className="hc-site__about-grid">
                <div className="hc-site__about-card"><h3>Our space</h3><p>Three dedicated rooms — consult suite, facial room, and IV lounge.</p></div>
                <div className="hc-site__about-card"><h3>Before your visit</h3><p>Digital intake and prep instructions by email — no clipboard at check-in.</p></div>
                <div className="hc-site__about-card"><h3>Policies</h3><p>24h cancellation · HIPAA records · Validated parking.</p></div>
              </div>
              <div className="hc-site__about-location">
                <h3>Find us</h3>
                <p>{CLINIC.address}, {CLINIC.city}</p>
                <p>{CLINIC.phone} · {CLINIC.email}</p>
                <div className="hc-site__map-placeholder" aria-hidden>Map · Harbor View Dr</div>
              </div>
            </div>
        </SitePane>

        <SitePane id="book" current={page}>
            <SitePageHeader eyebrow="Online scheduling" title="Book your visit" subtitle="Live availability synced to our clinic calendar — you'll see the exact provider and room." />
            <div className="hc-site__page--pad">
              {!confirmed && (
                <div className="hc-site__book-progress">
                  <span className={selectedTreatment ? 'hc-site__book-progress-step hc-site__book-progress-step--done' : 'hc-site__book-progress-step hc-site__book-progress-step--active'}>Treatment</span>
                  <span className={selectedSlot ? 'hc-site__book-progress-step hc-site__book-progress-step--done' : selectedTreatment ? 'hc-site__book-progress-step hc-site__book-progress-step--active' : 'hc-site__book-progress-step'}>Time</span>
                  <span className="hc-site__book-progress-step">Confirm</span>
                </div>
              )}
              {!confirmed ? (
                <div className="hc-site__book-layout">
                  <div className="hc-site__book-flow">
                    <div className="hc-site__book-step">
                      <span className="hc-site__step-num">1</span>
                      <div>
                        <p className="hc-site__step-label">Choose treatment</p>
                        <div className="hc-site__pill-row">
                          {PUBLISHED_TREATMENTS.map((t) => (
                            <button key={t.id} type="button" className={`hc-site__pill ${selectedTreatment === t.id ? 'hc-site__pill--on' : ''}`} onClick={() => { setSelectedTreatment(t.id); setSelectedSlot(null); }}>{t.name}</button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <div className="hc-site__book-step">
                      <span className="hc-site__step-num">2</span>
                      <div>
                        <p className="hc-site__step-label">Pick a time</p>
                        <div className="hc-site__slot-list">
                          {(selectedTreatment ? availableSlots : BOOKING_SLOTS).map((slot) => (
                            <button key={slot.id} type="button" className={`hc-site__slot ${selectedSlot === slot.id ? 'hc-site__slot--on' : ''}`} onClick={() => setSelectedSlot(slot.id)}>
                              <span className="hc-site__slot-time">{slot.day} · {slot.time}</span>
                              <span className="hc-site__slot-detail">{getPractitioner(slot.practitionerId)?.name} · {getRoom(slot.roomId)?.name}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                    <button type="button" className="hc-site__btn-primary" disabled={!selectedTreatment || !selectedSlot} onClick={confirmBooking}>Confirm booking</button>
                  </div>
                  <aside className="hc-site__book-aside"><h3>What happens next</h3><ol><li>Confirmation email</li><li>Digital intake form</li><li>Reminder 24h before</li><li>Check in — forms on file</li></ol></aside>
                </div>
              ) : (
                <div className="hc-site__confirm">
                  <div className="hc-site__confirm-icon">✓</div>
                  <h3>You&apos;re booked!</h3>
                  <p>{treatment?.name}</p>
                  <p className="hc-site__confirm-slot">{BOOKING_SLOTS.find((s) => s.id === selectedSlot)?.label}</p>
                  <button type="button" className="hc-site__btn-ghost" onClick={() => { setConfirmed(false); nav('portal'); }}>Go to my portal</button>
                </div>
              )}
            </div>
        </SitePane>

        <SitePane id="portal" current={page}>
            <SitePageHeader eyebrow="Signed in as Sarah M." title="My patient portal" subtitle="Your appointments, forms, and messages — private to you." />
            <div className="hc-site__page--pad hc-site__portal">
              <div className="hc-site__portal-grid">
                <article className="hc-site__portal-card hc-site__portal-card--accent">
                  <h3>Upcoming visit</h3>
                  <p className="hc-site__portal-big">Thu · 2:30 PM</p>
                  <p>Botox consult · Dr. Elena Chen · Consult Suite A</p>
                  <button type="button" className="hc-site__btn-ghost hc-site__btn-sm">Add to calendar</button>
                </article>
                <article className="hc-site__portal-card">
                  <h3>Intake form</h3>
                  <p className="hc-site__portal-status hc-site__portal-status--done">✓ Completed</p>
                  <p>Medical history on file</p>
                </article>
                <article className="hc-site__portal-card">
                  <h3>Messages</h3>
                  <p>2 messages from Harbor AI</p>
                  <button type="button" className="hc-site__btn-primary hc-site__btn-sm" onClick={() => setChatOpen(true)}>Open chat</button>
                </article>
                <article className="hc-site__portal-card">
                  <h3>Visit history</h3>
                  <ul className="hc-site__portal-list"><li>Hydrafacial · May 12</li><li>Consult · Mar 3</li></ul>
                </article>
              </div>
            </div>
        </SitePane>

        <SitePane id="faq" current={page}>
            <SitePageHeader eyebrow="Help center" title="Frequently asked questions" subtitle="Quick answers — or chat with Harbor AI for anything specific." />
            <div className="hc-site__page--pad">
              <div className="hc-site__faq-list">
                {FAQ.map((f) => (
                  <details key={f.q} className="hc-site__faq"><summary>{f.q}</summary><p>{f.a}</p></details>
                ))}
              </div>
              <button type="button" className="hc-site__btn-primary hc-site__btn-sm hc-site__faq-chat" onClick={() => setChatOpen(true)}>Still have questions? Chat with us</button>
            </div>
        </SitePane>

        <SitePane id="contact" current={page}>
            <SitePageHeader eyebrow="Get in touch" title="Contact us" subtitle="Visit, call, email, or chat — we respond fastest via Harbor AI." />
            <div className="hc-site__page--pad">
              <div className="hc-site__contact-grid">
                <div className="hc-site__contact-card"><h3>Visit</h3><p>{CLINIC.address}</p><p>{CLINIC.city}</p><p className="hc-site__contact-note">Validated parking · Wheelchair accessible</p></div>
                <div className="hc-site__contact-card"><h3>Call or email</h3><p>{CLINIC.phone}</p><p>{CLINIC.email}</p><p className="hc-site__contact-note">Front desk Mon–Fri 8am–6pm</p></div>
                <div className="hc-site__contact-card"><h3>Chat</h3><p>Fastest for booking and pricing questions.</p><button type="button" className="hc-site__btn-primary hc-site__btn-sm" onClick={() => setChatOpen(true)}>Start chat</button></div>
              </div>
            </div>
        </SitePane>
      </div>

        <SiteFooter onNavigate={nav} />
      </div>

      <HarborPatientChat open={chatOpen} onOpenChange={setChatOpen} onBookClick={() => nav('book')} />
    </div>
  );
}
