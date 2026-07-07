import { motion } from 'framer-motion';

export default function ExamplesManifesto() {
  return (
    <section className="relative py-20 sm:py-24 bg-navy text-white overflow-hidden">
      <div className="absolute inset-0 cinematic-grid opacity-[0.06] pointer-events-none invert" />
      <div className="container-max relative px-4 sm:px-6">
        <div className="grid md:grid-cols-3 gap-8 sm:gap-12 text-center md:text-left">
          {[
            { n: '01', t: 'AI-generated concepts tailored to each business' },
            { n: '02', t: 'Fit scores, features, and visual previews included' },
            { n: '03', t: 'Your version starts from any tool you admire' },
          ].map((item, i) => (
            <motion.div
              key={item.n}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1, duration: 0.6 }}
            >
              <span className="text-cyan-400 font-mono text-sm font-bold">{item.n}</span>
              <p className="mt-2 text-base sm:text-lg text-slate-300 leading-relaxed font-medium">{item.t}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
