import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'I\'m Harbor Intake AI — I handle forms, insurance, and booking so patients never wait on hold. 38 patients booked after hours last month. What do you need?';

const REPLIES: Record<string, string> = {
  botox:
    'Botox consult $420 with Dr. Chen. I\'ll send the digital intake now (4 min on phone) + screen POI contraindications — you arrive ready, not clipboarding. Want Thu 2:30 or Fri 11?',
  hydra:
    'Hydrafacial $189 · Jess Kim RN. I\'ll lock the slot, email prep + intake, and text a reminder 24h before. Most patients book this in under 45 seconds.',
  intake:
    'Digital intake beats the clipboard: history, allergies, consent — done before you walk in. Clinics using this cut front-desk phone time ~40%. Want the link?',
  insurance:
    'Share your carrier — I flag what we verify before consult day so billing never blindsides you. Complex cases escalate to staff in under 30 min.',
  book: 'Hydrafacial, Botox, IV drip, or laser? I match live rooms + providers and send confirmation + forms instantly.',
  hours: 'Clinic hours Mon–Sat — I book 24/7. Last night alone: 6 midnight bookings that would\'ve been lost voicemails.',
  default:
    'Pricing, intake forms, insurance basics, or a same-week slot — I reply in seconds and fill your calendar while the front desk sleeps.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('botox')) return REPLIES.botox;
  if (t.includes('hydra') || t.includes('facial')) return REPLIES.hydra;
  if (t.includes('intake') || t.includes('form') || t.includes('clipboard')) return REPLIES.intake;
  if (t.includes('insurance') || t.includes('ppo') || t.includes('cover')) return REPLIES.insurance;
  if (t.includes('book') || t.includes('appointment') || t.includes('slot')) return REPLIES.book;
  if (t.includes('hour') || t.includes('open') || t.includes('midnight') || t.includes('night')) return REPLIES.hours;
  return REPLIES.default;
}

interface Props {
  onBookClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function HarborPatientChat({ onBookClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="harbor"
      brandName="Harbor Intake AI"
      aiLabel="Clinical intake"
      statusText="Forms · insurance · slots · 24/7"
      greeting={GREETING}
      capabilityChips={['Digital intake', 'Insurance triage', 'Zero hold music']}
      hookProof="38 after-hours bookings last month · avg reply 12s"
      quickReplies={['Send intake now', 'Botox + insurance?', 'Book tonight']}
      fabLabel="Book without calling"
      fabBadge="Intake"
      placeholder="Treatments, forms, insurance…"
      poweredByText="Patients book at midnight · staff wake up to a full day"
      ctaLabel="Book my slot now"
      onCtaClick={onBookClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Harbor clinical intake chat"
    />
  );
}

export { aiReply };
