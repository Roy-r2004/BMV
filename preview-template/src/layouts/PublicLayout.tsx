import { Outlet } from 'react-router-dom';
import Nav from '../components/Nav';
import { brand, navigation } from '../data/mock';

export default function PublicLayout() {
  const items = navigation?.public ?? [];
  const bookPath =
    items.find((i) => /book/i.test(i.label))?.path ?? items[1]?.path ?? items[0]?.path ?? '/';

  return (
    <div className="flex min-h-screen flex-col bg-white">
      <Nav
        brandName={brand?.name ?? 'Brand'}
        items={items}
        cta={{ path: bookPath, label: 'Book Now' }}
      />
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-slate-950 px-6 py-14 text-center">
        <p className="text-lg font-semibold text-white">{brand?.name ?? 'Brand'}</p>
        <p className="mt-2 text-sm text-slate-400">{brand?.tagline ?? 'Premium experience, built for you.'}</p>
        <p className="mt-6 text-xs text-slate-500">
          © {new Date().getFullYear()} {brand?.name ?? 'Brand'}. All rights reserved.
        </p>
      </footer>
    </div>
  );
}
