import { motion } from 'framer-motion';

interface Props {
  score: number | null;
  conceptName: string | null;
  summary: string | null;
  features: string[];
  variant?: 'dark' | 'light';
}

export default function PreviewCard({
  score,
  conceptName,
  summary,
  features,
  variant = 'dark',
}: Props) {
  const light = variant === 'light';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className={
        light
          ? 'rounded-2xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm relative overflow-hidden'
          : 'card p-8 relative overflow-hidden'
      }
    >
      {!light && (
        <div className="absolute top-0 right-0 w-64 h-64 bg-blue-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
      )}
      {light && (
        <div className="absolute top-0 right-0 w-48 h-48 bg-indigo-100/60 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3 pointer-events-none" />
      )}
      <div className="relative z-10">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
          <div>
            <p className={`text-xs font-semibold uppercase tracking-[0.15em] mb-1 ${light ? 'text-indigo-600' : 'text-cyan-400'}`}>
              Your Custom MVP
            </p>
            <h2 className={`text-2xl sm:text-3xl font-bold ${light ? 'text-slate-900' : 'text-white'}`}>
              {conceptName || 'Custom Business MVP'}
            </h2>
          </div>
          {score !== null && (
            <div
              className={
                light
                  ? 'text-center px-6 py-3 rounded-2xl bg-indigo-50 border border-indigo-100'
                  : 'text-center px-6 py-3 rounded-2xl bg-gradient-to-br from-blue-500/20 to-teal-500/20 border border-cyan-500/20'
              }
            >
              <div className={`text-4xl font-bold ${light ? 'text-indigo-600' : 'gradient-text'}`}>{score}%</div>
              <p className={`text-xs ${light ? 'text-slate-500' : 'text-slate-400'}`}>Business-fit score</p>
            </div>
          )}
        </div>

        {summary && (
          <p className={`mb-5 leading-relaxed text-base sm:text-lg ${light ? 'text-slate-600' : 'text-slate-300'}`}>
            {summary}
          </p>
        )}

        {features.length > 0 && (
          <div>
            <h3 className={`font-semibold mb-3 ${light ? 'text-slate-900' : 'text-white'}`}>Top Features</h3>
            <div className="grid sm:grid-cols-2 gap-2">
              {features.map((f, i) => (
                <div key={i} className={`flex items-start gap-2 text-sm ${light ? 'text-slate-600' : 'text-slate-400'}`}>
                  <span className={`font-bold shrink-0 ${light ? 'text-indigo-500' : 'text-cyan-400'}`}>{i + 1}.</span>
                  <span>{f}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
