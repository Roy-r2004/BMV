import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { consultantAssetUrl, fetchShowcase, type StudioShowcaseCard } from '../api/consultant';

/** The public example engagements — real runs, explicitly listed, shown as
 *  the proof a consultancy shows instead of doing free work: finished
 *  engagements anyone can read cover to cover. Renders nothing until the
 *  gallery has entries, so the section can ship before the list is set. */
export default function ShowcaseEngagements() {
  const [cards, setCards] = useState<StudioShowcaseCard[]>([]);

  useEffect(() => {
    fetchShowcase()
      .then(setCards)
      .catch(() => setCards([]));
  }, []);

  if (cards.length === 0) return null;

  return (
    <section className="bg-white py-16 sm:py-20" id="example-engagements">
      <div className="container-max px-4 sm:px-6">
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-600 mb-3"
        >
          Example engagements
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.05 }}
          className="font-display text-2xl sm:text-4xl font-bold text-navy mb-4"
        >
          Read a finished engagement, cover to cover.
        </motion.h2>
        <p className="text-slate-600 max-w-2xl mb-10">
          These are complete, unedited outputs of our engagement process — the three-volume
          document set, the screens, the numbers. Open one and judge the standard yourself.
        </p>

        <div className="grid md:grid-cols-2 gap-6">
          {cards.map((c, i) => (
            <motion.div
              key={c.id}
              initial={{ opacity: 0, y: 18 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ delay: 0.08 + i * 0.08, duration: 0.5 }}
              className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-[0_16px_40px_-30px_rgba(15,23,42,0.4)] flex flex-col"
            >
              {c.image_url && (
                <Link to={`/demo/${c.id}`} className="block bg-[#0b1220]">
                  <img
                    src={consultantAssetUrl(c.image_url) ?? undefined}
                    alt={`${c.concept_name ?? c.business_name} — product screen`}
                    className="w-full h-48 object-cover object-top opacity-95"
                    loading="lazy"
                  />
                </Link>
              )}
              <div className="p-6 flex flex-col flex-1">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display text-xl font-bold text-navy">
                      {c.concept_name ?? c.business_name}
                    </h3>
                    <p className="text-sm text-slate-500 mt-0.5">{c.industry}</p>
                  </div>
                  <span className="shrink-0 text-[10px] font-bold uppercase tracking-wide text-blue-700 bg-blue-50 border border-blue-100 rounded-full px-2.5 py-1">
                    {c.operating_stage === 'opening' ? 'New venture' : 'Operating business'}
                  </span>
                </div>

                <div className="flex flex-wrap gap-2 mt-4">
                  {[
                    [c.stats.modules, 'modules'],
                    [c.stats.ai_agents, 'AI agents'],
                    [c.stats.journey_stages, 'journey stages'],
                    [c.stats.procedures, 'procedures'],
                  ]
                    .filter(([n]) => (n as number) > 0)
                    .map(([n, label]) => (
                      <span
                        key={label as string}
                        className="text-xs font-semibold text-slate-600 bg-slate-50 border border-slate-200 rounded-full px-2.5 py-1"
                      >
                        <strong className="text-blue-700">{n}</strong> {label}
                      </span>
                    ))}
                </div>

                <div className="mt-auto pt-5">
                  <Link
                    to={`/demo/${c.id}`}
                    className="inline-flex items-center gap-2 text-sm font-bold text-blue-700 hover:text-blue-800"
                  >
                    Read the full engagement
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-4 h-4">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                    </svg>
                  </Link>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
