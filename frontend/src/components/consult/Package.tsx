/**
 * The package: theirs to keep.
 *
 * It opens with Monday, not with the documents. What they can do this week,
 * before any software exists, is the part of the engagement they will use
 * first — and the part most consultancies bury on page forty. The documents
 * sit beside it, the screens below, then the pilot tracker, and last the
 * honest box: what the documents still assume, stated rather than left in the
 * fine print.
 *
 * Also the plan-only package, for a client who took the answer and not the
 * build: the same page without the build's documents, and the build one click
 * away.
 */
import { useState } from 'react';

import type { ActionPlan, CapacityPicture, PilotEntry, StudioAnswer, StudioExportKind } from '../../api/consultant';
import Tracker from './Tracker';
import { shortName } from '../../utils/names';

export interface PackageScreen {
  label: string;
  src: string;
  full: string;
}

function Thumb() {
  return (
    <span className="cx-thumb" aria-hidden="true">
      <i /><i /><i /><i /><i /><i />
    </span>
  );
}

function DocRow({ title, note, kind, primary, onDownload }: {
  title: string;
  note: string;
  kind: StudioExportKind;
  primary?: boolean;
  onDownload: (k: StudioExportKind) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <div className="cx-doc-row">
      <Thumb />
      <div className="min-w-0">
        <b className="block text-[17px] font-semibold">{title}</b>
        <span className="cx-muted text-[14.5px]">{failed ? 'The download could not start. Try again in a moment.' : note}</span>
      </div>
      <button
        type="button"
        className={`cx-btn cx-btn--sm ${primary ? 'cx-btn--blue' : 'cx-btn--ghost'}`}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setFailed(false);
          try {
            await onDownload(kind);
          } catch {
            setFailed(true);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? 'Preparing…' : 'Download'}
      </button>
    </div>
  );
}

function ShareButton({ onShare, onUnshare }: { onShare: () => Promise<string>; onUnshare: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="relative">
      <button
        type="button"
        className="cx-btn cx-btn--ghost"
        disabled={busy}
        aria-expanded={open}
        onClick={async () => {
          if (open) {
            setOpen(false);
            return;
          }
          setBusy(true);
          setError(null);
          try {
            setUrl(await onShare());
            setOpen(true);
          } catch {
            setError('The link could not be made just now.');
          } finally {
            setBusy(false);
          }
        }}
      >
        Share with a partner
      </button>
      {error ? <p className="cx-error mt-2 text-right text-[13.5px]">{error}</p> : null}
      {open && url ? (
        <div className="cx-card absolute right-0 z-20 mt-3 w-[min(440px,86vw)] p-5">
          <p className="font-semibold">A read-only link to this package</p>
          <p className="cx-muted mt-1 text-[14.5px]">They can read and download everything. They can't change anything or log your pilot.</p>
          <div className="mt-4 flex gap-2">
            <input className="cx-input h-10 flex-1 text-[14px]" readOnly value={url} onFocus={(e) => e.target.select()} aria-label="Share link" />
            <button
              type="button"
              className="cx-btn cx-btn--blue cx-btn--sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(url);
                  setCopied(true);
                  setTimeout(() => setCopied(false), 2200);
                } catch {
                  /* the link is selectable on screen */
                }
              }}
            >
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <button
            type="button"
            className="cx-link cx-small mt-4"
            onClick={async () => {
              await onUnshare();
              setOpen(false);
              setUrl(null);
            }}
          >
            Turn this link off
          </button>
        </div>
      ) : null}
    </div>
  );
}

function CopyMessage({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="cx-btn cx-btn--ghost cx-btn--sm"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2200);
        } catch {
          /* selectable on screen */
        }
      }}
    >
      {copied ? 'Copied' : 'Copy the message'}
    </button>
  );
}

const WORDS = ['No', 'One thing', 'Two things', 'Three things', 'Four things', 'Five things', 'Six things'];

