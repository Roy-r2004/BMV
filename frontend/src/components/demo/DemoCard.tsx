import { Link } from 'react-router-dom';
import { useId } from 'react';
import { motion } from 'framer-motion';
import type { CSSProperties } from 'react';
import type { DemoListItem } from '../../types/demo';

interface Props {
  demo: DemoListItem;
  index?: number;
  featured?: boolean;
}

const ease = [0.22, 1, 0.36, 1] as const;

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function cleanFeature(text: string) {
  return text.replace(/\*\*/g, '').replace(/^\+\+|\+\+$/g, '').trim();
}

function DemoPreview({ primary, secondary, conceptName, large }: { primary: string; secondary: string; conceptName: string; large?: boolean }) {
  return (
    <div className={`demo-preview ${large ? 'demo-preview--large' : ''}`}>
      <div className="demo-preview__chrome">
        <span className="demo-preview__dot demo-preview__dot--red" />
        <span className="demo-preview__dot demo-preview__dot--yellow" />
        <span className="demo-preview__dot demo-preview__dot--green" />
        <span className="demo-preview__url">{conceptName.toLowerCase().replace(/\s+/g, '')}.app</span>
      </div>
      <div className="demo-preview__body">
        <div className="demo-preview__sidebar" style={{ background: `linear-gradient(180deg, ${primary}22, ${primary}08)` }}>
          <div className="demo-preview__logo" style={{ background: primary }} />
          {[1, 2, 3, 4].map((n) => (
            <div key={n} className="demo-preview__nav-item" style={{ opacity: n === 1 ? 1 : 0.35 }} />
          ))}
        </div>
        <div className="demo-preview__main">
          <div className="demo-preview__hero" style={{ background: `linear-gradient(135deg, ${primary}, ${secondary || primary})` }}>
            <div className="demo-preview__hero-line demo-preview__hero-line--lg" />
            <div className="demo-preview__hero-line demo-preview__hero-line--sm" />
          </div>
          <div className="demo-preview__stats">
            {[1, 2, 3].map((n) => (
              <div key={n} className="demo-preview__stat">
                <div className="demo-preview__stat-bar" style={{ width: `${60 + n * 12}%`, background: primary }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function ScoreRing({ score, size = 56 }: { score: number; size?: number }) {
  const gradId = useId();
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <div className="demo-score-ring" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth="3" className="text-white/10" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={`url(#${gradId})`}
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
        />
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#60a5fa" />
            <stop offset="100%" stopColor="#22d3ee" />
          </linearGradient>
        </defs>
      </svg>
      <span className="demo-score-ring__label">{score}</span>
    </div>
  );
}

export default function DemoCard({ demo, index = 0, featured }: Props) {
  const primary = demo.primary_color || '#4f46e5';
  const secondary = demo.secondary_color || '#0891b2';
  const score = demo.business_fit_score ?? 0;
  const features = demo.preview_features.slice(0, featured ? 4 : 3).map(cleanFeature);

  if (featured) {
    return (
      <motion.article
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-60px' }}
        transition={{ duration: 0.8, ease }}
        className="demo-card demo-card--featured"
        style={{ '--demo-primary': primary, '--demo-secondary': secondary } as CSSProperties}
      >
        <div className="demo-card__glow" aria-hidden />
        <Link to={`/result/${demo.id}?from=demo`} className="demo-card__link">
          <div className="demo-card__featured-grid">
            <div className="demo-card__preview-wrap">
              <span className="demo-card__badge demo-card__badge--live">
                <span className="demo-card__live-dot" />
                Latest build
              </span>
              <DemoPreview primary={primary} secondary={secondary} conceptName={demo.concept_name} large />
            </div>
            <div className="demo-card__content">
              <div className="demo-card__meta">
                <span className="demo-card__industry">{demo.industry || 'Custom business'}</span>
                {score > 0 && <ScoreRing score={score} size={64} />}
              </div>
              <h2 className="demo-card__title">{demo.concept_name}</h2>
              <p className="demo-card__business">{demo.business_name}</p>
              {demo.preview_summary && (
                <p className="demo-card__summary">{cleanFeature(demo.preview_summary)}</p>
              )}
              {features.length > 0 && (
                <ul className="demo-card__features">
                  {features.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              )}
              <div className="demo-card__footer">
                <span className="demo-card__date">Generated {formatDate(demo.created_at)}</span>
                <span className="demo-card__cta">
                  Open live product
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                    <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </span>
              </div>
            </div>
          </div>
        </Link>
      </motion.article>
    );
  }

  return (
    <motion.article
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay: index * 0.08, duration: 0.65, ease }}
      whileHover={{ y: -8 }}
      className="demo-card demo-card--grid"
      style={{ '--demo-primary': primary, '--demo-secondary': secondary } as CSSProperties}
    >
      <div className="demo-card__glow" aria-hidden />
      <Link to={`/result/${demo.id}?from=demo`} className="demo-card__link">
        <DemoPreview primary={primary} secondary={secondary} conceptName={demo.concept_name} />
        <div className="demo-card__grid-body">
          <div className="demo-card__grid-top">
            <div>
              <span className="demo-card__industry demo-card__industry--sm">{demo.industry || 'Custom'}</span>
              <h3 className="demo-card__grid-title">{demo.concept_name}</h3>
              <p className="demo-card__grid-business">{demo.business_name}</p>
            </div>
            {score > 0 && <ScoreRing score={score} size={48} />}
          </div>
          {features.length > 0 && (
            <ul className="demo-card__grid-features">
              {features.slice(0, 2).map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          )}
          <span className="demo-card__grid-cta">
            Explore
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
              <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </Link>
    </motion.article>
  );
}
