import { useState } from 'react';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { EXAMPLE_OUTPUTS } from '../data/examples';
import ExampleProductPreview from './examples/ExampleProductPreview';
import GlowButton from './GlowButton';

const preview = EXAMPLE_OUTPUTS.slice(0, 3);
const ease = [0.22, 1, 0.36, 1] as const;

const SHORT: Record<string, { product: string; niche: string }> = {
  'business-xray': { product: 'X-Ray', niche: 'Sales intel' },
  hirewise: { product: 'HireWise', niche: 'Recruiting' },
  cashpath: { product: 'CashPath', niche: 'Spend AI' },
};

export default function ExamplesTeaser() {
  const [activeId, setActiveId] = useState(preview[0].id);
  const active = preview.find((e) => e.id === activeId) ?? preview[0];

  return (
    <section id="examples" className="examples-showcase section-padding">
      <div className="examples-showcase__bg" aria-hidden />
      <div className="container-max relative px-4 sm:px-6">
        <div className="examples-showcase__intro">
          <motion.p
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.45, ease }}
            className="examples-showcase__eyebrow"
          >
            Example outputs
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.05, duration: 0.55, ease }}
            className="examples-showcase__title"
          >
            Automation ideas our consultancy turns into apps
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1, duration: 0.5, ease }}
            className="examples-showcase__sub"
          >
            Click an example — the kind of AI product we recommend after we map what your business needs.
          </motion.p>
        </div>

        <div className="examples-showcase__layout examples-showcase__layout--tight">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.55, ease }}
            className="examples-showcase__stage"
          >
            <AnimatePresence mode="wait">
              <motion.div
                key={active.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.25, ease }}
                className="examples-showcase__frame"
              >
                <ExampleProductPreview example={active} size="md" />
                <div className="examples-showcase__caption">
                  <div>
                    <span className="examples-showcase__caption-ind">{active.industry}</span>
                    <strong>{active.name}</strong>
                    <p>{active.tagline}</p>
                  </div>
                  <Link to="/submit" className="examples-showcase__inline-cta">
                    Create yours →
                  </Link>
                </div>
              </motion.div>
            </AnimatePresence>
          </motion.div>

          <div className="examples-showcase__rail" role="tablist" aria-label="Example concepts">
            <p className="examples-showcase__rail-label">Pick an example</p>
            {preview.map((ex, i) => {
              const selected = ex.id === active.id;
              const short = SHORT[ex.id] ?? { product: ex.inspiredBy, niche: ex.industry };
              return (
                <motion.button
                  key={ex.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-label={`${short.product}: ${ex.name}`}
                  initial={{ opacity: 0, x: 12 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: 0.06 + i * 0.05, duration: 0.4, ease }}
                  onClick={() => setActiveId(ex.id)}
                  className={`examples-showcase__tab ${selected ? 'examples-showcase__tab--active' : ''}`}
                >
                  <span className="examples-showcase__tab-thumb" data-id={ex.id} aria-hidden />
                  <span className="examples-showcase__tab-copy">
                    <span className="examples-showcase__tab-ind">
                      {String(i + 1).padStart(2, '0')} · {short.niche}
                    </span>
                    <span className="examples-showcase__tab-name">{short.product}</span>
                  </span>
                  <span className="examples-showcase__tab-score">{ex.score}%</span>
                </motion.button>
              );
            })}
          </div>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="examples-showcase__actions"
        >
          <Link to="/demo" className="examples-showcase__link">
            View live demos
          </Link>
          <Link to="/examples" className="examples-showcase__link">
            All concept examples
          </Link>
          <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-flex">
            Create yours
          </GlowButton>
        </motion.div>
      </div>
    </section>
  );
}
