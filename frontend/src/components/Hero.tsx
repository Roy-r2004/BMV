import { useRef } from 'react';

import { motion, useScroll, useTransform } from 'framer-motion';

import { Link } from 'react-router-dom';

import GlowButton from './GlowButton';

import HeroTrustBar from './HeroTrustBar';
import HeroScrollCue from './HeroScrollCue';

import HeroOrbPanel from './3d/HeroOrbPanel';
import HeroDreamCircuits from './HeroDreamCircuits';



const easeOut = [0.22, 1, 0.36, 1] as const;



export default function Hero() {

  const ref = useRef<HTMLElement>(null);

  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end start'] });

  const y = useTransform(scrollYProgress, [0, 1], [0, 60]);

  const opacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);



  return (

    <section

      ref={ref}

      className="about-cinematic-hero relative flex items-center overflow-hidden pt-16 hero-surface"

    >

      <div className="absolute inset-0 hero-mesh pointer-events-none opacity-80" />

      <div className="absolute inset-0 cinematic-grid opacity-60 pointer-events-none" />

      <HeroDreamCircuits />

      <div className="hero-blob w-[500px] h-[280px] bg-blue-400/22 -top-24 -right-28" />

      <div className="hero-blob w-[420px] h-[240px] bg-cyan-400/18 -bottom-28 -left-24" />



      <motion.div

        style={{ y, opacity }}

        className="container-max relative z-10 px-4 w-full py-8 sm:py-10 min-h-[calc(100dvh-4rem)] flex items-center"

      >

        <div className="grid lg:grid-cols-2 gap-8 lg:gap-12 items-center w-full">

          <div className="text-center lg:text-left order-2 lg:order-1">

            <motion.span

              initial={{ opacity: 0, y: 16 }}

              animate={{ opacity: 1, y: 0 }}

              transition={{ duration: 0.5, ease: easeOut }}

              className="inline-flex items-center gap-2 px-3 py-1 rounded-full about-glass text-blue-700 text-[10px] sm:text-xs font-semibold uppercase tracking-[0.18em] mb-5 shadow-sm"

            >

              <span className="relative flex h-2 w-2">

                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />

                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />

              </span>

              BMV AI · Product consultancy

            </motion.span>



            <h1 className="mb-4">

              <motion.span

                initial={{ opacity: 0, y: 28 }}

                animate={{ opacity: 1, y: 0 }}

                transition={{ delay: 0.06, duration: 0.6, ease: easeOut }}

                className="block text-[1.85rem] sm:text-4xl lg:text-[2.75rem] font-bold text-navy leading-[1.1] tracking-tight"

              >

                AI consultancy for your business.

              </motion.span>

              <motion.span

                initial={{ opacity: 0, y: 28 }}

                animate={{ opacity: 1, y: 0 }}

                transition={{ delay: 0.14, duration: 0.6, ease: easeOut }}

                className="block text-[1.85rem] sm:text-4xl lg:text-[2.75rem] font-bold gradient-text-shimmer leading-[1.1] tracking-tight mt-1"

              >

                We consult, design, and build your version.

              </motion.span>

            </h1>



            <motion.p

              initial={{ opacity: 0, y: 16 }}

              animate={{ opacity: 1, y: 0 }}

              transition={{ delay: 0.22, duration: 0.5, ease: easeOut }}

              className="text-sm sm:text-base text-slate-600 max-w-lg mx-auto lg:mx-0 mb-4 leading-relaxed"

            >

              Share any app, dashboard, or workflow you admire. Our AI studies your business and the

              reference, then delivers a custom MVP blueprint and visual preview — in minutes.

            </motion.p>



            <motion.div

              initial={{ opacity: 0, y: 12 }}

              animate={{ opacity: 1, y: 0 }}

              transition={{ delay: 0.26, duration: 0.45, ease: easeOut }}

              className="hero-proof-strip mb-6"

            >

              <span>

                <strong>~3 min</strong> preview

              </span>

              <span className="hero-proof-strip__sep" aria-hidden />

              <span>Free to start</span>

              <span className="hero-proof-strip__sep" aria-hidden />

              <span>We build when ready</span>

            </motion.div>



            <motion.div

              initial={{ opacity: 0, y: 16 }}

              animate={{ opacity: 1, y: 0 }}

              transition={{ delay: 0.3, duration: 0.5, ease: easeOut }}

              className="flex flex-col sm:flex-row gap-2.5 justify-center lg:justify-start"

            >

              <GlowButton to="/submit" className="text-sm px-6 py-3">

                Create My Business Version

              </GlowButton>

              <Link

                to="/demo"

                className="inline-flex items-center justify-center px-5 py-3 rounded-xl border border-blue-200/80 text-slate-700 hover:text-blue-700 hover:border-blue-400 hover:bg-blue-50/50 transition-all text-sm font-medium about-glass shadow-sm"

              >

                See live demos

              </Link>

            </motion.div>



            <motion.div

              initial={{ opacity: 0, y: 16 }}

              animate={{ opacity: 1, y: 0 }}

              transition={{ delay: 0.38, duration: 0.5, ease: easeOut }}

            >

              <HeroTrustBar />

            </motion.div>

          </div>



          <motion.div

            initial={{ opacity: 0, scale: 0.94, y: 20 }}

            animate={{ opacity: 1, scale: 1, y: 0 }}

            transition={{ delay: 0.2, duration: 0.75, ease: easeOut }}

            className="order-1 lg:order-2 flex justify-center lg:justify-end"

          >

            <HeroOrbPanel />

          </motion.div>

        </div>

      </motion.div>

      <HeroScrollCue />

    </section>

  );

}

