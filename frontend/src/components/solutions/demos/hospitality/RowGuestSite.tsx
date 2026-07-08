import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import {
  HOTEL,
  ROOM_TYPES,
  BOOKING_OPTIONS,
  bookingForGuests,
  type BookingHold,
} from './rowData.ts';
import RowGuestChat from './RowGuestChat.tsx';
import { RowLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { onRowImageError } from './rowImageFallback.ts';

type Page = 'home' | 'rooms' | 'book';

const CONCIERGE_LINES = [
  { prompt: 'Quiet floor + firm pillows?', reply: 'Room 605 quiet wing · prefs saved to guest memory.' },
  { prompt: 'Late checkout Sunday?', reply: 'Approved until 1 PM · housekeeping board updated.' },
  { prompt: 'Dinner near the river?', reply: 'Untitled at 8:15 · eight-minute walk · held under your name.' },
  { prompt: 'Same bedding as last stay?', reply: 'Hypoallergenic loaded · still water only · seven stays remembered.' },
];

const ROOM_MEMORY: Record<string, string> = {
  classic: 'You liked courtyard quiet last March',
  corner: 'You booked this suite on your last two visits',
  'row-pent': 'Terrace evenings match your stay notes',
};

const REVIEWS = [
  { name: 'Claire D.', text: 'Seventh stay — they remembered hypoallergenic bedding without me asking.', stars: 5 },
  { name: 'James W.', text: 'Booked Corner Suite direct. Rate was lower than the big sites.', stars: 5 },
  { name: 'Sofia K.', text: 'Late checkout approved in chat; room status updated on the floor board.', stars: 5 },
];

interface Props {
  onBook: (hold: BookingHold) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'rh-guest__pane' : 'rh-guest__pane rh-guest__pane--hidden'}>
      {children}
    </div>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="rh-guest__footer">
      <div className="rh-guest__footer-grid">
        <div>
          <p className="rh-guest__footer-brand">{HOTEL.name}</p>
          <p className="rh-guest__footer-muted">{HOTEL.tagline}</p>
          <p className="rh-guest__footer-muted">{HOTEL.address}</p>
          <p className="rh-guest__footer-muted">{HOTEL.city}</p>
        </div>
        <div>
          <p className="rh-guest__footer-heading">Stay</p>
          {(['rooms', 'book'] as Page[]).map((p) => (
            <button key={p} type="button" className="rh-guest__footer-link" onClick={() => onNavigate(p)}>
              {p === 'rooms' ? 'Rooms & suites' : 'Book direct'}
            </button>
          ))}
        </div>
        <div>
          <p className="rh-guest__footer-heading">Concierge</p>
          <p className="rh-guest__footer-muted">24/7 AI · any language</p>
          <p className="rh-guest__footer-muted">Guest memory · returning prefs</p>
        </div>
        <div>
          <p className="rh-guest__footer-heading">Contact</p>
          <p className="rh-guest__footer-muted">{HOTEL.phone}</p>
          <p className="rh-guest__footer-muted">{HOTEL.email}</p>
        </div>
      </div>
      <p className="rh-guest__footer-copy">© 2026 {HOTEL.name}. Book direct — keep the OTA fee.</p>
    </footer>
  );
}

