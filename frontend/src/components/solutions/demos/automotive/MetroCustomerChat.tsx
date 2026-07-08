import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  "Metro Service Bot — book an oil change, tire rotation, or diagnostics in under a minute. I'll assign the right lift and send live repair progress to your phone.";

const REPLIES: Record<string, string> = {
  oil: 'Oil change booked ✓ Synthetic 5W-30 · Bay 2 (quick-service lift) · ~35 min. Drop keys at the desk or stay in the lounge — Status Bot texts each stage.',
  rotate: 'Tire rotation queued ✓ Alignment rack (Bay 1) preferred. AI will measure tread and flag uneven wear for upsell if needed. Slot locked for today 4:00 PM.',
  diag: 'Diagnostics scheduled ✓ Diag station Bay 4 · scanner calibrated. Send the check-engine code if you have it — or we pull codes on arrival. Est. 60 min.',
  status: 'Priya Nair — Bay 1 · Rotating tires (55%). Next: quality check → ready text. No need to call the front desk — Status Bot pushes live progress.',
  brakes: 'Brake service needs heavy-duty lift (Bay 3). Pads staged; ETA once parts clear hold. Typical $220–$480 depending on rotors. Want me to hold a slot?',
  upsell: 'Staff see Maintenance AI alerts: uneven wear → alignment (+$129), clogged cabin filter (+$48). You only approve — we never surprise-charge.',
  default: 'Say "oil change", "tire rotation", "diagnostics", or "is my car ready?" — I book, assign a bay by job type, and stream repair progress.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('oil') || t.includes('lube') || t.includes('synthetic')) return REPLIES.oil;
  if (t.includes('tire') || t.includes('rotat') || t.includes('balance')) return REPLIES.rotate;
  if (t.includes('diag') || t.includes('check engine') || t.includes('scan') || t.includes('code')) return REPLIES.diag;
  if (t.includes('status') || t.includes('ready') || t.includes('progress') || t.includes('where') || t.includes('car')) return REPLIES.status;
  if (t.includes('brake') || t.includes('pad') || t.includes('rotor')) return REPLIES.brakes;
  if (t.includes('upsell') || t.includes('align') || t.includes('recommend') || t.includes('filter')) return REPLIES.upsell;
  return REPLIES.default;
}

interface Props {
  onBookClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function MetroCustomerChat({ onBookClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="metro"
      brandName="Service Bot"
      aiLabel="Bay assistant"
      statusText="Book · bay · live status"
      greeting={GREETING}
      capabilityChips={['Book service', 'Bay assignment', 'Live progress']}
      hookProof="4.8★ · 92% bay utilization · fewer 'is it ready?' calls"
      quickReplies={['Book oil change', 'Tire rotation', "Is my car ready?"]}
      fabLabel="Book service"
      fabBadge="Service AI"
      placeholder="Oil change, diagnostics, status…"
      poweredByText="Full bays · fewer phone calls"
      ctaLabel="Book a bay"
      onCtaClick={onBookClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Metro Auto Care service assistant"
    />
  );
}
