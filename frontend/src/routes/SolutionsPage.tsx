import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import ConceptScreens from '../components/concepts/ConceptScreens';
import { CONCEPT_ICONS } from '../components/concepts/ConceptIcons';
import { useCycle } from '../components/showroom/useCycle';
import { CONCEPT_GROUPS, CONCEPTS } from '../data/concepts';
import '../styles/showroom.css';

// Everything shown comes from data/concepts. They are concepts, so the page
// says so and quotes no results.
const BY_GROUP = CONCEPT_GROUPS.map((g) => CONCEPTS.filter((c) => c.group === g));
const FACTS = [`${CONCEPTS.length} concepts`, `${CONCEPT_GROUPS.length} areas of the business`, 'Every one shown screen by screen'];

const PRINCIPLES = [
  'Whole systems, not single features',
  'Every concept shown screen by screen',
  'Yours starts from how your business actually works',
];

function Arrow() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

export default function SolutionsPage() {
  const [group, setGroup] = useState(0);
  const items = BY_GROUP[group];
  const [sel, pick] = useCycle(items.length, 5200);
  const c = items[Math.min(sel, items.length - 1)];
  const visualRef = useRef<HTMLDivElement>(null);

  const openGroup = (g: number, i = 0) => {
    setGroup(g);
    pick(i);
  };
  const showFromIndex = (g: number, i: number) => {
    openGroup(g, i);
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    visualRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
  };

  return (
    <div className="show-page min-h-screen overflow-x-clip">
      <SiteNav />

      {/* ── the concepts, screen by screen ─────────────────────────────── */}
      <section className="show-hero">
        <div className="container-max px-4 sm:px-6 show-hero-grid">
          <div className="show-intro">
            <h1 className="show-display show-h1">The future, built for your business.</h1>
            <p className="show-lede">
              AI software for whole operations, not another chatbot: systems that run the business, grow revenue, create
              and see the physical world. Each one is a concept we build around your business.
            </p>
            <ul className="show-facts">
              {FACTS.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </div>

          <div className="show-visual" ref={visualRef}>
            <ConceptScreens concepts={CONCEPTS} selected={CONCEPTS.indexOf(c)} />
            <article className="show-detail" aria-live="polite">
              <div className="show-detail-head">
                <span className="show-icon">{CONCEPT_ICONS[c.id]}</span>
                <div>
                  <h2 className="show-display show-detail-title">{c.name}</h2>
                  <span className="show-tag">{c.industry}</span> <span className="show-tag show-tag--quiet">Concept</span>
                </div>
              </div>
              <p className="show-detail-body">{c.tagline}</p>
              <dl className="show-pair">
                <div>
                  <dt>Who it's for</dt>
                  <dd>{c.buyer}</dd>
                </div>
                <div>
                  <dt>What changes</dt>
                  <dd>{c.change}</dd>
                </div>
              </dl>
              <ul className="show-ticks show-ticks--two">
                {c.features.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              <p className="show-detail-foot">A concept of what we can build, shaped around your business. Not a client case study.</p>
            </article>
          </div>

          <div className="show-picker">
            <div className="show-tabs" role="group" aria-label="Area of the business">
              {CONCEPT_GROUPS.map((g, i) => (
                <button key={g} type="button" aria-pressed={i === group} onClick={() => openGroup(i)}>
                  {g}
                </button>
              ))}
            </div>
            <ul className="show-picker-list">
              {items.map((x, i) => (
                <li key={x.id}>
                  <button
                    type="button"
                    className={x.id === c.id ? 'is-on' : undefined}
                    aria-pressed={x.id === c.id}
                    onClick={() => pick(i)}
                    onMouseEnter={() => pick(i)}
                    onFocus={() => pick(i)}
                  >
                    <span className="show-icon show-icon--sm">{CONCEPT_ICONS[x.id]}</span>
                    <span className="show-picker-name">
                      {x.name}
                      <small>{x.industry}</small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ── every concept, by area ─────────────────────────────────────── */}
      <section className="show-band">
        <div className="container-max px-4 sm:px-6">
          <h2 className="show-display show-h2">Every solution</h2>
          <p className="show-body">Choose any of them to see it screen by screen.</p>
          <div className="show-groups">
            {BY_GROUP.map((list, g) => (
              <div key={CONCEPT_GROUPS[g]}>
                <h3 className="show-display show-group-title">{CONCEPT_GROUPS[g]}</h3>
                <ul className="show-index show-index--one">
                  {list.map((x, i) => (
                    <li key={x.id}>
                      <button type="button" onClick={() => showFromIndex(g, i)}>
                        <span className="show-icon show-icon--sm">{CONCEPT_ICONS[x.id]}</span>
                        <span className="show-index-text">
                          <span className="show-index-name">{x.name}</span>
                          <span className="show-index-line">{x.tagline}</span>
                        </span>
                        <Arrow />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── what these have in common ──────────────────────────────────── */}
      <section className="show-section">
        <div className="container-max px-4 sm:px-6">
          <ul className="show-principles">
            {PRINCIPLES.map((p) => (
              <li key={p} className="show-display">
                {p}
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ── your own ───────────────────────────────────────────────────── */}
      <section className="show-close">
        <div className="container-max px-4 sm:px-6 show-close-inner">
          <div>
            <h2 className="show-display show-h2">Want one of these built for you?</h2>
            <p className="show-body">
              Tell us how your operation works and we'll tell you which of these fits, and what it would take to build.
            </p>
          </div>
          <Link to="/demo" className="show-cta">
            Find my AI fit
            <Arrow />
          </Link>
        </div>
      </section>

      <SiteFooter />
    </div>
  );
}
