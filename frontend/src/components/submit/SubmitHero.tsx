import { motion } from 'framer-motion';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function SubmitHero() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: easeOut }}
      className="text-center mb-10 sm:mb-12 relative"
    >
      <div className="hero-orb w-2 h-2 bg-blue-400/60 top-0 left-[8%] absolute" />
      <div className="hero-orb w-1.5 h-1.5 bg-cyan-400/50 top-4 right-[12%] absolute" style={{ animationDelay: '1.5s' }} />

      <motion.span
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1, duration: 0.5, ease: easeOut }}
        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-white/90 border border-blue-200/70 text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.18em] mb-5 shadow-sm backdrop-blur-sm"
      >
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
        </span>
        Free AI preview
      </motion.span>

      <h1 className="text-3xl sm:text-4xl lg:text-[2.75rem] font-bold text-navy mb-3 leading-[1.1] tracking-tight">
        Build your{' '}
        <span className="gradient-text-shimmer">business version</span>
      </h1>

      <p className="text-slate-600 max-w-xl mx-auto text-sm sm:text-base leading-relaxed">
        Five cinematic steps — then AI designs a custom MVP concept, visual demo, and build plan just for you.
      </p>

      <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 mt-6 text-[11px] sm:text-xs text-slate-500">
        {['~3 min to complete', 'No credit card', 'Preview in minutes'].map((item) => (
          <span key={item} className="flex items-center gap-1.5">
            <span className="w-1 h-1 rounded-full bg-cyan-500" />
            {item}
          </span>
        ))}
      </div>
    </motion.div>
  );
}
