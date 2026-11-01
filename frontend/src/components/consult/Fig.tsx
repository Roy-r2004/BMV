/**
 * A figure, whose it is, and where it came from.
 *
 * Every number on the answer and the plans is one of four kinds: yours, worked
 * out from yours, our estimate, or a published reference. The server says which
 * (the payload's `figures` map: how it prints, its kind, the tag word and one
 * plain sentence on where it came from), and this file only draws it.
 *
 * A figure is a button. Pressing it opens the source sentence right below it, in
 * place, and pressing it again closes it. It is a real button (keyboard: Enter
 * and Space open it, Escape closes it; `aria-expanded` says which), its name says
 * the figure first ("$22, yours: where this comes from"), its touch area is 44px
 * tall whatever the size of the text, and it takes the design system's focus
 * ring. Nothing here depends on hovering.
 *
 * In a sentence the first figure of each kind carries the full tag chip; later
 * figures of that kind in the same stretch of text are only underlined, in the
 * kind's colour, and are the same button. A row of tags (`Tags`) is for a figure
 * that is drawn some other way (a big number, a chart).
 *
 * A payload from before figures had tags has no map and no segments; every
 * export here then draws plain text and nothing else.
 */
import { Fragment, useId, useState, type CSSProperties, type ReactNode } from 'react';

import type { FigureJson, FigureKind, FigureMap, FigureSegment } from '../../api/consultant';

// The hues are the ones the data request's legend already uses: green for what they
// told us, amber and dashed for what we estimated, but the text is darkened until every
// chip is at least 4.5:1 on its own tint, on white (the answer's card) and on the pillar
// panel (#eef4ff): yours 6.07 / 5.57, worked out 7.30 / 6.65, our estimate 6.17 / 6.17,
// reference 7.70 / 7.70 (the tints are rgba(14,159,110,.10), rgba(37,99,235,.09), #fff1dc
// and #eef2f9). They are inline styles, because the answer's heading restyles every span
// inside it.
const COLOUR: Record<FigureKind, { color: string; background: string; border: string }> = {
  theirs: { color: '#0a6847', background: 'var(--cx-green-soft)', border: '1px solid transparent' },
  derived: { color: '#1a43b8', background: 'var(--cx-blue-soft)', border: '1px solid transparent' },
  ours: { color: '#8a4a00', background: 'var(--cx-amber-bg)', border: '1px dashed #8a4a00' },
  reference: { color: '#3d4b6e', background: '#eef2f9', border: '1px solid transparent' },
};
const colourOf = (kind: FigureKind) => COLOUR[kind] ?? COLOUR.reference;

// A figure that has no chip is underlined, and the line says the kind without colour:
// solid for yours, dashed for worked out, dotted for our estimate, double for a reference.
const LINE: Record<FigureKind, 'solid' | 'dashed' | 'dotted' | 'double'> = {
  theirs: 'solid',
  derived: 'dashed',
  ours: 'dotted',
  reference: 'double',
};

const BODY = { fontFamily: 'var(--cx-body)', letterSpacing: 0, textTransform: 'none' } as const;

// The design system's focus ring (consult.css: .cx-btn:focus-visible), and a target
// that is 44px tall however small the text: the pseudo-element is the extra reach (it is
// measured from the padding box, so the chip's 1px border is allowed for).
const FOCUS = 'focus-visible:outline-3 focus-visible:outline-offset-3 focus-visible:outline-[color:rgba(37,99,235,0.45)]';

const nameOf = (figure: string, info: FigureJson) => `${figure}, ${info.tag}: where this comes from`;

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="8"
      height="8"
      viewBox="0 0 8 8"
      aria-hidden="true"
      style={{ flex: 'none', transform: open ? 'rotate(180deg)' : undefined, transition: 'transform 0.15s' }}
    >
      <path d="M1 2.5 4 5.5 7 2.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function chipStyle(kind: FigureKind, height: number): CSSProperties {
  return {
    ...BODY,
    ...colourOf(kind),
    display: 'inline-flex',
    alignItems: 'center',
    gap: 4,
    height,
    padding: '0 8px',
    borderRadius: 999,
    fontSize: 11.5,
    fontWeight: 600,
    lineHeight: 1,
    whiteSpace: 'nowrap',
    verticalAlign: 'middle',
  };
}

/** The sentence that says where a figure came from, opened under it. */
function Source({ id, info }: { id: string; info: FigureJson }) {
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
      {info.source}
    </span>
  );
}

const closeOnEscape = (open: boolean, toggle: () => void) => (e: { key: string; stopPropagation: () => void }) => {
  if (e.key === 'Escape' && open) {
    e.stopPropagation();
    toggle();
  }
};

/** A figure inside a sentence: its text, and (with `chip`) its tag beside it. Pressing
 *  either opens the source below. With no entry in the map it is only its text. `trail`
 *  is the punctuation that follows the figure in the sentence ("." in "$32."): it stays
 *  with the figure, so an opened source never leaves it alone on a line. */
