/**
 * Building the package — only ever because they chose it.
 *
 * The answer stays pinned at the top: everything being written below is
 * built around it, and a client who can see that does not wonder whether the
 * build forgot what the diagnosis said. The documents fill one by one; what is
 * being written right now is named. They can close the page.
 */
import { motion, useReducedMotion } from 'framer-motion';
import { shortName } from '../../utils/names';

const DOCS = [
  { name: 'Your Monday plan', note: 'What you can start before any software exists', at: 30, doneAt: 35 },
  { name: 'Blueprint', note: 'What to build, in what order, and what it is worth', at: 42, doneAt: 56 },
  { name: 'Technical plan', note: 'For whoever builds it', at: 56, doneAt: 60 },
  { name: 'Operations manual', note: 'Who does what, every day', at: 60, doneAt: 62 },
  { name: 'Product screens', note: 'Each one checked twice', at: 62, doneAt: 100 },
] as const;

type State = 'done' | 'active' | 'pending';

function DocCard({ name, note, state, reduce }: { name: string; note: string; state: State; reduce: boolean }) {
  const lines = [80, 62, 0, 90, 76, 84, 58, 0, 76, 88, 60];
  return (
    <div>
      <div className={`cx-card cx-doc ${state}`}>
        <p className="cx-h3">{name}</p>
        {state !== 'pending' ? (
          <div className="mt-2 flex flex-1 flex-col gap-[11px]">
            {lines.map((w, i) =>
              w === 0 ? (
                <span key={i} className="h-2" />
              ) : (
                <span
                  key={i}
                  className={`cx-doc-line${state === 'active' && i > 5 ? ' writing' : ''}`}
                  style={{ width: `${w}%`, animationDelay: reduce ? undefined : `${(i % 5) * 0.35}s`, opacity: state === 'active' && i > 7 ? 0.5 : 1 }}
                />
              ),
            )}
          </div>
        ) : (
          <div className="flex-1" />
        )}
        {state === 'done' ? (
          <motion.span className="cx-tick self-end" initial={reduce ? false : { scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
            <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2.6} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
            </svg>
          </motion.span>
        ) : null}
      </div>
      <p className="mt-5 text-[19px] font-semibold">{name}</p>
      <p className={`mt-1 text-[15.5px] ${state === 'done' ? 'text-[var(--cx-green)]' : state === 'active' ? 'text-[var(--cx-blue)]' : 'cx-faint'}`}>
        {state === 'done' ? 'Ready' : state === 'active' ? 'Being written now' : note}
      </p>
    </div>
  );
}

export default function Building({
  businessName,
  finding,
  pct,
  elapsed,
  label,
  detail,
  notifyEmail,
  resultUrl,
  copied,
  onCopy,
}: {
  businessName: string;
  finding: string | null;
  pct: number;
  elapsed: string;
  label: string | null;
  detail: string | null;
  notifyEmail: string | null;
  resultUrl: string | null;
  copied: boolean;
  onCopy: () => void;
}) {
  const reduce = Boolean(useReducedMotion());
  const short = shortName(businessName);
  const progress = Math.max(2, Math.min(100, ((pct - 30) / 70) * 100));
  const stateOf = (at: number, doneAt: number): State => (pct >= doneAt ? 'done' : pct >= at ? 'active' : 'pending');

  return (
    <section className="pt-8">
      <div className="flex flex-wrap items-end justify-between gap-8">
        <div className="min-w-0">
          <h1 className="cx-h1">Building {short}'s package</h1>
          {finding ? (
            <p className="mt-7 inline-flex max-w-full flex-wrap items-center gap-4 rounded-full border border-[rgba(37,99,235,0.22)] bg-[#e8efff] py-2 pl-2 pr-6 text-[17px]">
              <span className="cx-chip cx-chip--solid" style={{ height: 32, padding: "0 16px" }}>Built around your answer</span>
              <span>{finding}</span>
            </p>
          ) : null}
        </div>
        <div className="text-right">
          <p className="cx-display text-[54px]">{elapsed}</p>
          <p className="cx-faint text-[16px]">of about 10 minutes</p>
        </div>
      </div>

      <div className="mt-10 h-[4px] rounded bg-[rgba(37,99,235,0.14)]" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100}>
        <div className="h-full rounded bg-[var(--cx-blue)] transition-all duration-700" style={{ width: `${progress}%` }} />
      </div>

      <div className="mt-12 grid gap-8 sm:grid-cols-2 xl:grid-cols-5">
        {DOCS.map((d) => (
          <DocCard key={d.name} name={d.name} note={d.note} state={stateOf(d.at, d.doneAt)} reduce={reduce} />
        ))}
      </div>

      <div className="cx-card mt-12 flex flex-wrap items-start gap-6 p-7">
        <span className="cx-chip cx-chip--amber">Happening now</span>
        <p className="min-w-0 flex-1 text-[18px] italic text-[var(--cx-txt2)]">
          {label || 'Getting started'}
          {detail ? <span className="not-italic cx-faint"> — {detail}</span> : null}
          <span className="cx-typing"><i /><i /><i /></span>
        </p>
      </div>

      <div className="mt-10 flex flex-wrap justify-between gap-4 text-[15.5px]">
        <p className="cx-muted">
          <b className="text-[var(--cx-txt)]">You can close this page.</b>{' '}
          {notifyEmail ? `We'll email ${notifyEmail} the moment it's ready.` : 'Your package stays at this address:'}{' '}
          {!notifyEmail && resultUrl ? (
            <button type="button" className="cx-link cx-small" onClick={onCopy}>{copied ? 'Link copied' : 'copy the link'}</button>
          ) : null}
        </p>
        <p className="cx-faint">Nothing here invents a figure. Anything unproven is marked.</p>
      </div>
    </section>
  );
}
