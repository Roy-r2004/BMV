import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { SectionHeading } from './AnimatedSection';

const faqs = [
  { q: 'Do you copy other products?', a: 'No. We use the reference only to understand the workflow you want, then design a custom version for your business.' },
  { q: 'Is the preview really free?', a: 'Yes. You get a free custom MVP blueprint and visual demo preview.' },
  { q: 'How long does the preview take?', a: 'Usually a few minutes. The AI analyzes your business and generates your custom concept.' },
  { q: 'What happens after I request a build?', a: 'Our team reviews your request, prepares a full proposal with scope and timeline, then follows up.' },
  { q: 'Do I need technical knowledge?', a: 'Not at all. Just describe your business and share a tool you like.' },
];

export default function FAQ() {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <section className="landing-section landing-section--light section-padding border-t border-slate-100">
      <div className="container-max max-w-3xl relative px-4 sm:px-6">
        <SectionHeading eyebrow="FAQ" title="Common questions" />
        <div className="space-y-3">
          {faqs.map((faq, i) => (
            <motion.div
              key={faq.q}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.04 }}
              className={`landing-faq-item ${open === i ? 'landing-faq-item--open' : ''}`}
            >
              <button
                type="button"
                className="w-full text-left p-5 font-semibold flex justify-between items-center text-navy hover:bg-slate-50/80 transition-colors text-sm sm:text-base"
                onClick={() => setOpen(open === i ? null : i)}
              >
                {faq.q}
                <span className={`text-blue-600 text-xl shrink-0 ml-3 transition-transform duration-300 ${open === i ? 'rotate-180' : ''}`}>
                  {open === i ? '−' : '+'}
                </span>
              </button>
              <AnimatePresence>
                {open === i && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.28 }}
                    className="overflow-hidden"
                  >
                    <div className="px-5 pb-5 text-slate-600 text-sm leading-relaxed border-t border-slate-100 pt-3">
                      {faq.a}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
