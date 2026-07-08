import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'Row Concierge — room preferences, local picks, and late checkout without the front-desk hold music. Ask me anything.';

const REPLIES: Record<string, string> = {
  checkout:
    'Late checkout until 1 PM is open on Classic & Corner this weekend — I sync housekeeping so your room is flagged, not rushed. Direct guests skip the $75 fee OTA guests pay.',
  room:
    'Claire\'s profile remembers hypoallergenic bedding + firm pillows. I can apply them to your hold before arrival, and floor 5 will see it on the board.',
  local:
    'Three locals love tonight: Avec (walk 4 min), Untitled Supper Club (jazz after 9), and the riverwalk loop at dusk. Want a 7:30 reservation hold — I book under guest name.',
  book:
    'Corner Suite Fri–Sun is $778 direct — same dates run ~$890 on OTAs after fees. I hold it 15 minutes; no commission, your rate stays yours.',
  memory:
    'Sofia Kim · 4 stays · quiet high floor · sparkling water waiting. Returning guests get preference memory auto-applied — front desk just welcomes them.',
  default:
    'Preferences, late checkout, local tips, or a direct hold — I turn questions into rooms that are ready when guests walk in.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('checkout') || t.includes('late') || t.includes('extend')) return REPLIES.checkout;
  if (t.includes('pillow') || t.includes('allerg') || t.includes('pref') || t.includes('bedding') || t.includes('room')) return REPLIES.room;
  if (t.includes('restaurant') || t.includes('local') || t.includes('dinner') || t.includes('bar') || t.includes('nearby')) return REPLIES.local;
  if (t.includes('book') || t.includes('rate') || t.includes('ota') || t.includes('suite') || t.includes('avail')) return REPLIES.book;
  if (t.includes('return') || t.includes('remember') || t.includes('memory') || t.includes('again')) return REPLIES.memory;
  return REPLIES.default;
}

interface Props {
  onBookClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function RowGuestChat({ onBookClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="row"
      brandName="Row Concierge"
      aiLabel="Concierge AI"
      statusText="Prefs · local · late checkout"
      greeting={GREETING}
      capabilityChips={['Guest memory', 'Direct rates', 'HK sync']}
      hookProof="78% of stays book direct — zero OTA commission"
      quickReplies={['Late checkout?', 'Local dinner', 'Book Corner Suite']}
      fabLabel="Ask concierge"
      fabBadge="AI"
      placeholder="Prefs, late checkout, local tips…"
      poweredByText="Five-star answers at 2am · staff sleep"
      ctaLabel="Book direct — skip OTA fees"
      onCtaClick={onBookClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="The Row Hotel concierge"
    />
  );
}
