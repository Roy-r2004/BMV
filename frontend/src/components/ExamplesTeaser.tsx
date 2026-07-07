import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { SectionHeading } from './AnimatedSection';
import { EXAMPLE_OUTPUTS } from '../data/examples';
import ExampleCard from './ExampleCard';
import GlowButton from './GlowButton';

const preview = EXAMPLE_OUTPUTS.slice(0, 3);

export default function ExamplesTeaser() {
  return (
    <section className="landing-section landing-section--mist section-padding">
      <div className="container-max relative px-4 sm:px-6">
        <SectionHeading
          eyebrow="Results"
          title="Example outputs"
          subtitle="See what our AI generates — then get your own custom version."
        />

        <div className="grid md:grid-cols-3 gap-5 mb-10">
          {preview.map((ex, i) => (
            <ExampleCard key={ex.id} example={ex} index={i} landing />
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="flex flex-col sm:flex-row flex-wrap justify-center gap-3"
        >
          <Link
            to="/demo"
            className="inline-flex items-center justify-center px-6 py-3 rounded-xl border border-emerald-300/80 text-emerald-800 bg-white hover:bg-emerald-50 font-medium text-sm transition-colors shadow-sm"
          >
            View live demos →
          </Link>
          <Link
            to="/examples"
            className="inline-flex items-center justify-center px-6 py-3 rounded-xl border border-blue-200 text-blue-700 bg-white hover:bg-blue-50 font-medium text-sm transition-colors shadow-sm"
          >
            Concept examples →
          </Link>
          <GlowButton to="/submit" className="text-sm px-6 py-3 !inline-flex">
            Create yours
          </GlowButton>
        </motion.div>
      </div>
    </section>
  );
}
