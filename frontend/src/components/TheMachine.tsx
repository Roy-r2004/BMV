import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';

// Heroicons-24-outline paths.
const ICONS = {
  form: 'M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM3.75 15.75A2.25 2.25 0 0 1 6 13.5h2.25a2.25 2.25 0 0 1 2.25 2.25V18a2.25 2.25 0 0 1-2.25 2.25H6A2.25 2.25 0 0 1 3.75 18v-2.25ZM13.5 6a2.25 2.25 0 0 1 2.25-2.25H18A2.25 2.25 0 0 1 20.25 6v2.25A2.25 2.25 0 0 1 18 10.5h-2.25a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25A2.25 2.25 0 0 1 13.5 18v-2.25Z',
  globe:
    'M12 21a9.004 9.004 0 0 0 8.716-6.747M12 21a9.004 9.004 0 0 1-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 0 1 7.843 4.582M12 3a8.997 8.997 0 0 0-7.843 4.582m15.686 0A11.953 11.953 0 0 1 12 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0 1 21 12c0 .778-.099 1.533-.284 2.253m-18.432-.001A8.959 8.959 0 0 1 3 12c0-.778.099-1.533.284-2.253',
  search: 'm21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z',
  grid: 'M6.429 9.75 2.25 12l4.179 2.25m0-4.5 5.571 3 5.571-3m-11.142 0L2.25 7.5 12 2.25l9.75 5.25-4.179 2.25m0 0L21.75 12l-4.179 2.25m0 0 4.179 2.25L12 21.75 2.25 16.5l4.179-2.25m11.142 0-5.571 3-5.571-3',
  cpu: 'M8.25 3v1.5M15.75 3v1.5M8.25 19.5V21M15.75 19.5V21M3 8.25H1.5M3 12H1.5M3 15.75H1.5M22.5 8.25H21M22.5 12H21M22.5 15.75H21M6.75 19.5h10.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v10.5a2.25 2.25 0 0 0 2.25 2.25Zm3-9h4.5v4.5h-4.5V9.75Z',
  doc: 'M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z',
  eye: 'M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  link: 'M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244',
} as const;

function Icon({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} className={className}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

// Every node is a REAL pipeline stage — the same stages a visitor watches
// tick by on /demo. No metaphors, no invented steps.
const ROW_A = [
  { icon: ICONS.form, title: 'Your intake', sub: '5 short steps, about 3 minutes' },
  { icon: ICONS.globe, title: 'Reads your site', sub: 'Real services, hours and tone' },
  { icon: ICONS.search, title: 'Diagnosis', sub: 'Business model, pain points, opportunity' },
  { icon: ICONS.grid, title: 'Decomposition', sub: 'Your product, broken into modules' },
] as const;

const ROW_B = [
  { icon: ICONS.cpu, title: 'Agent specs', sub: 'Brain · tools · guardrails, per module' },
  { icon: ICONS.doc, title: 'The documents', sub: 'Blueprint · technical plan · playbook' },
  { icon: ICONS.eye, title: 'Screens + QA', sub: 'Drawn, inspected, re-rolled if flawed' },
  { icon: ICONS.link, title: 'Your run', sub: 'A permanent link + a deck to keep', hot: true },
] as const;

function NodeRow({ nodes, offset }: { nodes: ReadonlyArray<{ icon: string; title: string; sub: string; hot?: boolean }>; offset?: boolean }) {
  return (
    <div className={`machine-row${offset ? ' machine-row--offset' : ''}`}>
      {nodes.map((n, i) => (
        <div className="contents" key={n.title}>
          {i > 0 && (
            <span className="machine-link" aria-hidden="true">
              <i className="machine-pulse" />
            </span>
          )}
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ delay: i * 0.08, duration: 0.45 }}
            className={`machine-node${n.hot ? ' machine-node--hot' : ''}`}
          >
            <Icon path={n.icon} className="w-4 h-4" />
            <p>{n.title}</p>
            <span>{n.sub}</span>
          </motion.div>
        </div>
      ))}
    </div>
  );
}

export default function TheMachine() {
  return (
    <section className="bg-white py-16 sm:py-20 overflow-hidden">
      <div className="container-max px-4 sm:px-6">
        <motion.p
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-[11px] font-bold uppercase tracking-[0.28em] text-blue-600 mb-3"
        >
          The machine
        </motion.p>
        <motion.h2
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.05 }}
          className="font-display text-2xl sm:text-3xl font-bold text-navy"
        >
          What actually happens in those four minutes.
        </motion.h2>
        <motion.p
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
          className="mt-3 text-slate-600 max-w-2xl leading-relaxed"
        >
          Every node below is a real stage of the pipeline — not a metaphor. Start a run and you
          watch these exact steps tick by, live.
        </motion.p>

        <div className="mt-10 machine">
          <NodeRow nodes={ROW_A} />
          <span className="machine-drop" aria-hidden="true">
            <i className="machine-pulse machine-pulse--v" />
          </span>
          <NodeRow nodes={ROW_B} offset />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 10 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mt-10 flex flex-wrap items-center gap-5"
        >
          <Link
            to="/demo"
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 px-6 py-3.5 font-bold text-white shadow-lg shadow-blue-600/30 hover:shadow-blue-500/40 hover:-translate-y-0.5 transition-all"
          >
            Start a run and watch it live <span aria-hidden>→</span>
          </Link>
          <p className="text-sm text-slate-500">Free. Yours to keep at a permanent link.</p>
        </motion.div>
      </div>
    </section>
  );
}
