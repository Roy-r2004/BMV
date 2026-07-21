import { IconGift, IconInspiration, IconTarget } from '../icons/SubmitIcons';

const TIPS = [
  {
    Icon: IconTarget,
    title: 'Be specific',
    text: 'The more detail you share, the sharper your custom preview becomes.',
    chip: 'Be specific',
  },
  {
    Icon: IconInspiration,
    title: 'Any reference works',
    text: 'A booking app, chatbot, dashboard — if you like it, we adapt the experience.',
    chip: 'Share inspiration',
  },
  {
    Icon: IconGift,
    title: 'Free preview',
    text: 'Custom concept, fit score, and visual demo — no cost, no commitment.',
    chip: 'Free preview',
  },
] as const;

function TipCard({ tip }: { tip: (typeof TIPS)[number] }) {
  const { Icon, title, text } = tip;
  return (
    <div className="rounded-2xl bg-white border border-blue-100/80 shadow-sm p-5">
      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center mb-3">
        <Icon className="w-5 h-5" />
      </div>
      <p className="font-bold text-navy text-sm mb-1">{title}</p>
      <p className="text-slate-500 leading-relaxed text-xs">{text}</p>
    </div>
  );
}

/** Mobile: compact chips. Desktop: full tip cards in the sidebar. */
export default function SubmitTips({ desktopOnly = false }: { desktopOnly?: boolean }) {
  if (desktopOnly) {
    return (
      <aside className="space-y-4 sticky top-24">
        {TIPS.map((tip) => (
          <TipCard key={tip.title} tip={tip} />
        ))}
        <div className="rounded-2xl border border-slate-800 bg-navy p-5 text-white">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-cyan-300/90 mb-2">
            What you get
          </p>
          <ul className="space-y-2.5 text-xs text-white/75">
            {['MVP blueprint', 'Business-fit score', 'Visual product demo', 'Technical plan outline'].map(
              (item) => (
                <li key={item} className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" />
                  {item}
                </li>
              ),
            )}
          </ul>
        </div>
      </aside>
    );
  }

  return (
    <div className="submit-tips-mobile lg:hidden" aria-label="Tips">
      {TIPS.map((tip) => (
        <span key={tip.chip}>{tip.chip}</span>
      ))}
    </div>
  );
}
