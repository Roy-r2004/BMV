import { useRef } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';

const CHAPTERS = [
  {
    tag: '01',
    kicker: 'The gap',
    title: 'AI everywhere. Clarity nowhere.',
    text: 'Owners see tools, agents, and demos daily — and still can’t tell what to automate first without burning months and budget.',
  },
  {
    tag: '02',
    kicker: 'The consultancy',
    title: 'We start inside your workflow.',
    text: 'Before we write a line of product code, we find the highest-leverage AI & automation opportunities for how you actually operate.',
  },
  {
    tag: '03',
    kicker: 'The proof',
    title: 'Feel it before you fund it.',
    text: 'A free custom product preview — a real surface you click — so conviction comes from experience, not a pitch.',
  },
  {
    tag: '04',
    kicker: 'The build',
    title: 'Then we ship what you felt.',
    text: 'Our engineers take the proven concept to production: APIs, UI, AI, infra — software your team owns and runs.',
  },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutStory() {
  const reduce = useReducedMotion();
  const containerRef = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ['start end', 'end start'],
  });
  const lineHeight = useTransform(scrollYProgress, [0.12, 0.82], ['0%', '100%']);

  return (
    <section ref={containerRef} className="about-boom-story">
      <div className="about-boom-story__glow" aria-hidden />
      <div className="container-max px-4 sm:px-6 py-24 sm:py-32">
        <div className="about-boom-story__layout">
          <div className="about-boom-story__sticky">
            <motion.p
              initial={reduce ? false : { opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              className="about-boom-story__eyebrow"
            >
              Our story
            </motion.p>
            <motion.h2
              initial={reduce ? false : { opacity: 0, y: 22 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.05, duration: 0.6, ease }}
              className="about-boom-story__title"
            >
              Why we
              <em> exist</em>
            </motion.h2>
            <motion.p
              initial={reduce ? false : { opacity: 0, y: 14 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: 0.1, duration: 0.5, ease }}
              className="about-boom-story__sub"
            >
              Close the gap between “we should use AI” and a working product your team actually runs —
              with proof before the build.
            </motion.p>

            <div className="about-boom-story__meter" aria-hidden>
              <motion.div style={reduce ? undefined : { height: lineHeight }} />
            </div>
          </div>

          <div className="about-boom-story__chapters">
            {CHAPTERS.map((ch, i) => (
              <motion.article
                key={ch.tag}
                initial={reduce ? false : { opacity: 0, x: 36 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-60px' }}
                transition={{ delay: i * 0.07, duration: 0.65, ease }}
                className="about-boom-story__chapter"
              >
                <div className="about-boom-story__chapter-top">
                  <span className="about-boom-story__num">{ch.tag}</span>
                  <span className="about-boom-story__kicker">{ch.kicker}</span>
                </div>
                <h3>{ch.title}</h3>
                <p>{ch.text}</p>
              </motion.article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
