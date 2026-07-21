import { motion, useReducedMotion } from 'framer-motion';

const PRINCIPLES = [
  {
    n: '01',
    title: 'Diagnose before you build',
    text: 'We find the automation that moves the needle — not a chatbot bolted onto a form because AI is trendy.',
    punch: 'Clarity first.',
  },
  {
    n: '02',
    title: 'Prove it live',
    text: 'A free clickable preview so you feel the product in your hands before you commit capital.',
    punch: 'Conviction from use.',
  },
  {
    n: '03',
    title: 'Ship production systems',
    text: 'Our team builds real software: AI, APIs, UI, infra — launch-ready systems, not demos that die in a folder.',
    punch: 'Built to run.',
  },
  {
    n: '04',
    title: 'Original by design',
    text: 'References inspire the workflow. We never clone proprietary code, brand assets, or design systems.',
    punch: 'Yours alone.',
  },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutPrinciples() {
  const reduce = useReducedMotion();

  return (
    <section className="about-boom-principles">
      <div className="container-max px-4 sm:px-6 py-24 sm:py-32">
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="about-boom-principles__head"
        >
          <p>Principles</p>
          <h2>
            How we work
            <em> — no theater.</em>
          </h2>
          <p className="about-boom-principles__lede">
            Four non-negotiables. Every engagement. Every build.
          </p>
        </motion.div>

        <div className="about-boom-principles__list">
          {PRINCIPLES.map((v, i) => (
            <motion.article
              key={v.n}
              initial={reduce ? false : { opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-50px' }}
              transition={{ delay: i * 0.08, duration: 0.55, ease }}
              className="about-boom-principles__row"
            >
              <span className="about-boom-principles__n">{v.n}</span>
              <div className="about-boom-principles__body">
                <p className="about-boom-principles__punch">{v.punch}</p>
                <h3>{v.title}</h3>
                <p>{v.text}</p>
              </div>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}
