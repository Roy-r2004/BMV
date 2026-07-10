import { Outlet, NavLink } from 'react-router-dom';
import { brand, navigation } from '../data/mock';

export default function AdminLayout() {
  const links = navigation?.admin ?? [];

  return (
    <div className="flex min-h-screen bg-slate-100">
      <aside className="hidden w-72 shrink-0 flex-col border-r border-slate-800 bg-slate-950 md:flex">
        <div className="border-b border-white/5 px-6 py-8">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Admin</p>
          <p className="mt-2 text-xl font-bold text-white">{brand?.name ?? 'Dashboard'}</p>
        </div>
        <nav className="flex flex-col gap-1 p-4">
          {links.map((link) => (
            <NavLink
              key={link.path}
              to={link.path}
              className={({ isActive }) =>
                `rounded-xl px-4 py-3 text-sm font-medium transition ${
                  isActive
                    ? 'bg-brand text-white shadow-lg shadow-brand/20'
                    : 'text-slate-400 hover:bg-white/5 hover:text-white'
                }`
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white px-6 py-5 lg:px-10">
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-400">Admin</p>
          <h1 className="mt-1 text-2xl font-bold text-slate-900">{brand?.name ?? 'Dashboard'}</h1>
        </header>
        <main className="flex-1 overflow-auto p-6 lg:p-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
