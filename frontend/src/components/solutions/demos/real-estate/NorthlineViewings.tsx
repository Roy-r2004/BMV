import { AGENCY, LISTINGS, TODAY_VIEWINGS } from './northlineData.ts';
import { onNorthlineImageError } from './northlineImageFallback.ts';

const TIMELINE = [
  { time: '9:30', label: 'Office standup', active: false },
  { time: '10:00', label: 'Alex P. · Oak Lane', active: true },
  { time: '11:30', label: 'Nina S. · Park View', active: false },
  { time: '2:00', label: 'James L. · River Loft', active: false },
];

interface Props {
  highlightBuyer?: string;
}

export default function NorthlineViewings({ highlightBuyer = 'Alex P.' }: Props) {
  const confirmed = TODAY_VIEWINGS.filter((v) => v.status === 'confirmed').length;
  const pending = TODAY_VIEWINGS.filter((v) => v.status === 'pending').length;
  const open = TODAY_VIEWINGS.filter((v) => v.status === 'open').length;

  return (
    <div className="nr-view">
      <div className="nr-view__grain" aria-hidden />
      <header className="nr-view__head">
        <div>
          <p className="nr-view__eyebrow">Saturday · Agent calendars</p>
          <h2>Viewings schedule</h2>
          <p className="nr-view__sub">{TODAY_VIEWINGS.length} tours today · live agent handoff</p>
        </div>
        <div className="nr-view__stats">
          <article><strong>{confirmed}</strong><span>Confirmed</span></article>
          <article><strong>{pending}</strong><span>Pending</span></article>
          <article><strong>{open}</strong><span>Open slots</span></article>
        </div>
      </header>

      <div className="nr-view__hero-strip">
        <img src={AGENCY.officeImage} alt="" onError={onNorthlineImageError} />
        <div className="nr-view__hero-shade" aria-hidden />
        <div className="nr-view__hero-copy">
          <p>Today&apos;s route</p>
          <strong>4 viewings · 3 agents · Brooklyn loop</strong>
        </div>
      </div>

      <div className="nr-view__timeline">
        {TIMELINE.map((t) => (
          <div key={t.time} className={`nr-view__timeline-item ${t.active ? 'nr-view__timeline-item--active' : ''}`}>
            <time>{t.time}</time>
            <span>{t.label}</span>
          </div>
        ))}
      </div>

      <div className="nr-view__layout">
        <section className="nr-view__schedule">
          <h3>Today&apos;s tours</h3>
          <ul className="nr-view__list">
            {TODAY_VIEWINGS.map((v) => {
              const highlighted = v.buyer === highlightBuyer;
              const listing = LISTINGS.find((l) => l.address === v.listing);
              return (
                <li key={`${v.time}-${v.buyer}`}>
                  <article className={`nr-view__card ${highlighted ? 'nr-view__card--highlight' : ''} nr-view__card--${v.status}`}>
                    <div className="nr-view__card-time">
                      <time>{v.time}</time>
                      <span className={`nr-view__status nr-view__status--${v.status}`}>{v.status}</span>
                    </div>
                    <div className="nr-view__card-body">
                      <strong>{v.buyer}</strong>
                      <p>{v.listing}</p>
                      <span className="nr-view__agent">{v.agent}</span>
                    </div>
                    {listing && (
                      <div className="nr-view__card-thumb">
                        <img src={listing.imageUrl} alt="" loading="lazy" onError={(e) => onNorthlineImageError(e, listing.address)} />
                      </div>
                    )}
                    {highlighted && <span className="nr-view__new-badge">Just booked</span>}
                  </article>
                </li>
              );
            })}
          </ul>
        </section>

        <aside className="nr-view__agents">
          <h3>Agent load</h3>
          <div className="nr-view__agent-bars">
            <div className="nr-view__agent-row">
              <span>Sarah Chen</span>
              <div className="nr-view__bar"><span style={{ width: '75%' }} /></div>
              <small>2 tours</small>
            </div>
            <div className="nr-view__agent-row">
              <span>Elena Ruiz</span>
              <div className="nr-view__bar"><span style={{ width: '50%' }} /></div>
              <small>1 tour</small>
            </div>
            <div className="nr-view__agent-row">
              <span>Marcus Webb</span>
              <div className="nr-view__bar"><span style={{ width: '50%' }} /></div>
              <small>1 tour</small>
            </div>
          </div>

          <h3>Upcoming week</h3>
          <ul className="nr-view__week">
            <li><strong>Sun</strong> 3 tours · Oak Lane open house</li>
            <li><strong>Mon</strong> 2 private showings</li>
            <li><strong>Tue</strong> Investor block · River Loft</li>
          </ul>

          <button type="button" className="nr-view__add-btn">+ Block viewing slot</button>
        </aside>
      </div>
    </div>
  );
}
