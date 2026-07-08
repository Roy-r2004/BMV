import { useCallback, useRef, useState, type ReactNode } from 'react';
import {
  HARBOR_FUND,
  DONATE_TIERS,
  IMPACT_STORIES,
  IMPACT_METER,
  storyForAmount,
  type Donation,
} from './harborFundData.ts';
import HarborDonorChat from './HarborDonorChat.tsx';
import OverlayCustomSections from '../shared/OverlayCustomSections.tsx';
import { HarborFundLogo } from '../shared/ShowcaseChatIcons.tsx';
import { onHarborFundImageError } from './harborFundImageFallback.ts';
import { OverlayHeroSub, OverlayHeroTitle } from '../shared/overlayUi.tsx';
import { useOverlayBrand } from '../../../../context/ShowcaseOverlayContext.tsx';

type Page = 'home' | 'donate' | 'volunteer';

const AI_SUGGESTIONS = [
  { amount: 50, why: 'Matches your last gift · highest meal velocity this week', badge: 'For you' },
  { amount: 100, why: 'Unlocks youth mentorship hours — 612 logged this quarter', badge: 'Amplify' },
  { amount: 250, why: 'Funds an emergency rent buffer for one household', badge: 'Deep impact' },
];

const REVIEWS = [
  { name: 'Maya Chen', text: 'I gave $50 and got a receipt naming the pier kitchen meals it funded — felt real.', stars: 5 },
  { name: 'Jordan Lee', text: 'Matched to a Saturday kitchen shift in one tap. Skills over whoever signed up first.', stars: 5 },
  { name: 'Elena Soto', text: 'Monthly upgrade took one SMS. Campaign progress emails write themselves.', stars: 5 },
];

interface Props {
  onDonate: (donation: Donation) => void;
  onVolunteerIntent?: () => void;
}

function SitePane({ id, current, children }: { id: Page; current: Page; children: ReactNode }) {
  return (
    <div className={current === id ? 'hg-site__pane' : 'hg-site__pane hg-site__pane--hidden'}>
      {children}
    </div>
  );
}

function SiteFooter({ onNavigate }: { onNavigate: (p: Page) => void }) {
  return (
    <footer className="hg-site__footer">
      <div className="hg-site__footer-grid">
        <div>
          <p className="hg-site__footer-brand">{HARBOR_FUND.name}</p>
          <p className="hg-site__footer-muted">{HARBOR_FUND.tagline}</p>
          <p className="hg-site__footer-muted">{HARBOR_FUND.address}</p>
          <p className="hg-site__footer-muted">{HARBOR_FUND.city}</p>
        </div>
        <div>
          <p className="hg-site__footer-heading">Hours</p>
          {HARBOR_FUND.hours.map((h) => (
            <p key={h.days} className="hg-site__footer-muted">
              <span>{h.days}</span> {h.time}
            </p>
          ))}
        </div>
        <div>
          <p className="hg-site__footer-heading">Explore</p>
          <button type="button" className="hg-site__footer-link" onClick={() => onNavigate('donate')}>Donate</button>
          <button type="button" className="hg-site__footer-link" onClick={() => onNavigate('volunteer')}>Volunteer</button>
          <button type="button" className="hg-site__footer-link" onClick={() => onNavigate('home')}>Home</button>
        </div>
        <div>
          <p className="hg-site__footer-heading">Contact</p>
          <p className="hg-site__footer-muted">{HARBOR_FUND.phone}</p>
          <p className="hg-site__footer-muted">{HARBOR_FUND.email}</p>
          <p className="hg-site__footer-legal">Privacy · 501(c)(3) · EIN on request</p>
        </div>
      </div>
      <p className="hg-site__footer-copy">© 2026 {HARBOR_FUND.name}. All rights reserved.</p>
    </footer>
  );
}

