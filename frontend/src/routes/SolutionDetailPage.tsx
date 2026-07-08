import { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import GlowButton from '../components/GlowButton';
import { getSolutionById } from '../data/solutions';
import { hasShowcaseDemo, getShowcaseDemo } from '../data/showcaseDemos';
import { hasCustomShowcaseDemo } from '../components/solutions/demos/showcaseRegistry';
import { SOLUTION_ICONS } from '../components/solutions/SolutionIcons';
import SolutionShowcaseDemo from '../components/solutions/SolutionShowcaseDemo';
import SolutionRequestModal from '../components/solutions/SolutionRequestModal';

const easeOut = [0.22, 1, 0.36, 1] as const;

export default function SolutionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const solution = id ? getSolutionById(id) : undefined;
  const [requestOpen, setRequestOpen] = useState(false);

  if (!solution) {
    return <Navigate to="/solutions" replace />;
  }

  const icon = SOLUTION_ICONS[solution.icon];
  const openRequest = () => setRequestOpen(true);
  const showcase = getShowcaseDemo(solution.id);
  const demoLive = hasShowcaseDemo(solution.id) || solution.demoStatus === 'live';

  return (
    <div className="min-h-screen bg-white overflow-x-hidden">
      <SiteNav />

      {/* Hero */}
      <section className="sol-detail-hero relative overflow-hidden pt-16">
        <div className="absolute inset-0 sol-detail-hero__mesh pointer-events-none" />
        <div className="absolute inset-0 cinematic-grid opacity-25 pointer-events-none" />
        <div className={`sol-detail-hero__accent bg-gradient-to-br ${solution.accent}`} aria-hidden />
        <div className="hero-blob w-[600px] h-[360px] bg-blue-500/15 -top-32 -right-24" />
        <div className="hero-blob w-[480px] h-[300px] bg-cyan-500/10 -bottom-40 -left-28" />

        <div className="container-max relative z-10 px-4 sm:px-6 py-10 sm:py-14">
          <motion.nav
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: easeOut }}
            className="sol-detail-breadcrumb"
            aria-label="Breadcrumb"
          >
            <Link to="/solutions">Solutions</Link>
            <span aria-hidden>/</span>
            <span>{solution.name}</span>
          </motion.nav>

          <div className="grid lg:grid-cols-[1fr_auto] gap-10 lg:gap-16 items-start mt-8">
            <div>
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, ease: easeOut }}
                className="flex flex-wrap items-center gap-4 mb-6"
              >
                <div className={`sol-detail-hero__icon bg-gradient-to-br ${solution.accent}`}>{icon}</div>
                <span className="sol-detail-badge">
                  {demoLive ? 'Live demo available' : 'Ready-made software'}
                </span>
              </motion.div>

              <motion.h1
                initial={{ opacity: 0, y: 24 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.65, delay: 0.05, ease: easeOut }}
                className="sol-detail-hero__title"
              >
                {solution.name}
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1, ease: easeOut }}
                className="sol-detail-hero__tagline"
              >
                {solution.tagline}
              </motion.p>

              <motion.p
                initial={{ opacity: 0, y: 18 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.15, ease: easeOut }}
                className="sol-detail-hero__desc"
              >
                {solution.description}
              </motion.p>

              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5, delay: 0.22, ease: easeOut }}
                className="flex flex-wrap gap-3 mt-8"
              >
                <GlowButton onClick={openRequest} className="text-sm px-7 py-3.5 !inline-block">
                  Get this for my business
                </GlowButton>
                {demoLive && (
                  <a href="#demo" className="sol-detail-ghost-btn">
                    Try live demo
                  </a>
                )}
                <a href="#included" className="sol-detail-ghost-btn">
                  See what's included
                </a>
              </motion.div>
            </div>

            <motion.aside
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.7, delay: 0.2, ease: easeOut }}
              className="sol-detail-summary about-gradient-ring"
            >
              <p className="sol-detail-summary__label">Included in this software</p>
              <ul className="sol-detail-summary__list">
                {solution.capabilities.map((cap) => (
                  <li key={cap}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
                      <polyline points="20 6 9 17 4 12" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    {cap}
                  </li>
                ))}
              </ul>
              <p className="sol-detail-summary__note">
                This is ready-made software — we customize branding, settings, and integrations so it runs as your version.
              </p>
            </motion.aside>
          </div>
        </div>

        <div className="sol-detail-hero__fade" aria-hidden />
      </section>

      {/* Plan */}
      <section id="included" className="section-padding bg-slate-50 relative scroll-mt-20">
        <div className="absolute inset-0 hero-mesh opacity-25 pointer-events-none" />
        <div className="container-max relative px-4 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="max-w-2xl mb-12"
          >
            <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">What's included</p>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-navy mb-3 tracking-tight">
              Software you already get
            </h2>
            <p className="text-slate-600 leading-relaxed">
              This isn't a concept — it's a complete package we already have. Here's everything included before we customize it for your business.
            </p>
          </motion.div>

          <div className="sol-detail-timeline">
            {solution.planPhases.map((phase, i) => (
              <motion.article
                key={phase.step}
                initial={{ opacity: 0, y: 28 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: i * 0.08, duration: 0.6, ease: easeOut }}
                className="sol-detail-phase about-gradient-ring"
              >
                <div className="sol-detail-phase__rail" aria-hidden>
                  <span className={`sol-detail-phase__dot bg-gradient-to-br ${solution.accent}`} />
                  {i < solution.planPhases.length - 1 && <span className="sol-detail-phase__line" />}
                </div>
                <div className="sol-detail-phase__body">
                  <div className="sol-detail-phase__meta">
                    <span className="sol-detail-phase__step">{phase.step}</span>
                    <span className="sol-detail-phase__duration">{phase.duration}</span>
                  </div>
                  <h3 className="sol-detail-phase__title">{phase.title}</h3>
                  <p className="sol-detail-phase__desc">{phase.description}</p>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="section-padding relative scroll-mt-20">
        <div className="container-max px-4 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center max-w-2xl mx-auto mb-12"
          >
            <p className="text-blue-600 font-medium mb-2 tracking-[0.2em] uppercase text-xs">Features</p>
            <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold text-navy mb-3 tracking-tight">
              What you get
            </h2>
            <p className="text-slate-600 leading-relaxed">
              Every feature below ships with the software — customer tools on one side, your team's dashboard on the other.
            </p>
          </motion.div>

          <div className="sol-detail-features">
            {solution.featureModules.map((mod, i) => (
              <motion.article
                key={mod.title}
                initial={{ opacity: 0, y: 32 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ delay: i * 0.1, duration: 0.65, ease: easeOut }}
                className={`sol-detail-module about-gradient-ring ${i === 0 ? 'sol-detail-module--wide' : ''}`}
              >
                <div className={`sol-detail-module__glow bg-gradient-to-br ${solution.accent}`} aria-hidden />
                <span className="sol-detail-module__index">0{i + 1}</span>
                <h3 className="sol-detail-module__title">{mod.title}</h3>
                <p className="sol-detail-module__desc">{mod.description}</p>
                <ul className="sol-detail-module__list">
                  {mod.items.map((item) => (
                    <li key={item}>
                      <span className={`sol-detail-module__check bg-gradient-to-br ${solution.accent}`}>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden>
                          <polyline points="20 6 9 17 4 12" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                      {item}
                    </li>
                  ))}
                </ul>
              </motion.article>
            ))}
          </div>
        </div>
      </section>

      {/* Demo slot */}
      <section id="demo" className="section-padding bg-[#060a14] relative overflow-hidden scroll-mt-20">
        <div className="absolute inset-0 demo-hero__mesh pointer-events-none" />
        <div className="absolute inset-0 cinematic-grid opacity-20 pointer-events-none" />
        <div className={`sol-detail-demo__orb bg-gradient-to-br ${solution.accent}`} aria-hidden />

        <div className="container-max relative z-10 px-4 sm:px-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center max-w-xl mx-auto mb-10"
          >
            <p className="demo-hero__eyebrow mx-auto w-fit mb-5">
              <span className="demo-hero__pulse" />
              Interactive demo
            </p>
            <h2 className="text-2xl sm:text-3xl font-bold text-white mb-3 tracking-tight">
              {demoLive ? 'Try it live' : 'Demo rolling out soon'}
            </h2>
            <p className="text-slate-400 leading-relaxed">
              {demoLive
                ? showcase
                  ? `Explore ${showcase.businessName} — a real walkthrough of the ${solution.name.toLowerCase()} platform we customize for your business.`
                  : 'Explore the live demo of this software — the same platform we customize for your business.'
                : `A live demo of our ${solution.name.toLowerCase()} software is on the way. Contact us to see it set up for your business.`}
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 32 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.7, ease: easeOut }}
            className={`sol-detail-demo__frame ${hasCustomShowcaseDemo(solution.id) ? 'sol-detail-demo__frame--wide' : ''}`}
          >
            {showcase ? (
              <SolutionShowcaseDemo showcase={showcase} onRequestClick={openRequest} />
            ) : solution.demoStatus === 'live' && solution.demoUrl ? (
              <div className="sol-detail-demo__browser">
                <div className="sol-detail-demo__chrome">
                  <span /><span /><span />
                  <div className="sol-detail-demo__url">{solution.demoUrl}</div>
                </div>
                <iframe
                  src={solution.demoUrl}
                  title={`${solution.name} demo`}
                  className="sol-detail-demo__iframe"
                  loading="lazy"
                />
              </div>
            ) : (
              <div className="sol-detail-demo__placeholder">
                <div className="sol-detail-demo__browser sol-detail-demo__browser--empty">
                  <div className="sol-detail-demo__chrome">
                    <span /><span /><span />
                    <div className="sol-detail-demo__url">demo.buildmyversion.com/{solution.id}</div>
                  </div>
                  <div className="sol-detail-demo__empty">
                    <div className={`sol-detail-demo__empty-icon bg-gradient-to-br ${solution.accent}`}>{icon}</div>
                    <p className="sol-detail-demo__empty-title">Demo coming soon</p>
                    <p className="sol-detail-demo__empty-sub">
                      We're preparing a live walkthrough of this software. Get in touch to see it configured for your business.
                    </p>
                    <GlowButton onClick={openRequest} className="text-sm px-6 py-3 !inline-block mt-2">
                      Get this software
                    </GlowButton>
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </div>
      </section>

      <SiteFooter />

      <SolutionRequestModal
        open={requestOpen}
        onClose={() => setRequestOpen(false)}
        industry={solution.name}
        solutionId={solution.id}
        solutionName={solution.name}
      />
    </div>
  );
}
