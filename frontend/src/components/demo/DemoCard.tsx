import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import type { DemoListItem } from '../../types/demo';

interface Props {
  demo: DemoListItem;
  index?: number;
  featured?: boolean;
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function DemoCard({ demo, index = 0, featured }: Props) {
  const primary = demo.primary_color || '#4f46e5';
  const score = demo.business_fit_score ?? 0;

  return (
    <motion.article
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay: index * 0.06, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -6 }}
      className={`about-gradient-ring about-glass h-full overflow-hidden transition-shadow duration-500 hover:shadow-xl hover:shadow-blue-500/10 rounded-2xl p-5 sm:p-6 flex flex-col ${
        featured ? 'ring-2 ring-emerald-200/80' : ''
      }`}
    >
      {featured && (
        <span className="self-start mb-3 px-2 py-0.5 rounded-full bg-emerald-500 text-white text-[10px] font-bold uppercase tracking-wider">
          Latest
        </span>
      )}

      <CardBody demo={demo} primary={primary} score={score} large={featured} />
    </motion.article>
  );
}

function CardBody({
  demo,
  primary,
  score,
  large,
}: {
  demo: DemoListItem;
  primary: string;
  score: number;
  large?: boolean;
}) {
  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-100">
          {demo.industry || 'Custom business'}
        </span>
        {score > 0 && (
          <span className={`font-bold gradient-text ${large ? 'text-3xl' : 'text-xl'}`}>{score}%</span>
        )}
      </div>

      <div className="flex items-start gap-3 mb-3">
        <div
          className="w-9 h-9 rounded-lg text-white flex items-center justify-center shrink-0 shadow-sm text-sm font-bold"
          style={{ backgroundColor: primary }}
        >
          {demo.concept_name.charAt(0)}
        </div>
        <div className="min-w-0">
          <h3 className={`font-bold text-navy leading-tight ${large ? 'text-xl sm:text-2xl' : 'text-lg'}`}>
            {demo.concept_name}
          </h3>
          <p className="text-xs text-slate-500 mt-0.5 truncate">{demo.business_name}</p>
        </div>
      </div>

      {demo.preview_summary && (
        <p className="text-sm text-slate-600 leading-relaxed mb-4 line-clamp-3">{demo.preview_summary}</p>
      )}

      {demo.preview_features.length > 0 && (
        <ul className="space-y-2 mb-4">
          {demo.preview_features.slice(0, large ? 5 : 4).map((f) => (
            <li key={f} className="text-sm text-slate-600 flex items-start gap-2">
              <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-teal-600 shrink-0 mt-0.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="20 6 9 17 4 12" />
              </svg>
              {f}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-auto pt-3 border-t border-slate-100/80 flex items-center justify-between gap-3">
        <p className="text-[11px] text-slate-400">Generated {formatDate(demo.created_at)}</p>
        <Link
          to={`/result/${demo.id}?from=demo`}
          className="text-sm font-semibold text-blue-600 hover:text-blue-700 shrink-0"
        >
          View live demo →
        </Link>
      </div>
    </>
  );
}
