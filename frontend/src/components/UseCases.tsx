import type { ReactNode } from 'react';
import AnimatedSection, { SectionHeading } from './AnimatedSection';

const iconClass = 'w-4 h-4 shrink-0 text-blue-600';

const icons = {
  chat: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  ),
  calendar: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </svg>
  ),
  dashboard: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </svg>
  ),
  leads: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  quote: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  ),
  portal: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  ),
  marketplace: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
      <path d="M3 6h18M16 10a4 4 0 0 1-8 0" />
    </svg>
  ),
  workflow: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="18" r="3" />
      <path d="M8.5 8.5L15.5 15.5" />
      <path d="M18 9v-1a2 2 0 0 0-2-2h-2M6 15v1a2 2 0 0 0 2 2h2" />
    </svg>
  ),
  automation: (
    <svg viewBox="0 0 24 24" fill="none" className={iconClass} stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
    </svg>
  ),
} satisfies Record<string, ReactNode>;

const useCases = [
  { label: 'AI customer assistants', icon: icons.chat },
  { label: 'Booking systems', icon: icons.calendar },
  { label: 'Internal dashboards', icon: icons.dashboard },
  { label: 'Lead follow-up systems', icon: icons.leads },
  { label: 'Quote generators', icon: icons.quote },
  { label: 'Client portals', icon: icons.portal },
  { label: 'Marketplaces', icon: icons.marketplace },
  { label: 'AI workflow tools', icon: icons.workflow },
  { label: 'Business automation', icon: icons.automation },
];

export default function UseCases() {
  return (
    <section className="landing-section landing-section--light section-padding border-t border-slate-100">
      <div className="container-max px-4 sm:px-6">
        <SectionHeading
          eyebrow="Possibilities"
          title="Built for any business"
          subtitle="Any tool or workflow can inspire your custom version."
        />
        <div className="flex flex-wrap justify-center gap-2.5">
          {useCases.map((uc, i) => (
            <AnimatedSection key={uc.label} delay={i * 0.02} className="inline-block">
              <span className="landing-pill">
                {uc.icon}
                {uc.label}
              </span>
            </AnimatedSection>
          ))}
        </div>
      </div>
    </section>
  );
}
