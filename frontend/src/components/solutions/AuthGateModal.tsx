import { Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';

interface Props {
  open: boolean;
  onClose: () => void;
  solutionName: string;
  returnPath: string;
}

export default function AuthGateModal({ open, onClose, solutionName, returnPath }: Props) {
  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, y: 16, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ duration: 0.25 }}
            className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="auth-gate-title"
          >
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-blue-600 mb-2">Your version</p>
            <h2 id="auth-gate-title" className="text-2xl font-bold text-navy mb-2">
              Sign in to edit with AI
            </h2>
            <p className="text-sm text-slate-600 mb-6 leading-relaxed">
              The demo is the same for everyone until you sign in. Your account gets a private copy of the{' '}
              {solutionName} template — edit colors, copy, sections, or code. Other users never see your changes.
            </p>
            <div className="flex flex-col gap-3">
              <Link
                to="/login"
                state={{ from: returnPath }}
                className="gradient-btn w-full justify-center !block text-sm py-3 text-center"
              >
                Sign in
              </Link>
              <Link
                to="/signup"
                state={{ from: returnPath }}
                className="text-center text-sm font-semibold text-blue-600 hover:underline py-2"
              >
                Create free account
              </Link>
              <button
                type="button"
                onClick={onClose}
                className="text-center text-sm text-slate-500 hover:text-slate-700 py-1"
              >
                Keep browsing the demo
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
