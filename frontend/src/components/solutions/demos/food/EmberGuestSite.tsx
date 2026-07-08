import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  RESTAURANT,
  MENU_SECTIONS,
  RESERVATION_SLOTS,
  slotsForParty,
  type MenuItem,
  type ReservationSlot,
} from './emberData.ts';
import EmberGuestChat from './EmberGuestChat.tsx';
import { EmberLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { onEmberImageError } from './emberImageFallback.ts';

type Page = 'home' | 'menu' | 'reserve';

const HERO_STATS = [
  { label: 'Covers tonight', value: '34' },
  { label: 'Direct orders', value: '15% off' },
  { label: 'Kitchen open', value: 'Until 11 PM' },
];

const JOURNEY = [
  { step: '1', title: 'Order or reserve', desc: 'Pick dishes for pickup or hold a patio table — no third-party apps.' },
  { step: '2', title: 'Menu concierge', desc: 'Menu AI answers allergens, suggests pairings, and routes patio parties to the kitchen.' },
  { step: '3', title: 'Arrive ready', desc: 'Kitchen fires your order on time. Your table is set when you walk in.' },
];

const REVIEWS = [
  { name: 'Daniel K.', text: 'Reserved patio for eight — set menu link arrived before we finished dessert planning.', stars: 5 },
  { name: 'Priya M.', text: 'Ordered truffle pasta direct. Pickup was exactly 25 minutes, still perfect.', stars: 5 },
  { name: 'Chris W.', text: 'Feels like a real neighborhood spot. Booked Saturday in two taps.', stars: 5 },
];

const ZONES = [
  { id: 'main', label: 'Main dining', desc: 'Intimate tables · full menu', seats: '2–6' },
  { id: 'patio', label: 'Patio', desc: 'Parties up to 8 · string lights', seats: '4–8' },
  { id: 'bar', label: 'Bar', desc: 'Walk-ins welcome · small plates', seats: '1–4' },
] as const;

const RESERVE_PERKS = [
  { label: 'No deposit', detail: 'Returning guests' },
  { label: 'Instant confirm', detail: 'SMS + email' },
  { label: 'Patio hold', detail: '15 min grace' },
];

interface Props {
  onReserve: (slot: ReservationSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'eo-guest__pane' : 'eo-guest__pane eo-guest__pane--hidden'}>
      {children}
    </div>
  );
}

function MenuCard({
  item,
  featured = false,
  onAdd,
}: {
  item: MenuItem;
  featured?: boolean;
  onAdd: (id: string) => void;
}) {
  return (
    <article className={`eo-guest__menu-card ${featured ? 'eo-guest__menu-card--featured' : ''}`}>
      <div className="eo-guest__menu-card-media">
        <img
          src={item.imageUrl}
          alt={item.name}
          loading="lazy"
          onError={(e) => onEmberImageError(e, item.name)}
        />
        <div className="eo-guest__menu-card-shade" aria-hidden />
        {item.tag && <span className="eo-guest__menu-badge eo-guest__menu-badge--float">{item.tag}</span>}
        <span className="eo-guest__menu-price-float">{item.price}</span>
      </div>
      <div className="eo-guest__menu-card-body">
        <div className="eo-guest__menu-row-title">
          <h3>{item.name}</h3>
        </div>
        <p>{item.desc}</p>
        <div className="eo-guest__menu-row-foot">
          <strong>{item.price}</strong>
          <button type="button" onClick={() => onAdd(item.id)}>Add to order</button>
        </div>
      </div>
    </article>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="eo-guest__footer">
      <div className="eo-guest__footer-grid">
        <div>
          <p className="eo-guest__footer-brand">{RESTAURANT.name}</p>
          <p className="eo-guest__footer-muted">{RESTAURANT.tagline}</p>
          <p className="eo-guest__footer-muted">{RESTAURANT.address}</p>
          <p className="eo-guest__footer-muted">{RESTAURANT.city}</p>
        </div>
        <div>
          <p className="eo-guest__footer-heading">Hours</p>
          {RESTAURANT.hours.map((h) => (
            <p key={h.days} className="eo-guest__footer-muted">
              <span>{h.days}</span> {h.time}
            </p>
          ))}
        </div>
        <div>
          <p className="eo-guest__footer-heading">Explore</p>
          {(['menu', 'reserve'] as Page[]).map((p) => (
            <button key={p} type="button" className="eo-guest__footer-link" onClick={() => onNavigate(p)}>
              {p === 'menu' ? 'Full menu' : 'Reserve a table'}
            </button>
          ))}
          <button type="button" className="eo-guest__footer-link" onClick={() => onNavigate('home')}>
            Home
          </button>
        </div>
        <div>
          <p className="eo-guest__footer-heading">Contact</p>
          <p className="eo-guest__footer-muted">{RESTAURANT.phone}</p>
          <p className="eo-guest__footer-muted">{RESTAURANT.email}</p>
          <p className="eo-guest__footer-legal">Privacy · Terms · Allergen notice</p>
        </div>
      </div>
      <p className="eo-guest__footer-copy">© 2026 {RESTAURANT.name}. All rights reserved.</p>
    </footer>
  );
}

