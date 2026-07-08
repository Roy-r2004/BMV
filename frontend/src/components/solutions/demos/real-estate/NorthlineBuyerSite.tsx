import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  AGENCY,
  AGENTS,
  LISTINGS,
  VIEWING_SLOTS,
  getAgent,
  slotsForListing,
  type Listing,
  type ViewingSlot,
} from './northlineData.ts';
import NorthlineBuyerChat from './NorthlineBuyerChat.tsx';
import { NorthlineLogo, IconArrowRight } from '../shared/ShowcaseChatIcons.tsx';
import { OverlayAiChips, OverlayCtaButton, OverlayEyebrow, OverlayHeroStats, OverlayHeroSub, OverlayHeroTitle } from '../shared/overlayUi.tsx';
import OverlayCustomSections from '../shared/OverlayCustomSections.tsx';
import { useOverlayBrand } from '../../../../context/ShowcaseOverlayContext.tsx';
import { onNorthlineImageError } from './northlineImageFallback.ts';

type Page = 'home' | 'listings' | 'view';

const HERO_STATS = [
  { label: 'Live listings', value: '38' },
  { label: 'Avg response', value: '< 2m' },
  { label: 'Viewings this week', value: '24' },
];

const JOURNEY = [
  { step: '1', title: 'Browse listings', desc: 'Every property on one site — photos, comps, HOA, and school zones.' },
  { step: '2', title: 'Listing AI answers', desc: 'HOA, schools, and comps on every property — lead score rises as buyers engage.' },
  { step: '3', title: 'Book a viewing', desc: 'Real agent calendars — qualified leads land in your CRM, not a spreadsheet.' },
];

const REVIEWS = [
  { name: 'Alex P.', text: 'Asked about HOA at 10pm — had a Saturday viewing booked before breakfast.', stars: 5 },
  { name: 'Nina S.', text: 'Felt like a premium agency site, not a portal clone. Elena knew our budget.', stars: 5 },
  { name: 'David R.', text: 'Sarah sent comps within minutes. Closed Oak Lane in 19 days.', stars: 5 },
];

interface Props {
  onBookViewing: (slot: ViewingSlot) => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'nr-site__pane' : 'nr-site__pane nr-site__pane--hidden'}>
      {children}
    </div>
  );
}

