import { motion } from 'framer-motion';
import type { ReactNode } from 'react';
import type { ExampleOutput } from '../data/examples';

const iconClass = 'w-5 h-5';

const EXAMPLE_ICONS: Record<string, ReactNode> = {
  'business-xray': (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 20V10M12 20V4M6 20v-6" />
    </svg>
  ),
  hirewise: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  cashpath: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="1" y="4" width="22" height="16" rx="2" /><path d="M1 10h22" />
    </svg>
  ),
  clinic: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  ),
  scaleyou: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
  ),
  visioncommerce: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" /><path d="M3 6h18M16 10a4 4 0 0 1-8 0" />
    </svg>
  ),
};

export function MiniPreview({ accent, tall }: { accent: string; tall?: boolean }) {
  return (
    <div className="mini-screen p-2">
      <div className="flex items-center gap-1 mb-2">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
        <span className="w-1.5 h-1.5 rounded-full bg-yellow-400" />
        <span className="w-1.5 h-1.5 rounded-full bg-green-400" />
      </div>
      <div className={`${tall ? 'h-20' : 'h-14'} rounded-md bg-gradient-to-br ${accent} mb-2 p-2 flex flex-col justify-end`}>
        <div className="h-1.5 w-16 bg-white/40 rounded" />
        <div className="h-1 w-10 bg-white/25 rounded mt-1" />
      </div>
      <div className="grid grid-cols-3 gap-1">
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-6 rounded bg-white border border-slate-100" />
        ))}
      </div>
    </div>
  );
}

interface Props {
  example: ExampleOutput;
  featured?: boolean;
  index?: number;
  landing?: boolean;
}

export default function ExampleCard({ example, featured, index = 0, landing }: Props) {
  const icon = EXAMPLE_ICONS[example.id];
  const cardClass = landing
    ? 'landing-card h-full overflow-hidden rounded-2xl'
    : 'about-gradient-ring about-glass h-full overflow-hidden transition-shadow duration-500 hover:shadow-xl hover:shadow-blue-500/10 rounded-2xl';

  return (
    <motion.article
      initial={{ opacity: 0, y: 32 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ delay: index * 0.06, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      whileHover={landing ? undefined : { y: -6 }}
      className={`${cardClass} ${featured ? '' : 'p-5'}`}
    >
      {featured ? (
        <div className="grid md:grid-cols-2">
          <div className="p-5 sm:p-8 bg-gradient-to-br from-slate-50/80 to-blue-50/60 relative overflow-hidden">
            <div className="absolute top-4 left-4 px-2 py-0.5 rounded-full bg-blue-600 text-white text-[10px] font-bold uppercase tracking-wider">
              Featured
            </div>
            <MiniPreview accent={example.accent} tall />
          </div>
          <div className="p-5 sm:p-8 flex flex-col">
            <CardBody example={example} icon={icon} large />
          </div>
        </div>
      ) : (
        <>
          <MiniPreview accent={example.accent} />
          <CardBody example={example} icon={icon} />
        </>
      )}
    </motion.article>
  );
}

function CardBody({ example, icon, large }: { example: ExampleOutput; icon?: ReactNode; large?: boolean }) {
  return (
    <>
      <div className="flex items-center justify-between mb-3 mt-4 first:mt-0">
        <span className="text-xs font-medium text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-100">
          {example.industry}
        </span>
        <span className={`font-bold gradient-text ${large ? 'text-3xl' : 'text-xl'}`}>{example.score}%</span>
      </div>

      <div className="flex items-start gap-3 mb-2">
        {icon && (
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center shrink-0 shadow-sm">
            {icon}
          </div>
        )}
        <h3 className={`font-bold text-navy leading-tight ${large ? 'text-xl sm:text-2xl' : 'text-lg'}`}>{example.name}</h3>
      </div>

      <p className="text-sm text-slate-600 leading-relaxed mb-4">{example.tagline}</p>

      <ul className="space-y-2 mb-4">
        {example.features.slice(0, large ? 5 : 4).map((f) => (
          <li key={f} className="text-sm text-slate-600 flex items-start gap-2">
            <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-teal-600 shrink-0 mt-0.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <polyline points="20 6 9 17 4 12" />
            </svg>
            {f}
          </li>
        ))}
      </ul>

      <div className="mt-auto pt-3 border-t border-slate-100/80">
        <p className="text-[11px] text-slate-400">Concept type: {example.inspiredBy}</p>
      </div>
    </>
  );
}