export default function EmberGuestSite({ onReserve }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [partySize, setPartySize] = useState(2);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [cart, setCart] = useState<string[]>([]);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const slots = slotsForParty(partySize);
  const slot = RESERVATION_SLOTS.find((s) => s.id === selectedSlot);
  const reserveStep = !selectedSlot ? 1 : 2;

  const confirmReserve = () => {
    const s = RESERVATION_SLOTS.find((r) => r.id === selectedSlot);
    if (!s) return;
    setConfirmed(true);
    onReserve(s);
  };

  const addToCart = (id: string) => {
    setCart((c) => [...c, id]);
  };

  return (
    <div className="eo-guest">
      <header className="eo-guest__header">
        <button type="button" className="eo-guest__brand" onClick={() => nav('home')}>
          <span className="eo-guest__mark" aria-hidden>
            <EmberLogo className="eo-guest__mark-svg" />
          </span>
          <span className="eo-guest__name">{RESTAURANT.name}</span>
        </button>
        <nav className="eo-guest__nav" aria-label="Site navigation">
          {(['home', 'menu', 'reserve'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`eo-guest__nav-link ${page === p ? 'eo-guest__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Home' : p === 'menu' ? 'Menu' : 'Reserve'}
            </button>
          ))}
        </nav>
        {cart.length > 0 ? (
          <button type="button" className="eo-guest__cart-pill" onClick={() => nav('menu')}>
            {cart.length} in cart
          </button>
        ) : (
          <button type="button" className="eo-guest__nav-cta" onClick={() => setChatOpen(true)}>
            Concierge
          </button>
        )}
      </header>

      <div className="eo-guest__scroll" ref={scrollRef}>
        <div className="eo-guest__main">
          <SitePane id="home" current={page}>
            <section className="eo-guest__hero">
              <img src={RESTAURANT.heroImage} alt="" className="eo-guest__hero-bg" onError={onEmberImageError} />
              <div className="eo-guest__hero-overlay" />
              <div className="eo-guest__hero-grain" aria-hidden />
              <div className="eo-guest__hero-content">
                <p className="eo-guest__hero-eyebrow">Wood-fired kitchen · Brooklyn</p>
                <div className="eo-guest__ai-chips" aria-label="AI capabilities">
                  <span>Menu AI</span>
                  <span>Allergen aware</span>
                  <span>Kitchen sync</span>
                </div>
                <h1 className="eo-guest__hero-title">
                  Ask the menu.
                  <span>Keep the 30%.</span>
                </h1>
                <p className="eo-guest__hero-sub">
                  Menu AI tags allergens, books patio parties, and routes direct orders — no aggregator cut.
                </p>
                <div className="eo-guest__ai-magnet" aria-label="AI proof">
                  <div><strong>34%</strong><span>revenue direct</span></div>
                  <div><strong>$0</strong><span>platform fees</span></div>
                  <div><strong>&lt;1m</strong><span>allergen answers</span></div>
                </div>
                <div className="eo-guest__hero-actions">
                  <button type="button" className="eo-guest__btn eo-guest__btn--primary" onClick={() => nav('menu')}>
                    Order pickup
                  </button>
                  <button type="button" className="eo-guest__btn eo-guest__btn--ghost" onClick={() => setChatOpen(true)}>
                    Ask concierge
                  </button>
                </div>
              </div>
            </section>

            <div className="eo-guest__hero-stats">
              {HERO_STATS.map((s) => (
                <div key={s.label} className="eo-guest__stat">
                  <strong>{s.value}</strong>
                  <span>{s.label}</span>
                </div>
              ))}
            </div>

            <section className="eo-guest__journey">
              <div className="eo-guest__section-inner">
                <h2 className="eo-guest__section-title">Your night, step by step</h2>
                <div className="eo-guest__journey-grid">
                  {JOURNEY.map((step) => (
                    <article key={step.step} className="eo-guest__journey-card">
                      <span className="eo-guest__journey-num">{step.step}</span>
                      <h3>{step.title}</h3>
                      <p>{step.desc}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="eo-guest__tonight">
              <div className="eo-guest__tonight-inner">
                <div>
                  <p className="eo-guest__section-eyebrow">Tonight</p>
                  <h2>From the hearth</h2>
                  <p>Chef&apos;s seasonal menu — updated daily at 4 PM.</p>
                </div>
              </div>
              <div className="eo-guest__dish-scroll">
                {MENU_SECTIONS[1].items.map((item) => (
                  <article key={item.id} className="eo-guest__dish-card">
                    <div className="eo-guest__dish-media">
                      <img src={item.imageUrl} alt={item.name} loading="lazy" onError={(e) => onEmberImageError(e, item.name)} />
                      {item.tag && <span className="eo-guest__dish-tag">{item.tag}</span>}
                    </div>
                    <div className="eo-guest__dish-body">
                      <h3>{item.name}</h3>
                      <p>{item.desc}</p>
                      <div className="eo-guest__dish-foot">
                        <strong>{item.price}</strong>
                        <button type="button" onClick={() => addToCart(item.id)}>Add</button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="eo-guest__home-menu">
              <div className="eo-guest__section-inner">
                <div className="eo-guest__home-menu-head">
                  <div>
                    <p className="eo-guest__section-eyebrow">Direct order</p>
                    <h2 className="eo-guest__section-title">The full menu</h2>
                    <p className="eo-guest__home-menu-lead">Every dish on one page — scroll, add, checkout direct.</p>
                  </div>
                  <button type="button" className="eo-guest__link-btn" onClick={() => nav('menu')}>
                    Order view
                    <IconArrowRight className="eo-guest__link-icon" />
                  </button>
                </div>
                {MENU_SECTIONS.map((section) => (
                  <div key={section.id} className="eo-guest__home-menu-section">
                    <h3>{section.title}</h3>
                    <div className="eo-guest__menu-grid">
                      {section.items.map((item) => (
                        <MenuCard key={item.id} item={item} featured={Boolean(item.tag)} onAdd={addToCart} />
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="eo-guest__story">
              <div className="eo-guest__story-grid">
                <div className="eo-guest__story-media">
                  <img src={RESTAURANT.kitchenImage} alt="" loading="lazy" onError={onEmberImageError} />
                  <span className="eo-guest__story-caption">Open hearth · local farms</span>
                </div>
                <div className="eo-guest__story-copy">
                  <p className="eo-guest__section-eyebrow">Our fire</p>
                  <h2>Ember & Oak</h2>
                  <p>
                    Open-hearth cooking, local farms, and a dining room built for long evenings.
                    Book direct — we remember your favorites.
                  </p>
                  <ul className="eo-guest__hours">
                    {RESTAURANT.hours.map((h) => (
                      <li key={h.days}><span>{h.days}</span><span>{h.time}</span></li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>

            <section className="eo-guest__reserve-cta">
              <img src={RESTAURANT.reserveImage} alt="" className="eo-guest__reserve-cta-photo" onError={onEmberImageError} />
              <div className="eo-guest__reserve-cta-shade" aria-hidden />
              <div className="eo-guest__reserve-cta-inner">
                <p className="eo-guest__section-eyebrow eo-guest__section-eyebrow--light">Saturday service</p>
                <h2>Patio tables still open</h2>
                <p>Parties up to 8 · string lights · set menu available</p>
                <button type="button" className="eo-guest__btn eo-guest__btn--primary" onClick={() => nav('reserve')}>
                  Reserve now
                  <IconArrowRight className="eo-guest__btn-icon" />
                </button>
              </div>
            </section>

            <section className="eo-guest__reviews">
              <div className="eo-guest__section-inner">
                <h2 className="eo-guest__section-title">What guests say</h2>
                <div className="eo-guest__review-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="eo-guest__review">
                      <p>&ldquo;{r.text}&rdquo;</p>
                      <footer>{'★'.repeat(r.stars)} · {r.name}</footer>
                    </blockquote>
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="menu" current={page}>
            <section className="eo-guest__menu-page">
              <header className="eo-guest__page-hero eo-guest__page-hero--menu">
                <img
                  src={RESTAURANT.menuHeroImage}
                  alt=""
                  className="eo-guest__page-hero-photo"
                  onError={onEmberImageError}
                />
                <div className="eo-guest__page-hero-bg" aria-hidden />
                <div className="eo-guest__page-hero-grain" aria-hidden />
                <div className="eo-guest__page-hero-inner">
                  <p className="eo-guest__section-eyebrow eo-guest__section-eyebrow--light">Direct order</p>
                  <h1>The menu</h1>
                  <p>Pickup & delivery — 15% off when you order direct this week.</p>
                </div>
              </header>
              {MENU_SECTIONS.map((section) => (
                <div key={section.id} className="eo-guest__menu-section">
                  <div className="eo-guest__menu-section-head">
                    <h2>{section.title}</h2>
                    <span>{section.items.length} dishes</span>
                  </div>
                  <div className="eo-guest__menu-grid">
                    {section.items.map((item) => (
                      <MenuCard key={item.id} item={item} featured={Boolean(item.tag)} onAdd={addToCart} />
                    ))}
                  </div>
                </div>
              ))}
              {cart.length > 0 && (
                <div className="eo-guest__cart-bar">
                  <span>{cart.length} items · est. pickup 25 min</span>
                  <button type="button" className="eo-guest__btn eo-guest__btn--primary eo-guest__btn--sm">
                    Checkout
                    <IconArrowRight className="eo-guest__btn-icon" />
                  </button>
                </div>
              )}
            </section>
          </SitePane>

          <SitePane id="reserve" current={page}>
            <section className="eo-guest__reserve-page">
              <div className="eo-guest__reserve-layout">
                <aside className="eo-guest__reserve-aside">
                  <img
                    src={RESTAURANT.reserveImage}
                    alt=""
                    className="eo-guest__reserve-photo"
                    onError={onEmberImageError}
                  />
                  <div className="eo-guest__reserve-aside-shade" aria-hidden />
                  <div className="eo-guest__reserve-grain" aria-hidden />
                  <div className="eo-guest__reserve-aside-inner">
                    <span className="eo-guest__reserve-mark" aria-hidden>
                      <EmberLogo className="eo-guest__reserve-mark-svg" />
                    </span>
                    <p className="eo-guest__section-eyebrow eo-guest__section-eyebrow--light">Book direct</p>
                    <h1>Reserve your table</h1>
                    <p>Main dining · patio · bar — Saturday service fills by Thursday.</p>

                    <ul className="eo-guest__zone-list">
                      {ZONES.map((z) => (
                        <li key={z.id} className={`eo-guest__zone-card eo-guest__zone-card--${z.id}`}>
                          <div className="eo-guest__zone-card-top">
                            <strong>{z.label}</strong>
                            <span>{z.seats} guests</span>
                          </div>
                          <p>{z.desc}</p>
                        </li>
                      ))}
                    </ul>

                    <div className="eo-guest__reserve-perks">
                      {RESERVE_PERKS.map((perk) => (
                        <div key={perk.label}>
                          <strong>{perk.label}</strong>
                          <span>{perk.detail}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </aside>

                <div className="eo-guest__reserve-main">
                  <div className="eo-guest__reserve-panel">
                    {!confirmed ? (
                      <>
                        <header className="eo-guest__reserve-panel-head">
                          <div>
                            <h2>Pick your time</h2>
                            <p>Saturday service · live availability</p>
                          </div>
                          <div className="eo-guest__reserve-steps">
                            <span className={reserveStep >= 1 ? 'eo-guest__step eo-guest__step--on' : 'eo-guest__step'}>Party</span>
                            <span className="eo-guest__reserve-step-line" aria-hidden />
                            <span className={reserveStep >= 2 ? 'eo-guest__step eo-guest__step--on' : 'eo-guest__step'}>Time</span>
                          </div>
                        </header>

                        <div className="eo-guest__party-picker">
                          <label htmlFor="party-size">How many guests?</label>
                          <div className="eo-guest__party-btns" id="party-size">
                            {[2, 4, 6, 8].map((n) => (
                              <button
                                key={n}
                                type="button"
                                className={partySize === n ? 'eo-guest__party-btn eo-guest__party-btn--on' : 'eo-guest__party-btn'}
                                onClick={() => { setPartySize(n); setSelectedSlot(null); }}
                              >
                                <strong>{n}</strong>
                                <span>{n === 2 ? 'Couple' : n === 4 ? 'Group' : n === 6 ? 'Family' : 'Party'}</span>
                              </button>
                            ))}
                          </div>
                        </div>

                        <p className="eo-guest__slot-label">Available times</p>
                        <div className="eo-guest__slot-grid">
                          {slots.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              className={`eo-guest__slot eo-guest__slot--${s.zone} ${selectedSlot === s.id ? 'eo-guest__slot--on' : ''}`}
                              onClick={() => setSelectedSlot(s.id)}
                            >
                              <span className="eo-guest__slot-zone">{s.zone}</span>
                              <strong>{s.time}</strong>
                              <span className="eo-guest__slot-day">{s.day}</span>
                              <span className="eo-guest__slot-seats">{s.seats} seats</span>
                              {selectedSlot === s.id && <span className="eo-guest__slot-check" aria-hidden>✓</span>}
                            </button>
                          ))}
                        </div>

                        {selectedSlot && (
                          <div className="eo-guest__reserve-confirm-bar">
                            <div>
                              <p>Your hold</p>
                              <strong>{slot?.label}</strong>
                            </div>
                            <button type="button" className="eo-guest__btn eo-guest__btn--primary" onClick={confirmReserve}>
                              Confirm
                              <IconArrowRight className="eo-guest__btn-icon" />
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="eo-guest__confirmed">
                        <span className="eo-guest__confirmed-ring" aria-hidden />
                        <span className="eo-guest__confirmed-logo" aria-hidden>
                          <EmberLogo className="eo-guest__confirmed-logo-svg" />
                        </span>
                        <h2>You&apos;re on the books.</h2>
                        <p className="eo-guest__confirmed-slot">{slot?.label}</p>
                        <dl className="eo-guest__confirmed-details">
                          <div><dt>Party</dt><dd>{partySize} guests</dd></div>
                          <div><dt>Zone</dt><dd className="eo-guest__confirmed-zone">{slot?.zone}</dd></div>
                          <div><dt>Status</dt><dd>Confirmed · SMS sent</dd></div>
                        </dl>
                        <p className="eo-guest__confirmed-note">Set menu link sent · patio section held · see you Saturday</p>
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

      <EmberGuestChat open={chatOpen} onOpenChange={setChatOpen} onReserveClick={() => nav('reserve')} />
    </div>
  );
}
