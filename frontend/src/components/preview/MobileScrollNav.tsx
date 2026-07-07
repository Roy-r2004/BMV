interface NavItem {
  id: string;
  label: string;
}

interface Props {
  items: NavItem[];
  activeId: string;
  onSelect: (id: string) => void;
  primary: string;
  className?: string;
}

/** Horizontal pill nav for small screens (dashboard, inbox, etc.). */
export default function MobileScrollNav({ items, activeId, onSelect, primary, className = '' }: Props) {
  return (
    <div
      className={`preview-mobile-nav flex gap-1.5 p-2 overflow-x-auto border-b border-slate-200 bg-white scrollbar-none ${className}`}
    >
      {items.map((item) => {
        const active = activeId === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelect(item.id)}
            className={`shrink-0 px-3 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
              active ? 'text-white shadow-sm' : 'text-slate-600 bg-slate-50 hover:bg-slate-100'
            }`}
            style={active ? { backgroundColor: primary } : undefined}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
