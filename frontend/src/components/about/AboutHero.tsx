import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';
import GlowButton from '../GlowButton';

const ease = [0.22, 1, 0.36, 1] as const;

export default function AboutHero() {
  const reduce = useReducedMotion();
  const [parallax, setParallax] = useState(false);
  const ref = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });
  const y = useTransform(scrollYProgress, [0, 1], [0, 80]);
  const opacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);

  useEffect(() => {
    const mq = window.matchMedia('(min-width: 768px)');
    const sync = () => setParallax(mq.matches && !reduce);
    sync();
    mq.addEventListener('change', sync);
    return () => mq.removeEventListener('change', sync);
  }, [reduce]);

  return (
    <section ref={ref} className="about-boom-hero relative flex items-center overflow-hidden pt-16">
      <div className="about-boom-hero__void" aria-hidden>
        <span className="about-boom-hero__orb about-boom-hero__orb--a" />
        <span className="about-boom-hero__orb about-boom-hero__orb--b" />
        <span className="about-boom-hero__orb about-boom-hero__orb--c" />
        <span className="about-boom-hero__stars" />
      </div>

      <motion.div
        style={parallax ? { y, opacity } : undefined}
        className="container-max relative z-10 px-4 sm:px-6 w-full py-10 sm:py-20 min-h-0 sm:min-h-[min(100dvh-4rem,44rem)] flex flex-col justify-center"
      >
        <motion.p
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease }}
          className="about-boom-hero__eyebrow"
        >
          <span className="about-boom-hero__pulse" />
          AI consultancy
        </motion.p>

        <motion.p
          initial={reduce ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.06, duration: 0.55, ease }}
          className="about-boom-hero__brand"
        >
          Build My Version
        </motion.p>

        <motion.h1
          initial={reduce ? false : { opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.12, duration: 0.7, ease }}
          className="about-boom-hero__title"
        >
          We find the AI your business
          <em> actually needs.</em>
        </motion.h1>

        <motion.p
          initial={reduce ? false : { opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22, duration: 0.55, ease }}
          className="about-boom-hero__sub"
        >
          Not another agency deck. We diagnose what to automate, prove it with a live product
          preview, then our engineers ship the real thing.
        </motion.p>

        <motion.div
          initial={reduce ? false : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.32, duration: 0.5, ease }}
          className="about-boom-hero__actions"
        >
          <GlowButton to="/demo" className="text-sm px-7 py-3.5 !inline-flex">
            Find my AI fit
          </GlowButton>
          <Link to="/demo" className="about-boom-hero__ghost">
            See live builds →
          </Link>
        </motion.div>
      </motion.div>

      <div className="about-boom-hero__scroll" aria-hidden>
        <span>Scroll</span>
        <i />
      </div>
    </section>
  );
}
