import { useState } from 'react';
import { HarborFundLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import {
  HARBOR_FUND,
  CAMPAIGNS,
  DONOR_SEGMENTS,
  VOLUNTEER_HOURS,
  campaignPct,
  type Campaign,
} from './harborFundData.ts';
import { onHarborFundImageError } from './harborFundImageFallback.ts';

type HubPage = 'campaigns' | 'segments' | 'hours';

const METRICS = [
  { label: 'Raised (Q2)', value: '$186k', sub: '75% of Bridge goal', accent: true },
  { label: 'Active donors', value: '1,842', sub: '+112 this week' },
  { label: 'Thank-yous sent', value: '186', sub: 'Under 60s avg' },
  { label: 'Volunteer hours', value: '3,660', sub: 'Matcher fill 91%' },
];

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'campaigns', label: 'Campaign rings', sub: 'Goal progress' },
  { id: 'segments', label: 'Donor segments', sub: 'Who gives' },
  { id: 'hours', label: 'Volunteer hours', sub: 'By skill area' },
];

function ProgressRing({ value, size = 72, label }: { value: number; size?: number; label?: string }) {
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const offset = c - (value / 100) * c;
  const gradId = `hg-ring-${value}-${size}`;
  return (
    <svg className="hg-hub__ring" width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden>
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#b8860b" />
          <stop offset="100%" stopColor="#14532d" />
        </linearGradient>
      </defs>
      <circle className="hg-hub__ring-bg" cx={size / 2} cy={size / 2} r={r} />
      <circle
        className="hg-hub__ring-fill"
        cx={size / 2}
        cy={size / 2}
        r={r}
        stroke={`url(#${gradId})`}
        strokeDasharray={c}
        strokeDashoffset={offset}
      />
      <text x={size / 2} y={size / 2 + (label ? 0 : 4)} textAnchor="middle" className="hg-hub__ring-text">
        {value}%
      </text>
      {label && (
        <text x={size / 2} y={size / 2 + 14} textAnchor="middle" className="hg-hub__ring-sub">
          {label}
        </text>
      )}
    </svg>
  );
}

function CampaignCard({ campaign }: { campaign: Campaign }) {
  const pct = campaignPct(campaign);
  return (
    <article className={`hg-hub__campaign hg-hub__campaign--${campaign.status}`}>
      <ProgressRing value={pct} size={88} />
      <div>
        <div className="hg-hub__campaign-top">
          <strong>{campaign.name}</strong>
          <span className={`hg-hub__status hg-hub__status--${campaign.status}`}>
            {campaign.status === 'active' ? 'Active' : campaign.status === 'closing' ? 'Closing soon' : 'Completed'}
          </span>
        </div>
        <p className="hg-hub__campaign-money">
          ${campaign.raised.toLocaleString()} / ${campaign.goal.toLocaleString()}
        </p>
        <p className="hg-hub__campaign-meta">
          {campaign.donors.toLocaleString()} donors
          {campaign.daysLeft > 0 ? ` · ${campaign.daysLeft} days left` : ' · Goal met'}
        </p>
      </div>
    </article>
  );
}

export default function HarborCampaignHub() {
  const [page, setPage] = useState<HubPage>('campaigns');

  return (
    <div className="hg-hub">
      <aside className="hg-hub__nav">
        <div className="hg-hub__brand">
          <HarborFundLogo className="hg-hub__brand-logo" />
          <div>
            <strong>Campaign hub</strong>
            <span>Harbor Give</span>
          </div>
        </div>
        <nav aria-label="Hub navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'hg-hub__nav-btn hg-hub__nav-btn--on' : 'hg-hub__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="hg-hub__nav-label">{item.label}</span>
              <span className="hg-hub__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className="hg-hub__nav-foot">
          <span className="hg-hub__nav-live" />
          Fund live
        </div>
      </aside>

      <main className="hg-hub__main">
        <div className="hg-hub__hero-strip">
          <img src={HARBOR_FUND.communityImage} alt="" onError={onHarborFundImageError} />
          <div className="hg-hub__hero-shade" aria-hidden />
          <div className="hg-hub__hero-copy">
            <p>{HARBOR_FUND.name}</p>
            <strong>Bridge the Gap · donor segments · volunteer hours</strong>
          </div>
        </div>

        <header className="hg-hub__head">
          <div>
            <p className="hg-hub__head-eyebrow">{HARBOR_FUND.product}</p>
            <h1>
              {page === 'campaigns'
                ? 'Campaign progress'
                : page === 'segments'
                  ? 'Donor segments'
                  : 'Volunteer hours'}
            </h1>
            <p>Lean team dashboard — progress rings, not a generic CRM</p>
          </div>
          <span className="hg-hub__live">Live</span>
        </header>

        <div className="hg-hub__metrics">
          {METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'hg-hub__metric hg-hub__metric--accent' : 'hg-hub__metric'}>
              <strong>{m.value}</strong>
              <span>{m.label}</span>
              <small>{m.sub}</small>
            </article>
          ))}
        </div>

        {page === 'campaigns' && (
          <div className="hg-hub__campaigns">
            {CAMPAIGNS.map((c) => (
              <CampaignCard key={c.id} campaign={c} />
            ))}
          </div>
        )}

        {page === 'segments' && (
          <>
            <div className="hg-hub__ai-banner">
              <div>
                <strong>
                  <IconSparkle className="hg-hub__sparkle" />
                  Segment AI — first-time donors up 18% this week
                </strong>
                <p>Thank-you sequences auto-tagged by segment · major gifts flagged for ED follow-up</p>
              </div>
              <span className="hg-hub__ai-banner-tag">5 segments</span>
            </div>
            <div className="hg-hub__segments">
              {DONOR_SEGMENTS.map((s) => (
                <article key={s.id} className="hg-hub__segment">
                  <div className="hg-hub__segment-swatch" style={{ background: s.color }} />
                  <div className="hg-hub__segment-body">
                    <strong>{s.label}</strong>
                    <span>{s.count} donors · avg {s.avgGift}</span>
                    <div className="hg-hub__segment-bar">
                      <div style={{ width: `${s.pct}%`, background: s.color }} />
                    </div>
                  </div>
                  <span className="hg-hub__segment-pct">{s.pct}%</span>
                </article>
              ))}
            </div>
          </>
        )}

        {page === 'hours' && (
          <div className="hg-hub__hours">
            {VOLUNTEER_HOURS.map((h) => (
              <article key={h.label} className="hg-hub__hour-row">
                <div className="hg-hub__hour-label">
                  <strong>{h.label}</strong>
                  <span>{h.hours.toLocaleString()} hrs</span>
                </div>
                <div className="hg-hub__hour-bar">
                  <div style={{ width: `${h.pct}%` }} />
                </div>
                <span className="hg-hub__hour-pct">{h.pct}%</span>
              </article>
            ))}
            <p className="hg-hub__hours-note">
              Matcher fill rate 91% · open shifts auto-pushed to skill-matched volunteers
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
