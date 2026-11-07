/**
 * Fact-finding: one question at a time, with the data request filling in
 * beside it.
 *
 * The right-hand list is everything we need to write their plans, grouped the
 * way a consultant's data request is. Each answer ticks something off; a file
 * can tick off several at once; "I don't know" is a real answer that turns a
 * line amber, because we estimate it and mark it as ours everywhere it is used.
 * They never have to go and fetch anything.
 */
import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';

import type { CaseFigure, DiscoveryQuestion, Fact } from '../../api/consultant';
import { Tags } from './Fig';

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xlsm,.pdf';
const RING = 2 * Math.PI * 25;

function inHand(f: Fact): boolean {
  return f.status !== 'need';
}

/** Every figure in the case file is theirs: the tag and the sentence on where it
 *  came from are what the server sent, and the words are only used when it sent
 *  none (an older server). */
function caseTag(c: CaseFigure) {
  return { key: `${c.source_id ?? ''}|${c.value}|${c.token}`, info: { display: c.display ?? c.value, kind: c.kind ?? 'theirs', tag: c.tag ?? 'yours', source: c.source } };
}

function DataRequest({ facts, caseFigures }: { facts: Fact[]; caseFigures: CaseFigure[] }) {
  const prev = useRef<Map<string, string>>(new Map());
  const [flash, setFlash] = useState<Set<string>>(new Set());

  useEffect(() => {
    const changed = new Set<string>();
    const next = new Map<string, string>();
    for (const f of facts) {
      const sig = `${f.status}|${f.value}`;
      next.set(f.key, sig);
      const before = prev.current.get(f.key);
      // A row flashes when it changes, not when the list first appears.
      if (prev.current.size > 0 && before !== sig && f.status !== 'need') changed.add(f.key);
    }
    prev.current = next;
    if (!changed.size) return;
    setFlash(changed);
    const t = window.setTimeout(() => setFlash(new Set()), 1100);
    return () => window.clearTimeout(t);
  }, [facts]);

  const groups: { name: string; items: Fact[] }[] = [];
  for (const f of facts) {
    const name = f.group || 'Other';
    let g = groups.find((x) => x.name === name);
    if (!g) {
      g = { name, items: [] };
      groups.push(g);
    }
    g.items.push(f);
  }
  const total = facts.length;
  const n = facts.filter(inHand).length;
  const offset = total ? RING * (1 - n / total) : RING;

  return (
    <aside className="cx-pane cx-drl" aria-label="What we need to build your plans">
      <div className="cx-drl-head">
        <svg className="cx-ring" viewBox="0 0 60 60" aria-hidden="true">
          <defs>
            <linearGradient id="cx-rg" x1="0" x2="1">
              <stop offset="0" stopColor="#2563eb" />
              <stop offset="1" stopColor="#06b6d4" />
            </linearGradient>
          </defs>
          <circle className="bg" cx="30" cy="30" r="25" />
          <circle className="fg" cx="30" cy="30" r="25" strokeDasharray={RING.toFixed(1)} strokeDashoffset={offset.toFixed(1)} />
          <text x="30" y="35" textAnchor="middle" fontFamily="'Source Serif 4', Georgia, serif" fontWeight="600" fontSize="15" fill="#0b1736">{n}</text>
        </svg>
        <div>
          <h3>What we need to build your plans</h3>
          <p aria-live="polite">
            {total === 0 ? 'The list appears as we learn what matters.' : n === total ? `All ${total} in hand` : `${n} of ${total} in hand. ${total - n} still to go.`}
          </p>
        </div>
      </div>

      {groups.map((g) => (
        <div key={g.name} className="cx-group">
          <h4>{g.name}</h4>
          {g.items.map((f) => {
            const cls = f.status === 'got' || f.status === 'file' ? 'got' : f.status === 'estimate' ? 'est' : 'need';
            return (
              <div key={f.key} className={`cx-item ${cls}${flash.has(f.key) ? ' flash' : ''}`}>
                <span className="dot" aria-hidden="true" />
                <span className="n">
                  {f.label}
                  {f.status === 'file' ? <small style={{ display: 'block', fontSize: 11.5, color: 'var(--cx-txt3)' }}>From a file you sent</small> : null}
                </span>
                <span className="v">
                  {f.status === 'estimate' ? (
                    <>{f.value || "We'll estimate"}<small>our estimate</small></>
                  ) : f.status === 'file' ? (
                    <>{f.value}<small>yours</small></>
                  ) : f.status === 'got' ? (
                    <>{f.value}<small>yours</small></>
                  ) : null}
                </span>
              </div>
            );
          })}
        </div>
      ))}

      {caseFigures.length ? (
        <div className="cx-group">
          <h4>What we read in your answers</h4>
          {caseFigures.map((c) => {
            const t = caseTag(c);
            return (
              <div key={t.key} className="cx-item got" style={{ display: 'block' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8 }}>
                  <span className="n" style={{ minWidth: 0 }}>{c.label || c.token}</span>
                  <span className="v">{t.info.display}</span>
                </div>
                {c.source ? <Tags items={[t]} className="mt-1" /> : null}
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="cx-legend">
        <span><i style={{ background: '#0e9f6e' }} />Yours</span>
        <span><i style={{ background: '#fff1dc', border: '1.5px dashed #a85b00' }} />Our estimate</span>
        <span><i style={{ border: '1.5px solid #c3d2ee' }} />Still needed</span>
      </div>
    </aside>
  );
}

export default function Interview({
  question,
  facts,
  asked,
  loading,
  done,
  stalled,
  closing,
  lastHeard,
  onAnswer,
  onDontKnow,
  files,
  fileBusy,
  fileNote,
  onAddFiles,
  onFinish,
  finishError,
  submitting,
  caseFigures,
}: {
  question: DiscoveryQuestion | null;
  facts: Fact[];
  asked: number;
  loading: boolean;
  done: boolean;
  /** Set when the next question could not be got. Shown in its place, with the
   *  one thing the client can do: Continue, which asks again. */
  stalled: { message: string; onContinue: () => void } | null;
  closing: string;
  lastHeard: string | null;
  onAnswer: (value: string) => void;
  onDontKnow: () => void;
  files: File[];
  fileBusy: boolean;
  fileNote: string | null;
  onAddFiles: (f: File[]) => void;
  onFinish: () => void;
  finishError?: string | null;
  submitting?: boolean;
  /** What we have read in their answers so far (the case file's figures). Each says it
   *  is theirs and where it came from. Nothing is shown when there are none. */
  caseFigures?: CaseFigure[];
}) {
  const reduce = useReducedMotion();
  const [text, setText] = useState('');
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const toGo = facts.filter((f) => f.status === 'need').length;
  const fromYou = facts.filter((f) => f.status === 'got' || f.status === 'file').length;
  const estimates = facts.filter((f) => f.status === 'estimate').length;

  useEffect(() => {
    setText('');
    if (question) inputRef.current?.focus({ preventScroll: true });
  }, [question?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = () => {
    const v = text.trim();
    if (!v || loading) return;
    onAnswer(v);
    setText('');
  };

  const dropZone = (
    <div
      className={`cx-drop${dragging ? ' drag' : ''}${stalled ? ' off' : ''}`}
      onDragOver={(e) => {
        // Always prevented, or the browser opens a dropped file in this tab.
        e.preventDefault();
        if (!stalled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        const list = Array.from(e.dataTransfer.files ?? []);
        // A file read starts a round; none may start behind a stall.
        if (list.length && !stalled) onAddFiles(list);
      }}
    >
      <button type="button" onClick={() => fileRef.current?.click()} disabled={fileBusy || Boolean(stalled)}>
        {fileBusy ? (
          <>Reading your file<span className="cx-typing"><i /><i /><i /></span></>
        ) : (
          'Drop an export, a price list or a budget here, and we read the numbers ourselves'
        )}
      </button>
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          const list = Array.from(e.target.files ?? []);
          if (list.length) onAddFiles(list);
          e.target.value = '';
        }}
      />
      {fileNote ? (
        <small style={{ color: 'var(--cx-green)', fontWeight: 500 }} aria-live="polite">{fileNote}</small>
      ) : (
        <small>CSV, Excel or PDF, from any system. You can drop a file at any point.</small>
      )}
      {files.length ? (
        <div className="cx-files">
          {files.map((f, i) => (
            <span key={`${f.name}-${i}`} className="cx-chip cx-chip--blue">{f.name}</span>
          ))}
        </div>
      ) : null}
    </div>
  );

  return (
    <section className="cx-stage">
      <p className="cx-kicker">Fact-finding</p>
      <h1 className="cx-title">We keep asking until we have everything we need to build.</h1>
      <p className="cx-lede">
        One question at a time, each one depending on what you've already said. If you don't know, say so: we estimate it
        and mark it everywhere it's used.
      </p>

      <div className="cx-ff">
        <div className="cx-pane cx-ask">
          <AnimatePresence mode="wait" initial={false}>
            {stalled ? (
              <motion.div key="stalled" className="cx-stalled" role="alert" initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <p className="cx-ask-meta"><span>Question {asked + 1}</span></p>
                <p className="cx-stalled-msg">{stalled.message}</p>
                <div className="cx-row">
                  <button type="button" className="cx-btn cx-btn--blue" onClick={stalled.onContinue} autoFocus>Continue</button>
                </div>
              </motion.div>
            ) : done ? (
              <motion.div key="done" className="cx-done" initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                <p className="cx-ask-meta"><span>Fact-finding complete</span></p>
                <h2 style={{ marginTop: 18 }}>That's everything we need to build your plans.</h2>
                <p className="cx-why" style={{ fontSize: 15, color: 'var(--cx-txt2)' }}>
                  {closing || "Nothing for you to go and fetch. Where you didn't know, we estimated, and every plan says so."}
                </p>
                <div className="cx-sum">
                  <div><b>{asked}</b>questions asked</div>
                  <div><b>{fromYou}</b>facts from you</div>
                  <div><b>{estimates}</b>our estimates, marked</div>
                </div>
                {finishError ? <p className="cx-error" role="alert" style={{ marginTop: 16 }}>{finishError}</p> : null}
                <div className="cx-row" style={{ marginTop: 24 }}>
                  <button type="button" className="cx-btn cx-btn--blue" onClick={onFinish} disabled={submitting}>
                    {submitting ? 'Starting…' : 'Start the analysis'}
                  </button>
                </div>
              </motion.div>
            ) : loading || !question ? (
              <motion.div key="loading" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }}>
                <p className="cx-ask-meta">
                  <span>Question {asked + 1}</span>
                  <span><b>{toGo}</b> {toGo === 1 ? 'fact' : 'facts'} still to go</span>
                </p>
                <p className="cx-lead" style={{ marginTop: 18 }}>
                  {asked === 0 ? 'Reading your brief' : 'Reading your answer'}
                  <span className="cx-typing"><i /><i /><i /></span>
                </p>
                <div style={{ display: 'grid', gap: 10, marginTop: 18 }}>
                  <div className="cx-skel" style={{ width: '80%', height: 18 }} />
                  <div className="cx-skel" style={{ width: '55%', height: 18 }} />
                </div>
                {lastHeard ? <p className="cx-heard">{lastHeard}</p> : null}
              </motion.div>
            ) : (
              <motion.div
                key={question.id}
                initial={reduce ? false : { opacity: 0, y: 14 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? undefined : { opacity: 0, y: -8 }}
                transition={{ duration: 0.3 }}
              >
                <p className="cx-ask-meta">
                  <span>Question {asked + 1}</span>
                  <span><b>{toGo}</b> {toGo === 1 ? 'fact' : 'facts'} still to go</span>
                </p>
                <h2>{question.label}</h2>
                {question.why ? <p className="cx-why">{question.why}</p> : null}

                <div className="cx-opts">
                  {(question.options ?? []).map((o) => (
                    <button key={o} type="button" className="cx-opt" onClick={() => onAnswer(o)} disabled={loading}>
                      {o}
                    </button>
                  ))}
                  <button type="button" className="cx-opt est" onClick={onDontKnow} disabled={loading}>
                    I don't know, estimate it for us
                  </button>
                </div>

                <form
                  className="cx-type"
                  onSubmit={(e) => {
                    e.preventDefault();
                    submit();
                  }}
                >
                  <input
                    ref={inputRef}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Or say it in your own words"
                    aria-label={question.label}
                  />
                  <button type="submit" className="cx-btn cx-btn--ghost" disabled={!text.trim()}>Answer</button>
                </form>
                <p className="cx-heard" aria-live="polite">{lastHeard ?? ''}</p>
              </motion.div>
            )}
          </AnimatePresence>

          {done ? null : dropZone}
        </div>

        <DataRequest facts={facts} caseFigures={caseFigures ?? []} />
      </div>
    </section>
  );
}