export default function Fig({ id, text, figures, chip = true, trail = '' }: {
  id: string;
  text: string;
  figures?: FigureMap | null;
  /** The full tag chip beside the number, or only the number underlined. */
  chip?: boolean;
  trail?: string;
}) {
  const info = figures?.[id];
  const [open, setOpen] = useState(false);
  const panel = useId();
  if (!info) return <>{text}{trail}</>;
  const toggle = () => setOpen((v) => !v);
  const colour = colourOf(info.kind).color;
  return (
    <>
      <span style={{ display: 'inline', color: 'inherit', whiteSpace: 'nowrap' }}>
        <button
          type="button"
          className={`relative cursor-pointer before:absolute before:-inset-x-1 before:-inset-y-3 before:content-[''] ${FOCUS}`}
          style={{
            display: 'inline',
            margin: 0,
            padding: 0,
            border: 0,
            background: 'none',
            font: 'inherit',
            letterSpacing: 'inherit',
            color: 'inherit',
            textAlign: 'inherit',
            whiteSpace: 'nowrap',
            ...(chip ? {} : {
              textDecorationLine: 'underline',
              textDecorationStyle: LINE[info.kind] ?? 'solid',
              textDecorationColor: colour,
              textDecorationThickness: open ? 3 : 2,
              textUnderlineOffset: 4,
            }),
          }}
          aria-expanded={open}
          aria-controls={open ? panel : undefined}
          aria-label={nameOf(text, info)}
          data-figure={text}
          onClick={toggle}
          onKeyDown={closeOnEscape(open, toggle)}
        >
          {text}
          {chip ? (
            <span style={{ ...chipStyle(info.kind, 22), marginLeft: 4 }}>
              {info.tag}
              <Chevron open={open} />
            </span>
          ) : null}
        </button>
        {trail}
      </span>
      {open ? <Source id={panel} info={info} /> : null}
    </>
  );
}

const TRAILING = /^[.,;:!?)\]}'"\u2019\u201d\u00bb]+/;

/** Prose in the pieces the server sent: plain text, and a Fig for each bound
 *  number. The first figure of each kind carries the chip, the rest are underlined.
 *  With no pieces (an older payload) it is the plain text. */
export function Segments({ segments, text, figures }: {
  segments?: FigureSegment[] | null;
  text: string;
  figures?: FigureMap | null;
}): ReactNode {
  if (!segments?.length) return <>{text}</>;
  const seen = new Set<FigureKind>();
  // the punctuation right after a figure travels with it (see `Fig`)
  const pieces = segments.map((s) => ({ ...s, trail: '' }));
  for (let i = 0; i + 1 < pieces.length; i++) {
    const next = pieces[i + 1];
    const m = pieces[i].figure && !next.figure ? TRAILING.exec(next.text) : null;
    if (m) {
      pieces[i].trail = m[0];
      next.text = next.text.slice(m[0].length);
    }
  }
  return (
    <>
      {pieces.map((s, i) => {
        if (!s.figure) return s.text ? <Fragment key={i}>{s.text}</Fragment> : null;
        const kind = figures?.[s.figure]?.kind;
        const chip = !kind || !seen.has(kind);
        if (kind) seen.add(kind);
        return <Fig key={i} id={s.figure} text={s.text} figures={figures} chip={chip} trail={s.trail} />;
      })}
    </>
  );
}

export interface TagItem {
  key: string;
  info: FigureJson;
}

/** Tags in a row, for a figure that is drawn some other way (a big number, a
 *  chart). One source opens at a time, below the row. With `labelled`, each tag
 *  carries its figure's number, so a row of several says which is which. The
 *  tags are far enough apart that the 44px touch areas do not overlap. */
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
    <div className={className} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '16px 10px', ...BODY }}>
      {lead ? <span className="cx-faint" style={{ fontSize: 13 }}>{lead}</span> : null}
      {items.map(({ key, info }) => {
        const isOpen = open === key;
        const toggle = () => setOpen(isOpen ? null : key);
        return (
          <button
            key={key}
            type="button"
            className={`relative cursor-pointer before:absolute before:-inset-x-1 before:-inset-y-[9px] before:content-[''] ${FOCUS}`}
            style={{
              ...chipStyle(info.kind, 28),
              padding: '0 10px',
              cursor: 'pointer',
              boxShadow: isOpen ? 'inset 0 0 0 1px currentColor' : undefined,
            }}
            aria-expanded={isOpen}
            aria-controls={isOpen ? panel : undefined}
            aria-label={nameOf(info.display, info)}
            data-figure={info.display}
            onClick={toggle}
            onKeyDown={closeOnEscape(isOpen, toggle)}
          >
            {labelled ? `${info.display} · ${info.tag}` : info.tag}
            <Chevron open={isOpen} />
          </button>
        );
      })}
      {shown ? (
        <span style={{ flexBasis: '100%', marginTop: -8 }}>
          <Source id={panel} info={shown.info} />
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
