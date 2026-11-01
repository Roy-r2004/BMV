/**
 * A figure, whose it is, and where it came from.
 *
 * Every number on the answer and the plans is one of four kinds: yours, worked
 * out from yours, our estimate, or a published reference. The server says which
 * (the payload's `figures` map: how it prints, its kind, the tag word and one
 * plain sentence on where it came from), and this file only draws it.
 *
 * The tag is a button. Pressing it opens the source sentence right below the
 * figure, in place, and pressing it again closes it. It is a real button
 * (keyboard: Enter and Space open it, Escape closes it; `aria-expanded` says
 * which) and its touch area is wider than the pill, so it works with one thumb
 * on a phone. Nothing here depends on hovering.
 *
 * A payload from before figures had tags has no map and no segments; every
 * export here then draws plain text and nothing else.
 */
import { Fragment, useId, useState, type ReactNode } from 'react';

import type { FigureJson, FigureKind, FigureMap, FigureSegment } from '../../api/consultant';

// The tag's colours are the ones the data request's legend already uses: green
// for what they told us, amber and dashed for what we estimated.
const CHIP: Record<FigureKind, string> = {
  theirs: 'cx-chip--green',
  derived: 'cx-chip--blue',
  ours: 'cx-chip--amber',
  reference: 'cx-chip--dim',
};

// Inline styles, because the answer's heading restyles every span inside it and
// the data request restyles every small: these must hold wherever they land.
const BODY = { fontFamily: 'var(--cx-body)', letterSpacing: 0, textTransform: 'none' } as const;

function TagButton({ info, label, open, controls, onToggle }: {
  info: FigureJson;
  label: string;
  open: boolean;
  controls: string;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className={`cx-chip ${CHIP[info.kind] ?? 'cx-chip--dim'} relative cursor-pointer gap-1 align-middle before:absolute before:-inset-2 before:content-[''] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2563eb]`}
      style={{
        ...BODY,
        display: 'inline-flex',
        height: 22,
        minHeight: 22,
        padding: '0 8px',
        marginLeft: 4,
        fontSize: 11.5,
        lineHeight: 1,
        whiteSpace: 'nowrap',
        border: info.kind === 'ours' ? '1px dashed var(--cx-amber)' : '1px solid transparent',
      }}
      aria-expanded={open}
      aria-controls={open ? controls : undefined}
      aria-label={`${label}: where this comes from`}
      onClick={onToggle}
      onKeyDown={(e) => {
        if (e.key === 'Escape' && open) {
          e.stopPropagation();
          onToggle();
        }
      }}
    >
      {label}
      <svg
        width="8"
        height="8"
        viewBox="0 0 8 8"
        aria-hidden="true"
        style={{ flex: 'none', transform: open ? 'rotate(180deg)' : undefined, transition: 'transform 0.15s' }}
      >
        <path d="M1 2.5 4 5.5 7 2.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  );
}

/** The sentence that says where a figure came from, opened under it. */
function Source({ id, info, lead }: { id: string; info: FigureJson; lead?: string }) {
  return (
    <span
      id={id}
      role="note"
      style={{
        ...BODY,
        display: 'block',
        margin: '6px 0 2px',
        padding: '8px 12px',
        borderRadius: 10,
        background: '#fff',
        border: '1px solid var(--cx-line)',
        color: 'var(--cx-txt2)',
        font: '400 13px/1.4 var(--cx-body)',
        whiteSpace: 'normal',
      }}
    >
      {lead ? <b style={{ fontWeight: 600, color: 'var(--cx-txt)' }}>{lead} </b> : null}
      {info.source}
    </span>
  );
}

/** A figure inside a sentence: its text, its tag, and its source below when the
 *  tag is pressed. With no entry in the map it is only its text. */
export default function Fig({ id, text, figures }: { id: string; text: string; figures?: FigureMap | null }) {
  const info = figures?.[id];
  const [open, setOpen] = useState(false);
  const panel = useId();
  if (!info) return <>{text}</>;
  return (
    <>
      <span style={{ display: 'inline', color: 'inherit', whiteSpace: 'nowrap' }}>
        {text}
        <TagButton info={info} label={info.tag} open={open} controls={panel} onToggle={() => setOpen((v) => !v)} />
      </span>
      {open ? <Source id={panel} info={info} /> : null}
    </>
  );
}

/** Prose in the pieces the server sent: plain text, and a Fig for each bound
 *  number. With no pieces (an older payload) it is the plain text. */
export function Segments({ segments, text, figures }: {
  segments?: FigureSegment[] | null;
  text: string;
  figures?: FigureMap | null;
}): ReactNode {
  if (!segments?.length) return <>{text}</>;
  return (
    <>
      {segments.map((s, i) =>
        s.figure ? <Fig key={i} id={s.figure} text={s.text} figures={figures} /> : <Fragment key={i}>{s.text}</Fragment>,
      )}
    </>
  );
}

export interface TagItem {
  key: string;
  info: FigureJson;
}

/** Tags in a row, for a figure that is drawn some other way (a big number, a
 *  chart). One source opens at a time, below the row. With `labelled`, each tag
 *  carries its figure's number, so a row of several says which is which. */
export function Tags({ items, labelled = false, lead, className = 'mt-2' }: {
  items: TagItem[];
  labelled?: boolean;
  /** Muted words before the first tag: "Length of the plan". */
  lead?: string;
  className?: string;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const panel = useId();
  if (!items.length) return null;
  const shown = items.find((i) => i.key === open);
  return (
    <div className={className} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6, ...BODY }}>
      {lead ? <span className="cx-faint" style={{ fontSize: 13 }}>{lead}</span> : null}
      {items.map(({ key, info }) => (
        <span key={key} style={{ display: 'inline-flex', marginLeft: -4 }}>
          <TagButton
            info={info}
            label={labelled ? `${info.display} · ${info.tag}` : info.tag}
            open={open === key}
            controls={panel}
            onToggle={() => setOpen(open === key ? null : key)}
          />
        </span>
      ))}
      {shown ? (
        <span style={{ flexBasis: '100%' }}>
          <Source id={panel} info={shown.info} lead={labelled && items.length > 1 ? `${shown.info.display}:` : undefined} />
        </span>
      ) : null}
    </div>
  );
}

/** `Tags` for figures named by id, looked up in the payload's map. Ids the map
 *  does not hold are left out; with none left it draws nothing. */
export function FigTags({ ids, figures, labelled, lead, className }: {
  ids: string[];
  figures?: FigureMap | null;
  /** Default: labelled when there is more than one. */
  labelled?: boolean;
  lead?: string;
  className?: string;
}) {
  const items: TagItem[] = [];
  for (const id of new Set(ids)) {
    const info = figures?.[id];
    if (info) items.push({ key: id, info });
  }
  return <Tags items={items} labelled={labelled ?? items.length > 1} lead={lead} className={className} />;
}
