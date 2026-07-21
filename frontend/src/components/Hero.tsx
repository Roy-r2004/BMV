import { useEffect, useRef, useState } from 'react';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import { Link } from 'react-router-dom';
import GlowButton from './GlowButton';
import HeroScrollCue from './HeroScrollCue';
import HeroProductStage from './HeroProductStage';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function Hero() {
  const reduce = useReducedMotion();
  const [parallax, setParallax] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 48]);
  const opacity = useTransform(scrollYProgress, [0, 0.75], [1, 0]);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const sync = () => setParallax(mq.matches && !reduce);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [reduce]);

  return (
    <section ref={ref} className="bmv-hero relative flex items-center overflow-hidden pt-16">
      <div className="bmv-hero__atmosphere" aria-hidden />
      <div className="bmv-hero__grain" aria-hidden />
      <div className="bmv-hero__wash" aria-hidden />

      <motion.div
        style={parallax ? { y, opacity } : undefined}
        className="container-max relative z-10 px-4 sm:px-6 w-full py-7 sm:py-10 min-h-0 sm:min-h-[min(100dvh-4rem,46rem)] flex items-center"
      >
        <div className="grid lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] gap-8 lg:gap-14 items-center w-full">
          <div className="text-center lg:text-left">
            <motion.p
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: easeOut }}
              className="bmv-hero__brand"
            >
              Build My Version
            </motion.p>

            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05, duration: 0.45, ease: easeOut }}
              className="bmv-hero__eyebrow"
            >
              AI consultancy
            </motion.p>

            <motion.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.08, duration: 0.6, ease: easeOut }}
              className="bmv-hero__headline"
            >
              We find the AI & automation your business actually needs.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.18, duration: 0.5, ease: easeOut }}
              className="bmv-hero__support"
            >
              Tell us how you work. We spot the right automations, show a custom product preview,
              then our team builds it — free to start.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.28, duration: 0.5, ease: easeOut }}
              className="flex flex-col sm:flex-row gap-3 justify-center lg:justify-start items-stretch sm:items-center"
            >
              <GlowButton to="/submit" className="text-sm px-7 py-3.5">
                Find my AI fit
              </GlowButton>
              <Link to="/demo" className="bmv-hero__secondary">
                See live demos
              </Link>
            </motion.div>
          </div>

          <div>
            <HeroProductStage />
          </div>
        </div>
      </motion.div>

      <HeroScrollCue />
    </section>
  );
}
