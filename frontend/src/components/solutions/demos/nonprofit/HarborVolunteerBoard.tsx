import { useMemo, useState } from 'react';
import { HarborFundLogo, IconSparkle } from '../shared/ShowcaseChatIcons.tsx';
import {
  VOLUNTEER_SKILLS,
  matchVolunteerOpps,
  type VolunteerOpp,
} from './harborFundData.ts';
import { onHarborFundImageError } from './harborFundImageFallback.ts';

interface Props {
  highlightSkills?: string[];
}

function OppCard({
  opp,
  selected,
  onSelect,
}: {
  opp: VolunteerOpp;
  selected: boolean;
  onSelect: () => void;
}) {
  const open = opp.spots - opp.filled;
  return (
    <article className={`hg-board__card ${selected ? 'hg-board__card--on' : ''}`}>
      <div className="hg-board__score" title={`${opp.matchScore}% skill match`}>
        <span className="hg-board__score-ring" aria-hidden />
        <strong>{opp.matchScore}%</strong>
        <span>skill fit</span>
      </div>
      <img src={opp.imageUrl} alt="" onError={onHarborFundImageError} />
      <div className="hg-board__card-body">
        <h3>{opp.title}</h3>
        <p className="hg-board__when">{opp.when}</p>
        <p className="hg-board__where">{opp.where} · {opp.hours}h</p>
        <p className="hg-board__desc">{opp.desc}</p>
        <div className="hg-board__skills">
          {opp.skills.map((s) => (
            <span key={s}>{VOLUNTEER_SKILLS.find((v) => v.id === s)?.label ?? s}</span>
          ))}
        </div>
        <div className="hg-board__spots">
          <div className="hg-board__spots-bar">
            <div style={{ width: `${(opp.filled / opp.spots) * 100}%` }} />
          </div>
          <span>{open} of {opp.spots} spots open</span>
        </div>
        <button type="button" className="hg-board__claim" onClick={onSelect}>
          {selected ? 'Signed up' : 'Claim shift'}
        </button>
      </div>
    </article>
  );
}

export default function HarborVolunteerBoard({ highlightSkills }: Props) {
  const [selectedSkills, setSelectedSkills] = useState<string[]>(
    highlightSkills?.length ? highlightSkills : ['kitchen', 'logistics'],
  );
  const [claimed, setClaimed] = useState<string | null>(null);

  const matches = useMemo(() => matchVolunteerOpps(selectedSkills), [selectedSkills]);

  const toggleSkill = (id: string) => {
    setSelectedSkills((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );
  };

  return (
    <div className="hg-board">
      <header className="hg-board__head">
        <div className="hg-board__brand">
          <HarborFundLogo className="hg-board__logo" />
          <div>
            <h2>Volunteer board</h2>
            <p>Skills matched to open opportunities</p>
          </div>
        </div>
        <span className="hg-board__ai-pill">
          <IconSparkle className="hg-board__sparkle" />
          Matcher live
        </span>
      </header>

      <div className="hg-board__skill-bar">
        <p>Your skills</p>
        <div className="hg-board__skill-chips">
          {VOLUNTEER_SKILLS.map((s) => (
            <button
              key={s.id}
              type="button"
              className={selectedSkills.includes(s.id) ? 'hg-board__chip hg-board__chip--on' : 'hg-board__chip'}
              onClick={() => toggleSkill(s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {claimed && (
        <div className="hg-board__claimed">
          <IconSparkle className="hg-board__sparkle" />
          <span>
            Shift claimed — thank-you bot will confirm + send rematch if waitlisted.
          </span>
          <button type="button" onClick={() => setClaimed(null)}>Dismiss</button>
        </div>
      )}

      <div className="hg-board__grid">
        {matches.map((opp) => (
          <OppCard
            key={opp.id}
            opp={opp}
            selected={claimed === opp.id}
            onSelect={() => setClaimed(opp.id)}
          />
        ))}
      </div>
    </div>
  );
}
