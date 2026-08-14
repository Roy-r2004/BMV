import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import GlowButton from './GlowButton';

const faqs = [
  {
    q: 'Do you copy other products?',
    a: 'No. The reference is only a workflow cue. We design a custom product for your business, customers, and brand — never a clone.',
  },
  {
    q: 'Is the preview really free?',
    a: 'Yes. You get a free custom MVP blueprint and a visual product preview. No card required to start.',
  },
  {
    q: 'How long does the preview take?',
    a: 'Our AI studies your business and the tool you admire, then builds a scoped concept you can click through — typically ready while you stay on the page.',
  },
  {
    q: 'What happens after I request a build?',
    a: 'We review your preview, confirm package and add-ons with you, then our team scopes timeline and delivers the real product.',
  },
  {
    q: 'Do I need technical knowledge?',
    a: 'Not at all. Describe how your business runs — we find the automation opportunities, show a preview, and handle the build.',
  },
  {
    q: 'Are you a software agency or an AI consultancy?',
    a: 'An AI consultancy. Our main job is discovering what your business needs to automate with AI — then we prove it with a preview and build the real product with our team.',
  },
  {
    q: 'Can this work for my industry?',
    a: 'Yes. Booking, ops dashboards, hiring, finance, marketplaces, and internal tools — if there is a workflow to improve, we can find the AI version for you.',
  },
];

const ease = [0.22, 1, 0.36, 1] as const;

export default function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section id="faq" className="faq-showcase section-padding">
      <div className="faq-showcase__bg" aria-hidden />
      <div className="container-max relative px-4 sm:px-6">
        <div className="faq-showcase__grid">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.55, ease }}
            className="faq-showcase__intro"
          >
            <p className="faq-showcase__eyebrow">FAQ</p>
            <h2 className="faq-showcase__title">Clear answers before you start</h2>
            <p className="faq-showcase__sub">
              We are an AI consultancy first: we find what your business should automate, show a
              free preview, then build only when it feels right.
            </p>

            <div className="faq-showcase__proof">
              <div>
                <strong>AI</strong>
                <span>consultancy</span>
              </div>
              <div>
                <strong>Free</strong>
                <span>fit preview</span>
              </div>
              <div>
                <strong>Human</strong>
                <span>build team</span>
              </div>
            </div>

            <div className="faq-showcase__cta">
              <GlowButton to="/demo" className="text-sm px-6 py-3.5 !inline-flex">
                Create My Business Version
              </GlowButton>
            </div>
          </motion.div>

          <div className="faq-showcase__list">
            {faqs.map((faq, i) => {
              const isOpen = open === i;
              return (
                <motion.div
                  key={faq.q}
                  initial={{ opacity: 0, y: 14 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.04, duration: 0.45, ease }}
                  className={`faq-showcase__item ${isOpen ? 'faq-showcase__item--open' : ''}`}
                >
                  <button
                    type="button"
                    className="faq-showcase__q"
                    aria-expanded={isOpen}
                    onClick={() => setOpen(isOpen ? null : i)}
                  >
                    <span className="faq-showcase__num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="faq-showcase__q-text">{faq.q}</span>
                    <span className={`faq-showcase__icon ${isOpen ? 'faq-showcase__icon--open' : ''}`} aria-hidden>
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                        <path d="M12 5v14M5 12h14" strokeLinecap="round" />
                      </svg>
                    </span>
                  </button>
                  <AnimatePresence initial={false}>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease }}
                        className="overflow-hidden"
                      >
                        <p className="faq-showcase__a">{faq.a}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
