import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { SectionHeading } from './AnimatedSection';

const iconClass = 'w-5 h-5';

const icons = {
  business: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  ),
  link: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" /><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  ),
  ai: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="3" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2" />
    </svg>
  ),
  build: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  ),
} satisfies Record<string, ReactNode>;

type PreviewKind = 'business' | 'link' | 'ai' | 'build';

const steps: {
  num: string;
  title: string;
  desc: string;
  icon: ReactNode;
  preview: PreviewKind;
  featured?: boolean;
}[] = [
  {
    num: '01',
    title: 'Tell us how you work',
    desc: 'Share your industry, workflows, and where time or money leaks.',
    icon: icons.business,
    preview: 'business',
  },
  {
    num: '02',
    title: 'Point to inspiration',
    desc: 'Optional: a tool or process you admire — we use it as a cue, not a clone.',
    icon: icons.link,
    preview: 'link',
  },
  {
    num: '03',
    title: 'We find your AI fit',
    desc: 'Our consultancy AI maps what to automate, then shows a custom product preview.',
    icon: icons.ai,
    preview: 'ai',
    featured: true,
  },
  {
    num: '04',
    title: 'We build it for you',
    desc: 'Approve the concept and our team ships the real automation product.',
    icon: icons.build,
    preview: 'build',
  },
];

function StepPreview({ kind }: { kind: PreviewKind }) {
  if (kind === 'business') {
    return (
      <div className="process-preview process-preview--business" aria-hidden>
        <span className="process-preview__label">Your business</span>
        <span className="process-preview__field" />
        <span className="process-preview__field process-preview__field--short" />
        <span className="process-preview__chip">Clinic · Coaching · Ops</span>
      </div>
    );
  }

  if (kind === 'link') {
    return (
      <div className="process-preview process-preview--link" aria-hidden>
        <span className="process-preview__url">
          <span className="process-preview__url-dot" />
          app-you-admire.com
        </span>
        <span className="process-preview__thumb" />
      </div>
    );
  }

  if (kind === 'ai') {
    return (
      <div className="process-preview process-preview--ai" aria-hidden>
        <span className="process-preview__spark" />
        <span className="process-preview__blocks">
          <span className="process-preview__block process-preview__block--wide" />
          <span className="process-preview__block" />
          <span className="process-preview__block process-preview__block--accent" />
        </span>
      </div>
    );
  }

  return (
    <div className="process-preview process-preview--build" aria-hidden>
      <span className="process-preview__shield" />
      <span className="process-preview__launch">Launch ready</span>
    </div>
  );
}

export default function HowItWorks() {
  return (
    <section id="how-it-works" className="landing-section landing-section--mist process-section section-padding">
      <div className="process-section__bg" aria-hidden>
        <div className="process-section__orb process-section__orb--a" />
        <div className="process-section__orb process-section__orb--b" />
      </div>

      <div className="container-max relative px-4 sm:px-6">
        <SectionHeading
          eyebrow="AI consultancy"
          title="How we find what to automate"
          subtitle="We diagnose the AI and automation opportunities in your business — then prove it with a preview before you build."
        />

        <div className="process-flow">
          <div className="process-flow__pipeline" aria-hidden>
            <span className="process-flow__pulse" />
          </div>

          <div className="process-flow__grid">
            {steps.map((step, i) => (
              <motion.article
                key={step.num}
                initial={{ opacity: 0, y: 32 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ delay: i * 0.08, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                className={`process-card ${step.featured ? 'process-card--featured' : ''}`}
              >
                <span className="process-card__watermark" aria-hidden>
                  {step.num}
                </span>
                <div className="process-card__preview-wrap">
                  <StepPreview kind={step.preview} />
                </div>
                <div className="process-card__body">
                  <div className="process-card__head">
                    <span className="process-card__num">{step.num}</span>
                    <div className="process-card__icon">{step.icon}</div>
                  </div>
                  <h3 className="process-card__title">{step.title}</h3>
                  <p className="process-card__desc">{step.desc}</p>
                </div>
              </motion.article>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
