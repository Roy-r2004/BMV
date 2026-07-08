import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import { matchTutors, SUBJECTS } from './summitData.ts';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'Summit Tutor Match — tell me subject + level and I\'ll pair you with the right tutor, prep pack, and session slot. No generic booking forms.';

const REPLIES: Record<string, string> = {
  math: `Algebra II tutors: Dr. Elena Ruiz (98% match) Thu 4:30 or Fri 3:15. Prep pack auto-sent 24h before — quadratic review + video walkthrough included.`,
  science: 'Chemistry with Marcus Chen — 94% match. Lab prep materials ship before every session. Noah\'s mole-ratio pack went out Monday.',
  english: 'Priya Nair for essay coaching — thesis frameworks, timed drills, SAT verbal strategy. Mia\'s on a 20-pack; parents get weekly progress auto-sent.',
  sat: 'James Okonkwo runs SAT strategy — diagnostic → 8-week roadmap. Calculator strategies pack already queued for Ethan\'s Thursday session.',
  prep: 'Prep automation: worksheets, videos, and quizzes land in family inbox 24h before each session. Tutors teach — AI handles materials.',
  report: 'Parent reports: weekly summaries with session notes, homework completion, and next-week focus. Sarah got Ava\'s math report this morning — zero manual emails.',
  billing: '8-session pack $720 · renewals auto-remind 7 days out. David\'s renewal is due Mar 14 — invoice queued with one-tap pay link.',
  default: 'Subject + level → tutor match → prep pack → session. Ask math, SAT, prep packs, or parent reports.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('algebra') || t.includes('math') || t.includes('calc')) return REPLIES.math;
  if (t.includes('chem') || t.includes('science') || t.includes('bio')) return REPLIES.science;
  if (t.includes('essay') || t.includes('english') || t.includes('writing')) return REPLIES.english;
  if (t.includes('sat') || t.includes('act') || t.includes('test')) return REPLIES.sat;
  if (t.includes('prep') || t.includes('material') || t.includes('pack')) return REPLIES.prep;
  if (t.includes('parent') || t.includes('report') || t.includes('weekly')) return REPLIES.report;
  if (t.includes('bill') || t.includes('pack') || t.includes('renew')) return REPLIES.billing;
  if (t.includes('match') || t.includes('tutor')) {
    const matches = matchTutors('math', 'Algebra II');
    const top = matches[0];
    return top
      ? `${top.name} — ${top.matchScore}% match for Algebra II. ${top.bio.split('.')[0]}.`
      : REPLIES.default;
  }
  return REPLIES.default;
}

interface Props {
  onMatchClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function SummitStudentChat({ onMatchClick, open, onOpenChange }: Props) {
  const subjectNames = SUBJECTS.map((s) => s.name).join(' · ');

  return (
    <ShowcaseChatWidget
      theme="summit"
      brandName="Tutor Match AI"
      aiLabel="Tutor matcher"
      statusText="Subject pairing live"
      greeting={GREETING}
      capabilityChips={['Tutor match', 'Prep automation', 'Parent reports', 'Auto billing']}
      hookProof="94% parent satisfaction · prep packs sent before every session"
      quickReplies={['Match Algebra II tutor', 'Send prep pack', 'Parent weekly report']}
      fabLabel="Match my tutor"
      fabBadge="Match"
      placeholder={`${subjectNames}…`}
      poweredByText="Tutors teach. AI matches, preps, and reports."
      ctaLabel="See tutor matches"
      onCtaClick={onMatchClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Summit Tutoring tutor matcher"
    />
  );
}
