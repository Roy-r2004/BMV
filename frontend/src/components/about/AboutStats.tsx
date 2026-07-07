import { motion } from 'framer-motion';

const STATS = [
  { value: '10+', label: 'Production systems shipped', detail: 'SaaS, marketplaces, AI agents' },
  { value: 'AI', label: 'Core expertise', detail: 'LLMs, agents, computer vision' },
  { value: 'Full-stack', label: 'End-to-end builds', detail: 'Web, mobile, APIs, infra' },
  { value: 'Enterprise', label: 'Scale-ready', detail: 'Microservices & real users' },
];

export default function AboutStats() {
  return (
    <section className="relative py-20 sm:py-24 bg-white">
      <div className="container-max px-4 sm:px-6">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
          {STATS.map((s, i) => (
            <motion.div
              key={s.label}
              initial={{ opacity: 0, y: 32 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * 0.1, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              className="about-gradient-ring about-glass rounded-2xl p-6 sm:p-7 group hover:shadow-xl hover:shadow-blue-500/10 transition-shadow duration-500"
            >
              <p className="text-3xl sm:text-4xl font-bold gradient-text mb-2 group-hover:scale-105 transition-transform origin-left duration-300">
                {s.value}
              </p>
              <p className="font-semibold text-navy text-sm sm:text-base mb-1">{s.label}</p>
              <p className="text-xs text-slate-500 leading-relaxed">{s.detail}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
