import { motion, useReducedMotion } from 'framer-motion';

const lines = [
  { text: 'Most businesses guess at AI.', tone: 'soft' as const },
  { text: 'We map the workflow. Find the automation. Prove it with a product.', tone: 'mid' as const },
  { text: 'Then we build it.', tone: 'boom' as const },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutManifesto() {
  const reduce = useReducedMotion();

  return (
    <section className="about-boom-manifesto">
      <div className="about-boom-manifesto__glow" aria-hidden />
      <div className="container-max relative px-4 sm:px-6 py-24 sm:py-32">
        {lines.map((line, i) => (
          <motion.p
            key={line.text}
            initial={reduce ? false : { opacity: 0, y: 40 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ delay: i * 0.12, duration: 0.75, ease }}
            className={`about-boom-manifesto__line about-boom-manifesto__line--${line.tone}`}
          >
            {line.text}
          </motion.p>
        ))}
      </div>
    </section>
  );
}
