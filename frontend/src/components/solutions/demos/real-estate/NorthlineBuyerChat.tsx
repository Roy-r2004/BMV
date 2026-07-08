import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';

const GREETING =
  'I\'m Northline Listing AI — HOA, schools, and comps answered on the listing page. Agents wake up to scored, booked viewings — not empty inquiry forms.';

const REPLIES: Record<string, string> = {
  hoa: '22 Oak Lane HOA $240/mo · parking included. Lead score jumped to 94 (budget match). Saturday 10am with Sarah is open — want it locked before another buyer grabs it?',
  schools: 'Williamsburg zone — PS 132 0.4 mi, MS 126 0.6 mi. I\'ll attach the school pack to your viewing invite so agents sound sharp without researching at midnight.',
  comp: 'Comps: Cedar Row $1.38M, Park View $965K condo. AI sheet lands with the tour — buyers feel informed, agents close faster.',
  score: 'Hot lead: $1.2–1.4M fits Oak Lane. Sarah gets the brief + suggested offer framing. Cold leads stay in nurture — no wasted dials.',
  viewing: 'Sat: Oak Lane 10am (Sarah) or Park View 11:30 (Elena). Calendars sync — zero "does Saturday work?" email chains.',
  valuation: 'Free AI valuation in 24h — address + beds. Sellers lean in; your pipeline fills without open-house grit alone.',
  default: 'Ask HOA, schools, comps, or "book tour" — I qualify + score so agents only chase people ready to move.',
};

function reply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('hoa') || t.includes('fee')) return REPLIES.hoa;
  if (t.includes('school') || t.includes('district')) return REPLIES.schools;
  if (t.includes('comp') || t.includes('compare') || t.includes('similar')) return REPLIES.comp;
  if (t.includes('score') || t.includes('qualified') || t.includes('hot')) return REPLIES.score;
  if (t.includes('view') || t.includes('tour') || t.includes('saturday') || t.includes('book')) return REPLIES.viewing;
  if (t.includes('valuat') || t.includes('worth') || t.includes('sell')) return REPLIES.valuation;
  return REPLIES.default;
}

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onViewingClick?: () => void;
}

export default function NorthlineBuyerChat({ open, onOpenChange, onViewingClick }: Props) {
  return (
    <ShowcaseChatWidget
      theme="northline"
      brandName="Listing AI Agent"
      aiLabel="Lead-scoring AI"
      statusText="MLS-aware · qualifies 24/7"
      greeting={GREETING}
      capabilityChips={['Instant HOA/school answers', 'Hot lead scores', 'Tour on calendar']}
      hookProof="23 qualified leads this week · under 2 min response"
      quickReplies={['HOA on Oak Lane?', 'Am I a hot lead?', 'Book Sat tour']}
      fabLabel="Ask this listing"
      fabBadge="Score"
      placeholder="HOA, schools, comps, tours…"
      poweredByText="Every listing works nights — agents get warm tours"
      ctaLabel="Book Saturday tour"
      onCtaClick={onViewingClick}
      onReply={reply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Northline listing AI assistant"
    />
  );
}
