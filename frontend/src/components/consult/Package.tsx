/**
 * Your plans: everything needed to build it, theirs to keep.
 *
 * A shelf of documents first (only the ones that exist), then how it gets
 * done — the implementation roadmap, with who does each phase — beside the
 * few calls only the owner can make. We do the work; they make the calls.
 * Last, the screens and the honest box: what we estimated, marked in every
 * plan rather than left in the fine print.
 */
import { useState } from 'react';

import type { DecisionState, FigureMap, Roadmap, StudioAnswer, StudioExportKind, SystemPayload } from '../../api/consultant';
import { shortName } from '../../utils/names';
import { FigTags, Segments } from './Fig';
import SystemViewer from './SystemViewer';

export interface PackageScreen {
  label: string;
  src: string;
  full: string;
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
          <p className="font-semibold">A read-only link to your plans</p>
          <p className="cx-muted mt-1 text-[14.5px]">They can read and download everything. They can't change anything or make the calls.</p>
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

type BookAction = { label: string; run: () => Promise<void> | void };

function Book({ cover, title, body, action, extra, meta }: {
  cover: string;
  title: string;
  body: string;
  action?: BookAction;
  /** A second way to take it — the document row's own download, beside View. */
  extra?: BookAction;
  meta?: string;
}) {
  // The label of the action that is running, so only that one says so.
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const run = (a: BookAction) => async () => {
    setBusy(a.label);
    setFailed(false);
    try {
      await a.run();
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };
  const button = (a: BookAction) => (
    <button type="button" disabled={busy !== null} onClick={run(a)}>
      {busy === a.label ? 'Preparing…' : a.label}
    </button>
  );
  return (
    <div className="cx-pane cx-book">
      <div className={`cx-cover ${cover}`} aria-hidden="true" />
      <div className="min-w-0">
        <h3>{title}</h3>
        <p>{failed ? 'We could not start the download. Press the button again when you are ready.' : body}</p>
        {action || extra || meta ? (
          <div className="meta">
            {action ? button(action) : null}
            {extra ? button(extra) : null}
            {meta ? <span>{meta}</span> : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export default function Package({
  businessName,
  answer,
  fallbackFinding,
  roadmap,
  figures,
  decisions,
  unverified,
  screens,
  system,
  docs,
  stats,
  onDownload,
  onShare,
  onUnshare,
  onChoose,
  onGoAhead,
  onRetryRoadmap,
  onOpenScreen,
  readOnly,
}: {
  businessName: string;
  answer: StudioAnswer | null;
  fallbackFinding: string | null;
  roadmap: Roadmap | null;
  /** The figures the answer and the roadmap name: whose each is, and where from.
   *  Absent on an older payload, which is then shown without tags. */
  figures?: FigureMap | null;
  decisions: DecisionState;
  unverified: string[];
  /** The PNG screens of older runs. Shown only when there is no system. */
  screens: PackageScreen[];
  /** The navigable system. Replaces the screens when it is available. */
  system?: SystemPayload | null;
  docs: { blueprint: boolean; technical: boolean; operations: boolean };
  stats?: { modules?: number; agents?: number; screens?: number };
  onDownload: (k: StudioExportKind) => Promise<void>;
  onShare?: () => Promise<string>;
  onUnshare?: () => Promise<void>;
  onChoose?: (id: string, option: string) => void;
  onGoAhead?: () => Promise<void>;
  onRetryRoadmap?: () => void;
  onOpenScreen?: (s: PackageScreen) => void;
  readOnly?: boolean;
}) {
  const [going, setGoing] = useState(false);
  const [goError, setGoError] = useState<string | null>(null);
  const [zipBusy, setZipBusy] = useState(false);
  const [showAssumptions, setShowAssumptions] = useState(false);

  const short = shortName(businessName);
  const finding = answer ? [answer.headline, answer.turn].filter(Boolean).join(' ') : fallbackFinding;
  const phases = roadmap?.phases ?? [];
  const calls = roadmap?.decisions ?? [];
  const choices = decisions.choices ?? {};
  const ready = roadmap?.status === 'ready';
  const writingRoadmap = roadmap?.status === 'writing';
  const failedRoadmap = roadmap?.status === 'failed';
  const assumptions = Array.from(
    new Set([...(roadmap?.assumptions ?? []), ...unverified].map((s) => s.trim()).filter(Boolean)),
  );
  const screenCount = stats?.screens ?? screens.length;
  const agents = stats?.agents ?? 0;
  // The system, when this run has one. Legacy runs fall back to their PNGs.
  const sys = system?.available && system.html && system.screens.length ? system : null;

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });

  const goAhead = async () => {
    if (!onGoAhead) return;
    setGoing(true);
    setGoError(null);
    try {
      await onGoAhead();
    } catch {
      setGoError('We could not send your go-ahead just now. Your choices are still on this page; press the button again when you are ready.');
    } finally {
      setGoing(false);
    }
  };

  const downloadAll = async () => {
    setZipBusy(true);
    try {
      await onDownload('zip');
    } catch {
      /* the individual downloads remain */
    } finally {
      setZipBusy(false);
    }
  };

  return (
    <section className="cx-stage">
      <p className="cx-kicker">Your plans</p>
      <div className="cx-plans-head">
        <div className="min-w-0" style={{ maxWidth: '46em' }}>
          <h1 className="cx-title">Everything needed to build it. Written for {short}.</h1>
          <p className="cx-lede">
            {finding ? (
              <>
                Built around the answer:{' '}
                {answer ? (
                  <>
                    <Segments segments={answer.headline_segments} text={answer.headline} figures={figures} />
                    {answer.turn ? <>{' '}<Segments segments={answer.turn_segments} text={answer.turn} figures={figures} /></> : null}
                  </>
                ) : (
                  finding
                )}{' '}
              </>
            ) : null}
            Every figure in these plans is one you gave us, arithmetic on those figures, or an estimate marked as ours.
          </p>
        </div>
        {!readOnly && onShare && onUnshare ? <ShareButton onShare={onShare} onUnshare={onUnshare} /> : null}
      </div>

      <div className="cx-shelf">
        {docs.blueprint ? (
          <Book
            cover=""
            title="The blueprint"
            body="The decision, the financial case, every module, the org chart, the scoreboard, and what could make it fail."
            action={{ label: 'Download', run: () => onDownload('blueprint') }}
            meta={stats?.modules ? plural(stats.modules, 'module', 'modules') : undefined}
          />
        ) : null}
        {docs.technical ? (
          <Book
            cover="c2"
            title="The technical plan"
            body="How the system works, the data model, each AI agent's tools and guardrails, the APIs, security and build order."
            action={{ label: 'Download', run: () => onDownload('technical') }}
          />
        ) : null}
        {docs.operations ? (
          <Book
            cover="c3"
            title="The operations manual"
            body="How the work runs, day to day, once it's live: routines, checklists and who does what."
            action={{ label: 'Download', run: () => onDownload('operations') }}
          />
        ) : null}
        {sys ? (
          <Book
            cover="c4"
            title="Your system, screen by screen"
            body={`Every screen your team and customers will use, drawn for ${short}. Navigate it here, or take the PDF.`}
            action={{ label: 'View', run: () => scrollTo('cx-system') }}
            extra={sys.pdf_available ? { label: 'Download as PDF', run: () => onDownload('system') } : undefined}
            meta={plural(sys.screens.length, 'screen', 'screens')}
          />
        ) : screens.length ? (
          <Book
            cover="c4"
            title="Your product screens"
            body={`The screens your team and customers will use, drawn for ${short}.`}
            action={{ label: 'View', run: () => scrollTo('cx-screens') }}
            meta={plural(screenCount, 'screen', 'screens')}
          />
        ) : null}
        {agents > 0 ? (
          <Book
            cover="c5"
            title="Your AI team"
            body="What each agent decides alone, and where it hands over to a person. In the blueprint."
            action={docs.blueprint ? { label: 'Read', run: () => onDownload('blueprint') } : undefined}
            meta={plural(agents, 'agent', 'agents')}
          />
        ) : null}
        {ready && phases.length ? (
          <Book
            cover="c6"
            title="The implementation roadmap"
            body="Who does what, phase by phase, from go-ahead to running on the new system."
            action={{ label: 'Read', run: () => scrollTo('cx-roadmap') }}
            meta={plural(phases.length, 'phase', 'phases')}
          />
        ) : null}
      </div>

      <div className="cx-plan-grid">
        <div className="cx-pane cx-road" id="cx-roadmap">
          <h3>{roadmap?.title || 'How it gets done'}</h3>
          <p>{roadmap?.summary || 'We do the work. You make the calls.'}</p>
          {ready && phases.length ? <FigTags ids={['PLAN-WEEKS']} figures={figures} lead="Length of the plan" labelled /> : null}
          {ready && phases.length ? (
            <ol className="cx-phases">
              {phases.map((ph, i) => (
                <li key={`${ph.when}-${i}`} className="cx-phase">
                  <span className="when">{ph.when}</span>
                  <div>
                    <h4>{ph.title}</h4>
                    <p>{ph.do}</p>
                    <div className="who">
                      <span className="cx-chip cx-chip--blue">{ph.by === 'together' ? 'Together' : 'We do it'}</span>
                      {ph.you ? <span className="cx-chip cx-chip--dim">You: {ph.you}</span> : null}
                      <FigTags ids={[`PLAN-PHASE-${i + 1}-WEEKS`]} figures={figures} labelled className="" />
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : writingRoadmap || !roadmap ? (
            <div className="cx-phases" aria-live="polite">
              <p className="cx-muted" style={{ fontSize: 14.5 }}>
                Writing your roadmap<span className="cx-typing"><i /><i /><i /></span>
              </p>
              {[0, 1, 2].map((i) => (
                <div key={i} className="cx-phase">
                  <div className="cx-skel" style={{ width: '70%' }} />
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div className="cx-skel" style={{ width: '60%' }} />
                    <div className="cx-skel" style={{ width: '90%' }} />
                  </div>
                </div>
              ))}
            </div>
          ) : failedRoadmap || (ready && !phases.length) ? (
            <div className="cx-phases">
              <p style={{ fontSize: 15 }}>We couldn't write the roadmap just now. Everything else is ready.</p>
              {onRetryRoadmap && !readOnly ? (
                <button type="button" className="cx-btn cx-btn--blue cx-btn--sm" style={{ marginTop: 14 }} onClick={onRetryRoadmap}>
                  Write it again
                </button>
              ) : null}
            </div>
          ) : null}
        </div>

        <div className="cx-pane cx-decide">
          <h3>Only you can decide</h3>
          <p>
            {calls.length
              ? `${calls.length === 1 ? 'One call' : `${calls.length} calls`}. No homework.`
              : ready ? 'Nothing to decide yet. No homework.' : 'Your calls appear with the roadmap.'}
          </p>
          {calls.map((c) => {
            const picked = choices[c.id];
            return (
              <div key={c.id} className={`cx-dec${picked ? ' ok' : ''}`}>
                <h4>{c.question}</h4>
                {c.detail ? <p>{c.detail}</p> : null}
                <div className="cx-opts" role="radiogroup" aria-label={c.question}>
                  {c.options.map((o) => (
                    <button
                      key={o}
                      type="button"
                      role="radio"
                      aria-checked={picked === o}
                      className={`cx-opt${picked === o ? ' sel' : ''}`}
                      disabled={readOnly || !onChoose || Boolean(decisions.go_ahead)}
                      onClick={() => onChoose?.(c.id, o)}
                    >
                      {o}
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          <div className="cx-final">
            {decisions.go_ahead ? (
              <p className="cx-gotit" role="status">We've got it. We'll be in touch within one working day.</p>
            ) : !readOnly && onGoAhead ? (
              <button type="button" className="cx-btn cx-btn--blue" onClick={goAhead} disabled={going}>
                {going ? 'Sending…' : 'Have us build it'}
              </button>
            ) : null}
            {goError ? <p className="cx-error" role="alert">{goError}</p> : null}
            {docs.blueprint || docs.technical || docs.operations ? (
              <button type="button" className="cx-btn cx-btn--ghost" onClick={downloadAll} disabled={zipBusy}>
                {zipBusy ? 'Preparing…' : 'Download everything'}
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {sys ? (
        <div id="cx-system" style={{ scrollMarginTop: 20 }}>
          <div className="mt-14 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="cx-h3" style={{ fontSize: 'clamp(22px, 2vw, 28px)' }}>Your system, screen by screen</h2>
            <p className="cx-faint text-[15px]">Drawn for {short}, with sample data. Click the sidebar inside it, or pick a screen from the list.</p>
          </div>
          <SystemViewer system={sys} businessName={businessName} readOnly={readOnly} onDownloadPdf={() => onDownload('system')} />
        </div>
      ) : screens.length ? (
        <div id="cx-screens" style={{ scrollMarginTop: 20 }}>
          <div className="mt-14 flex flex-wrap items-baseline justify-between gap-3">
            <h2 className="cx-h3" style={{ fontSize: 'clamp(22px, 2vw, 28px)' }}>Your product screens</h2>
            <p className="cx-faint text-[15px]">Drawn for {short}, with sample data.</p>
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
        </div>
      ) : null}

      {assumptions.length ? (
        <div className="cx-assume">
          <div className="cx-row" style={{ justifyContent: 'space-between' }}>
            <p style={{ margin: 0 }}>
              <b>We estimated {plural(assumptions.length, 'thing', 'things')}.</b> Each is marked in every plan.
            </p>
            <button type="button" className="cx-link cx-small" onClick={() => setShowAssumptions((v) => !v)} aria-expanded={showAssumptions}>
              {showAssumptions ? 'Hide them' : 'See what they are'}
            </button>
          </div>
          {showAssumptions ? (
            <ul>
              {assumptions.map((a) => (
                <li key={a}>• {a}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
