import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
  businessName: string;
  industry?: string | null;
  conceptName?: string | null;
}

const steps = [
  {
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden>
        <path d="M10 12a2 2 0 100-4 2 2 0 000 4z" />
        <path fillRule="evenodd" d="M.458 10C1.732 5.943 5.522 3 10 3s8.268 2.943 9.542 7c-1.274 4.057-5.064 7-9.542 7S1.732 14.057.458 10zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
      </svg>
    ),
    title: 'This is your custom product concept',
    desc: 'Our AI studied your business and designed this — it shows what your actual app could look like.',
  },
  {
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden>
        <path fillRule="evenodd" d="M6.672 1.911a1 1 0 10-1.932.518l.259.966a1 1 0 001.932-.518l-.26-.966zM2.429 4.74a1 1 0 10-.517 1.932l.966.259a1 1 0 00.517-1.932l-.966-.26zm8.814-.569a1 1 0 00-1.415-1.414l-.707.707a1 1 0 101.415 1.415l.707-.708zm-7.071 7.072l.707-.707A1 1 0 003.465 9.12l-.708.707a1 1 0 001.415 1.415zm3.2-5.171a1 1 0 00-1.3 1.3l4 10a1 1 0 001.823.075l1.38-2.759 3.018 3.02a1 1 0 001.414-1.415l-3.019-3.02 2.76-1.379a1 1 0 00-.076-1.822l-10-4z" clipRule="evenodd" />
      </svg>
    ),
    title: 'Click the tabs to explore it',
    desc: 'Switch between the public website, booking flow, inbox, and admin dashboard — all built for your business.',
  },
  {
    icon: (
      <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4" aria-hidden>
        <path fillRule="evenodd" d="M12.293 5.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L14.586 11H3a1 1 0 110-2h11.586l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
      </svg>
    ),
    title: 'Like what you see? Request the real build',
    desc: 'Scroll down for your full blueprint and proposal, then ask our team to build the real working product.',
  },
];

export default function PreviewExplainer({ businessName, industry, conceptName }: Props) {
  const [dismissed, setDismissed] = useState(false);

  return (
    <AnimatePresence>
      {!dismissed && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8, height: 0, marginBottom: 0 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          className="preview-explainer"
        >
          <div className="preview-explainer__inner">
            <div className="preview-explainer__badge">
              <span className="preview-explainer__pulse" />
              AI-generated preview · {conceptName || businessName}
              {industry ? ` · ${industry}` : ''}
            </div>

            <div className="preview-explainer__steps">
              {steps.map((s) => (
                <div key={s.title} className="preview-explainer__step">
                  <span className="preview-explainer__step-icon">{s.icon}</span>
                  <div>
                    <p className="preview-explainer__step-title">{s.title}</p>
                    <p className="preview-explainer__step-desc">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <button
              type="button"
              className="preview-explainer__dismiss"
              onClick={() => setDismissed(true)}
              aria-label="Dismiss this explanation"
            >
              Got it
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
