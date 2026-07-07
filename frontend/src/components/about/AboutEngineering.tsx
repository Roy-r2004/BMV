import { motion } from 'framer-motion';

const STACK = [
  'Large Language Models', 'AI Agents', 'Computer Vision', 'FastAPI', 'React',
  'Microservices', 'Vector Databases', 'Real-time Streaming', 'SaaS Architecture',
  'Mobile Apps', 'Web Scraping', 'Enterprise AI', 'Docker', 'PostgreSQL',
];

const DOMAINS = [
  'AI marketplaces',
  'Competitive intelligence',
  'Autonomous sales',
  'Recruitment platforms',
  'Booking systems',
  'Enterprise dashboards',
];

export default function AboutEngineering() {
  const marqueeItems = [...STACK, ...STACK];

  return (
    <section className="py-20 sm:py-28 bg-slate-950 text-white relative overflow-hidden">
      <div className="absolute inset-0 cinematic-grid opacity-[0.06] pointer-events-none invert" />
      <div className="hero-blob w-[500px] h-[300px] bg-blue-500/15 top-0 right-0" />

      <div className="container-max relative px-4 sm:px-6 mb-12 sm:mb-16">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-2xl"
        >
          <p className="text-cyan-400 font-medium mb-3 tracking-[0.2em] uppercase text-xs">Engineering depth</p>
          <h2 className="text-3xl sm:text-4xl font-bold mb-4 leading-tight">
            Production patterns.<br />
            <span className="text-blue-300">Built for real users.</span>
          </h2>
          <p className="text-slate-400 leading-relaxed">
            Our team has shipped AI marketplaces, competitive intelligence SaaS, autonomous sales engines,
            recruitment platforms, and enterprise systems — the same engineering patterns power what we build for you.
          </p>
        </motion.div>
      </div>

      <div className="relative mb-14 overflow-hidden">
        <div className="absolute left-0 top-0 bottom-0 w-24 bg-gradient-to-r from-slate-950 to-transparent z-10 pointer-events-none" />
        <div className="absolute right-0 top-0 bottom-0 w-24 bg-gradient-to-l from-slate-950 to-transparent z-10 pointer-events-none" />
        <div className="about-marquee-track gap-3 px-2">
          {marqueeItems.map((item, i) => (
            <span
              key={`${item}-${i}`}
              className="shrink-0 px-4 py-2 rounded-full text-sm font-medium text-slate-300 border border-white/10 bg-white/5 backdrop-blur-sm"
            >
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="container-max relative px-4 sm:px-6">
        <motion.p
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-xs uppercase tracking-[0.2em] text-slate-500 mb-4"
        >
          Domains we&apos;ve shipped in
        </motion.p>
        <div className="flex flex-wrap gap-2">
          {DOMAINS.map((d, i) => (
            <motion.span
              key={d}
              initial={{ opacity: 0, scale: 0.9 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className="px-4 py-2 rounded-xl text-sm text-blue-100 bg-gradient-to-r from-blue-600/20 to-cyan-500/10 border border-blue-500/20"
            >
              {d}
            </motion.span>
          ))}
        </div>
      </div>
    </section>
  );
}
