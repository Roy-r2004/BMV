import { useEffect, useMemo, useState } from 'react';
import { RowLogo } from '../shared/ShowcaseChatIcons.tsx';
import {
  HOUSEKEEPING_FLOORS,
  HOUSEKEEPING_ROOMS,
  HOUSEKEEPING_SUMMARY,
  roomsByFloor,
  type RoomStatus,
} from './rowData.ts';

const STATUS_META: Record<RoomStatus, { label: string; short: string; action?: string }> = {
  dirty: { label: 'Dirty', short: 'Dirty', action: 'Assign clean' },
  cleaning: { label: 'In progress', short: 'Cleaning', action: 'Mark clean' },
  clean: { label: 'Clean', short: 'Ready', action: 'Inspect' },
  inspected: { label: 'Inspected', short: 'Cleared', action: 'Release' },
  occupied: { label: 'Occupied', short: 'In-house' },
};

const STATUSES: RoomStatus[] = ['dirty', 'cleaning', 'clean', 'inspected', 'occupied'];

interface Props {
  highlightRoom?: string;
}

export default function RowHousekeeping({ highlightRoom }: Props) {
  const [floor, setFloor] = useState<number>(highlightRoom ? Number(highlightRoom[0]) || 4 : 4);
  const [statusFilter, setStatusFilter] = useState<RoomStatus | 'all'>('all');
  const [selected, setSelected] = useState<string | null>(highlightRoom ?? null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (highlightRoom) {
      setSelected(highlightRoom);
      const f = Number(highlightRoom[0]);
      if (HOUSEKEEPING_FLOORS.includes(f as (typeof HOUSEKEEPING_FLOORS)[number])) setFloor(f);
    }
  }, [highlightRoom]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 3200);
    return () => window.clearInterval(id);
  }, []);

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
    HOUSEKEEPING_ROOMS.forEach((r) => {
      map[r.status] += 1;
    });
    return map;
  }, []);

  const floorCounts = useMemo(
    () =>
      HOUSEKEEPING_FLOORS.map((f) => {
        const list = roomsByFloor(f);
        return {
          floor: f,
          dirty: list.filter((r) => r.status === 'dirty' || r.status === 'cleaning').length,
          ready: list.filter((r) => r.status === 'clean' || r.status === 'inspected').length,
          total: list.length,
        };
      }),
    [],
  );

  const queue = useMemo(
    () =>
      HOUSEKEEPING_ROOMS.filter((r) => r.status === 'dirty' || r.status === 'cleaning').sort((a, b) => {
        if (a.status === 'dirty' && b.status !== 'dirty') return -1;
        if (b.status === 'dirty' && a.status !== 'dirty') return 1;
        return a.number.localeCompare(b.number);
      }),
    [],
  );

  const selectedRoom = HOUSEKEEPING_ROOMS.find((r) => r.number === selected) ?? rooms[0];
  const syncMessages = [
    HOUSEKEEPING_SUMMARY.syncNote,
    'Late checkout on 405 · hypoallergenic loaded',
    'VIP prep 504 · front desk waiting on inspect',
    'Departure 401 still dirty · Reyes assigned',
  ];
  const syncLine = syncMessages[tick % syncMessages.length];

  return (
    <div className="rh-hk">
      <header className="rh-hk__head">
        <div className="rh-hk__brand">
          <RowLogo className="rh-hk__logo" />
          <div>
            <p className="rh-hk__eyebrow">Floor ops · live</p>
            <h1>Housekeeping</h1>
          </div>
        </div>
        <div className="rh-hk__kpis" role="list">
          {STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              role="listitem"
              className={`rh-hk__kpi rh-hk__kpi--${s} ${statusFilter === s ? 'rh-hk__kpi--on' : ''}`}
              onClick={() => setStatusFilter((cur) => (cur === s ? 'all' : s))}
            >
              <em>{counts[s]}</em>
              <span>{STATUS_META[s].label}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="rh-hk__sync" role="status">
        <span className="rh-hk__sync-dot" aria-hidden />
        <span key={tick} className="rh-hk__sync-text">
          {syncLine}
        </span>
        <button type="button" className="rh-hk__sync-clear" onClick={() => setStatusFilter('all')}>
          Show all floors
        </button>
      </div>

      <div className="rh-hk__body">
        <aside className="rh-hk__side">
          <p className="rh-hk__side-label">Floors</p>
          <div className="rh-hk__floors" role="tablist" aria-label="Floors">
            {floorCounts.map((f) => (
              <button
                key={f.floor}
                type="button"
                role="tab"
                aria-selected={floor === f.floor}
                className={`rh-hk__floor ${floor === f.floor ? 'rh-hk__floor--on' : ''}`}
                onClick={() => {
                  setFloor(f.floor);
                  setStatusFilter('all');
                }}
              >
                <strong>{f.floor}</strong>
                <div className="rh-hk__floor-bar" aria-hidden>
                  <i style={{ width: `${(f.ready / f.total) * 100}%` }} />
                </div>
                <span>
                  {f.ready}/{f.total} ready
                  {f.dirty > 0 ? ` · ${f.dirty} open` : ''}
                </span>
              </button>
            ))}
          </div>

          <p className="rh-hk__side-label">Priority queue</p>
          <ul className="rh-hk__queue">
            {queue.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  className={`rh-hk__queue-item rh-hk__queue-item--${r.status} ${selected === r.number ? 'rh-hk__queue-item--on' : ''}`}
                  onClick={() => {
                    setFloor(r.floor);
                    setSelected(r.number);
                    setStatusFilter('all');
                  }}
                >
                  <strong>{r.number}</strong>
                  <span>{STATUS_META[r.status].short}</span>
                  <em>{r.attendant?.replace('Lead · ', '') ?? 'Unassigned'}</em>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <main className="rh-hk__main">
          <div className="rh-hk__main-head">
            <div>
              <h2>Floor {floor}</h2>
              <p>
                {rooms.length} rooms
                {statusFilter !== 'all' ? ` · ${STATUS_META[statusFilter].label}` : ''}
                {' · '}
                Concierge prefs synced
              </p>
            </div>
            {statusFilter !== 'all' && (
              <button type="button" className="rh-hk__clear" onClick={() => setStatusFilter('all')}>
                Clear filter
              </button>
            )}
          </div>

          <div className="rh-hk__corridor" aria-label={`Floor ${floor} corridor`}>
            <div className="rh-hk__corridor-label">North wing</div>
            <div className="rh-hk__board">
              {rooms.map((room) => (
                <button
                  key={room.id}
                  type="button"
                  className={`rh-hk__room rh-hk__room--${room.status} ${selected === room.number || highlightRoom === room.number ? 'rh-hk__room--pulse' : ''}`}
                  onClick={() => setSelected(room.number)}
                >
                  <div className="rh-hk__room-rail" aria-hidden />
                  <div className="rh-hk__room-top">
                    <strong className="rh-hk__room-num">{room.number}</strong>
                    <span className={`rh-hk__room-status rh-hk__room-status--${room.status}`}>
                      {STATUS_META[room.status].short}
                    </span>
                  </div>
                  <p className="rh-hk__room-type">{room.type}</p>
                  {room.status === 'cleaning' && (
                    <div className="rh-hk__progress" aria-hidden>
                      <i style={{ width: room.number.endsWith('2') ? '62%' : '38%' }} />
                    </div>
                  )}
                  {room.guest && <p className="rh-hk__room-guest">{room.guest}</p>}
                  {room.checkout && <p className="rh-hk__room-co">C/O {room.checkout}</p>}
                  {room.note && <p className="rh-hk__room-note">{room.note}</p>}
                  {room.attendant && <p className="rh-hk__room-att">{room.attendant}</p>}
                </button>
              ))}
            </div>
            {rooms.length === 0 && (
              <p className="rh-hk__empty">No rooms on this floor match the filter.</p>
            )}
          </div>
        </main>

        {selectedRoom && (
          <aside className="rh-hk__detail">
            <p className="rh-hk__side-label">Room detail</p>
            <div className={`rh-hk__detail-card rh-hk__detail-card--${selectedRoom.status}`}>
              <div className="rh-hk__detail-top">
                <strong>{selectedRoom.number}</strong>
                <span>{STATUS_META[selectedRoom.status].label}</span>
              </div>
              <p className="rh-hk__detail-type">
                {selectedRoom.type} · Floor {selectedRoom.floor}
              </p>
              {selectedRoom.guest && (
                <div className="rh-hk__detail-row">
                  <span>Guest</span>
                  <strong>{selectedRoom.guest}</strong>
                </div>
              )}
              {selectedRoom.checkout && (
                <div className="rh-hk__detail-row">
                  <span>Checkout</span>
                  <strong>{selectedRoom.checkout}</strong>
                </div>
              )}
              {selectedRoom.attendant && (
                <div className="rh-hk__detail-row">
                  <span>Attendant</span>
                  <strong>{selectedRoom.attendant}</strong>
                </div>
              )}
              {selectedRoom.note && (
                <div className="rh-hk__detail-note">
                  <span>AI / desk note</span>
                  <p>{selectedRoom.note}</p>
                </div>
              )}
              {STATUS_META[selectedRoom.status].action && (
                <button type="button" className="rh-hk__detail-action">
                  {STATUS_META[selectedRoom.status].action}
                </button>
              )}
            </div>
            <div className="rh-hk__detail-ai">
              <strong>Desk sync</strong>
              <p>Arrival 504 needs inspected. Late C/O prefs on 405 push to Reyes tablet.</p>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
}
