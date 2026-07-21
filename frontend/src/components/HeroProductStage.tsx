import { motion } from 'framer-motion';

const ease = [0.22, 1, 0.36, 1] as const;

/** Dominant product visual for the landing hero — shows the BMV loop. */
export default function HeroProductStage() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 28, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: 0.18, duration: 0.75, ease }}
      className="bmv-hero-stage relative w-full max-w-[34rem] mx-auto lg:mx-0 lg:ml-auto"
    >
      <div className="bmv-hero-stage__glow" aria-hidden />

      <div className="bmv-hero-stage__frame">
        <div className="bmv-hero-stage__chrome">
          <span className="bmv-hero-stage__dot bmv-hero-stage__dot--r" />
          <span className="bmv-hero-stage__dot bmv-hero-stage__dot--y" />
          <span className="bmv-hero-stage__dot bmv-hero-stage__dot--g" />
          <span className="bmv-hero-stage__url">buildmyversion.com/preview</span>
          <span className="bmv-hero-stage__live">Live preview</span>
        </div>

        <div className="bmv-hero-stage__body">
          <div className="bmv-hero-stage__rail">
            <span className="bmv-hero-stage__rail-mark">BMV</span>
            <span className="bmv-hero-stage__rail-line" />
            <span>Overview</span>
            <span>Flows</span>
            <span className="bmv-hero-stage__rail-active">Your version</span>
          </div>

          <div className="bmv-hero-stage__main">
            <motion.div
              className="bmv-hero-stage__panel bmv-hero-stage__panel--ref"
              animate={{ y: [0, -4, 0] }}
              transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut' }}
            >
              <p className="bmv-hero-stage__kicker">Reference</p>
              <p className="bmv-hero-stage__title">Tool you admire</p>
              <div className="bmv-hero-stage__bars">
                <span style={{ width: '78%' }} />
                <span style={{ width: '54%' }} />
                <span style={{ width: '66%' }} />
              </div>
            </motion.div>

            <motion.div
              className="bmv-hero-stage__arrow"
              animate={{ x: [0, 4, 0], opacity: [0.55, 1, 0.55] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: 'easeInOut' }}
              aria-hidden
            >
              →
            </motion.div>

            <motion.div
              className="bmv-hero-stage__panel bmv-hero-stage__panel--out"
              animate={{ y: [0, 5, 0] }}
              transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut', delay: 0.4 }}
            >
              <p className="bmv-hero-stage__kicker">Your fit</p>
              <p className="bmv-hero-stage__title">AI & automation plan</p>
              <ul className="bmv-hero-stage__list">
                <li>What to automate first</li>
                <li>Clickable product preview</li>
                <li>Ready for our team to build</li>
              </ul>
            </motion.div>
          </div>

          <motion.div
            className="bmv-hero-stage__status"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.7, duration: 0.5 }}
          >
            <span className="bmv-hero-stage__pulse" />
            Free AI consultancy — find your fit
          </motion.div>
        </div>
      </div>
    </motion.div>
  );
}
