import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import type { IndustrySolution } from '../../data/solutions';
import { hasShowcaseDemo } from '../../data/showcaseDemos';
import { SOLUTION_ICONS } from './SolutionIcons';

interface Props {
  solution: IndustrySolution;
  index?: number;
}

const ease = [0.22, 1, 0.36, 1] as const;

export default function SolutionCard({ solution, index = 0 }: Props) {
  const icon = SOLUTION_ICONS[solution.icon];

  return (
    <motion.article
      initial={{ opacity: 0, y: 28 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay: index * 0.05, duration: 0.6, ease }}
      whileHover={{ y: -6 }}
      className="solution-card about-gradient-ring"
    >
      <Link to={`/solutions/${solution.id}`} className="solution-card__link">
        <div className="solution-card__top">
          <div className={`solution-card__icon bg-gradient-to-br ${solution.accent}`}>{icon}</div>
          <span className="solution-card__badge">
            {hasShowcaseDemo(solution.id) || solution.demoStatus === 'live' ? 'Live demo' : 'Ready-made'}
          </span>
        </div>

        <h3 className="solution-card__title">{solution.name}</h3>
        <p className="solution-card__tagline">{solution.tagline}</p>

        <ul className="solution-card__list">
          {solution.highlights.map((c) => (
            <li key={c}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="20 6 9 17 4 12" />
              </svg>
              {c}
            </li>
          ))}
        </ul>

        <span className="solution-card__cta">
          See what's included
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M5 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </Link>
    </motion.article>
  );
}
