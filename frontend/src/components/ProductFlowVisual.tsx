import { useEffect, useState, type ReactNode } from 'react';
import { motion } from 'framer-motion';

const iconClass = 'w-5 h-5';

const icons = {
  business: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  reference: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  ),
  ai: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  ),
  preview: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="5" y="2" width="14" height="20" rx="2" />
      <path d="M12 18h.01" />
    </svg>
  ),
  check: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="20 6 9 17 4 12" />
    </svg>
  ),
} satisfies Record<string, ReactNode>;

const STEPS = [
  { id: 'business', title: 'Your business', detail: 'Clinic · Leads · Customers', icon: icons.business },
  { id: 'reference', title: 'Tool you like', detail: 'Booking app · Chatbot · Dashboard', icon: icons.reference },
  { id: 'ai', title: 'AI adapts it', detail: 'Blueprint · Features · Analysis', icon: icons.ai },
  { id: 'preview', title: 'Your business version', detail: 'Visual demo · Build plan', icon: icons.preview, output: true },
];

export default function ProductFlowVisual() {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setPhase((p) => (p + 1) % 4), 2800);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="product-flow-visual relative w-full max-w-xl lg:max-w-2xl mx-auto" aria-hidden>
      <div className="absolute -inset-4 rounded-[2rem] bg-gradient-to-br from-blue-400/35 via-cyan-300/25 to-indigo-500/30 blur-2xl opacity-80" />
      <div className="absolute -inset-1 rounded-[1.75rem] bg-gradient-to-br from-blue-500/20 via-cyan-400/15 to-blue-600/25 blur-md" />

      <motion.div
        animate={{ y: [0, -6, 0] }}
        transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
        className="relative rounded-[1.75rem] border border-blue-200/70 bg-white/95 backdrop-blur-md p-5 sm:p-6 lg:p-7 shadow-2xl shadow-blue-500/20"
        style={{ transform: 'perspective(1200px) rotateY(-2deg) rotateX(1deg)' }}
      >
        <div className="flex items-center justify-between gap-3 mb-4 pb-4 border-b border-slate-100/90">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-400 shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-yellow-400 shadow-sm" />
            <span className="w-3 h-3 rounded-full bg-green-400 shadow-sm" />
          </div>
          <span className="text-xs text-slate-400 font-mono truncate">buildmyversion.ai / preview</span>
          <span className="text-[10px] font-bold text-cyan-600 bg-cyan-50 px-2.5 py-1 rounded-full border border-cyan-200/80 tracking-wide">
            LIVE
          </span>
        </div>

        <div className="space-y-3">
          {STEPS.map((step, i) => {
            const isActive = phase === i;
            const isDone = phase > i;

            return (
              <motion.div
                key={step.id}
                layout
                animate={{
                  scale: isActive ? 1.02 : 1,
                  opacity: isActive || isDone ? 1 : 0.72,
                }}
                transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
                className={`rounded-2xl border px-4 py-3.5 sm:px-5 sm:py-4 transition-colors duration-500 ${
                  isActive
                    ? 'border-blue-300/90 bg-gradient-to-r from-blue-50 via-cyan-50/90 to-blue-50/80 shadow-lg shadow-blue-500/10 ring-1 ring-blue-200/50'
                    : isDone
                      ? 'border-teal-200/90 bg-teal-50/50'
                      : 'border-slate-100 bg-slate-50/70'
                }`}
              >
                <div className="flex items-center gap-3.5">
                  <div
                    className={`w-10 h-10 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center shrink-0 transition-all duration-500 ${
                      isActive
                        ? 'bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-lg shadow-blue-500/30'
                        : isDone
                          ? 'bg-teal-500 text-white shadow-md shadow-teal-500/20'
                          : 'bg-slate-100 text-slate-400'
                    }`}
                  >
                    {isDone ? icons.check : step.icon}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-base sm:text-lg font-semibold text-navy leading-tight">{step.title}</p>
                    {(isActive || isDone) && (
                      <p className="text-xs sm:text-sm text-slate-500 mt-1">{step.detail}</p>
                    )}
                    {step.output && isActive && (
                      <motion.div
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.45, delay: 0.15 }}
                        className="mt-3 grid grid-cols-3 gap-2 sm:gap-2.5"
                      >
                        {[
                          { label: 'Hero', color: 'from-blue-500 to-blue-600' },
                          { label: 'Features', color: 'from-cyan-500 to-teal-500' },
                          { label: 'Admin', color: 'from-indigo-500 to-blue-600' },
                        ].map((s, idx) => (
                          <motion.div
                            key={s.label}
                            initial={{ opacity: 0, scale: 0.92 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.2 + idx * 0.08, duration: 0.35 }}
                            className={`h-14 sm:h-16 rounded-xl bg-gradient-to-br ${s.color} p-2 flex flex-col justify-end shadow-md`}
                          >
                            <span className="text-[9px] sm:text-[10px] text-white/95 font-semibold bg-black/25 rounded-md px-1.5 py-0.5 w-fit">
                              {s.label}
                            </span>
                          </motion.div>
                        ))}
                      </motion.div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>

        <div className="mt-4 pt-4 border-t border-slate-100/90 flex items-center justify-between text-xs text-slate-500">
          <span className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-50" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
            </span>
            AI pipeline running locally
          </span>
          <span className="text-blue-600 font-semibold">Step {phase + 1} of 4</span>
        </div>
      </motion.div>
    </div>
  );
}
