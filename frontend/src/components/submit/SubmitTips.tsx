import { motion } from 'framer-motion';
import { IconGift, IconInspiration, IconTarget } from '../icons/SubmitIcons';

const TIPS = [
  {
    Icon: IconTarget,
    title: 'Be specific',
    text: 'The more detail you share, the sharper your custom preview becomes.',
  },
  {
    Icon: IconInspiration,
    title: 'Any reference works',
    text: 'A booking app, chatbot, dashboard — if you like it, we adapt the experience.',
  },
  {
    Icon: IconGift,
    title: 'Free preview',
    text: 'Custom concept, fit score, and visual demo — no cost, no commitment.',
  },
] as const;

const easeOut = [0.22, 1, 0.36, 1] as const;

function TipCard({ tip, index, compact }: { tip: (typeof TIPS)[number]; index: number; compact?: boolean }) {
  const { Icon, title, text } = tip;
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 + index * 0.08, duration: 0.55, ease: easeOut }}
      whileHover={{ y: -4 }}
      className={`about-gradient-ring about-glass rounded-2xl shadow-lg shadow-blue-500/5 transition-shadow duration-500 hover:shadow-xl hover:shadow-blue-500/10 ${
        compact ? 'shrink-0 w-64 p-4' : 'p-5'
      }`}
    >
      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center mb-3 shadow-md shadow-blue-500/25">
        <Icon className="w-5 h-5" />
      </div>
      <p className={`font-bold text-navy ${compact ? 'text-xs' : 'text-sm'} mb-1`}>{title}</p>
      <p className={`text-slate-500 leading-relaxed ${compact ? 'text-[11px]' : 'text-xs'}`}>{text}</p>
    </motion.div>
  );
}

export default function SubmitTips() {
  return (
    <>
      <aside className="lg:hidden flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 snap-x snap-mandatory mb-6 lg:mb-0">
        {TIPS.map((tip, i) => (
          <div key={tip.title} className="snap-start">
            <TipCard tip={tip} index={i} compact />
          </div>
        ))}
      </aside>

      <aside className="hidden lg:block space-y-4 sticky top-24">
        {TIPS.map((tip, i) => (
          <TipCard key={tip.title} tip={tip} index={i} />
        ))}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.6 }}
          className="rounded-2xl border border-blue-100/60 bg-gradient-to-br from-navy to-slate-800 p-5 text-white relative overflow-hidden"
        >
          <div className="absolute inset-0 cinematic-grid opacity-[0.08] pointer-events-none invert" />
          <div className="relative">
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300/90 mb-2">What you get</p>
            <ul className="space-y-2.5 text-xs text-white/75">
              {['MVP blueprint', 'Business-fit score', 'Visual product demo', 'Technical plan outline'].map((item) => (
                <li key={item} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-gradient-to-r from-blue-400 to-cyan-400 shrink-0" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </motion.div>
      </aside>
    </>
  );
}
