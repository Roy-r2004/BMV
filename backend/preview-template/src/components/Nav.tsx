import { Link, NavLink } from 'react-router-dom';

interface NavItem {
  path: string;
  label: string;
}

interface Props {
  brandName?: string;
  items?: NavItem[];
  cta?: { path: string; label: string };
}

export default function Nav({ brandName = 'Brand', items = [], cta }: Props) {
  return (
    <header className="sticky top-0 z-50 border-b border-slate-200/60 bg-white/95 backdrop-blur-lg shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-6 px-6 py-4 lg:px-8">
        <Link
          to={items[0]?.path ?? '/'}
          className="text-xl font-bold tracking-tight text-brand lg:text-2xl"
        >
          {brandName}
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
          {items.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === items[0]?.path}
              className={({ isActive }) =>
                `text-sm font-medium transition-colors ${isActive ? 'text-brand' : 'text-slate-600 hover:text-slate-900'}`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        {cta && (
          <Link
            to={cta.path}
            className="rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white shadow-md shadow-brand/25 transition hover:bg-brand-dark"
          >
            {cta.label}
          </Link>
        )}
      </div>
    </header>
  );
}
