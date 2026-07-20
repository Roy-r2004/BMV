import { AiFeatureDeck, AiFeaturePanel, PublicNav, PublicShell, type AiFeatureItem } from '@/ui';

const FEATURES: AiFeatureItem[] = [
  {
    id: 'studio-faq-assistant',
    name: 'Studio FAQ assistant',
    description: 'Answers glaze and firing questions for shoppers',
    category: 'chat',
    demo_hint: 'Ask something a real pottery studio customer would ask Clay & Kiln',
    demo_prompts: [
      'What should I know about glaze and firing?',
      'How does Studio FAQ assistant work at Clay & Kiln?',
      'Can beginners get help with kiln firing this week?',
    ],
    demo_results: {
      'What should I know about glaze and firing?':
        'Clay & Kiln: For “What should I know about glaze and firing?” — answers glaze and firing questions for shoppers. Here’s the short answer, what to prepare, and when a human should join.',
      'How does Studio FAQ assistant work at Clay & Kiln?':
        'Clay & Kiln: “How does Studio FAQ assistant work at Clay & Kiln?” — we walk customers through glaze and firing step by step, including timing, cost cues, and the next action to take.',
      'Can beginners get help with kiln firing this week?':
        'Clay & Kiln: Yes — for “Can beginners get help with kiln firing this week?”, the assistant qualifies the request, shares what kiln firing involves, and offers the best next booking path.',
    },
    placement_label: 'Customer assistant',
    placement_path: '/faq',
    placement_title: 'FAQ',
  },
  {
    id: 'class-waitlist-ai',
    name: 'Class waitlist AI',
    description: 'Predicts no-shows and fills open seats',
    category: 'automation',
    demo_hint: 'Trigger the automation Clay & Kiln actually needs',
    demo_prompts: [
      'Notify the next person waiting for class seats',
      'Chase what’s missing for glaze and firing',
      'Run tonight’s follow-ups for Clay & Kiln',
    ],
    demo_results: {
      'Notify the next person waiting for class seats':
        'Automation for “Notify the next person waiting for class seats”: message drafted, spot held for 30 minutes, next guest in line ready if they decline.',
      'Chase what’s missing for glaze and firing':
        'Chase sequence for “Chase what’s missing for glaze and firing”: reminder #1 sent about glaze and firing, escalates tomorrow if still open.',
      'Run tonight’s follow-ups for Clay & Kiln':
        'Tonight’s follow-ups for Clay & Kiln are queued — review → approve → run. Covers class seats and glaze and firing.',
    },
    placement_label: 'Automation',
    placement_path: '/classes',
    placement_title: 'Classes',
  },
  {
    id: 'owner-daily-digest',
    name: 'Owner daily digest',
    description: 'Summarizes orders and kiln status each morning',
    category: 'digest',
    demo_hint: "Generate today's brief for Clay & Kiln",
    demo_prompts: [
      'Summarize kiln status for today',
      'What needs attention around orders?',
      'Top priorities for Clay & Kiln',
    ],
    demo_results: {
      'Summarize kiln status for today':
        'Daily brief — “Summarize kiln status for today”: 3 priorities · 1 risk · 1 win tied to kiln status. Owner can act in under a minute.',
      'What needs attention around orders?':
        'Attention list for “What needs attention around orders?”: overdue follow-ups, capacity risk on orders, and one customer waiting on a reply.',
      'Top priorities for Clay & Kiln':
        "Top priorities for Clay & Kiln: protect today's kiln status, clear the orders queue, and confirm tomorrow's commitments.",
    },
    placement_label: 'Owner digest',
    placement_path: '/owner/dashboard',
    placement_title: 'Dashboard',
  },
];

/** Local demo of the AI feature chat stage (hub + in-context panel). */
export default function AiFeaturesReferencePage() {
  return (
    <PublicShell
      brandName="Clay & Kiln"
      nav={
        <PublicNav
          items={[
            { label: 'AI features', href: '/_catalogue/ai' },
            { label: 'Public catalogue', href: '/_catalogue/public' },
          ]}
        />
      }
    >
      <AiFeatureDeck features={FEATURES} brandName="Clay & Kiln" />
      <div className="mx-auto max-w-3xl px-6 pb-20 sm:px-10">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.2em] text-neutral-500">
          In-context panel (as on FAQ / Classes)
        </p>
        <AiFeaturePanel feature={FEATURES[0]} brandName="Clay & Kiln" />
      </div>
    </PublicShell>
  );
}
