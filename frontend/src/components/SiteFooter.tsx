import { Link, type To } from 'react-router-dom';
import Logo from './Logo';

type FooterLink = { to: To; label: string };

const PRODUCT_LINKS: FooterLink[] = [
  { to: '/demo', label: 'Start a consultation' },
  { to: '/solutions', label: 'Solutions' },
  { to: '/private-ai', label: 'Private AI' },
];

const COMPANY_LINKS: FooterLink[] = [
  { to: '/about', label: 'About us' },
  { to: { pathname: '/about', hash: 'process' }, label: 'How an engagement runs' },
  { to: '/login', label: 'Sign in' },
];

export default function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="site-footer relative bg-navy text-white overflow-hidden">
      <div className="h-px bg-gradient-to-r from-transparent via-cyan-400/80 to-transparent" />
      <div className="absolute inset-0 cinematic-grid opacity-[0.04] pointer-events-none invert" />
      <div className="absolute -top-32 right-0 w-96 h-96 rounded-full bg-blue-500/10 blur-3xl pointer-events-none" />

      <div className="container-max relative px-4 sm:px-6 pt-14 pb-8">
        <div className="grid grid-cols-1 md:grid-cols-12 gap-10 lg:gap-12 mb-12">
          <div className="md:col-span-5 lg:col-span-4">
            <Logo to="/" size="md" showName theme="dark" />
            <p className="mt-4 text-sm text-slate-400 leading-relaxed max-w-sm">
              A consultancy in your browser. It tests your question against your own figures and tells you what to do, with every number traced to where it came from.
            </p>
            <div className="mt-5 inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-xs text-slate-300">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-60" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-400" />
              </span>
              BMV · Registered in Dubai, United Arab Emirates
            </div>
          </div>

          <div className="md:col-span-3 lg:col-span-2 md:col-start-7 lg:col-start-6">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-300 mb-4">Product</p>
            <ul className="space-y-3">
              {PRODUCT_LINKS.map((l) => (
                <li key={l.label}>
                  <Link
                    to={l.to}
                    className="text-sm text-slate-400 hover:text-white transition-colors duration-200 inline-flex items-center gap-1 group"
                  >
                    <span className="w-0 group-hover:w-2 h-px bg-cyan-400 transition-all duration-200" />
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="md:col-span-3 lg:col-span-2">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-300 mb-4">Company</p>
            <ul className="space-y-3">
              {COMPANY_LINKS.map((l) => (
                <li key={l.label}>
                  <Link
                    to={l.to}
                    className="text-sm text-slate-400 hover:text-white transition-colors duration-200 inline-flex items-center gap-1 group"
                  >
                    <span className="w-0 group-hover:w-2 h-px bg-cyan-400 transition-all duration-200" />
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div className="md:col-span-12 lg:col-span-3 lg:col-start-10">
            <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-blue-300 mb-4">Start now</p>
            <p className="text-sm text-slate-400 mb-4 leading-relaxed">
              Say what you're trying to work out. It asks one question at a time and comes back with an answer you can check.
            </p>
            <Link
              to="/demo"
              className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl bg-gradient-to-r from-blue-600 to-cyan-500 text-white text-sm font-semibold shadow-lg shadow-blue-500/25 hover:shadow-blue-500/40 hover:-translate-y-0.5 transition-all duration-300"
            >
              Start a consultation
            </Link>
          </div>
        </div>

        <div className="pt-8 border-t border-white/10 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-slate-500">
          <p>
            © {year} <span className="text-slate-400 font-medium">Build My Version</span>
            {' '}· BMV AI
          </p>
          <div className="flex gap-6">
            <Link to="/solutions" className="hover:text-slate-300 transition-colors">Solutions</Link>
            <Link to="/about" className="hover:text-slate-300 transition-colors">About</Link>
            <Link to="/private-ai" className="hover:text-slate-300 transition-colors">Private AI</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