function ConciergeMoment({ onOpen }: { onOpen: () => void }) {
  const [idx, setIdx] = useState(0);
  const [phase, setPhase] = useState<'prompt' | 'typing' | 'reply'>('prompt');
  const [typed, setTyped] = useState('');
  const line = CONCIERGE_LINES[idx];

  useEffect(() => {
    setPhase('prompt');
    setTyped('');
    const t1 = window.setTimeout(() => setPhase('typing'), 900);
    return () => window.clearTimeout(t1);
  }, [idx]);

  useEffect(() => {
    if (phase !== 'typing') return;
    const full = line.reply;
    let i = 0;
    setTyped('');
    const id = window.setInterval(() => {
      i += 1;
      setTyped(full.slice(0, i));
      if (i >= full.length) {
        window.clearInterval(id);
        setPhase('reply');
      }
    }, 28);
    return () => window.clearInterval(id);
  }, [phase, line.reply]);

  useEffect(() => {
    if (phase !== 'reply') return;
    const t = window.setTimeout(() => {
      setIdx((n) => (n + 1) % CONCIERGE_LINES.length);
    }, 2800);
    return () => window.clearTimeout(t);
  }, [phase]);

  return (
    <section className="rh-guest__concierge">
      <div className="rh-guest__concierge-media">
        <img src={HOTEL.loungeImage} alt="" onError={(e) => onRowImageError(e)} />
        <div className="rh-guest__concierge-shade" aria-hidden />
      </div>
      <div className="rh-guest__concierge-copy">
        <p className="rh-guest__section-eyebrow rh-guest__section-eyebrow--light">Concierge AI</p>
        <h2>Your stay, already underway</h2>
        <p className="rh-guest__concierge-lead">
          Prefs, late checkout, and local picks — answered before you arrive.
        </p>
        <div className="rh-guest__concierge-chat" aria-live="polite">
          <div className="rh-guest__concierge-bubble rh-guest__concierge-bubble--guest">
            {line.prompt}
          </div>
          <div className="rh-guest__concierge-bubble rh-guest__concierge-bubble--ai">
            {phase === 'typing' && typed.length === 0 ? (
              <span className="rh-guest__concierge-dots" aria-hidden>
                <i /><i /><i />
              </span>
            ) : (
              <>
                {typed || line.reply}
                {phase === 'typing' && <span className="rh-guest__concierge-caret" aria-hidden />}
              </>
            )}
          </div>
        </div>
        <button type="button" className="rh-guest__btn rh-guest__btn--gold" onClick={onOpen}>
          Open concierge
          <IconArrowRight className="rh-guest__btn-icon" />
        </button>
      </div>
    </section>
  );
}

