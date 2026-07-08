import ShowcaseChatWidget from '../shared/ShowcaseChatWidget.tsx';

const GREETING =
  'Counsel AI — I run conflict checks, review clauses in uploads, chase your vault, and draft engagement letters. What matter are you opening?';

const REPLIES: Record<string, string> = {
  conflict:
    'Conflict scan complete for Chen LLC — no overlaps with 847 active matters. Clearance valid 30 days. Rachel Holt has Thu 10am once vault hits 75%.',
  clause:
    'Clause review flagged indemnity cap in vendor agreement §4.2 — liability uncapped in your draft. Partner brief queued for Rachel Holt.',
  vault:
    'Vault status: 2 of 4 verified. Cap table + signer ID chasing — reminders every 48h until upload. Partners only see billable-ready files.',
  engage:
    'Engagement letter 80% drafted from your matter brief. Final partner review after Thu consult — no re-asking basics.',
  consult:
    'Thu 10am corporate with Rachel Holt · Fri 2pm employment with Marcus Chen. Conflict cleared · vault link sent automatically.',
  corporate:
    'Corporate matter: conflict scan, clause review on vendor agreements, vault checklist. Most clients finish in 12 minutes — not 6 emails.',
  default:
    'Ask about conflict clearance, clause flags, vault status, or partner consults. Try "run conflict check" or "what\'s missing from vault?"',
};

function reply(text: string): string {
  const t = text.toLowerCase();
  if (t.includes('conflict') || t.includes('clear') || t.includes('clearance')) return REPLIES.conflict;
  if (t.includes('clause') || t.includes('indemn') || t.includes('contract') || t.includes('§')) return REPLIES.clause;
  if (t.includes('vault') || t.includes('doc') || t.includes('upload') || t.includes('missing') || t.includes('file')) return REPLIES.vault;
  if (t.includes('engage') || t.includes('letter') || t.includes('fee')) return REPLIES.engage;
  if (t.includes('consult') || t.includes('book') || t.includes('thursday') || t.includes('partner')) return REPLIES.consult;
  if (t.includes('corp') || t.includes('vendor') || t.includes('llc') || t.includes('saas')) return REPLIES.corporate;
  return REPLIES.default;
}

interface Props {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  onMatterClick?: () => void;
}

export default function ApexClientChat({ open, onOpenChange, onMatterClick }: Props) {
  return (
    <ShowcaseChatWidget
      theme="apex"
      brandName="Counsel AI"
      aiLabel="Legal automation"
      statusText="Conflict · clauses · vault · live"
      greeting={GREETING}
      capabilityChips={['Conflict scan', 'Clause review', 'Vault chaser', 'Engagement draft']}
      hookProof="9 billable-ready matters this week · 0 surprise conflicts"
      quickReplies={['Run conflict check', 'Review my clause risk', 'What\'s missing from vault?']}
      fabLabel="Counsel AI"
      fabBadge="Live"
      placeholder="Conflict, clauses, vault, consult…"
      poweredByText="Lawyers bill counsel — AI handles the admin layer"
      ctaLabel="Open matter"
      onCtaClick={onMatterClick}
      onReply={reply}
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel="Apex Counsel AI assistant"
    />
  );
}
