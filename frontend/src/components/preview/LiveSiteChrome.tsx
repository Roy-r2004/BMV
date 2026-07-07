import type { ReactNode } from 'react';

export type SectionId = 'top' | 'features' | 'how-it-works' | 'chat' | 'dashboard';

interface NavItem {
  id: SectionId;
  label: string;
}

interface Props {
  productName: string;
  primary: string;
  secondary: string;
  primaryCta: string;
  nav: NavItem[];
  active: SectionId;
  onNav: (id: SectionId) => void;
  children: ReactNode;
}

export default function LiveSiteChrome({
  productName,
  primary,
  primaryCta,
  nav,
  active,
  onNav,
  children,
}: Props) {
  return (
    <div className="live-chrome bg-white min-h-full flex flex-col">
      <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-14 sm:h-16 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => onNav('top')}
            className="flex items-center gap-2.5 shrink-0 group"
          >
            <span
              className="w-9 h-9 rounded-xl flex items-center justify-center text-white text-sm font-bold shadow-md group-hover:scale-105 transition-transform"
              style={{ background: `linear-gradient(135deg, ${primary}, #818cf8)` }}
            >
              {productName.charAt(0)}
            </span>
            <span className="font-semibold text-slate-900 text-sm sm:text-base tracking-tight">
              {productName}
            </span>
          </button>

          <nav className="hidden md:flex items-center gap-1">
            {nav.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => onNav(item.id)}
                className={`px-3.5 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                  active === item.id
                    ? 'text-white shadow-md'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                }`}
                style={active === item.id ? { backgroundColor: primary } : undefined}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <button
            type="button"
            onClick={() => onNav('chat')}
            className="shrink-0 px-4 sm:px-5 py-2 rounded-full text-white text-xs sm:text-sm font-semibold shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all"
            style={{ backgroundColor: primary, boxShadow: `0 8px 24px ${primary}35` }}
          >
            {primaryCta}
          </button>
        </div>

        <div className="md:hidden flex gap-1 px-4 pb-3 overflow-x-auto scrollbar-none">
          {nav.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onNav(item.id)}
              className={`shrink-0 px-3 py-1.5 rounded-full text-xs font-medium ${
                active === item.id ? 'text-white' : 'text-slate-600 bg-slate-100'
              }`}
              style={active === item.id ? { backgroundColor: primary } : undefined}
            >
              {item.label}
            </button>
          ))}
        </div>
      </header>
      {children}
    </div>
  );
}
