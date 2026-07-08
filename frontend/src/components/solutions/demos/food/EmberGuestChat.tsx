import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'Ember Menu Concierge — allergens, patio parties, and direct orders that skip the 30% app fee. Ask me anything on tonight\'s menu.';

const REPLIES: Record<string, string> = {
  allergen:
    'Cedar salmon + burrata are GF. Truffle pasta has dairy + gluten — I note it on the reservation so the kitchen never surprises a guest. Dietary trust = repeat covers.',
  party:
    'Patio holds 8 · Sat 7:45 open. I attach the set menu, candle add-on, and flag allergens to the floor — one thread, zero phone tag for the GM.',
  menu: 'Tonight\'s movers: truffle tagliatelle, oak ribeye, cedar salmon. Want a pairing? I\'ll upsell wine that actually fits — guests tip higher when they feel guided.',
  delivery: 'Order direct — no DoorDash cut. Avg 35 min, SMS when the driver leaves. Houses that stay direct keep ~$8–12 more per ticket.',
  table: 'Main ~35 min · bar has 2 seats · patio reserved for parties. Hold 7:45? I sync the table plan + kitchen in one tap.',
  default: 'Allergies, parties, pickup, or "what\'s good tonight" — I convert questions into reserved tables and kitchen tickets.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('gluten') || t.includes('allerg') || t.includes('dairy') || t.includes('gf')) return REPLIES.allergen;
  if (t.includes('party') || t.includes('birthday') || t.includes('group') || t.includes('patio')) return REPLIES.party;
  if (t.includes('deliver') || t.includes('pickup') || t.includes('order') || t.includes('fee')) return REPLIES.delivery;
  if (t.includes('menu') || t.includes('truffle') || t.includes('special') || t.includes('wine')) return REPLIES.menu;
  if (t.includes('table') || t.includes('reserv') || t.includes('wait')) return REPLIES.table;
  return REPLIES.default;
}

interface Props {
  onReserveClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function EmberGuestChat({ onReserveClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="ember"
      brandName="Menu Concierge"
      aiLabel="Menu & table AI"
      statusText="Allergens · parties · kitchen synced"
      greeting={GREETING}
      capabilityChips={['GF / allergen tag', 'Party planner', 'Keep 30% margins']}
      hookProof="34% of revenue now direct — no aggregator fees"
      quickReplies={['GF for 4?', 'Party of 8 Sat', 'Order direct']}
      fabLabel="Ask the menu"
      fabBadge="Concierge"
      placeholder="Allergies, party size, specials…"
      poweredByText="Turn dietary anxiety into reserved covers"
      ctaLabel="Reserve patio tonight"
      onCtaClick={onReserveClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Ember menu and reservation concierge"
    />
  );
}
