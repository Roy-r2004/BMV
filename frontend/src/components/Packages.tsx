import { motion } from 'framer-motion';
import { SectionHeading } from './AnimatedSection';

const packages = [
  { name: 'MVP Blueprint', label: 'Free preview', desc: 'Custom concept, business-fit score, top features, and visual demo preview.', features: ['Business-fit analysis', 'Visual demo preview', 'Key features overview', 'User journey outline'] },
  { name: 'Custom MVP Build', label: 'Custom quote', desc: 'Our team builds your working MVP with pages, database, AI workflows, and deployment.', features: ['Full MVP development', 'AI integration', 'Admin dashboard', 'Deployment setup', 'Launch support'], highlight: true },
  { name: 'Full Product', label: 'Tailored scope', desc: 'Extended product with advanced features, integrations, and ongoing development.', features: ['Everything in MVP', 'Advanced integrations', 'Multi-user roles', 'Analytics', 'Ongoing updates'] },
];

export default function Packages() {
  return (
    <section className="landing-section landing-section--mist section-padding">
      <div className="container-max relative px-4 sm:px-6">
        <SectionHeading eyebrow="Services" title="Packages" subtitle="Start free. Scale when you're ready." />
        <div className="grid md:grid-cols-3 gap-5">
          {packages.map((pkg, i) => (
            <motion.div
              key={pkg.name}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.55 }}
              className={`landing-card p-6 h-full ${pkg.highlight ? 'landing-card--featured' : ''}`}
            >
              {pkg.highlight && (
                <span className="inline-block text-[10px] font-bold text-white bg-gradient-to-r from-blue-600 to-cyan-500 px-2.5 py-0.5 rounded-full uppercase tracking-wide mb-3">
                  Most popular
                </span>
              )}
              <h3 className="font-bold text-lg text-navy mb-0.5">{pkg.name}</h3>
              <p className="text-xl font-bold gradient-text mb-2">{pkg.label}</p>
              <p className="text-slate-500 text-sm mb-4 leading-relaxed">{pkg.desc}</p>
              <ul className="space-y-2">
                {pkg.features.map((f) => (
                  <li key={f} className="text-sm text-slate-600 flex gap-2 items-start">
                    <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-teal-600 shrink-0 mt-0.5" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
