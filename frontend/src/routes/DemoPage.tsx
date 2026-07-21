import { useEffect, useMemo, useState } from 'react';
import type { CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import CinematicCTA from '../components/CinematicCTA';
import GlowButton from '../components/GlowButton';
import { listDemos } from '../api/demos';
import type { DemoListItem } from '../types/demo';
import '../styles/demo-magazine.css';

const ease = [0.22, 1, 0.36, 1] as const;

function clean(text: string) {
  return text.replace(/\*\*/g, '').replace(/^\+\+|\+\+$/g, '').trim();
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function DemoPage() {
  const reduce = useReducedMotion();
  const [demos, setDemos] = useState<DemoListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('All');

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const data = await listDemos();
        if (alive) setDemos(data.demos);
      } catch {
        if (alive) setError('Could not load live demos.');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const industries = useMemo(() => {
    const set = new Set<string>();
    demos.forEach((d) => {
      if (d.industry) set.add(d.industry);
    });
    return ['All', ...Array.from(set)];
  }, [demos]);

  const filtered = useMemo(() => {
    if (filter === 'All') return demos;
    return demos.filter((d) => (d.industry || '') === filter);
  }, [demos, filter]);

  const featured = filtered[0] ?? null;
  const rest = featured ? filtered.filter((d) => d.id !== featured.id) : [];

  return (
    <div className="demo-mag">
      <SiteNav />

      <header className="demo-mag__hero">
        <div className="container-max px-4 sm:px-6">
          <div className="demo-mag__hero-inner">
            <motion.p
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="demo-mag__eyebrow"
            >
              Live builds · AI consultancy
            </motion.p>
            <motion.h1
              initial={reduce ? false : { opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05, duration: 0.55, ease }}
              className="demo-mag__title"
            >
              Products we built
              <em>for real businesses.</em>
            </motion.h1>
            <motion.p
              initial={reduce ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, duration: 0.5, ease }}
              className="demo-mag__sub"
            >
              Browse live builds from our consultancy. Open any product to explore it — then we find
              the AI & automation fit for yours.
            </motion.p>
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.16, duration: 0.45, ease }}
              className="demo-mag__actions"
            >
              <GlowButton to="/submit" className="text-sm px-7 py-3.5 !inline-flex">
                Find my AI fit
              </GlowButton>
              <a href="#builds" className="demo-mag__text-link">
                Browse builds ↓
              </a>
            </motion.div>
          </div>
        </div>
      </header>

      <main id="builds" className="demo-mag__main">
        <div className="container-max px-4 sm:px-6">
          {loading && (
            <div className="demo-mag__state">
              <div className="demo-mag__spinner" />
              Loading live builds…
            </div>
          )}

          {error && <p className="demo-mag__error">{error}</p>}

          {!loading && !error && demos.length === 0 && (
            <div className="demo-mag__state">
              <p>No live builds yet — yours could be first.</p>
              <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-flex">
                Create my version
              </GlowButton>
            </div>
          )}

          {!loading && demos.length > 0 && (
            <>
              {industries.length > 2 && (
                <div className="demo-mag__filters" role="toolbar" aria-label="Filter by industry">
                  {industries.map((ind) => (
                    <button
                      key={ind}
                      type="button"
                      className={`demo-mag__chip ${filter === ind ? 'demo-mag__chip--on' : ''}`}
                      onClick={() => setFilter(ind)}
                    >
                      {ind}
                    </button>
                  ))}
                </div>
              )}

              {featured && (
                <motion.article
                  initial={reduce ? false : { opacity: 0, y: 18 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.5, ease }}
                  className="demo-mag__featured"
                >
                  <div className="demo-mag__meta">
                    <span className="demo-mag__live">
                      <i /> Live build
                    </span>
                    <span className="demo-mag__ind">{featured.industry || 'Custom'}</span>
                    {featured.business_fit_score != null && featured.business_fit_score > 0 && (
                      <span className="demo-mag__score">{featured.business_fit_score}% fit</span>
                    )}
                  </div>
                  <h2>{featured.concept_name}</h2>
                  <p className="demo-mag__biz">{featured.business_name}</p>
                  {featured.preview_summary && (
                    <p className="demo-mag__summary">{clean(featured.preview_summary)}</p>
                  )}
                  {featured.preview_features.length > 0 && (
                    <ul className="demo-mag__feats">
                      {featured.preview_features.slice(0, 3).map((f) => (
                        <li key={f}>{clean(f)}</li>
                      ))}
                    </ul>
                  )}
                  <div className="demo-mag__featured-cta">
                    <GlowButton
                      to={`/result/${featured.id}?from=demo`}
                      className="text-sm px-7 py-3.5 !inline-flex"
                    >
                      Open live product
                    </GlowButton>
                    <span className="demo-mag__date">Generated {formatDate(featured.created_at)}</span>
                  </div>
                </motion.article>
              )}

              {rest.length > 0 && (
                <>
                  <h3 className="demo-mag__list-label">More live builds</h3>
                  <div className="demo-mag__grid">
                    {rest.map((demo, i) => (
                      <motion.article
                        key={demo.id}
                        initial={reduce ? false : { opacity: 0, y: 16 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        viewport={{ once: true }}
                        transition={{ delay: i * 0.05, duration: 0.45, ease }}
                        className="demo-mag__card"
                        style={
                          {
                            '--d-p': demo.primary_color || '#2563eb',
                            '--d-s': demo.secondary_color || '#0891b2',
                          } as CSSProperties
                        }
                      >
                        <Link to={`/result/${demo.id}?from=demo`} className="demo-mag__card-link">
                          <div className="demo-mag__card-top">
                            <span className="demo-mag__card-num" aria-hidden>
                              {String(i + 1).padStart(2, '0')}
                            </span>
                            {demo.business_fit_score != null && demo.business_fit_score > 0 && (
                              <span className="demo-mag__score">{demo.business_fit_score}%</span>
                            )}
                          </div>
                          <span className="demo-mag__card-ind">{demo.industry || 'Custom'}</span>
                          <h3>{demo.concept_name}</h3>
                          <p>{demo.business_name}</p>
                          {demo.preview_summary && (
                            <p className="demo-mag__card-sum">{clean(demo.preview_summary)}</p>
                          )}
                          <span className="demo-mag__card-cta">Open live product →</span>
                        </Link>
                      </motion.article>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </main>

      <CinematicCTA
        eyebrow="AI consultancy"
        title="Ready for your own live product?"
        subtitle="Tell us how you work. We find what to automate, then our team builds a real app for your business."
        primaryLabel="Find my AI fit"
        secondaryLabel="How it works"
        secondaryTo="/#how-it-works"
      />
      <SiteFooter />
    </div>
  );
}
