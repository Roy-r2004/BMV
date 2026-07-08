import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  SALON,
  PUBLISHED_SERVICES,
  WEBSITE_BARBERS,
  BOOKING_SLOTS,
  slotsForService,
  getBarber,
  getChair,
  type Service,
  type TimeSlot,
} from './studioData.ts';
import StudioClientChat from './StudioClientChat.tsx';
import OverlayCustomSections from '../shared/OverlayCustomSections.tsx';
import { onStudioImageError } from './studioImageFallback.ts';
import { OverlayHeroSub, OverlayHeroTitle } from '../shared/overlayUi.tsx';

const GALLERY = [
  { src: 'https://images.unsplash.com/photo-1622286342621-4bd786c2447c?auto=format&w=500&h=620&fit=crop&q=80', tag: '#skinfade' },
  { src: 'https://images.unsplash.com/photo-1593702279376-c20678a3ba38?w=500&h=620&fit=crop&q=80', tag: '#lineup' },
  { src: 'https://images.unsplash.com/photo-1521590834618-9849727af8b0?auto=format&w=500&h=620&fit=crop&q=80', tag: '#beardsculpt' },
  { src: 'https://images.unsplash.com/photo-1585747860715-2ba37e788b70?auto=format&w=500&h=620&fit=crop&q=80', tag: '#studionine' },
];

const JOURNEY = [
  { step: '1', title: 'Book or walk in', desc: 'Real-time chair availability — pick your barber or check the live wait.' },
  { step: '2', title: 'Style memory DM', desc: 'AI recalls your fade, barber, and loyalty — books from Instagram without the back-and-forth.' },
  { step: '3', title: 'Sit in your chair', desc: 'Your guard, part, and style notes are already on the board when you arrive.' },
];

const REVIEWS = [
  { name: 'Devon S.', text: 'Booked at midnight, walked in right on time. Marcus remembered my fade.', stars: 5 },
  { name: 'Chris D.', text: 'VIP slot is worth it — style notes saved every visit. Feels like a members club.', stars: 5 },
  { name: 'Jordan P.', text: 'Jay\'s cut + beard combo is the move. Hot towel finish every single time.', stars: 5 },
];

const NEXT_SLOT: Record<string, string> = {
  marcus: 'Fri 11:30 AM',
  jay: 'Thu 5:15 PM',
  alex: 'Today 3:00 PM',
};

type Page = 'home' | 'menu' | 'book';

interface Props {
  onBook: (slot: TimeSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'sn-shop__pane' : 'sn-shop__pane sn-shop__pane--hidden'}>
      {children}
    </div>
  );
}

function ServiceRow({
  service,
  onBook,
}: {
  service: Service;
  onBook: (serviceId: string) => void;
}) {
  return (
    <article className="sn-shop__menu-row">
      <div className="sn-shop__menu-row-left">
        <span className="sn-shop__menu-icon">{service.icon}</span>
        <div>
          <div className="sn-shop__menu-row-title">
            <h3>{service.name}</h3>
            {service.tag && <span className="sn-shop__menu-tag">{service.tag}</span>}
          </div>
          <p>{service.desc}</p>
          <small>With {service.barberIds.map((id) => getBarber(id)?.name.split(' ')[0]).join(', ')}</small>
        </div>
      </div>
      <div className="sn-shop__menu-row-right">
        <span className="sn-shop__menu-price">{service.price}</span>
        <span className="sn-shop__menu-dur">{service.duration}</span>
        <button type="button" className="sn-shop__btn sn-shop__btn--sm sn-shop__btn--gold" onClick={() => onBook(service.id)}>
          Book
        </button>
      </div>
    </article>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="sn-shop__footer">
      <div className="sn-shop__footer-grid">
        <div>
          <p className="sn-shop__footer-brand">{SALON.name}</p>
          <p className="sn-shop__footer-muted">{SALON.tagline}</p>
          <p className="sn-shop__footer-muted">{SALON.address}</p>
          <p className="sn-shop__footer-muted">{SALON.city}</p>
        </div>
        <div>
          <p className="sn-shop__footer-heading">Hours</p>
          {SALON.hours.map((h) => (
            <p key={h.days} className="sn-shop__footer-muted">
              <span>{h.days}</span> {h.time}
            </p>
          ))}
        </div>
        <div>
          <p className="sn-shop__footer-heading">Explore</p>
          <button type="button" className="sn-shop__footer-link" onClick={() => onNavigate('menu')}>Service menu</button>
          <button type="button" className="sn-shop__footer-link" onClick={() => onNavigate('book')}>Book a cut</button>
          <button type="button" className="sn-shop__footer-link" onClick={() => onNavigate('home')}>Home</button>
        </div>
        <div>
          <p className="sn-shop__footer-heading">Contact</p>
          <p className="sn-shop__footer-muted">{SALON.phone}</p>
          <p className="sn-shop__footer-muted">{SALON.email}</p>
          <p className="sn-shop__footer-legal">Privacy · Terms · Nine Club</p>
        </div>
      </div>
      <p className="sn-shop__footer-copy">© 2026 {SALON.name}. All rights reserved.</p>
    </footer>
  );
}

