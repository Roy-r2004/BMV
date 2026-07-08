import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import { DONATE_TIERS, storyForAmount, VOLUNTEER_OPPS } from './harborFundData.ts';
import '../../../../styles/showcase-chat.css';

const GREETING =
  "Harbor Give AI — I suggest donation amounts with real impact stories, match volunteers to open shifts, and send personalized thank-you receipts. What would you like to do?";

const REPLIES: Record<string, string> = {
  donate:
    'Smart suggest: $50 (Neighbor) — funds 1 week of tutoring supplies. $100 keeps a family grocery box for a month. Want a one-time gift or monthly?',
  impact:
    'Your $50 last month helped serve 3,200 pier-kitchen meals. Campaign AI routes gifts to the highest-need queue within the hour.',
  volunteer:
    'Skill match live: Pier kitchen (kitchen + logistics) 94% · After-school tutoring 88% · Grocery distribution 82%. Tell me your skills and I’ll place you.',
  thank:
    'Thank-you automation: personalized PDF receipt + impact story emailed in under 60 seconds. Maya’s $50 receipt cited meals @ the pier kitchen.',
  monthly:
    'Monthly Anchor $100 — Impact story auto-sent each billing cycle. You can pause anytime. Elena just upgraded from one-time to monthly via SMS.',
  campaign:
    'Bridge the Gap 2026: $186,420 of $250,000 (75%). 1,842 donors · 42 days left. First-time segment grew 18% this week.',
  default:
    'Ask about donate amounts, volunteer matching, thank-you receipts, or campaign progress — I’ll guide with impact stories.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('thank') || t.includes('receipt')) return REPLIES.thank;
  if (t.includes('month') || t.includes('recurring')) return REPLIES.monthly;
  if (t.includes('campaign') || t.includes('goal') || t.includes('bridge')) return REPLIES.campaign;
  if (t.includes('volunteer') || t.includes('skill') || t.includes('shift') || t.includes('match')) {
    const top = VOLUNTEER_OPPS[0];
    return `Top match: ${top.title} (${top.when}) — needs ${top.skills.join(' + ')}. ${REPLIES.volunteer}`;
  }
  if (t.includes('impact') || t.includes('story') || t.includes('meal')) return REPLIES.impact;
  if (t.includes('donate') || t.includes('gift') || t.includes('give') || t.includes('$')) {
    const suggested = DONATE_TIERS.find((d) => d.suggested) ?? DONATE_TIERS[1];
    const story = storyForAmount(suggested.amount);
    return `Suggested $${suggested.amount} (${suggested.label}): ${suggested.impact}. Impact story: ${story.title} — ${story.metric}.`;
  }
  return REPLIES.default;
}

interface Props {
  onDonateClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function HarborDonorChat({ onDonateClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="harborfund"
      brandName="Harbor Give AI"
      aiLabel="Donation + volunteer AI"
      statusText="Impact matching live"
      greeting={GREETING}
      capabilityChips={['Smart donate', 'Volunteer match', 'Thank-you bot', 'Campaign AI']}
      hookProof="$240k raised this quarter · 1,200 volunteers placed"
      quickReplies={['Suggest my gift amount', 'Match me to a shift', 'Send thank-you receipt']}
      fabLabel="Ask Harbor AI"
      fabBadge="Give"
      placeholder="Donate, volunteer, impact…"
      poweredByText="Gifts & skills matched to real community need."
      ctaLabel="Start a donation"
      onCtaClick={onDonateClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Harbor Community Fund donation assistant"
    />
  );
}