export default function Package({
  mode,
  businessName,
  answer,
  fallbackFinding,
  capacity,
  plan,
  log,
  unverified,
  screens,
  docs,
  onDownload,
  onShare,
  onUnshare,
  canEdit,
  onSaveWeek,
  onRetryPlan,
  onBuild,
  onOpenScreen,
  readOnly,
}: {
  mode: 'full' | 'plan';
  businessName: string;
  answer: StudioAnswer | null;
  fallbackFinding: string | null;
  capacity: CapacityPicture | null;
  plan: ActionPlan | null;
  log: PilotEntry[];
  unverified: string[];
  screens: PackageScreen[];
  docs: { blueprint: boolean; technical: boolean; operations: boolean };
  onDownload: (k: StudioExportKind) => Promise<void>;
  onShare?: () => Promise<string>;
  onUnshare?: () => Promise<void>;
  canEdit: boolean;
  onSaveWeek?: (week: number, values: Record<string, number>, note: string) => Promise<void>;
  onRetryPlan?: () => void;
  onBuild?: () => void;
  onOpenScreen?: (s: PackageScreen) => void;
  readOnly?: boolean;
}) {
  const [showAssumptions, setShowAssumptions] = useState(false);
  const short = shortName(businessName);
  const finding = answer ? [answer.headline, answer.turn].filter(Boolean).join(' ') : fallbackFinding;
  const ready = plan?.status === 'ready';
  // No plan at all is 'being written' only on the plan-only page, where
  // taking the answer starts one. On a package built before plans existed it
  // means there is none yet, and they can ask for it.
  const writing = plan ? plan.status === 'writing' : mode === 'plan';
  const assumptions = Array.from(new Set([...(plan?.assumptions ?? []), ...unverified].map((s) => s.trim()).filter(Boolean)));
  const title =
    mode === 'plan'
      ? ready ? `${short}'s plan is ready.` : `Writing ${short}'s plan.`
      : `${short}'s package is ready.`;

  return (
    <section className="pt-8">
      <div className="flex flex-wrap items-end justify-between gap-8">
        <div className="min-w-0 max-w-[62ch]">
          <h1 className="cx-h2">{title}</h1>
          {finding ? (
            <p className="cx-lead mt-5">
              {mode === 'full' ? 'Built around your answer: ' : 'Your answer: '}
              {finding}
              {mode === 'plan' ? ' Start with the steps below — none of them needs software.' : ''}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-3">
          {!readOnly && onShare && onUnshare ? <ShareButton onShare={onShare} onUnshare={onUnshare} /> : null}
          {mode === 'full' ? (
            <button type="button" className="cx-btn cx-btn--blue" onClick={() => void onDownload('zip').catch(() => undefined)}>
              Download everything
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-10 grid gap-8 lg:grid-cols-[1.12fr_1fr]">
        <section className="cx-tint p-8 sm:p-9">
          <h2 className="cx-h3" style={{ fontSize: "clamp(24px, 2.2vw, 32px)" }}>Start here on Monday</h2>
          <p className="cx-muted mt-2">None of these needs the software to be built first.</p>
          {ready ? (
            <ol className="mt-6">
              {(plan?.monday ?? []).map((s, i) => (
                <li key={i} className="grid grid-cols-[44px_1fr] gap-3 border-t border-[rgba(37,99,235,0.2)] py-5">
                  <span className="cx-step-n">{i + 1}</span>
                  <div>
                    <b className="block text-[18px] font-semibold leading-snug">{s.do}</b>
                    {s.why ? <span className="cx-muted mt-1 block text-[15px]">{s.why}</span> : null}
                  </div>
                </li>
              ))}
            </ol>
          ) : writing ? (
            <div className="mt-6 space-y-5" aria-live="polite">
              <p className="cx-muted">Writing your plan — about half a minute<span className="cx-typing"><i /><i /><i /></span></p>
              {[0, 1, 2].map((i) => (
                <div key={i} className="grid grid-cols-[44px_1fr] gap-3">
                  <span className="cx-step-n opacity-40">{i + 1}</span>
                  <div className="space-y-2 pt-2"><div className="cx-skel w-11/12" /><div className="cx-skel w-6/12" /></div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-6">
              <p>
                {plan
                  ? "We couldn't write the plan just now."
                  : 'We can write what you can start on Monday from your answer. About half a minute.'}
              </p>
              {onRetryPlan && !readOnly ? (
                <button type="button" className="cx-btn cx-btn--blue cx-btn--sm mt-4" onClick={onRetryPlan}>
                  {plan ? 'Try again' : 'Write my Monday plan'}
                </button>
              ) : null}
            </div>
          )}
        </section>

        <section className="cx-card p-8">
          <h2 className="cx-h3">Your documents</h2>
          <div className="mt-4">
            {ready ? (
              <DocRow title={plan?.title || 'Your plan'} note={`${plan?.weeks ?? 6} weeks, ${plan?.message ? 'the message, ' : ''}the tracking sheet`} kind="pilot" primary onDownload={onDownload} />
            ) : null}
            {mode === 'full' && docs.blueprint ? (
              <DocRow title="Blueprint" note="What to build, in what order, and what it's worth" kind="blueprint" onDownload={onDownload} />
            ) : null}
            {mode === 'full' && docs.technical ? (
              <DocRow title="Technical plan" note="For whoever builds it" kind="technical" onDownload={onDownload} />
            ) : null}
            {mode === 'full' && docs.operations ? (
              <DocRow title="Operations manual" note="Who does what, every day" kind="operations" onDownload={onDownload} />
            ) : null}
          </div>
          {mode === 'plan' && onBuild && !readOnly ? (
            <div className="mt-6 border-t border-[var(--cx-line)] pt-6">
              <p className="font-semibold">Want the system too?</p>
              <p className="cx-muted mt-1 text-[15px]">
                The blueprint, technical plan, operations manual and product screens, built around this answer. About ten minutes.
              </p>
              <button type="button" className="cx-btn cx-btn--ghost cx-btn--sm mt-4" onClick={onBuild}>Build the system too</button>
            </div>
          ) : null}
        </section>
      </div>

      {ready && (plan?.schedule?.length || plan?.message) ? (
        <div className="mt-8 grid gap-8 lg:grid-cols-2">
          {plan?.schedule?.length ? (
            <section className="cx-card p-8">
              <h2 className="cx-h3">Week by week</h2>
              <ol className="mt-4">
                {plan.schedule.map((r, i) => (
                  <li key={i} className="grid grid-cols-[110px_1fr] gap-4 border-t border-[var(--cx-line)] py-3 first:border-t-0">
                    <b className="text-[15px] font-semibold text-[var(--cx-blue)]">{r.when}</b>
                    <span className="text-[15.5px]">{r.do}</span>
                  </li>
                ))}
              </ol>
            </section>
          ) : null}
          {plan?.message ? (
            <section className="cx-card p-8">
              <div className="flex flex-wrap items-baseline justify-between gap-3">
                <h2 className="cx-h3">The message, ready to send</h2>
                <CopyMessage text={plan.message.text} />
              </div>
              <p className="cx-faint mt-1 text-[14.5px]">To {plan.message.to}</p>
              <p className="mt-4 whitespace-pre-line rounded-2xl bg-[#f5f8ff] p-5 text-[16px] leading-relaxed">{plan.message.text}</p>
            </section>
          ) : null}
        </div>
      ) : null}

      {mode === 'full' && screens.length > 0 ? (
        <>
          <div className="mt-14 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="cx-h3" style={{ fontSize: "clamp(24px, 2.2vw, 32px)" }}>Your product screens</h2>
            <p className="cx-faint text-[15px]">Drawn for {short}, each checked twice before it reached you.</p>
          </div>
          <div className="mt-6 grid gap-7 md:grid-cols-2 xl:grid-cols-3">
            {screens.slice(0, 6).map((s) => (
              <figure key={s.full}>
                <button type="button" className="cx-shot" onClick={() => onOpenScreen?.(s)} aria-label={`Enlarge ${s.label}`}>
                  <img src={s.src} alt={`${s.label} screen`} loading="lazy" />
                </button>
                <figcaption className="mt-3 font-semibold">{s.label}</figcaption>
              </figure>
            ))}
          </div>
        </>
      ) : null}

      {ready && plan?.measures?.length ? (
        <div className="mt-14">
          <Tracker plan={plan} log={log} capacity={capacity} canEdit={canEdit && !readOnly} onSave={onSaveWeek} />
        </div>
      ) : null}

      {assumptions.length ? (
        <div className="cx-tint mt-14 p-6 sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-6">
            <p className="max-w-[80ch] text-[16.5px] cx-muted">
              <b className="text-[var(--cx-txt)]">
                {WORDS[Math.min(assumptions.length, 6)] ?? `${assumptions.length} things`} in {mode === 'full' ? 'these documents are' : 'this plan are'} still assumptions.
              </b>{' '}
              {ready ? 'The pilot is how you settle them.' : 'Nothing here treats them as settled.'}
            </p>
            <button type="button" className="cx-btn cx-btn--ghost" onClick={() => setShowAssumptions((v) => !v)} aria-expanded={showAssumptions}>
              {showAssumptions ? 'Hide them' : 'See what they are'}
            </button>
          </div>
          {showAssumptions ? (
            <ul className="mt-5 space-y-2">
              {assumptions.map((a) => (
                <li key={a} className="text-[15.5px]">• {a}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
