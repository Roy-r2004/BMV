import { useMemo, useState } from 'react';
import { SummitLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import { WEEK_SESSIONS, getStudent, getTutor, getSubject, type SessionSlot } from './summitData.ts';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'];

const MATERIAL_ICON: Record<string, string> = {
  worksheet: '📄',
  video: '▶',
  quiz: '✓',
  reading: '📖',
};

interface Props {
  highlightStudent?: string;
}

export default function SummitSessionCalendar({ highlightStudent }: Props) {
  const [selectedDay, setSelectedDay] = useState('Thursday');
  const [expandedSlot, setExpandedSlot] = useState<string | null>('ws-thu-1');

  const sessionsByDay = useMemo(() => {
    const map: Record<string, SessionSlot[]> = {};
    DAYS.forEach((d) => { map[d] = []; });
    WEEK_SESSIONS.forEach((s) => {
      if (map[s.day]) map[s.day].push(s);
    });
    return map;
  }, []);

  const daySessions = sessionsByDay[selectedDay] || [];
  const prepSent = WEEK_SESSIONS.filter((s) => s.materials.length > 0).length;
  const completed = WEEK_SESSIONS.filter((s) => s.status === 'completed').length;

  return (
    <div className="sm-calendar">
      <header className="sm-calendar__head">
        <div className="sm-calendar__brand">
          <SummitLogo className="sm-calendar__logo" />
          <div>
            <h2>Session week</h2>
            <span>Prep packs attached per slot — AI sends 24h before</span>
          </div>
        </div>
        <span className="sm-calendar__ai-pill">
          <IconSparkle className="sm-calendar__sparkle" />
          Prep automation
        </span>
      </header>

      <div className="sm-calendar__stats">
        <div><strong>{WEEK_SESSIONS.length}</strong><span>Sessions</span></div>
        <div><strong>{prepSent}</strong><span>Prep packs sent</span></div>
        <div><strong>{completed}</strong><span>Completed</span></div>
        <div><strong>24h</strong><span>Auto-send window</span></div>
      </div>

      <div className="sm-calendar__week">
        {DAYS.map((day) => {
          const count = sessionsByDay[day]?.length ?? 0;
          const hasHighlight = sessionsByDay[day]?.some((s) => {
            const student = getStudent(s.studentId);
            return student?.name === highlightStudent;
          });
          return (
            <button
              key={day}
              type="button"
              className={`sm-calendar__day ${selectedDay === day ? 'sm-calendar__day--on' : ''} ${hasHighlight ? 'sm-calendar__day--highlight' : ''}`}
              onClick={() => setSelectedDay(day)}
            >
              <span className="sm-calendar__day-name">{day.slice(0, 3)}</span>
              <span className="sm-calendar__day-count">{count || '—'}</span>
            </button>
          );
        })}
      </div>

      <div className="sm-calendar__slots">
        {daySessions.length === 0 ? (
          <p className="sm-calendar__empty">No sessions scheduled — tutors available for makeup slots.</p>
        ) : (
          daySessions.map((slot) => {
            const student = getStudent(slot.studentId);
            const tutor = getTutor(slot.tutorId);
            const subject = getSubject(slot.subjectId);
            const isExpanded = expandedSlot === slot.id;
            const isHighlight = student?.name === highlightStudent;

            return (
              <article
                key={slot.id}
                className={`sm-calendar__slot ${isExpanded ? 'sm-calendar__slot--open' : ''} ${isHighlight ? 'sm-calendar__slot--highlight' : ''}`}
              >
                <button
                  type="button"
                  className="sm-calendar__slot-head"
                  onClick={() => setExpandedSlot(isExpanded ? null : slot.id)}
                >
                  <div className="sm-calendar__slot-time">
                    <strong>{slot.time}</strong>
                    <span className={`sm-calendar__status sm-calendar__status--${slot.status}`}>
                      {slot.status === 'completed' ? 'Done' : slot.status === 'prep-sent' ? 'Prep sent' : 'Scheduled'}
                    </span>
                  </div>
                  <div className="sm-calendar__slot-info">
                    <strong>{student?.name} · {slot.level}</strong>
                    <span>{tutor?.name} · {subject?.name}</span>
                  </div>
                  <div className="sm-calendar__slot-materials-badge">
                    {slot.materials.length > 0 ? (
                      <span>{slot.materials.length} materials</span>
                    ) : (
                      <span className="sm-calendar__slot-materials-badge--pending">Prep pending</span>
                    )}
                  </div>
                </button>

                {isExpanded && (
                  <div className="sm-calendar__slot-body">
                    <div className="sm-calendar__slot-meta">
                      <span>{slot.durationMin} min</span>
                      <span>{student?.grade}</span>
                      <span>Parent: {student?.parentName}</span>
                    </div>

                    {slot.materials.length > 0 ? (
                      <div className="sm-calendar__materials">
                        <h4>Attached materials</h4>
                        <ul>
                          {slot.materials.map((m) => (
                            <li key={m.id}>
                              <span className="sm-calendar__mat-icon">{MATERIAL_ICON[m.type]}</span>
                              <div>
                                <strong>{m.name}</strong>
                                <span>{m.type} · sent {m.sentAt}</span>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : (
                      <div className="sm-calendar__prep-queue">
                        <IconSparkle className="sm-calendar__sparkle" />
                        <p>Prep pack auto-queued — will send 24h before session</p>
                      </div>
                    )}
                  </div>
                )}
              </article>
            );
          })
        )}
      </div>
    </div>
  );
}
