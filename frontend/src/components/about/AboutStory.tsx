import { useRef } from 'react';
import { motion, useScroll, useTransform } from 'framer-motion';

const CHAPTERS = [
  {
    tag: '01',
    title: 'The idea',
    text: 'Business owners keep seeing tools they love — but adapting them feels impossible without a dev team.',
  },
  {
    tag: '02',
    title: 'The product',
    text: 'Build My Version lets you describe your business, share any reference, and instantly see a custom MVP concept with visual preview.',
  },
  {
    tag: '03',
    title: 'The team',
    text: 'A growing team of AI engineers who\'ve shipped production systems — marketplaces, SaaS platforms, autonomous agents, and enterprise AI.',
  },
  {
    tag: '04',
    title: 'Today',
    text: 'We\'re building the company around making custom software accessible to every business owner.',
  },
];

export default function AboutStory() {
  const containerRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: containerRef, offset: ['start end', 'end start'] });
  const lineHeight = useTransform(scrollYProgress, [0.1, 0.85], ['0%', '100%']);

  return (
    <section ref={containerRef} className="section-padding bg-slate-50 relative overflow-hidden">
      <div className="absolute inset-0 hero-mesh pointer-events-none opacity-40" />

      <div className="container-max relative">
        <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-12 lg:gap-20">
          <div className="lg:sticky lg:top-28 lg:self-start">
            <motion.p
              initial={{ opacity: 0, x: -20 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true }}
              className="text-blue-600 font-medium mb-3 tracking-[0.2em] uppercase text-xs"
            >
              Our story
            </motion.p>
            <motion.h2
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1 }}
              className="text-3xl sm:text-4xl lg:text-5xl font-bold text-navy leading-tight mb-4"
            >
              Why we exist
            </motion.h2>
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.2 }}
              className="text-slate-600 leading-relaxed max-w-md"
            >
              From a simple frustration to a platform — and a company — built to close the gap between inspiration and execution.
            </motion.p>

            <div className="hidden lg:block relative w-1 h-48 mt-12 ml-2 bg-blue-100 rounded-full overflow-hidden">
              <motion.div style={{ height: lineHeight }} className="about-story-line w-full rounded-full origin-top" />
            </div>
          </div>

          <div className="space-y-6 sm:space-y-8">
            {CHAPTERS.map((ch, i) => (
              <motion.article
                key={ch.tag}
                initial={{ opacity: 0, x: 40 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ delay: i * 0.08, duration: 0.65, ease: [0.22, 1, 0.36, 1] }}
                className="about-gradient-ring about-glass rounded-2xl p-6 sm:p-8 hover:shadow-lg hover:shadow-blue-500/10 transition-all duration-500"
              >
                <div className="flex items-start gap-4">
                  <span className="shrink-0 w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center text-sm font-bold shadow-lg shadow-blue-500/25">
                    {ch.tag}
                  </span>
                  <div>
                    <h3 className="text-xl sm:text-2xl font-bold text-navy mb-2">{ch.title}</h3>
                    <p className="text-slate-600 leading-relaxed">{ch.text}</p>
                  </div>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
