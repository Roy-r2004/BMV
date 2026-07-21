import { motion, useReducedMotion } from 'framer-motion';

const STEPS = [
  {
    n: '01',
    value: 'Diagnose',
    label: 'What to automate',
    detail: 'We map your workflow and pin the AI that actually moves the needle.',
  },
  {
    n: '02',
    value: 'Prove',
    label: 'With a live preview',
    detail: 'A clickable product for your business — not a deck, not a mockup PDF.',
  },
  {
    n: '03',
    value: 'Ship',
    label: 'Real engineering',
    detail: 'Our team builds the production system: AI, APIs, UI, infra.',
  },
  {
    n: '04',
    value: 'Own',
    label: 'Your version',
    detail: 'Custom software you run. Inspired by references — never a clone.',
  },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutStats() {
  const reduce = useReducedMotion();

  return (
    <section className="about-boom-stats">
      <div className="container-max px-4 sm:px-6 py-20 sm:py-28">
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease }}
          className="about-boom-stats__head"
        >
          <p>The method</p>
          <h2>
            Four moves.
            <em> Zero guesswork.</em>
          </h2>
          <p className="about-boom-stats__lede">
            From “we should use AI” to a system your team owns — in a sequence you can feel.
          </p>
        </motion.div>

        <div className="about-boom-stats__rail" aria-hidden>
          <span className="about-boom-stats__rail-line" />
        </div>

        <ol className="about-boom-stats__grid">
          {STEPS.map((s, i) => (
            <motion.li
              key={s.value}
              initial={reduce ? false : { opacity: 0, y: 32 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: i * 0.1, duration: 0.6, ease }}
              className="about-boom-stats__card"
            >
              <div className="about-boom-stats__node">
                <span>{s.n}</span>
              </div>
              <p className="about-boom-stats__value">{s.value}</p>
              <p className="about-boom-stats__label">{s.label}</p>
              <p className="about-boom-stats__detail">{s.detail}</p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
