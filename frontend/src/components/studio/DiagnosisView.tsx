/**
 * The reasoning, shown before the recommendation that rests on it.
 *
 * This is the only screen in the product where the client watches us think
 * rather than reads what we produced. So it shows the explanations we set
 * aside, not just the one we kept; it shows which of their own figures did
 * the work; and it shows what we could NOT establish.
 *
 * A diagnosis that hides its weaknesses is worth less than one that names
 * them — the client can act on "we could not verify this without your
 * booking export", and cannot act on false confidence.
 */
import type { StudioDiagnosis } from '../../api/consultant';

const VERDICT: Record<string, { label: string; tone: string }> = {
  supported: { label: 'Supported by your numbers', tone: 'text-emerald-700 bg-emerald-50 border-emerald-200' },
  refuted: { label: 'Ruled out', tone: 'text-slate-600 bg-slate-100 border-slate-200' },
  untestable: { label: 'Could not verify', tone: 'text-amber-700 bg-amber-50 border-amber-200' },
};

function Verdict({ verdict }: { verdict?: string | null }) {
  const v = VERDICT[verdict ?? ''] ?? VERDICT.untestable;
  return (
    <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${v.tone}`}>
      {v.label}
    </span>
  );
}

export default function DiagnosisView({ diagnosis }: { diagnosis: StudioDiagnosis }) {
  const { leading, considered, status, weaknesses, challenges } = diagnosis;
  const killed = challenges.filter((c) => c.kills);

  return (
    <div className="studio-panel p-6 sm:p-9">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
        What we think is actually wrong
      </p>

      <h2 className="mt-3 text-xl sm:text-2xl font-bold text-navy leading-snug">{leading.statement}</h2>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Verdict verdict={leading.verdict} />
        {leading.area ? (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            {leading.area}
          </span>
        ) : null}
        {leading.software_can_fix === false ? (
          <span className="rounded-full border border-slate-300 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            Software alone won't fix this
          </span>
        ) : null}
        {leading.from_owner ? (
          <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-600">
            This is what you told us
          </span>
        ) : null}
      </div>

      {leading.because ? <p className="mt-4 text-slate-700 leading-relaxed">{leading.because}</p> : null}

      {leading.cites.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            Resting on your own figures
          </p>
          <ul className="mt-2 space-y-1.5">
            {leading.cites.map((c) => (
              <li key={c.id} className="text-[0.95rem] text-slate-700">
                <span className="font-mono text-xs text-slate-400">{c.id}</span>{' '}
                <span className="font-semibold">{c.text}</span>
                {c.source ? <span className="text-slate-500"> — {c.source}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {leading.would_need ? (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm font-semibold text-amber-800">We could not verify this</p>
          <p className="mt-1 text-sm text-amber-900">{leading.would_need}</p>
        </div>
      ) : null}

      {considered.length > 0 ? (
        <div className="mt-7 border-t border-slate-200 pt-6">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            What else we considered
          </p>
          <ul className="mt-3 space-y-3">
            {considered.map((h, i) => (
              <li key={i}>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-slate-700">{h.statement}</span>
                  <Verdict verdict={h.verdict} />
                </div>
                {h.because ? <p className="mt-0.5 text-sm text-slate-500">{h.because}</p> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-7 border-t border-slate-200 pt-6">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
          What we did to try to break it
        </p>
        {status === 'unchallenged' ? (
          <p className="mt-2 text-sm text-slate-600">
            The review could not be run on this engagement. Nothing has tested this conclusion except
            the evidence above — read it with that in mind.
          </p>
        ) : (
          <>
            <p className="mt-2 text-sm text-slate-600">
              {killed.length > 0
                ? 'A reviewer found a hole in this. It is the best reading we have, not a settled fact.'
                : 'Two reviewers argued against this from different angles. Neither could bring it down.'}
            </p>
            <ul className="mt-3 space-y-2">
              {challenges.map((c, i) => (
                <li key={i} className="flex gap-2.5 text-sm">
                  <span
                    className={`mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full ${
                      c.kills ? 'bg-rose-500' : 'bg-emerald-500'
                    }`}
                  />
                  <span className="text-slate-600">
                    <span className="font-semibold text-slate-700">
                      {c.angle === 'confirmation' ? 'Are we just agreeing with you?' : 'Does something else explain it?'}
                    </span>{' '}
                    {c.because}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {weaknesses.length > 0 ? (
          <div className="mt-4 rounded-xl bg-slate-50 p-4">
            <p className="text-sm font-semibold text-slate-700">Worth knowing</p>
            <ul className="mt-1.5 space-y-1">
              {weaknesses.map((w, i) => (
                <li key={i} className="text-sm text-slate-600">
                  {w}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}
