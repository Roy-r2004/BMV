const ICONS: Record<string, string> = {
  users: '👥', sparkles: '✨', chart: '📊', bell: '🔔', calendar: '📅',
  chat: '💬', shield: '🛡️', zap: '⚡', heart: '❤️', star: '⭐',
  default: '🚀',
};

interface Props {
  headline: string;
  subheadline: string;
  primaryCta: string;
  secondaryCta: string;
  primaryColor?: string;
  productName?: string;
}

export default function ProductHeroMockup({ headline, subheadline, primaryCta, secondaryCta, primaryColor = '#2563eb', productName }: Props) {
  return (
    <div className="rounded-2xl overflow-hidden border border-slate-200 shadow-lg">
      <div className="bg-slate-800 px-4 py-2 flex items-center gap-2">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-400" />
          <div className="w-3 h-3 rounded-full bg-yellow-400" />
          <div className="w-3 h-3 rounded-full bg-green-400" />
        </div>
        <span className="text-slate-400 text-xs ml-2">{productName || 'your-product.com'}</span>
      </div>
      <div className="p-8 sm:p-12 text-center" style={{ background: `linear-gradient(135deg, ${primaryColor}15, ${primaryColor}05)` }}>
        <h2 className="text-2xl sm:text-3xl font-bold text-navy mb-3">{headline}</h2>
        <p className="text-slate-600 max-w-lg mx-auto mb-6">{subheadline}</p>
        <div className="flex gap-3 justify-center flex-wrap">
          <button className="px-6 py-2.5 rounded-lg text-white font-semibold text-sm" style={{ backgroundColor: primaryColor }}>
            {primaryCta}
          </button>
          <button className="px-6 py-2.5 rounded-lg border-2 font-semibold text-sm" style={{ borderColor: primaryColor, color: primaryColor }}>
            {secondaryCta}
          </button>
        </div>
      </div>
    </div>
  );
}

export function getIcon(name: string) {
  return ICONS[name] || ICONS.default;
}
