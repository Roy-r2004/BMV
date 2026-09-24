/**
 * Their week, drawn spot by spot from what they told us.
 *
 * One dot per unit they sell: a reformer spot, a seat, a chair. Filled is
 * sold, deep blue is a slot that sells out, a ring is someone who could not
 * get in — dashed when they told us there is a waiting list but not how long.
 * A time is shown only when they named it; a column they did not name has no
 * time on it, because inventing a timetable would be inventing a fact.
 */
import type { CapacityPicture } from '../../api/consultant';
import { fmt, sayTime, weekHeadline } from '../../utils/week';

function Dots({ capacity, taken, hot, waitlist, mini, slots }: {
  capacity: number;
  taken: number | null;
  hot: boolean;
  waitlist: number | 'unknown' | null;
  mini: boolean;
  /** How many slots share the row: more of them, smaller dots. */
  slots: number;
}) {
  // Past about thirty dots a cell stops reading as a count and starts reading
  // as texture; a bar says "how full" more honestly at that size.
  if (capacity > 30) {
    const pct = taken != null ? Math.min(100, (taken / capacity) * 100) : 0;
    return (
      <div className={`cx-bar${hot ? ' hot' : ''}`} title={`${fmt(taken)} of ${fmt(capacity)}`}>
        <b style={{ width: `${pct}%` }} />
      </div>
    );
  }
  const cols = capacity <= 12 ? Math.ceil(capacity / 2) : Math.ceil(capacity / 3);
  const filled = taken != null ? Math.round(taken) : 0;
  const rings = waitlist === 'unknown' ? 1 : waitlist ?? 0;
  const size = mini ? 6 : slots <= 4 ? 10 : slots <= 6 ? 8 : 6;
  const gap = mini ? 2.5 : Math.max(2.5, size / 2.5);
  // How full it is was never said: hollow, not empty. Empty dots would say
  // "nobody comes", which is a fact they did not give us either.
  const unknown = taken == null && !hot;
  return (
    <div
      className={`cx-dots${hot ? ' hot' : ''}${unknown ? ' unknown' : ''}`}
      style={{ gridTemplateColumns: `repeat(${cols}, ${size}px)`, gap }}
      aria-hidden="true"
    >
      {Array.from({ length: capacity }, (_, i) => (
        <i key={i} className={i < filled ? 'on' : ''} style={mini ? undefined : { width: size, height: size }} />
      ))}
      {Array.from({ length: Math.min(rings, cols * 2) }, (_, i) => (
        <i key={`w${i}`} className={`wait${waitlist === 'unknown' ? ' unknown' : ''}`} />
      ))}
    </div>
  );
}

export default function WeekGrid({ picture, mini = false }: { picture: CapacityPicture; mini?: boolean }) {
  if (picture.shape === 'total') {
    const scale = picture.dot_scale || 1;
    const total = Math.ceil(picture.capacity / scale);
    const on = picture.taken != null ? Math.round(picture.taken / scale) : 0;
    return (
      <div>
        <div className="cx-pool" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <i key={i} className={i < on ? 'on' : ''} style={mini ? { width: 6, height: 6 } : undefined} />
          ))}
        </div>
        {scale > 1 ? (
          <p className="cx-faint cx-small mt-3">Each dot is {fmt(scale)} {picture.unit_plural}.</p>
        ) : null}
      </div>
    );
  }

  const grid = picture.grid ?? [];
  const times = picture.times ?? [];
  const labelW = mini ? 34 : 46;
  const cols = `${labelW}px repeat(${times.length}, minmax(0, 1fr))`;
  return (
    <div className={`cx-week${mini ? ' mini' : ''}`} role="img" aria-label={weekHeadline(picture)}>
      <div className="cx-week-head" style={{ gridTemplateColumns: cols }}>
        <span />
        {times.map((t, i) => (
          <span key={i} className={`cx-week-t${t && picture.full?.includes(t) ? ' hot' : ''}`}>
            {sayTime(t)}
          </span>
        ))}
      </div>
      {grid.map((row) => (
        <div className="cx-week-row" key={row.day} style={{ gridTemplateColumns: cols }}>
          <span className="cx-week-d">{row.day}</span>
          {row.slots.map((s, i) => (
            <Dots key={i} capacity={s.capacity} taken={s.taken} hot={s.full} waitlist={s.waitlist} mini={mini} slots={times.length} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** The legend: what a dot, a dark dot and a ring mean, in their words. */
export function WeekLegend({ picture }: { picture: CapacityPicture }) {
  if (picture.shape === 'total') {
    return (
      <p className="cx-small cx-muted">
        <b className="text-[var(--cx-txt)]">Your capacity.</b> Each dot is{' '}
        {picture.dot_scale && picture.dot_scale > 1 ? `${fmt(picture.dot_scale)} ${picture.unit_plural}` : `one ${picture.unit}`}; the dark ones are used.
      </p>
    );
  }
  const rings =
    picture.waitlist
      ? picture.waitlist_size
        ? ' The rings are people who couldn’t get in.'
        : ' A dashed ring marks the waiting list you mentioned — you didn’t say how long it is.'
      : '';
  const noun = picture.slot_noun || 'slot';
  const plural = /(s|x|ch|sh)$/.test(noun) ? `${noun}es` : `${noun}s`;
  const hollow = picture.typical_taken == null ? ` Hollow dots are ${plural} you didn’t tell us how full they are.` : '';
  return (
    <p className="cx-small cx-muted">
      <b className="text-[var(--cx-txt)]">Your week.</b> Each dot is one {picture.unit}.{rings}{hollow}
    </p>
  );
}
