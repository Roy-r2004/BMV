import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';

export interface DeliveryNavItem {
  id: string;
  label: string;
  short: string;
  ready: boolean;
}

interface Props {
  items: DeliveryNavItem[];
  embedded?: boolean;
  compact?: boolean;
}

export default function DeliveryNavigator({ items, embedded = false, compact = false }: Props) {
  const [active, setActive] = useState(items[0]?.id ?? '');

  useEffect(() => {
    const observers: IntersectionObserver[] = [];

    items.forEach((item) => {
      const el = document.getElementById(item.id);
      if (!el) return;

      const obs = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) setActive(item.id);
        },
        { rootMargin: '-25% 0px -60% 0px', threshold: 0 },
      );
      obs.observe(el);
      observers.push(obs);
    });

    return () => observers.forEach((o) => o.disconnect());
  }, [items]);

  const navigate = (id: string) => {
    setActive(id);
    // Live product + build plans live outside FullDeliveryPackage — scroll directly.
    if (id === 'live-product' || id === 'build-plans') {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    // Delivery sections listen for this event (expand accordion, then scroll).
    window.dispatchEvent(new CustomEvent('delivery-navigate', { detail: { sectionId: id } }));
  };

  const readyCount = items.filter((i) => i.ready).length;

  return (
    <div className={embedded ? '' : 'delivery-nav sticky top-[3.75rem] z-30 mb-8 -mx-4 sm:mx-0 px-4 sm:px-0'}>
      <div
        className={`rounded-2xl border border-slate-200/80 bg-white/95 backdrop-blur-xl shadow-lg shadow-slate-200/40 ${
          compact ? 'p-2' : 'p-3 sm:p-4'
        }`}
      >
        {!compact && (
          <div className="flex items-center justify-between gap-3 mb-3 px-1">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400">
              Full package
            </p>
            <span className="text-[10px] font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-full">
              {readyCount}/{items.length} sections
            </span>
          </div>
        )}
        <div className={`flex gap-1.5 overflow-x-auto scrollbar-none ${compact ? '' : 'pb-0.5'}`}>
          {items.map((item) => {
            const isActive = active === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => navigate(item.id)}
                className={`shrink-0 flex items-center gap-2 px-3 sm:px-3.5 py-2 rounded-xl text-xs sm:text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? 'bg-indigo-600 text-white shadow-md shadow-indigo-200'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                } ${!item.ready ? 'opacity-45' : ''}`}
              >
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    item.ready ? 'bg-emerald-400' : 'bg-slate-300'
                  } ${isActive ? 'bg-white/80' : ''}`}
                />
                <span className="hidden sm:inline">{item.label}</span>
                <span className="sm:hidden">{item.short}</span>
              </button>
            );
          })}
        </div>
        {!compact && (
          <div className="h-1 mt-3 rounded-full bg-slate-100 overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full"
              animate={{ width: `${(readyCount / Math.max(items.length, 1)) * 100}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