export default function StudioClientSite({ onBook }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedService, setSelectedService] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const startBook = (serviceId: string) => {
    setSelectedService(serviceId);
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

  const service = PUBLISHED_SERVICES.find((s) => s.id === selectedService);
  const slots = selectedService ? slotsForService(selectedService) : BOOKING_SLOTS;
  const bookStep = !selectedService ? 1 : !selectedSlot ? 2 : 3;

  return (
    <div className="sn-shop">
      <header className="sn-shop__header">
        <button type="button" className="sn-shop__brand" onClick={() => nav('home')}>
          <span className="sn-shop__mark">9</span>
          <span className="sn-shop__name">{SALON.name}</span>
        </button>
        <nav className="sn-shop__nav" aria-label="Shop navigation">
          {(['home', 'menu', 'book'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`sn-shop__nav-link ${page === p ? 'sn-shop__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Home' : p === 'menu' ? 'Menu' : 'Book'}
            </button>
          ))}
        </nav>
        <button type="button" className="sn-shop__cta" onClick={() => nav('book')}>Book a cut</button>
      </header>

      <div className="sn-shop__scroll" ref={scrollRef}>
        <div className="sn-shop__main">
          <SitePane id="home" current={page}>
            <section className="sn-shop__hero" data-overlay-target="hero">
              <img src={SALON.heroImage} alt="" className="sn-shop__hero-bg" onError={onStudioImageError} />
              <div className="sn-shop__hero-overlay" />
              <div className="sn-shop__hero-grain" aria-hidden />
              <div className="sn-shop__hero-content">
                <p className="sn-shop__eyebrow">{SALON.tagline}</p>
                <div className="sn-shop__ai-chips" aria-label="AI capabilities">
                  <span>Style memory</span>
                  <span>DM booking</span>
                  <span>Waitlist fill</span>
                </div>
                <OverlayHeroTitle
                  className="sn-shop__hero-title"
                  primary="Cuts that hit."
                  accent="DMs that book themselves."
                />
                <OverlayHeroSub className="sn-shop__hero-sub">
                  Style memory AI recalls your fade + barber — Instagram DMs become confirmed chairs while barbers cut.
                </OverlayHeroSub>
                <div className="sn-shop__ai-magnet" aria-label="AI proof">
                  <div><strong>71%</strong><span>rebook rate</span></div>
                  <div><strong>4.2m</strong><span>avg DM reply</span></div>
                  <div><strong>0</strong><span>phone tag</span></div>
                </div>
                <div className="sn-shop__hero-actions">
                  <button type="button" className="sn-shop__btn sn-shop__btn--gold" onClick={() => nav('book')}>Pick a time</button>
                  <button type="button" className="sn-shop__btn sn-shop__btn--ghost" onClick={() => setChatOpen(true)}>DM the shop</button>
                </div>
                <div className="sn-shop__trust">
                  <span>★ 4.9</span>
                  <span>2,400+ clients</span>
                  <span>Brooklyn · Since 2018</span>
                </div>
              </div>
              <aside className="sn-shop__walkin">
                <span className="sn-shop__walkin-pulse" />
                <p className="sn-shop__walkin-label">Walk-in right now</p>
                <p className="sn-shop__walkin-wait">~25 min</p>
                <p className="sn-shop__walkin-barber">Alex · Chair 3</p>
                <button type="button" className="sn-shop__walkin-btn" onClick={() => setChatOpen(true)}>Check live wait</button>
              </aside>
            </section>

            <OverlayCustomSections />

            <section className="sn-shop__journey">
              <div className="sn-shop__section-inner">
                <h2 className="sn-shop__section-title">Your cut, step by step</h2>
                <div className="sn-shop__journey-grid">
                  {JOURNEY.map((step) => (
                    <article key={step.step} className="sn-shop__journey-card">
                      <span className="sn-shop__journey-num">{step.step}</span>
                      <h3>{step.title}</h3>
                      <p>{step.desc}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="sn-shop__menu-strip">
              <div className="sn-shop__menu-strip-inner">
                <div className="sn-shop__menu-strip-head">
                  <p className="sn-shop__menu-strip-title">Quick picks</p>
                  <button type="button" className="sn-shop__menu-strip-link" onClick={() => nav('menu')}>Full menu →</button>
                </div>
                <div className="sn-shop__quick-grid">
                  {PUBLISHED_SERVICES.map((s) => (
                    <button key={s.id} type="button" className="sn-shop__quick-card" onClick={() => startBook(s.id)}>
                      {s.tag && <span className="sn-shop__menu-item-tag">{s.tag}</span>}
                      <span className="sn-shop__quick-name">{s.name}</span>
                      <p>{s.desc}</p>
                      <div className="sn-shop__quick-foot">
                        <strong>{s.price}</strong>
                        <span>{s.duration}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            </section>

            <section className="sn-shop__home-menu">
              <div className="sn-shop__section-inner">
                <div className="sn-shop__home-menu-head">
                  <div>
                    <span className="sn-shop__section-eyebrow">Prices & duration</span>
                    <h2 className="sn-shop__section-title">The full service menu</h2>
                    <p className="sn-shop__home-menu-lead">Every service on one page — scroll, pick your barber, book direct.</p>
                  </div>
                  <button type="button" className="sn-shop__menu-strip-link sn-shop__menu-strip-link--dark" onClick={() => nav('menu')}>
                    Menu view →
                  </button>
                </div>
                <div className="sn-shop__menu-board sn-shop__menu-board--home">
                  {PUBLISHED_SERVICES.map((s) => (
                    <ServiceRow key={s.id} service={s} onBook={startBook} />
                  ))}
                </div>
              </div>
            </section>

            <section className="sn-shop__roster">
              <div className="sn-shop__section-head">
                <span className="sn-shop__section-eyebrow">Your chair, every time</span>
                <h2>The barbers</h2>
                <p>Three masters. No rotations. Book your guy and he&apos;ll have your notes ready.</p>
              </div>
              <div className="sn-shop__roster-grid">
                {WEBSITE_BARBERS.map((b) => (
                  <article key={b.id} className="sn-shop__barber">
                    <div className="sn-shop__barber-photo">
                      <img src={b.imageUrl} alt={b.name} loading="lazy" onError={(e) => onStudioImageError(e, b.photoInitial)} />
                      <div className="sn-shop__barber-overlay">
                        <span className="sn-shop__barber-next">Next: {NEXT_SLOT[b.id]}</span>
                      </div>
                    </div>
                    <div className="sn-shop__barber-body">
                      <h3>{b.name}</h3>
                      <p className="sn-shop__barber-title">{b.title}</p>
                      <div className="sn-shop__barber-tags">
                        {b.specialties.map((t) => <span key={t}>{t}</span>)}
                      </div>
                      <button type="button" className="sn-shop__barber-book" onClick={() => nav('book')}>
                        Book {b.name.split(' ')[0]}
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="sn-shop__gallery">
              <div className="sn-shop__section-head sn-shop__section-head--dark">
                <span className="sn-shop__section-eyebrow sn-shop__section-eyebrow--gold">#StudioNine</span>
                <h2>Fresh out the chair</h2>
                <p>Tag us on IG — we repost the sharpest fades every week.</p>
              </div>
              <div className="sn-shop__gallery-grid">
                {GALLERY.map((g, i) => (
                  <figure key={i} className="sn-shop__gallery-cell">
                    <img src={g.src} alt="" loading="lazy" onError={onStudioImageError} />
                    <figcaption>{g.tag}</figcaption>
                  </figure>
                ))}
              </div>
            </section>

            <section className="sn-shop__loyalty">
              <div className="sn-shop__loyalty-card">
                <div className="sn-shop__loyalty-stamps" aria-label="5 of 8 loyalty stamps">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <span key={i} className={i < 5 ? 'sn-shop__stamp sn-shop__stamp--filled' : 'sn-shop__stamp'}>{i < 5 ? '✂' : ''}</span>
                  ))}
                </div>
                <div className="sn-shop__loyalty-copy">
                  <span className="sn-shop__loyalty-badge">Nine Club</span>
                  <h3>5 of 8 cuts — next one&apos;s on us</h3>
                  <p>Stamps apply automatically when you book. VIP members skip the wait.</p>
                  <button type="button" className="sn-shop__btn sn-shop__btn--gold sn-shop__btn--sm" onClick={() => nav('book')}>Book to earn</button>
                </div>
              </div>
            </section>

            <section className="sn-shop__book-cta">
              <img src={SALON.shopImage} alt="" className="sn-shop__book-cta-photo" onError={onStudioImageError} />
              <div className="sn-shop__book-cta-shade" aria-hidden />
              <div className="sn-shop__book-cta-inner">
                <span className="sn-shop__section-eyebrow sn-shop__section-eyebrow--gold">Live chairs</span>
                <h2>Friday fades still open</h2>
                <p>Marcus · Jay · Alex — real slots synced to the board</p>
                <button type="button" className="sn-shop__btn sn-shop__btn--gold" onClick={() => nav('book')}>
                  Book your chair
                </button>
              </div>
            </section>

            <section className="sn-shop__reviews">
              <div className="sn-shop__section-inner">
                <div className="sn-shop__section-head">
                  <span className="sn-shop__section-eyebrow">Client love</span>
                  <h2 className="sn-shop__section-title">Word on the street</h2>
                </div>
                <div className="sn-shop__reviews-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="sn-shop__review">
                      <p>&ldquo;{r.text}&rdquo;</p>
                      <footer>{'★'.repeat(r.stars)} · {r.name}</footer>
                    </blockquote>
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="menu" current={page}>
            <section className="sn-shop__menu-page">
              <header className="sn-shop__page-head sn-shop__page-head--menu">
                <span className="sn-shop__page-eyebrow">Prices & duration</span>
                <h1>Service menu</h1>
                <p>Every cut includes style notes saved to your profile. Gratuity appreciated.</p>
              </header>
              <div className="sn-shop__menu-board">
                {PUBLISHED_SERVICES.map((s) => (
                  <ServiceRow key={s.id} service={s} onBook={startBook} />
                ))}
              </div>
            </section>
          </SitePane>

          <SitePane id="book" current={page}>
            <section className="sn-shop__book-page">
              <header className="sn-shop__page-head">
                <span className="sn-shop__page-eyebrow">{confirmed ? 'Confirmed' : 'Live availability'}</span>
                <h1>{confirmed ? 'You\'re in the chair' : 'Book your cut'}</h1>
                <p>{confirmed ? 'Confirmation sent — your barber has your notes.' : 'Real slots synced to the board. Pick service, then time.'}</p>
              </header>

              {!confirmed && (
                <div className="sn-shop__book-progress" aria-label="Booking progress">
                  {['Service', 'Time', 'Confirm'].map((label, i) => (
                    <span
                      key={label}
                      className={`sn-shop__book-progress-step ${bookStep > i + 1 ? 'sn-shop__book-progress-step--done' : bookStep === i + 1 ? 'sn-shop__book-progress-step--active' : ''}`}
                    >
                      {label}
                    </span>
                  ))}
                </div>
              )}

              {!confirmed ? (
                <div className="sn-shop__book-grid">
                  <div className="sn-shop__book-col">
                    <p className="sn-shop__book-step">1 · Pick your service</p>
                    <div className="sn-shop__book-services">
                      {PUBLISHED_SERVICES.map((s) => (
                        <button
                          key={s.id}
                          type="button"
                          className={`sn-shop__book-svc ${selectedService === s.id ? 'sn-shop__book-svc--on' : ''}`}
                          onClick={() => { setSelectedService(s.id); setSelectedSlot(null); }}
                        >
                          <span className="sn-shop__book-svc-icon">{s.icon}</span>
                          <div>
                            <strong>{s.name}</strong>
                            <span>{s.price} · {s.duration}</span>
                          </div>
                        </button>
                      ))}
                    </div>

                    <p className="sn-shop__book-step">2 · Pick barber & time</p>
                    <div className="sn-shop__book-slots">
                      {slots.length === 0 ? (
                        <p className="sn-shop__book-empty">No slots for this service — try another or DM us.</p>
                      ) : (
                        slots.map((slot) => {
                          const barber = getBarber(slot.barberId);
                          return (
                            <button
                              key={slot.id}
                              type="button"
                              className={`sn-shop__book-slot ${selectedSlot === slot.id ? 'sn-shop__book-slot--on' : ''}`}
                              onClick={() => setSelectedSlot(slot.id)}
                            >
                              <span className="sn-shop__book-slot-time">{slot.day} · {slot.time}</span>
                              <span className="sn-shop__book-slot-detail">
                                {barber && <img src={barber.imageUrl} alt="" className="sn-shop__book-slot-avatar" onError={(e) => onStudioImageError(e, barber.photoInitial)} />}
                                {barber?.name} · {getChair(slot.chairId)?.name}
                              </span>
                            </button>
                          );
                        })
                      )}
                    </div>

                    <button
                      type="button"
                      className="sn-shop__btn sn-shop__btn--gold sn-shop__btn--wide"
                      disabled={!selectedService || !selectedSlot}
                      onClick={confirmBooking}
                    >
                      Lock it in →
                    </button>
                  </div>

                  <aside className="sn-shop__book-aside">
                    <h3>Included with every cut</h3>
                    <ul>
                      <li>SMS reminder 2h before</li>
                      <li>Style notes saved to profile</li>
                      <li>Nine Club stamp on check-in</li>
                      <li>Free reschedule up to 4h out</li>
                    </ul>
                    {selectedService && service && (
                      <div className="sn-shop__book-preview">
                        <p>Your pick</p>
                        <strong>{service.name}</strong>
                        <span>{service.price} · {service.duration}</span>
                        {selectedSlot && (
                          <p className="sn-shop__book-preview-slot">
                            {BOOKING_SLOTS.find((s) => s.id === selectedSlot)?.label}
                          </p>
                        )}
                      </div>
                    )}
                  </aside>
                </div>
              ) : (
                <div className="sn-shop__confirmed">
                  <div className="sn-shop__confirmed-ring" aria-hidden />
                  <div className="sn-shop__confirmed-check">✂</div>
                  <h2>You&apos;re booked.</h2>
                  <p className="sn-shop__confirmed-svc">{service?.name}</p>
                  <p className="sn-shop__confirmed-slot">{BOOKING_SLOTS.find((s) => s.id === selectedSlot)?.label}</p>
                  <p className="sn-shop__confirmed-note">Text sent · loyalty stamp pending · see you soon</p>
                </div>
              )}
            </section>
          </SitePane>
        </div>

        <SiteFooter onNavigate={nav} />
      </div>

      <StudioClientChat open={chatOpen} onOpenChange={setChatOpen} onBookClick={() => nav('book')} />
    </div>
  );
}
