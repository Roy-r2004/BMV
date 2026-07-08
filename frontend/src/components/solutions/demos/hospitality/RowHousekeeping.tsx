import { useMemo, useState } from 'react';
import { RowLogo } from '../shared/ShowcaseChatIcons.tsx';
import {
  HOUSEKEEPING_FLOORS,
  HOUSEKEEPING_ROOMS,
  roomsByFloor,
  type RoomStatus,
} from './rowData.ts';

const STATUS_META: Record<RoomStatus, { label: string; short: string }> = {
  dirty: { label: 'Dirty', short: 'Dirty' },
  cleaning: { label: 'Cleaning', short: 'In progress' },
  clean: { label: 'Clean', short: 'Ready' },
  inspected: { label: 'Inspected', short: 'Cleared' },
  occupied: { label: 'Occupied', short: 'In-house' },
};

const STATUSES: RoomStatus[] = ['dirty', 'cleaning', 'clean', 'inspected', 'occupied'];

interface Props {
  highlightRoom?: string;
}

export default function RowHousekeeping({ highlightRoom }: Props) {
  const [floor, setFloor] = useState<number>(4);
  const [statusFilter, setStatusFilter] = useState<RoomStatus | 'all'>('all');

  const rooms = useMemo(() => {
    const list = roomsByFloor(floor);
    if (statusFilter === 'all') return list;
    return list.filter((r) => r.status === statusFilter);
  }, [floor, statusFilter]);

  const counts = useMemo(() => {
    const map: Record<RoomStatus, number> = {
      dirty: 0,
      cleaning: 0,
      clean: 0,
      inspected: 0,
      occupied: 0,
    };
    HOUSEKEEPING_ROOMS.forEach((r) => { map[r.status] += 1; });
    return map;
  }, []);

  const floorCounts = useMemo(() => {
    return HOUSEKEEPING_FLOORS.map((f) => {
      const list = roomsByFloor(f);
      return {
        floor: f,
        dirty: list.filter((r) => r.status === 'dirty' || r.status === 'cleaning').length,
        ready: list.filter((r) => r.status === 'clean' || r.status === 'inspected').length,
      };
    });
  }, []);

  return (
    <div className="rh-hk">
      <header className="rh-hk__head">
        <div className="rh-hk__brand">
          <RowLogo className="rh-hk__logo" />
          <div>
            <h1>Housekeeping board</h1>
            <p>Live rooms · prefs synced from concierge</p>
          </div>
        </div>
        <div className="rh-hk__legend">
          {STATUSES.map((s) => (
            <span key={s} className={`rh-hk__legend-item rh-hk__legend-item--${s}`}>
              <i aria-hidden />
              {STATUS_META[s].label}
              <em>{counts[s]}</em>
            </span>
          ))}
        </div>
      </header>

      <div className="rh-hk__sync-bar">
        <span className="rh-hk__sync-dot" aria-hidden />
        Front desk live · late checkout on 405 &amp; VIP prep on 504
      </div>

      <div className="rh-hk__floor-rail" role="tablist" aria-label="Floors">
        {floorCounts.map((f) => (
          <button
            key={f.floor}
            type="button"
            role="tab"
            aria-selected={floor === f.floor}
            className={`rh-hk__floor-tab ${floor === f.floor ? 'rh-hk__floor-tab--on' : ''}`}
            onClick={() => setFloor(f.floor)}
          >
            <strong>Floor {f.floor}</strong>
            <span>{f.ready} ready · {f.dirty} open</span>
          </button>
        ))}
      </div>

      <div className="rh-hk__filters">
        <button
          type="button"
          className={statusFilter === 'all' ? 'rh-hk__filter rh-hk__filter--on' : 'rh-hk__filter'}
          onClick={() => setStatusFilter('all')}
        >
          All rooms
        </button>
        {STATUSES.map((s) => (
          <button
            key={s}
            type="button"
            className={statusFilter === s ? `rh-hk__filter rh-hk__filter--on rh-hk__filter--${s}` : `rh-hk__filter rh-hk__filter--${s}`}
            onClick={() => setStatusFilter(s)}
          >
            {STATUS_META[s].label}
          </button>
        ))}
      </div>

      <div className="rh-hk__board" aria-label={`Floor ${floor} rooms`}>
        {rooms.map((room) => (
          <article
            key={room.id}
            className={`rh-hk__room rh-hk__room--${room.status} ${highlightRoom === room.number ? 'rh-hk__room--pulse' : ''}`}
          >
            <div className="rh-hk__room-top">
              <strong className="rh-hk__room-num">{room.number}</strong>
              <span className={`rh-hk__room-status rh-hk__room-status--${room.status}`}>
                {STATUS_META[room.status].short}
              </span>
            </div>
            <p className="rh-hk__room-type">{room.type}</p>
            {room.guest && <p className="rh-hk__room-guest">{room.guest}</p>}
            {room.checkout && <p className="rh-hk__room-co">C/O {room.checkout}</p>}
            {room.note && <p className="rh-hk__room-note">{room.note}</p>}
            {room.attendant && <p className="rh-hk__room-att">{room.attendant}</p>}
          </article>
        ))}
      </div>

      <footer className="rh-hk__foot">
        <div>
          <strong>Desk sync</strong>
          <span>Arrival 504 needs inspected · departure 401 still dirty</span>
        </div>
        <div>
          <strong>AI flags</strong>
          <span>Late C/O · hypoallergenic · VIP turndown</span>
        </div>
      </footer>
    </div>
  );
}
