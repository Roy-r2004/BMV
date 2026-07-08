import { useMemo, useState } from 'react';
import { NorthlineLogo } from '../shared/ShowcaseChatIcons.tsx';
import { AGENCY, AGENTS, CRM_LEADS, LISTINGS, type Lead } from './northlineData.ts';
import { onNorthlineImageError } from './northlineImageFallback.ts';

type HubPage = 'pipeline' | 'listings' | 'agents' | 'connect';

const METRICS = [
  { label: 'Hot leads', value: '14', sub: 'AI-scored this week', accent: true },
  { label: 'Viewings today', value: '6', sub: '2 need follow-up' },
  { label: 'Listings live', value: '38', sub: 'Across 3 agents' },
  { label: 'Avg response', value: '< 2m', sub: 'AI + agent handoff' },
];

const NAV: { id: HubPage; label: string; sub: string }[] = [
  { id: 'pipeline', label: 'Pipeline', sub: 'Hot leads' },
  { id: 'listings', label: 'Listings', sub: 'Inventory' },
  { id: 'agents', label: 'Agents', sub: 'Team roster' },
  { id: 'connect', label: 'Connect', sub: 'Integrations' },
];

const PAGE_TITLE: Record<HubPage, string> = {
  pipeline: 'Agent CRM',
  listings: 'Listing manager',
  agents: 'Team roster',
  connect: 'Connections',
};

const KANBAN: { score: Lead['score']; label: string; hint: string }[] = [
  { score: 'hot', label: 'Hot', hint: 'Book viewing' },
  { score: 'warm', label: 'Warm', hint: 'Nurture' },
  { score: 'cold', label: 'Cold', hint: 'Re-engage' },
];

const CONNECT = [
  { name: 'MLS feed', detail: 'REBNY · sync every 15m', on: true },
  { name: 'Zillow leads', detail: 'Auto-score + route', on: true },
  { name: 'DocuSign', detail: 'Offer packets ready', on: true },
  { name: 'Calendar sync', detail: 'Google · agent viewings', on: true },
];

const SCORE_LABEL: Record<Lead['score'], string> = {
  hot: 'Hot',
  warm: 'Warm',
  cold: 'Cold',
};

export default function NorthlineAgentCRM() {
  const [page, setPage] = useState<HubPage>('pipeline');

  const leadsByScore = useMemo(() => {
    const map: Record<Lead['score'], Lead[]> = { hot: [], warm: [], cold: [] };
    CRM_LEADS.forEach((lead) => map[lead.score].push(lead));
    return map;
  }, []);

  return (
    <div className="nr-crm">
      <aside className="nr-crm__nav">
        <div className="nr-crm__brand">
          <NorthlineLogo className="nr-crm__brand-logo" />
          <div>
            <strong>Northline CRM</strong>
            <span>Agent hub</span>
          </div>
        </div>
        <nav aria-label="CRM navigation">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={page === item.id ? 'nr-crm__nav-btn nr-crm__nav-btn--on' : 'nr-crm__nav-btn'}
              onClick={() => setPage(item.id)}
            >
              <span className="nr-crm__nav-label">{item.label}</span>
              <span className="nr-crm__nav-sub">{item.sub}</span>
            </button>
          ))}
        </nav>
        <div className="nr-crm__nav-foot">
          <span className="nr-crm__nav-live" />
          Pipeline live
        </div>
      </aside>

      <main className="nr-crm__main">
        <div className="nr-crm__hero-strip">
          <img src={AGENCY.officeImage} alt="" onError={onNorthlineImageError} />
          <div className="nr-crm__hero-shade" aria-hidden />
          <div className="nr-crm__hero-grain" aria-hidden />
          <div className="nr-crm__hero-copy">
            <p>Brooklyn & Manhattan</p>
            <strong>14 hot leads · 6 viewings today</strong>
          </div>
        </div>

        <header className="nr-crm__head">
          <div>
            <p className="nr-crm__head-eyebrow">{AGENCY.name}</p>
            <h1>{PAGE_TITLE[page]}</h1>
            <p>Saturday · 14 qualified leads · 3 agents on route</p>
          </div>
          <span className="nr-crm__live">Live</span>
        </header>

        <div className="nr-crm__metrics">
          {METRICS.map((m) => (
            <article key={m.label} className={m.accent ? 'nr-crm__metric nr-crm__metric--accent' : 'nr-crm__metric'}>
              <strong>{m.value}</strong>
              <span>{m.label}</span>
              <small>{m.sub}</small>
            </article>
          ))}
        </div>

        {page === 'pipeline' && (
          <>
            <div className="nr-crm__ai-banner">
              <div>
                <strong>14 hot leads scored overnight — competitors got forms, you got tours</strong>
                <p>Budget + timeline + engagement ranked · agents only dial the top 5</p>
              </div>
              <span className="nr-crm__ai-banner-tag">Deal magnet</span>
            </div>
            <div className="nr-crm__kanban">
            {KANBAN.map((col) => (
              <section key={col.score} className="nr-crm__column">
                <header>
                  <h3>{col.label}</h3>
                  <span>{col.hint}</span>
                </header>
                <ul>
                  {leadsByScore[col.score].map((lead) => (
                    <li key={lead.id}>
                      <article className={`nr-crm__lead nr-crm__lead--${lead.score}`}>
                        <div className="nr-crm__lead-top">
                          <strong>{lead.name}</strong>
                          <span className={`nr-crm__score nr-crm__score--${lead.score}`}>{SCORE_LABEL[lead.score]}</span>
                        </div>
                        <p className="nr-crm__lead-listing">{lead.listing}</p>
                        <div className="nr-crm__lead-meta">
                          <span>{lead.source}</span>
                          <span>{lead.budget}</span>
                        </div>
                        <footer>{lead.lastActivity}</footer>
                      </article>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          </>
        )}

        {page === 'listings' && (
          <div className="nr-crm__listings">
            {LISTINGS.map((l) => (
              <article key={l.id} className="nr-crm__listing-card">
                <img src={l.imageUrl} alt={l.address} loading="lazy" onError={(e) => onNorthlineImageError(e, l.address)} />
                <div>
                  <h3>{l.address}</h3>
                  <p>{l.neighborhood} · {l.price}</p>
                  <span>{l.beds} bed · {l.baths} bath · {l.sqft} sqft</span>
                  {l.tag && <em>{l.tag}</em>}
                </div>
                <button type="button">Edit</button>
              </article>
            ))}
          </div>
        )}

        {page === 'agents' && (
          <div className="nr-crm__agents">
            {AGENTS.map((a) => (
              <article key={a.id} className="nr-crm__agent-card">
                <img src={a.imageUrl} alt={a.name} loading="lazy" onError={(e) => onNorthlineImageError(e, a.photoInitial)} />
                <div>
                  <h3>{a.name}</h3>
                  <p>{a.title}</p>
                  <p className="nr-crm__agent-bio">{a.bio}</p>
                  <div className="nr-crm__agent-tags">
                    {a.specialties.map((t) => <span key={t}>{t}</span>)}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {page === 'connect' && (
          <div className="nr-crm__connect">
            {CONNECT.map((c) => (
              <article key={c.name} className={c.on ? 'nr-crm__connect-card nr-crm__connect-card--on' : 'nr-crm__connect-card'}>
                <div>
                  <h3>{c.name}</h3>
                  <p>{c.detail}</p>
                </div>
                <span className="nr-crm__toggle" aria-hidden>{c.on ? 'On' : 'Off'}</span>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
