import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';

const GREETING =
  'Peak Form Coach AI — I pick classes that match your goals, move sessions when life hits, and ping you before streaks (and memberships) die.';

const REPLIES: Record<string, string> = {
  hiit: 'HIIT Burn Thu 6:30 with Maya — 92% goal match for fat-loss. 3 spots left. Hold one and your streak stays green.',
  strength:
    'Strength Lab · Derek Thu 7:30. I\'ll surface last deadlift PR + form tips so coach starts productive, not small-talk.',
  streak: '12-day streak. Missed Wed — Thu HIIT saves it. Churn risk: low. Studios lose money when streaks break unnoticed — I don\'t let that happen.',
  pr: 'PR logged. Derek gets your numbers before class. Want strength instead of HIIT Thursday? One tap, calendar + coach synced.',
  trial: 'Week 1 free — unlimited. I\'ll sequence HIIT + recovery from your onboarding answers so the trial feels personalized, not salesy.',
  reschedule: 'Moved → Thu 6:30 HIIT. Maya briefed, streak kept, no "sorry can we move?" guilt spiral. Members stay.',
  default: 'Class fit, reschedule, streak, or trial — I protect adherence so coaches sell results, not chase no-shows.',
};

function reply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('hiit') || t.includes('cardio') || t.includes('burn')) return REPLIES.hiit;
  if (t.includes('strength') || t.includes('lift') || t.includes('squat')) return REPLIES.strength;
  if (t.includes('streak') || t.includes('missed') || t.includes('adherence') || t.includes('churn')) return REPLIES.streak;
  if (t.includes('pr') || t.includes('deadlift') || t.includes('record')) return REPLIES.pr;
  if (t.includes('trial') || t.includes('free') || t.includes('join')) return REPLIES.trial;
  if (t.includes('move') || t.includes('reschedul') || t.includes('thursday')) return REPLIES.reschedule;
  return REPLIES.default;
}

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onBookClick?: () => void;
}

export default function PeakFormMemberChat({ open, onOpenChange, onBookClick }: Props) {
  return (
    <ShowcaseChatWidget
      theme="peakform"
      brandName="Adherence Coach AI"
      aiLabel="Retention coach"
      statusText="Streaks · reschedules · churn watch"
      greeting={GREETING}
      capabilityChips={['Class fit engine', 'One-tap reschedule', 'Churn saved early']}
      hookProof="89% 30-day retention · coaches see who needs a nudge"
      quickReplies={['Save my streak', 'Move HIIT to Thu', 'Start free trial']}
      fabLabel="Keep me accountable"
      fabBadge="Streak"
      placeholder="Reschedule, streak, class fit…"
      poweredByText="Members stay because AI catches drift before cancel"
      ctaLabel="Hold my class spot"
      onCtaClick={onBookClick}
      onReply={reply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Peak Form adherence coach"
    />
  );
}