function ListingCard({ listing, onView }: { listing: Listing; onView: (id: string) => void }) {
  const agent = getAgent(listing.agentId);
  return (
    <article className={`nr-site__listing-card ${listing.tag ? 'nr-site__listing-card--featured' : ''}`}>
      <div className="nr-site__listing-media">
        <img src={listing.imageUrl} alt={listing.address} loading="lazy" onError={(e) => onNorthlineImageError(e, listing.address)} />
        <div className="nr-site__listing-shade" aria-hidden />
        {listing.tag && <span className="nr-site__listing-badge">{listing.tag}</span>}
        <span className="nr-site__listing-price">{listing.price}</span>
      </div>
      <div className="nr-site__listing-body">
        <h3>{listing.address}</h3>
        <p className="nr-site__listing-hood">{listing.neighborhood}</p>
        <p>{listing.desc}</p>
        <div className="nr-site__listing-meta">
          <span>{listing.beds} bed</span>
          <span>{listing.baths} bath</span>
          <span>{listing.sqft} sqft</span>
        </div>
        {agent && <span className="nr-site__listing-agent">Listed by {agent.name}</span>}
        <button type="button" className="nr-site__btn nr-site__btn--primary nr-site__btn--sm" onClick={() => onView(listing.id)}>
          Book viewing
        </button>
      </div>
    </article>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  const brandName = useOverlayBrand(AGENCY.name);
  return (
    <footer className="nr-site__footer">
      <div className="nr-site__footer-grid">
        <div>
          <p className="nr-site__footer-brand">{brandName}</p>
          <p className="nr-site__footer-muted">{AGENCY.tagline}</p>
          <p className="nr-site__footer-muted">{AGENCY.address}</p>
          <p className="nr-site__footer-muted">{AGENCY.city}</p>
        </div>
        <div>
          <p className="nr-site__footer-heading">Explore</p>
          <button type="button" className="nr-site__footer-link" onClick={() => onNavigate('listings')}>All listings</button>
          <button type="button" className="nr-site__footer-link" onClick={() => onNavigate('view')}>Book a viewing</button>
          <button type="button" className="nr-site__footer-link" onClick={() => onNavigate('home')}>Home</button>
        </div>
        <div>
          <p className="nr-site__footer-heading">Contact</p>
          <p className="nr-site__footer-muted">{AGENCY.phone}</p>
          <p className="nr-site__footer-muted">{AGENCY.email}</p>
          <p className="nr-site__footer-legal">Privacy · Fair housing · MLS</p>
        </div>
      </div>
      <p className="nr-site__footer-copy">© 2026 {brandName}. All rights reserved.</p>
    </footer>
  );
}

export default function NorthlineBuyerSite({ onBookViewing }: Props) {
  const brandName = useOverlayBrand(AGENCY.name);
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [selectedListing, setSelectedListing] = useState<string>('oak-lane');
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const startViewing = (listingId: string) => {
    setSelectedListing(listingId);
    setSelectedSlot(null);
    setConfirmed(false);
    nav('view');
  };

  const slots = slotsForListing(selectedListing);
  const listing = LISTINGS.find((l) => l.id === selectedListing);
  const slot = VIEWING_SLOTS.find((s) => s.id === selectedSlot);
  const viewStep = !selectedSlot ? 1 : 2;

  const confirmViewing = () => {
    const s = VIEWING_SLOTS.find((v) => v.id === selectedSlot);
    if (!s) return;
    setConfirmed(true);
    onBookViewing(s);
  };

  return (
    <div className="nr-site">
      <header className="nr-site__header">
        <button type="button" className="nr-site__brand" onClick={() => nav('home')}>
          <NorthlineLogo className="nr-site__mark" />
          <span className="nr-site__name">{brandName}</span>
        </button>
        <nav className="nr-site__nav" aria-label="Site navigation">
          {(['home', 'listings', 'view'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`nr-site__nav-link ${page === p ? 'nr-site__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Home' : p === 'listings' ? 'Listings' : 'Book viewing'}
            </button>
          ))}
        </nav>
        <button type="button" className="nr-site__nav-cta" onClick={() => setChatOpen(true)}>
          Ask AI
        </button>
      </header>

      <div className="nr-site__scroll" ref={scrollRef}>
        <div className="nr-site__main">
          <SitePane id="home" current={page}>
            <section className="nr-site__hero" data-overlay-target="hero">
              <img src={AGENCY.heroImage} alt="" className="nr-site__hero-bg" onError={onNorthlineImageError} />
              <div className="nr-site__hero-overlay" />
              <div className="nr-site__hero-grain" aria-hidden />
              <div className="nr-site__hero-content">
                <OverlayEyebrow className="nr-site__hero-eyebrow">Brooklyn · Manhattan · AI-qualified leads</OverlayEyebrow>
                <OverlayAiChips
                  className="nr-site__ai-chips"
                  aria-label="AI capabilities"
                  defaults={['Listing AI', 'Lead scoring', 'Tour booking']}
                />
                <OverlayHeroTitle
                  className="nr-site__hero-title"
                  primary="Listings that sell"
                  accent="while agents sleep."
                />
                <OverlayHeroSub className="nr-site__hero-sub">
                  Listing AI answers HOA &amp; schools, scores buyers, and books tours — warm leads, not inquiry spam.
                </OverlayHeroSub>
                <div className="nr-site__ai-magnet" aria-label="AI proof">
                  <div><strong>23</strong><span>qualified this week</span></div>
                  <div><strong>&lt;2m</strong><span>avg response</span></div>
                  <div><strong>94</strong><span>hot-lead score</span></div>
                </div>
                <div className="nr-site__hero-actions">
                  <OverlayCtaButton
                    className="nr-site__btn nr-site__btn--primary"
                    defaultLabel="Browse listings"
                    onClick={() => nav('listings')}
                  />
                  <OverlayCtaButton
                    className="nr-site__btn nr-site__btn--ghost"
                    defaultLabel="Ask listing AI"
                    slot="secondary"
                    onClick={() => setChatOpen(true)}
                  />
                </div>
              </div>
            </section>

            <OverlayHeroStats className="nr-site__hero-stats" statClassName="nr-site__stat" defaults={HERO_STATS} />

            <OverlayCustomSections />

            <section className="nr-site__journey">
              <div className="nr-site__section-inner">
                <h2 className="nr-site__section-title">From browse to booked viewing</h2>
                <div className="nr-site__journey-grid">
                  {JOURNEY.map((step) => (
                    <article key={step.step} className="nr-site__journey-card">
                      <span className="nr-site__journey-num">{step.step}</span>
                      <h3>{step.title}</h3>
                      <p>{step.desc}</p>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="nr-site__featured">
              <div className="nr-site__section-inner">
                <div className="nr-site__featured-head">
                  <div>
                    <p className="nr-site__section-eyebrow">Just listed</p>
                    <h2 className="nr-site__section-title">Featured homes</h2>
                  </div>
                  <button type="button" className="nr-site__link-btn" onClick={() => nav('listings')}>
                    All listings
                    <IconArrowRight className="nr-site__link-icon" />
                  </button>
                </div>
                <div className="nr-site__listing-grid">
                  {LISTINGS.slice(0, 3).map((l) => (
                    <ListingCard key={l.id} listing={l} onView={startViewing} />
                  ))}
                </div>
              </div>
            </section>

            <section className="nr-site__home-listings">
              <div className="nr-site__section-inner">
                <p className="nr-site__section-eyebrow">Full inventory</p>
                <h2 className="nr-site__section-title">Every listing on one page</h2>
                <p className="nr-site__home-listings-lead">Scroll the full catalog — photos, specs, and one-tap viewing requests.</p>
                <div className="nr-site__listing-grid">
                  {LISTINGS.map((l) => (
                    <ListingCard key={l.id} listing={l} onView={startViewing} />
                  ))}
                </div>
              </div>
            </section>

            <section className="nr-site__agents">
              <div className="nr-site__section-inner">
                <p className="nr-site__section-eyebrow">Your team</p>
                <h2 className="nr-site__section-title">Agents who close</h2>
                <div className="nr-site__agents-grid">
                  {AGENTS.map((a) => (
                    <article key={a.id} className="nr-site__agent-card">
                      <div className="nr-site__agent-photo">
                        <img src={a.imageUrl} alt={a.name} loading="lazy" onError={(e) => onNorthlineImageError(e, a.photoInitial)} />
                      </div>
                      <h3>{a.name}</h3>
                      <p className="nr-site__agent-title">{a.title}</p>
                      <div className="nr-site__agent-tags">
                        {a.specialties.map((t) => <span key={t}>{t}</span>)}
                      </div>
                      <button type="button" className="nr-site__btn nr-site__btn--outline nr-site__btn--sm" onClick={() => nav('view')}>
                        Book with {a.name.split(' ')[0]}
                      </button>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="nr-site__valuation-cta">
              <img src={AGENCY.valuationImage} alt="" className="nr-site__valuation-photo" onError={onNorthlineImageError} />
              <div className="nr-site__valuation-shade" aria-hidden />
              <div className="nr-site__valuation-inner">
                <p className="nr-site__section-eyebrow nr-site__section-eyebrow--light">Free valuation</p>
                <h2>What&apos;s your home worth?</h2>
                <p>AI comp report in 24 hours — no obligation.</p>
                <button type="button" className="nr-site__btn nr-site__btn--primary" onClick={() => setChatOpen(true)}>
                  Get my estimate
                </button>
              </div>
            </section>

            <section className="nr-site__reviews">
              <div className="nr-site__section-inner">
                <h2 className="nr-site__section-title">What buyers say</h2>
                <div className="nr-site__review-grid">
                  {REVIEWS.map((r) => (
                    <blockquote key={r.name} className="nr-site__review">
                      <p>&ldquo;{r.text}&rdquo;</p>
                      <footer>{'★'.repeat(r.stars)} · {r.name}</footer>
                    </blockquote>
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="listings" current={page}>
            <section className="nr-site__listings-page">
              <header className="nr-site__page-hero">
                <img src={AGENCY.listingsHeroImage} alt="" className="nr-site__page-hero-photo" onError={onNorthlineImageError} />
                <div className="nr-site__page-hero-bg" aria-hidden />
                <div className="nr-site__page-hero-inner">
                  <p className="nr-site__section-eyebrow nr-site__section-eyebrow--light">Live inventory</p>
                  <h1>Listings</h1>
                  <p>{LISTINGS.length} homes · updated daily from MLS feed</p>
                </div>
              </header>
              <div className="nr-site__section-inner">
                <div className="nr-site__listing-grid">
                  {LISTINGS.map((l) => (
                    <ListingCard key={l.id} listing={l} onView={startViewing} />
                  ))}
                </div>
              </div>
            </section>
          </SitePane>

          <SitePane id="view" current={page}>
            <section className="nr-site__view-page">
              <div className="nr-site__view-layout">
                <aside className="nr-site__view-aside">
                  <img src={listing?.imageUrl || AGENCY.heroImage} alt="" className="nr-site__view-photo" onError={onNorthlineImageError} />
                  <div className="nr-site__view-aside-shade" aria-hidden />
                  <div className="nr-site__view-aside-inner">
                    <NorthlineLogo className="nr-site__view-mark" />
                    <p className="nr-site__section-eyebrow nr-site__section-eyebrow--light">Book a tour</p>
                    <h1>Schedule a viewing</h1>
                    <p>Real agent calendars — instant confirm + CRM handoff.</p>
                    {listing && (
                      <div className="nr-site__view-listing-pick">
                        <strong>{listing.address}</strong>
                        <span>{listing.price} · {listing.neighborhood}</span>
                      </div>
                    )}
                  </div>
                </aside>
                <div className="nr-site__view-main">
                  <div className="nr-site__view-panel">
                    {!confirmed ? (
                      <>
                        <header className="nr-site__view-panel-head">
                          <div>
                            <h2>Pick your time</h2>
                            <p>Live agent availability</p>
                          </div>
                          <div className="nr-site__view-steps">
                            <span className={viewStep >= 1 ? 'nr-site__step nr-site__step--on' : 'nr-site__step'}>Property</span>
                            <span className="nr-site__step-line" aria-hidden />
                            <span className={viewStep >= 2 ? 'nr-site__step nr-site__step--on' : 'nr-site__step'}>Time</span>
                          </div>
                        </header>
                        <label className="nr-site__view-label">Which listing?</label>
                        <div className="nr-site__view-listings">
                          {LISTINGS.map((l) => (
                            <button
                              key={l.id}
                              type="button"
                              className={`nr-site__view-listing-btn ${selectedListing === l.id ? 'nr-site__view-listing-btn--on' : ''}`}
                              onClick={() => { setSelectedListing(l.id); setSelectedSlot(null); }}
                            >
                              <strong>{l.address}</strong>
                              <span>{l.price}</span>
                            </button>
                          ))}
                        </div>
                        <label className="nr-site__view-label">Available tours</label>
                        <div className="nr-site__view-slots">
                          {slots.map((s) => (
                            <button
                              key={s.id}
                              type="button"
                              className={`nr-site__view-slot ${selectedSlot === s.id ? 'nr-site__view-slot--on' : ''}`}
                              onClick={() => setSelectedSlot(s.id)}
                            >
                              <strong>{s.time}</strong>
                              <span>{s.day}</span>
                              <small>{getAgent(s.agentId)?.name}</small>
                            </button>
                          ))}
                        </div>
                        {selectedSlot && (
                          <div className="nr-site__view-confirm-bar">
                            <div>
                              <p>Your tour</p>
                              <strong>{slot?.label}</strong>
                            </div>
                            <button type="button" className="nr-site__btn nr-site__btn--primary" onClick={confirmViewing}>
                              Confirm
                              <IconArrowRight className="nr-site__btn-icon" />
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="nr-site__confirmed">
                        <span className="nr-site__confirmed-ring" aria-hidden />
                        <NorthlineLogo className="nr-site__confirmed-logo" />
                        <h2>Viewing booked.</h2>
                        <p className="nr-site__confirmed-slot">{slot?.label}</p>
                        <p className="nr-site__confirmed-note">Calendar invite sent · agent briefed · see you Saturday</p>
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

      <NorthlineBuyerChat open={chatOpen} onOpenChange={setChatOpen} onViewingClick={() => nav('view')} />
    </div>
  );
}