export default function HarborDonorSite({ onDonate, onVolunteerIntent }: Props) {
  const brandName = useOverlayBrand(HARBOR_FUND.name);
  const [page, setPage] = useState<Page>('home');
  const scrollRef = useRef<HTMLDivElement>(null);
  const [amount, setAmount] = useState(50);
  const [recurring, setRecurring] = useState(false);
  const [donorName, setDonorName] = useState('Maya Chen');
  const [confirmed, setConfirmed] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const nav = useCallback((p: Page) => {
    setPage(p);
    scrollRef.current?.scrollTo(0, 0);
  }, []);

  const pct = Math.min(100, Math.round((IMPACT_METER.raised / IMPACT_METER.goal) * 100));
  const story = storyForAmount(amount);
  const tier = DONATE_TIERS.find((t) => t.amount === amount);
  const suggestion = AI_SUGGESTIONS.find((s) => s.amount === amount);

  const confirmGift = () => {
    setConfirmed(true);
    onDonate({
      id: `don-${Date.now()}`,
      amount,
      tier: tier?.label ?? 'Custom',
      donorName,
      recurring,
      campaignId: 'bridge',
    });
  };

  return (
    <div className="hg-site">
      <header className="hg-site__header">
        <button type="button" className="hg-site__brand" onClick={() => nav('home')}>
          <HarborFundLogo className="hg-site__mark" />
          <span className="hg-site__name">{HARBOR_FUND.name}</span>
        </button>
        <nav className="hg-site__nav" aria-label="Site navigation">
          {(['home', 'donate', 'volunteer'] as Page[]).map((p) => (
            <button
              key={p}
              type="button"
              className={`hg-site__nav-link ${page === p ? 'hg-site__nav-link--on' : ''}`}
              onClick={() => nav(p)}
            >
              {p === 'home' ? 'Home' : p === 'donate' ? 'Donate' : 'Volunteer'}
            </button>
          ))}
        </nav>
        <button type="button" className="hg-site__nav-cta" onClick={() => setChatOpen(true)}>
          Ask AI
        </button>
      </header>

      <div className="hg-site__scroll" ref={scrollRef}>
        <div className="hg-site__main">
          <SitePane id="home" current={page}>
            <section className="hg-site__hero" data-overlay-target="hero">
              <img src={HARBOR_FUND.heroImage} alt="" className="hg-site__hero-bg" onError={onHarborFundImageError} />
              <div className="hg-site__hero-overlay" />
              <div className="hg-site__hero-grain" aria-hidden />
              <div className="hg-site__hero-content">
                <p className="hg-site__hero-brand">{brandName}</p>
                <OverlayHeroTitle className="hg-site__hero-title" primary="Give where it lands." />
                <OverlayHeroSub className="hg-site__hero-sub">
                  Neighbors funding meals, mentorship, and housing — one gift, one shift at a time.
                </OverlayHeroSub>
                <div className="hg-site__hero-ctas">
                  <button type="button" className="hg-site__btn hg-site__btn--primary" onClick={() => nav('donate')}>
                    Donate
                  </button>
                  <button
                    type="button"
                    className="hg-site__btn hg-site__btn--ghost"
                    onClick={() => { onVolunteerIntent?.(); nav('volunteer'); }}
                  >
                    Volunteer
                  </button>
                </div>
              </div>
            </section>

            <OverlayCustomSections />

            <section className="hg-site__campaign" id="campaign">
              <div className="hg-site__campaign-inner">
                <div className="hg-site__campaign-copy">
                  <p className="hg-site__section-eyebrow">Bridge the Gap 2026</p>
                  <h2>This season&apos;s campaign</h2>
                  <p>
                    Live impact meter and smart gift tiers — moved here so the welcome stays quiet and purposeful.
                  </p>
                </div>

                <div className="hg-site__meter">
                  <div className="hg-site__meter-head">
                    <strong>Campaign progress</strong>
                    <span>{pct}% funded</span>
                  </div>
                  <div className="hg-site__meter-bar" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                    <div style={{ width: `${pct}%` }} />
                  </div>
                  <div className="hg-site__meter-nums">
                    <span>${IMPACT_METER.raised.toLocaleString()} raised</span>
                    <span>Goal ${IMPACT_METER.goal.toLocaleString()}</span>
                  </div>
                  <div className="hg-site__meter-stats">
                    <span>{IMPACT_METER.donors.toLocaleString()} donors</span>
                    <span>{IMPACT_METER.meals.toLocaleString()} meals</span>
                    <span>{IMPACT_METER.families} families</span>
                  </div>
                </div>

                <div className="hg-site__donate-widget">
                  <p className="hg-site__widget-label">Choose a gift tier</p>
                  <div className="hg-site__tier-row">
                    {DONATE_TIERS.map((t) => (
                      <button
                        key={t.amount}
                        type="button"
                        className={`hg-site__tier ${amount === t.amount ? 'hg-site__tier--on' : ''} ${t.suggested ? 'hg-site__tier--suggest' : ''}`}
                        onClick={() => setAmount(t.amount)}
                      >
                        ${t.amount}
                        {t.suggested && <em>Best match</em>}
                      </button>
                    ))}
                  </div>
                  <p className="hg-site__tier-impact">{story.metric} · {tier?.impact ?? story.story}</p>
                  <button type="button" className="hg-site__btn hg-site__btn--primary" onClick={() => nav('donate')}>
                    Continue with ${amount}
                  </button>
                </div>
              </div>
            </section>

            <section className="hg-site__section hg-site__section--stories">
              <h2>Impact stories</h2>
              <p className="hg-site__section-sub">Each gift amount maps to a living community outcome.</p>
              <div className="hg-site__stories">
                {IMPACT_STORIES.map((s) => (
                  <article key={s.id} className="hg-site__story">
                    <div className="hg-site__story-media">
                      <img
                        src={s.imageUrl}
                        alt={s.title}
                        data-hg-scene={s.id}
                        onError={(e) => onHarborFundImageError(e, s.id)}
                      />
                      <span className="hg-site__story-amt">${s.amount}+</span>
                    </div>
                    <div className="hg-site__story-body">
                      <h3>{s.title}</h3>
                      <p>{s.story}</p>
                      <div className="hg-site__story-foot">
                        <strong>{s.metric}</strong>
                        <span>Campaign AI</span>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="hg-site__section">
              <h2>From the community</h2>
              <div className="hg-site__reviews">
                {REVIEWS.map((r) => (
                  <blockquote key={r.name} className="hg-site__review">
                    <p>“{r.text}”</p>
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

          <SitePane id="donate" current={page}>
            <section className="hg-site__page-hero">
              <h1>Complete your gift</h1>
              <p>Smart amount · impact story · thank-you receipt queued automatically.</p>
            </section>
            <div className="hg-site__donate-flow">
              <div className="hg-site__donate-form">
                <label>
                  Your name
                  <input value={donorName} onChange={(e) => setDonorName(e.target.value)} />
                </label>

                <div className="hg-site__ai-suggest">
                  <p className="hg-site__widget-label">AI amount suggestions</p>
                  <div className="hg-site__suggest-list">
                    {AI_SUGGESTIONS.map((s) => (
                      <button
                        key={s.amount}
                        type="button"
                        className={`hg-site__suggest ${amount === s.amount ? 'hg-site__suggest--on' : ''}`}
                        onClick={() => setAmount(s.amount)}
                      >
                        <span className="hg-site__suggest-badge">{s.badge}</span>
                        <strong>${s.amount}</strong>
                        <em>{s.why}</em>
                      </button>
                    ))}
                  </div>
                </div>

                <p className="hg-site__widget-label">Or pick a tier</p>
                <div className="hg-site__tier-row">
                  {DONATE_TIERS.map((t) => (
                    <button
                      key={t.amount}
                      type="button"
                      className={`hg-site__tier ${amount === t.amount ? 'hg-site__tier--on' : ''}`}
                      onClick={() => setAmount(t.amount)}
                    >
                      ${t.amount}
                    </button>
                  ))}
                </div>
                {suggestion && (
                  <p className="hg-site__suggest-why">{suggestion.why}</p>
                )}
                <label className="hg-site__check">
                  <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
                  Make this monthly — impact story each cycle
                </label>
                <button
                  type="button"
                  className="hg-site__btn hg-site__btn--primary"
                  onClick={confirmGift}
                  disabled={confirmed}
                >
                  {confirmed ? 'Gift confirmed' : `Give $${amount}${recurring ? '/mo' : ''}`}
                </button>
              </div>
              <aside className="hg-site__impact-card">
                <div className="hg-site__story-media">
                  <img
                    src={story.imageUrl}
                    alt={story.title}
                    data-hg-scene={story.id}
                    onError={(e) => onHarborFundImageError(e, story.id)}
                  />
                  <span className="hg-site__story-amt">Impact · ${amount}</span>
                </div>
                <div className="hg-site__impact-card-body">
                  <h3>{story.title}</h3>
                  <p>{story.story}</p>
                  <div className="hg-site__story-foot">
                    <strong>{story.metric}</strong>
                    <span>Campaign AI</span>
                  </div>
                  <ul className="hg-site__impact-beats">
                    <li>Thank-you bot drafts your receipt in under 60s</li>
                    <li>Impact story ties to Bridge the Gap live meter</li>
                    <li>Tax PDF · EIN on file · privacy-first</li>
                  </ul>
                  {confirmed && (
                    <div className="hg-site__receipt-note">
                      Thank-you bot: personalized receipt → inbox in &lt;60s
                    </div>
                  )}
                </div>
              </aside>
            </div>
            <SiteFooter onNavigate={nav} />
          </SitePane>

          <SitePane id="volunteer" current={page}>
            <section className="hg-site__page-hero">
              <h1>Volunteer with purpose</h1>
              <p>Open the Volunteer board for skill match scores — or ask Harbor AI to place you.</p>
            </section>
            <div className="hg-site__vol-cta">
              <img src={HARBOR_FUND.communityImage} alt="" onError={onHarborFundImageError} />
              <div>
                <h2>Skills → opportunities</h2>
                <p>Kitchen, tutoring, logistics, outreach, admin, tech — AI ranks open shifts by fit.</p>
                <button
                  type="button"
                  className="hg-site__btn hg-site__btn--primary"
                  onClick={() => onVolunteerIntent?.()}
                >
                  Open volunteer board
                </button>
              </div>
            </div>
            <SiteFooter onNavigate={nav} />
          </SitePane>
        </div>
      </div>

      <HarborDonorChat
        open={chatOpen}
        onOpenChange={setChatOpen}
        onDonateClick={() => { setChatOpen(false); nav('donate'); }}
      />
    </div>
  );
}
