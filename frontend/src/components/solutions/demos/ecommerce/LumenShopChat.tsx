import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'Lumen Shopper AI — describe the room or vibe and I\'ll find pieces that fit. Track orders and start returns right here too.';

const REPLIES: Record<string, string> = {
  search:
    'For a warm minimalist bedroom: Halo table lamp ($96), Cloud weave throw ($78), and Matte ceramic vase ($42). I bundled them — save $32 vs buying separately.',
  bundle:
    'Our "Warm minimalist bedroom" bundle is AI-curated: lamp, throw, vase, pillows. $264 bundled · ships free. Want me to add it to cart?',
  order:
    'Order #LM-48291 is out for delivery today by 6 PM via UPS. Tracking link sent to your email. Need a return label instead?',
  return:
    'Return label ready — pickup scheduled Wed. Refund hits in 3–5 days once scanned. No restocking fee on lighting.',
  stock:
    'Round brass mirror and ceramic vase are low stock (6–8 left). I can hold one for 24h if you\'re deciding.',
  default: 'Try "warm minimalist lamp for bedroom", ask about a bundle, or say "where\'s my order #LM-48291".',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('lamp') || t.includes('bedroom') || t.includes('minimal') || t.includes('warm') || t.includes('search'))
    return REPLIES.search;
  if (t.includes('bundle') || t.includes('set') || t.includes('curat')) return REPLIES.bundle;
  if (t.includes('order') || t.includes('track') || t.includes('ship') || t.includes('where')) return REPLIES.order;
  if (t.includes('return') || t.includes('exchange') || t.includes('refund')) return REPLIES.return;
  if (t.includes('stock') || t.includes('left') || t.includes('available')) return REPLIES.stock;
  return REPLIES.default;
}

interface Props {
  onShopClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function LumenShopChat({ onShopClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="lumen"
      brandName="Shopper AI"
      aiLabel="Search & order AI"
      statusText="Natural search · bundles · order help"
      greeting={GREETING}
      capabilityChips={['Style search', 'Curated bundles', 'Order & returns']}
      hookProof="68% of shoppers find items faster with AI search"
      quickReplies={['Warm lamp for bedroom', 'Where\'s my order?', 'Start a return']}
      fabLabel="Shop with AI"
      fabBadge="Shopper"
      placeholder="Describe what you're looking for…"
      poweredByText="Turn vague ideas into shoppable sets"
      ctaLabel="View AI bundle"
      onCtaClick={onShopClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Lumen shopper and order assistant"
    />
  );
}