export default function RowGuestSite({ onBook }: Props) {
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [guests, setGuests] = useState(2);
  const [selectedHold, setSelectedHold] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [memoryApplied, setMemoryApplied] = useState(true);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const holds = bookingForGuests(guests);
  const hold = BOOKING_OPTIONS.find((h) => h.id === selectedHold);

  const confirmBook = () => {
    const h = BOOKING_OPTIONS.find((b) => b.id === selectedHold);
    if (!h) return;
    setConfirmed(true);
    onBook(h);
  };

  return (
    <div className="rh-guest">
      <header className="rh-guest__header">
        <button type="button" className="rh-guest__brand" onClick={() => nav('home')}>
          <span className="rh-guest__mark" aria-hidden>
            <RowLogo className="rh-guest__mark-svg" />
          </span>
          <span className="rh-guest__name">{HOTEL.name}</span>
        </button>
        <nav className="rh-guest__nav" aria-label="Site navigation">
          {(['home', 'rooms', 'book'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`rh-guest__nav-link ${page === p ? 'rh-guest__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Stay' : p === 'rooms' ? 'Rooms' : 'Book'}
            </button>
          ))}
        </nav>
        <button type="button" className="rh-guest__nav-cta" onClick={() => setChatOpen(true)}>
          Concierge
        </button>
      </header>

      <div className="rh-guest__scroll" ref={scrollRef}>
        <div className="rh-guest__main">
          <SitePane id="home" current={page}>
            <section className="rh-guest__hero">
              <img
                src={HOTEL.heroImage}
                alt=""
                className="rh-guest__hero-bg"
                onError={(e) => onRowImageError(e)}
              />
              <div className="rh-guest__hero-overlay" />
              <div className="rh-guest__hero-grain" aria-hidden />
              <div className="rh-guest__hero-content">
                <h1 className="rh-guest__hero-title">
                  The Row
                  <span>Hotel</span>
                </h1>
                <p className="rh-guest__hero-sub">
                  Forty-six keys on the corridor — quiet, remembered, book direct.
                </p>
                <div className="rh-guest__hero-actions">
                  <button type="button" className="rh-guest__btn rh-guest__btn--primary" onClick={() => nav('book')}>
                    Book your stay
                  </button>
                </div>
              </div>
            </section>

            <ConciergeMoment onOpen={() => setChatOpen(true)} />

            <section className="rh-guest__rooms-preview">
              <div className="rh-guest__section-inner">
                <div className="rh-guest__rooms-head">
                  <div>
                    <p className="rh-guest__section-eyebrow">Accommodations</p>
                    <h2 className="rh-guest__section-title">Rooms that know you</h2>
                    <p className="rh-guest__section-lead">Guest memory surfaces the stays you already love.</p>
                  </div>
                  <button type="button" className="rh-guest__link-btn" onClick={() => nav('rooms')}>
                    View all
                    <IconArrowRight className="rh-guest__link-icon" />
                  </button>
                </div>
                <div className="rh-guest__room-grid">
                  {ROOM_TYPES.map((room) => (
                    <article key={room.id} className="rh-guest__room-card">
                      <div className="rh-guest__room-media">
                        <img src={room.imageUrl} alt={room.name} loading="lazy" onError={(e) => onRowImageError(e, room.name)} />
                        {room.tag && <span className="rh-guest__room-tag">{room.tag}</span>}
                      </div>
                      <div className="rh-guest__room-body">
                        <p className="rh-guest__room-size">{room.size}</p>
                        <h3>{room.name}</h3>
                        <p>{room.desc}</p>
                        {ROOM_MEMORY[room.id] && (
                          <p className="rh-guest__room-memory">
                            <span>Memory</span>
                            {ROOM_MEMORY[room.id]}
                          </p>
                        )}
                        <div className="rh-guest__room-foot">
                          <strong>{room.rate}<em> / night</em></strong>
                          <button type="button" onClick={() => nav('book')}>Hold</button>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="rh-guest__story">
              <div className="rh-guest__story-grid">
                <div className="rh-guest__story-media">
                  <img src={HOTEL.lobbyImage} alt="" loading="lazy" onError={(e) => onRowImageError(e)} />
                </div>
                <div className="rh-guest__story-copy">
                  <p className="rh-guest__section-eyebrow">Guest memory</p>
                  <h2>We remember how you stay</h2>
                  <p>
                    Returning guests get preferences applied before check-in — bedding, floor preference,
                    late checkout habits. Concierge AI holds the thread; staff deliver the welcome.
                  </p>
                </div>
              </div>
            </section>

            <section className="rh-guest__reviews">
              <div className="rh-guest__section-inner">
                <h2 className="rh-guest__section-title">Guest notes</h2>
                <div className="rh-guest__review-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="rh-guest__review">
                      <p>&ldquo;{r.text}&rdquo;</p>
                      <footer>{'★'.repeat(r.stars)} · {r.name}</footer>
                    </blockquote>
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="rooms" current={page}>
            <section className="rh-guest__rooms-page">
              <header className="rh-guest__page-hero">
                <img src={HOTEL.suiteImage} alt="" className="rh-guest__page-hero-photo" onError={(e) => onRowImageError(e)} />
                <div className="rh-guest__page-hero-shade" aria-hidden />
                <div className="rh-guest__page-hero-inner">
                  <p className="rh-guest__section-eyebrow rh-guest__section-eyebrow--light">Accommodations</p>
                  <h1>Rooms &amp; suites</h1>
                  <p>Forty-six keys · wine quiet · linen light</p>
                </div>
              </header>
              <div className="rh-guest__room-grid rh-guest__room-grid--page">
                {ROOM_TYPES.map((room) => (
                  <article key={room.id} className="rh-guest__room-card rh-guest__room-card--wide">
                    <div className="rh-guest__room-media">
                      <img src={room.imageUrl} alt={room.name} loading="lazy" onError={(e) => onRowImageError(e, room.name)} />
                      {room.tag && <span className="rh-guest__room-tag">{room.tag}</span>}
                    </div>
                    <div className="rh-guest__room-body">
                      <p className="rh-guest__room-size">{room.size}</p>
                      <h3>{room.name}</h3>
                      <p>{room.desc}</p>
                      {ROOM_MEMORY[room.id] && (
                        <p className="rh-guest__room-memory">
                          <span>Memory</span>
                          {ROOM_MEMORY[room.id]}
                        </p>
                      )}
                      <ul className="rh-guest__amenity-list">
                        {room.amenities.map((a) => <li key={a}>{a}</li>)}
                      </ul>
                      <div className="rh-guest__room-foot">
                        <strong>{room.rate}<em> {room.nightsFrom}</em></strong>
                        <button type="button" className="rh-guest__btn rh-guest__btn--primary rh-guest__btn--sm" onClick={() => nav('book')}>
                          Book direct
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </SitePane>

          <SitePane id="book" current={page}>
            <section className="rh-guest__book-page">
              <div className="rh-guest__book-layout">
                <aside className="rh-guest__book-aside">
                  <img src={HOTEL.loungeImage} alt="" className="rh-guest__book-photo" onError={(e) => onRowImageError(e)} />
                  <div className="rh-guest__book-aside-shade" aria-hidden />
                  <div className="rh-guest__book-aside-inner">
                    <span className="rh-guest__book-mark" aria-hidden>
                      <RowLogo className="rh-guest__book-mark-svg" />
                    </span>
                    <p className="rh-guest__section-eyebrow rh-guest__section-eyebrow--light">Direct only</p>
                    <h1>Hold your stay</h1>
                    <p>No OTA markup. Preferences collected pre-arrival. Concierge on standby.</p>
                    <ul className="rh-guest__book-perks">
                      <li><strong>Best rate</strong><span>Guaranteed vs OTA</span></li>
                      <li><strong>Guest memory</strong><span>Prefs auto-applied</span></li>
                      <li><strong>Flexible</strong><span>Late checkout via AI</span></li>
                    </ul>
                  </div>
                </aside>

                <div className="rh-guest__book-main">
                  <div className="rh-guest__book-panel">
                    {!confirmed ? (
                      <>
                        {memoryApplied && (
                          <aside className="rh-guest__memory-nudge" aria-live="polite">
                            <div>
                              <strong>Welcome back, Claire</strong>
                              <p>High floor · late checkout until 1 PM — apply your prefs?</p>
                            </div>
                            <div className="rh-guest__memory-nudge-actions">
                              <button type="button" className="rh-guest__memory-yes" onClick={() => setMemoryApplied(false)}>
                                Apply
                              </button>
                              <button type="button" className="rh-guest__memory-skip" onClick={() => setMemoryApplied(false)}>
                                Skip
                              </button>
                            </div>
                          </aside>
                        )}

                        <header className="rh-guest__book-panel-head">
                          <div>
                            <h2>Live availability</h2>
                            <p>Weekend · Chicago corridor</p>
                          </div>
                        </header>

                        <div className="rh-guest__guest-picker">
                          <label htmlFor="rh-guests">Guests</label>
                          <div className="rh-guest__guest-btns" id="rh-guests">
                            {[1, 2].map((n) => (
                              <button
                                key={n}
                                type="button"
                                className={guests === n ? 'rh-guest__guest-btn rh-guest__guest-btn--on' : 'rh-guest__guest-btn'}
                                onClick={() => { setGuests(n); setSelectedHold(null); }}
                              >
                                {n}
                              </button>
                            ))}
                          </div>
                        </div>

                        <p className="rh-guest__slot-label">Available holds</p>
                        <div className="rh-guest__slot-grid">
                          {holds.map((h) => (
                            <button
                              key={h.id}
                              type="button"
                              className={`rh-guest__slot ${selectedHold === h.id ? 'rh-guest__slot--on' : ''}`}
                              onClick={() => setSelectedHold(h.id)}
                            >
                              <strong>{h.roomName}</strong>
                              <span>{h.checkIn} → {h.checkOut}</span>
                              <em>{h.nights} night{h.nights > 1 ? 's' : ''} · {h.rate}</em>
                              {selectedHold === h.id && <span className="rh-guest__slot-check" aria-hidden>✓</span>}
                            </button>
                          ))}
                        </div>

                        {selectedHold && (
                          <div className="rh-guest__book-confirm-bar">
                            <div>
                              <p>Your hold</p>
                              <strong>{hold?.label}</strong>
                            </div>
                            <button type="button" className="rh-guest__btn rh-guest__btn--primary" onClick={confirmBook}>
                              Confirm direct
                              <IconArrowRight className="rh-guest__btn-icon" />
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="rh-guest__confirmed">
                        <span className="rh-guest__confirmed-logo" aria-hidden>
                          <RowLogo className="rh-guest__confirmed-logo-svg" />
                        </span>
                        <h2>You&apos;re confirmed.</h2>
                        <p className="rh-guest__confirmed-slot">{hold?.label}</p>
                        <dl className="rh-guest__confirmed-details">
                          <div><dt>Room</dt><dd>{hold?.roomName}</dd></div>
                          <div><dt>Total</dt><dd>{hold?.rate}</dd></div>
                          <div><dt>Fees</dt><dd>$0 OTA commission</dd></div>
                        </dl>
                        <p className="rh-guest__confirmed-note">
                          Pre-arrival prefs link sent · concierge standing by · housekeeping notified
                        </p>
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

      <RowGuestChat open={chatOpen} onOpenChange={setChatOpen} onBookClick={() => nav('book')} />
    </div>
  );
}
