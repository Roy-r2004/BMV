/**
 * Their file, turned into figures the diagnosis can cite.
 *
 * This sits at the gate rather than in the intake form on purpose. The
 * diagnosis has just told them, in its own words, what it could not verify —
 * "we would need to know whether those 320 sessions were booked or
 * completed". A drop zone underneath that sentence is a request they
 * understand the reason for. The same field on page six of a signup form is
 * one nobody fills.
 *
 * Every figure shown here was checked against the cell it was cited from.
 * Anything that did not check out was dropped before it reached this list,
 * and the count is shown — a client who sends a file deserves to know we
 * threw part of it away.
 */
import { useRef, useState } from 'react';

import type { StudioFigure } from '../../api/consultant';

const ICON = {
  upload: 'M12 16.5V9.75m0 0 3 3m-3-3-3 3M6.75 19.5a4.5 4.5 0 0 1-1.41-8.775 5.25 5.25 0 0 1 10.233-2.33 3 3 0 0 1 3.758 3.848A3.752 3.752 0 0 1 18 19.5H6.75Z',
  trash: 'M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.2v.917m7.5 0a48.667 48.667 0 00-7.5 0',
};

function Glyph({ path, className }: { path: string; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} className={className} aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

export default function EvidenceDrop({
  figures,
  wouldNeed,
  onUpload,
  onDelete,
  busy,
  note,
  error,
}: {
  figures: StudioFigure[];
  /** What the diagnosis said it could not establish. Names the ask. */
  wouldNeed: string | null;
  onUpload: (file: File) => void;
  onDelete: (id: string) => void;
  busy: boolean;
  /** e.g. "Read 6 figures — 2 we could not verify were dropped." */
  note: string | null;
  error: string | null;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const take = (files: FileList | null) => {
    if (files?.[0] && !busy) onUpload(files[0]);
  };

  return (
    <div className="studio-panel p-6 sm:p-8 mt-6">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
        Send us the numbers
      </p>
      <p className="mt-2 text-slate-700">
        {wouldNeed
          ? `We could not settle this from what you've told us. ${wouldNeed}`
          : 'A booking export, a P&L, a sales report — anything with real figures in it. We read it, and diagnose again with what it says.'}
      </p>

      <div
        className={`mt-4 rounded-2xl border-2 border-dashed p-7 text-center transition ${
          over ? 'border-blue-400 bg-blue-50/60' : 'border-slate-300'
        } ${busy ? 'opacity-60' : 'cursor-pointer hover:border-slate-400'}`}
        onClick={() => !busy && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          take(e.dataTransfer.files);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') input.current?.click();
        }}
      >
        <Glyph path={ICON.upload} className="mx-auto w-7 h-7 text-slate-400" />
        <p className="mt-2 font-semibold text-navy">
          {busy ? 'Reading your file…' : 'Drop a spreadsheet, CSV or PDF'}
        </p>
        <p className="mt-1 text-sm text-slate-500">
          {busy ? 'This takes a few seconds.' : 'Up to 8MB. We only read the figures.'}
        </p>
        <input
          ref={input}
          type="file"
          className="hidden"
          accept=".csv,.tsv,.txt,.xlsx,.xlsm,.pdf"
          onChange={(e) => take(e.target.files)}
        />
      </div>

      {error ? (
        <p className="mt-3 text-sm text-rose-600" role="alert">
          {error}
        </p>
      ) : null}
      {note ? <p className="mt-3 text-sm text-emerald-700">{note}</p> : null}

      {figures.length > 0 ? (
        <div className="mt-6">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">
            What we read from your files
          </p>
          <ul className="mt-3 divide-y divide-slate-200">
            {figures.map((f) => (
              <li key={f.id} className="flex items-start gap-3 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="text-slate-800">
                    <span className="font-semibold">
                      {f.value.toLocaleString()} {f.unit}
                    </span>
                    {f.time_basis && f.time_basis !== 'n/a' ? (
                      <span className="text-slate-500"> per {f.time_basis}</span>
                    ) : null}
                    {f.text ? <span className="text-slate-600"> — {f.text}</span> : null}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    <span className="font-mono">{f.id}</span> · {f.source}
                  </p>
                </div>
                <button
                  type="button"
                  className="shrink-0 rounded-lg p-2 text-slate-400 hover:bg-rose-50 hover:text-rose-600"
                  disabled={busy}
                  onClick={() => onDelete(f.id)}
                  aria-label={`Remove ${f.text || f.id}`}
                  title="We read this wrong — drop it"
                >
                  <Glyph path={ICON.trash} className="w-4 h-4" />
                </button>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-slate-500">
            Each one was checked against the cell it came from. If we read something wrong, drop
            it — nothing we conclude should rest on a figure you don't recognise.
          </p>
        </div>
      ) : null}
    </div>
  );
}
