import { motion, useReducedMotion } from 'framer-motion';

const STACK = [
  'Large Language Models',
  'AI Agents',
  'Computer Vision',
  'FastAPI',
  'React',
  'Microservices',
  'Vector Databases',
  'Real-time Streaming',
  'SaaS Architecture',
  'Mobile Apps',
  'Enterprise AI',
  'PostgreSQL',
];

const DOMAINS = [
  'Competitive intelligence',
  'Autonomous sales',
  'Recruitment platforms',
  'Booking systems',
  'Spend intelligence',
  'Enterprise dashboards',
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutEngineering() {
  const reduce = useReducedMotion();
  const marqueeItems = [...STACK, ...STACK];

  return (
    <section className="about-boom-eng">
      <div className="container-max relative px-4 sm:px-6 mb-12 sm:mb-14">
        <motion.div
          initial={reduce ? false : { opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.55, ease }}
          className="about-boom-eng__intro"
        >
          <p>Engineering depth</p>
          <h2>
            Production patterns.
            <em> Built for real users.</em>
          </h2>
          <p className="about-boom-eng__sub">
            The same team patterns behind competitive intelligence, hiring AI, spend systems, and
            autonomous sales — applied to your business.
          </p>
        </motion.div>
      </div>

      <div className="about-boom-eng__marquee" aria-hidden>
        <div className="about-boom-eng__fade about-boom-eng__fade--l" />
        <div className="about-boom-eng__fade about-boom-eng__fade--r" />
        <div className={`about-marquee-track gap-3 px-2 ${reduce ? '' : ''}`}>
          {marqueeItems.map((item, i) => (
            <span key={`${item}-${i}`} className="about-boom-eng__chip">
              {item}
            </span>
          ))}
        </div>
      </div>

      <div className="container-max relative px-4 sm:px-6 mt-12">
        <p className="about-boom-eng__domains-label">Domains we&apos;ve shipped in</p>
        <div className="about-boom-eng__domains">
          {DOMAINS.map((d, i) => (
            <motion.span
              key={d}
              initial={reduce ? false : { opacity: 0, scale: 0.95 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.05, duration: 0.4, ease }}
            >
              {d}
            </motion.span>
          ))}
        </div>
      </div>
    </section>
  );
}
