import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import SolutionRequestForm from './SolutionRequestForm';

interface Props {
  open: boolean;
  onClose: () => void;
  industry: string;
  solutionId: string;
  solutionName: string;
}

const ease = [0.22, 1, 0.36, 1] as const;

export default function SolutionRequestModal({
  open,
  onClose,
  industry,
  solutionId,
  solutionName,
}: Props) {
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="solution-request-modal" role="dialog" aria-modal="true" aria-labelledby="solution-request-title">
          <motion.button
            type="button"
            className="solution-request-modal__backdrop"
            aria-label="Close"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          <motion.div
            className="solution-request-modal__panel solution-request-modal__panel--compact"
            initial={{ opacity: 0, y: 32, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ duration: 0.45, ease }}
          >
            <div className="solution-request-modal__header">
              <div>
                <p className="solution-request-modal__eyebrow">{solutionName}</p>
                <h2 id="solution-request-title" className="solution-request-modal__title">
                  Get this for my business
                </h2>
                <p className="solution-request-modal__sub">
                  You already saw the demo — just leave your details and we&apos;ll customize this software for you.
                </p>
              </div>
              <button type="button" className="solution-request-modal__close" onClick={onClose} aria-label="Close">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
                </svg>
              </button>
            </div>

            <div className="solution-request-modal__body">
              <SolutionRequestForm
                industry={industry}
                solutionId={solutionId}
                solutionName={solutionName}
                onClose={onClose}
              />
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
