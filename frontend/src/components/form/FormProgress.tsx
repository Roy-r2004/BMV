import { motion } from 'framer-motion';
import { IconCheck, STEP_ICONS } from '../icons/SubmitIcons';

export interface StepMeta {
  id: string;
  label: string;
  subtitle: string;
}

interface Props {
  steps: StepMeta[];
  current: number;
}

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function FormProgress({ steps, current }: Props) {
  const pct = ((current + 1) / steps.length) * 100;

  return (
    <div className="w-full submit-progress">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[10px] sm:text-xs font-bold text-blue-600 uppercase tracking-[0.2em]">
          Step {current + 1} of {steps.length}
        </span>
        <span className="text-[10px] sm:text-xs font-mono text-slate-500 tabular-nums">{Math.round(pct)}%</span>
      </div>

      <div className="relative h-2 rounded-full bg-blue-100/80 overflow-hidden mb-5 sm:mb-6 shadow-inner">
        <motion.div
          className="absolute inset-y-0 left-0 rounded-full submit-progress-fill"
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.55, ease: easeOut }}
        />
        <motion.div
          className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow-md shadow-blue-500/30 border-2 border-cyan-400"
          initial={false}
          animate={{ left: `calc(${pct}% - 6px)` }}
          transition={{ duration: 0.55, ease: easeOut }}
        />
      </div>

      <div className="hidden sm:flex items-start justify-between gap-1 relative">
        <div className="absolute top-5 left-[10%] right-[10%] h-px bg-gradient-to-r from-transparent via-blue-200 to-transparent" aria-hidden />
        {steps.map((step, i) => {
          const done = i < current;
          const active = i === current;
          const icon = STEP_ICONS[i];

          return (
            <motion.div
              key={step.id}
              initial={false}
              animate={{
                scale: active ? 1.02 : 1,
                opacity: i > current + 1 ? 0.45 : 1,
              }}
              transition={{ duration: 0.35, ease: easeOut }}
              className={`flex-1 flex flex-col items-center text-center px-1 min-w-0 ${
                active ? 'z-10' : ''
              }`}
            >
              <div
                className={`relative w-10 h-10 rounded-xl flex items-center justify-center mb-2 transition-all duration-400 ${
                  active
                    ? 'bg-gradient-to-br from-blue-600 to-cyan-500 text-white shadow-lg shadow-blue-500/30 ring-4 ring-blue-500/15'
                    : done
                      ? 'bg-teal-50 text-teal-600 border border-teal-200'
                      : 'bg-white/80 text-slate-400 border border-slate-100'
                }`}
              >
                {done ? <IconCheck className="w-4 h-4" /> : icon}
                {active && (
                  <motion.span
                    layoutId="step-glow"
                    className="absolute inset-0 rounded-xl bg-cyan-400/20 blur-md -z-10"
                    transition={{ duration: 0.4 }}
                  />
                )}
              </div>
              <p
                className={`text-[9px] font-bold uppercase tracking-wider truncate w-full ${
                  active ? 'text-blue-600' : done ? 'text-teal-600' : 'text-slate-400'
                }`}
              >
                {step.label}
              </p>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
