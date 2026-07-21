import { motion } from 'framer-motion';

import { scrollToId } from '../utils/scroll';

export default function HeroScrollCue() {
  return (
    <motion.button
      type="button"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 1.1, duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      onClick={() => scrollToId('how-it-works', 'smooth')}
      className="hero-scroll-cue"
      aria-label="Scroll to see how it works"
    >
      <span className="hero-scroll-cue__label">See how it works</span>
      <span className="hero-scroll-cue__mouse" aria-hidden>
        <span className="hero-scroll-cue__wheel" />
      </span>
    </motion.button>
  );
}
