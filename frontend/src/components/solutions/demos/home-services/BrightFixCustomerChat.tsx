import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';
import '../../../../styles/showcase-chat.css';

const GREETING =
  'BrightFix Quote AI — describe the job, send photos, and I\'ll price it and dispatch the nearest tech. Emergency? Say "burst pipe" and we move now.';

const REPLIES: Record<string, string> = {
  emergency:
    'Emergency flagged ✓ Nearest tech Mike R. is 12 min from Central — I\'ve sent your photos to dispatch. Shut off the main valve if you can; ETA text incoming.',
  leak: 'Active leak — $185–$420 typical. Send a photo of the shutoff and I\'ll confirm parts. South Austin has 2 techs free; dispatch score 94.',
  drain: 'Clogged drain runs $120–$280. If it\'s backing up into other fixtures, that\'s sewer — higher priority. Want today or this week?',
  heater: 'No hot water — often thermocouple ($180) or full unit ($1,200+). How old is the heater? I\'ll match HVAC-plumb certified tech.',
  quote: 'I\'ve got job type, urgency, and zone. Ballpark $165–$385 for drain work in Central. Confirm and I\'ll route to dispatch — avg 4 min to assign.',
  status: 'James T. — tech Sara is on-site at Congress Ave (in progress). You\'ll get "done" + review link automatically. No need to call the office.',
  review: 'Post-job review bot sent Linda W. a Google link 12m after close — she left 5★. We only ask happy customers; protects your rating.',
  default: 'Job type, photos, urgency, or "where\'s my tech?" — I quote, dispatch, and send live status without phone tag.',
};

function aiReply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('emergency') || t.includes('burst') || t.includes('flood') || t.includes('spray')) return REPLIES.emergency;
  if (t.includes('leak') || t.includes('pipe') || t.includes('water')) return REPLIES.leak;
  if (t.includes('drain') || t.includes('clog') || t.includes('sink') || t.includes('toilet')) return REPLIES.drain;
  if (t.includes('heater') || t.includes('hot water')) return REPLIES.heater;
  if (t.includes('quote') || t.includes('price') || t.includes('cost') || t.includes('how much')) return REPLIES.quote;
  if (t.includes('status') || t.includes('where') || t.includes('eta') || t.includes('tech')) return REPLIES.status;
  if (t.includes('review') || t.includes('google') || t.includes('star')) return REPLIES.review;
  return REPLIES.default;
}

interface Props {
  onQuoteClick?: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export default function BrightFixCustomerChat({ onQuoteClick, open, onOpenChange }: Props) {
  return (
    <ShowcaseChatWidget
      theme="brightfix"
      brandName="Quote AI"
      aiLabel="Dispatch assistant"
      statusText="Quote · dispatch · live status"
      greeting={GREETING}
      capabilityChips={['Instant quote', 'Photo intake', 'Auto dispatch']}
      hookProof="4.9★ · avg 4 min quote-to-dispatch"
      quickReplies={['Burst pipe emergency', 'Get a quote', 'Where\'s my tech?']}
      fabLabel="Get a quote"
      fabBadge="Quote AI"
      placeholder="Describe the job or upload issue…"
      poweredByText="Fewer calls · fuller schedules"
      ctaLabel="Start quote wizard"
      onCtaClick={onQuoteClick}
      onReply={aiReply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="BrightFix quote and dispatch assistant"
    />
  );
}
