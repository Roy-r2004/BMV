import { motion } from 'framer-motion';
import { Link } from 'react-router-dom';
import { SectionHeading } from './AnimatedSection';
import { BUILD_PLANS } from '../data/buildPlans';

export default function Packages() {
  return (
    <section className="landing-section landing-section--mist section-padding">
      <div className="container-max relative px-4 sm:px-6">
        <SectionHeading
          eyebrow="Packages"
          title="Start free. Choose how we build."
          subtitle="After your live preview we write packages for your business. Pricing is quoted with you — never checkout online."
        />
        <div className="grid md:grid-cols-3 gap-5">
          {BUILD_PLANS.map((pkg, i) => (
            <motion.div
              key={pkg.id}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.07, duration: 0.55 }}
              className={`landing-card p-6 h-full flex flex-col ${pkg.highlight ? 'landing-card--featured' : ''}`}
            >
              {pkg.badge ? (
                <span className="inline-block text-[10px] font-bold text-white bg-slate-900 px-2.5 py-0.5 rounded-full uppercase tracking-wide mb-3 w-fit">
                  {pkg.badge}
                </span>
              ) : null}
              <h3 className="font-bold text-lg text-navy mb-0.5">{pkg.name}</h3>
              <p className="text-xs font-medium text-slate-500 mb-2">{pkg.timeline}</p>
              <p className="text-slate-500 text-sm mb-4 leading-relaxed">{pkg.tagline}</p>
              <ul className="space-y-2 flex-1">
                {pkg.includes.slice(0, 4).map((f) => (
                  <li key={f} className="text-sm text-slate-600 flex gap-2 items-start">
                    <span className="text-teal-600 shrink-0" aria-hidden>
                      ✓
                    </span>
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/demo"
                className="mt-5 inline-flex justify-center rounded-xl bg-slate-900 text-white text-sm font-semibold px-4 py-2.5 hover:bg-slate-800 transition"
              >
                Start with a free preview
              </Link>
            </motion.div>
          ))}
        </div>
        <p className="mt-6 text-center text-sm text-slate-500">
          After your live preview you’ll pick a package and optional add-ons — we confirm the quote
          with you.
        </p>
      </div>
    </section>
  );
}
