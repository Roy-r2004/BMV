import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import { BOOKING_SLOTS } from './studioData.ts';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'Studio Nine DM bot — I remember your fade, your barber, your stamps. Instagram DMs book chairs while you cut. What\'s good?';

const REPLIES: Record<string, string> = {
  fade: `Skin fades $38 · 45 min. Jay has ${BOOKING_SLOTS.filter((s) => s.serviceId === 'fade').map((s) => s.time).join(' or ')} — your #2 guard is already on file. Tick one and walk in like a regular.`,
  beard: 'Cut + beard $55 — hot towel, shape, cleanup. I\'ll lock your usual barber so you never re-explain the line again.',
  memory: 'Last visit: #2 guard · line-up · Jay · Chair 2. Loyalty 5/8 — one more cut unlocks a free VIP. That\'s why regulars never bounce.',
  waitlist: 'Cancel just opened 5:30 — I auto-texted the waitlist. First reply gets the chair. Chairs stop idling; money stops leaking.',
  book: 'Fade, cut+beard, VIP, or kids? Say day + barber — I confirm in-thread. No "can you do next week?" ping-pong.',
  walk: 'Walk-ins ~25 min · Alex Chair 3. Or I ping you the second a chair frees — you\'re never guessing.',
  default: 'Style memory + live chair board = every DM becomes a booking. Ask fade, wait, or "my usual."',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('fade') || t.includes('guard')) return REPLIES.fade;
  if (t.includes('beard')) return REPLIES.beard;
  if (t.includes('remember') || t.includes('usual') || t.includes('last time') || t.includes('memory')) return REPLIES.memory;
  if (t.includes('wait') || t.includes('cancel')) return REPLIES.waitlist;
  if (t.includes('book') || t.includes('slot') || t.includes('thu') || t.includes('jay')) return REPLIES.book;
  if (t.includes('walk')) return REPLIES.walk;
  return REPLIES.default;
}

interface Props {
  onBookClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function StudioClientChat({ onBookClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="studio"
      brandName="Style Memory DM"
      aiLabel="Style memory AI"
      statusText="IG + WhatsApp · booking live"
      greeting={GREETING}
      capabilityChips={['Remembers your fade', 'Books from DMs', 'Fills cancellations']}
      hookProof="71% rebook when AI DM\'s regulars · chairs stay full"
      quickReplies={['My usual fade', 'Waitlist me', 'Book Jay Thu']}
      fabLabel="DM → chair locked"
      fabBadge="Memory"
      placeholder="Fade, beard, wait time…"
      poweredByText="Barbers cut. AI books, reminds, and rebooks."
      ctaLabel="Lock my chair"
      onCtaClick={onBookClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Studio Nine DM booking"
    />
  );
}
