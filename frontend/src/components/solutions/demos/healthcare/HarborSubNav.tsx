interface Item<T extends string> {
  id: T;
  label: string;
  badge?: number;
}

interface Props<T extends string> {
  items: Item<T>[];
  active: T;
  onChange: (id: T) => void;
  className?: string;
}

export default function HarborSubNav<T extends string>({ items, active, onChange, className = '' }: Props<T>) {
  return (
    <nav className={`hc-subnav ${className}`} aria-label="Section navigation">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          className={`hc-subnav__btn ${active === item.id ? 'hc-subnav__btn--active' : ''}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {item.badge != null && item.badge > 0 && (
            <span className="hc-subnav__badge">{item.badge}</span>
          )}
        </button>
      ))}
    </nav>
  );
}
