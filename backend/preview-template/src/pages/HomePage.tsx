import Nav from '../components/Nav';
import { brand, images, navigation, services } from '../data/mock';

export default function HomePage() {
  const ctaLink = navigation.public.find((l) => l.path.includes('book')) ?? navigation.public.at(-1);

  return (
    <>
      <Nav cta={ctaLink ? { path: ctaLink.path, label: ctaLink.label } : undefined} />
      <section className="relative flex min-h-[85vh] items-center overflow-hidden">
        <img src={images.hero} alt="" className="absolute inset-0 h-full w-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/50 to-black/30" />
        <div className="relative mx-auto max-w-7xl px-6 py-24">
          <span className="mb-4 inline-block rounded-full bg-white/10 px-4 py-1 text-xs font-semibold uppercase tracking-wider text-white">
            Welcome
          </span>
          <h1 className="max-w-2xl text-5xl font-extrabold tracking-tight text-white md:text-6xl">
            {brand.name}
          </h1>
          <p className="mt-4 max-w-xl text-lg text-slate-200">{brand.tagline}</p>
          <div className="mt-8 flex flex-wrap gap-4">
            <a href="/book" className="rounded-full bg-brand px-6 py-3 font-semibold text-white hover:bg-brand-dark">
              Book now
            </a>
            <a href="/services" className="rounded-full border-2 border-white px-6 py-3 font-semibold text-white hover:bg-white/10">
              View services
            </a>
          </div>
        </div>
      </section>
      <section className="bg-slate-50 py-20">
        <div className="mx-auto max-w-7xl px-6">
          <h2 className="text-3xl font-bold text-slate-900">Popular services</h2>
          <div className="mt-10 grid gap-6 md:grid-cols-3">
            {services.map((s) => (
              <div key={s.id} className="rounded-2xl border border-slate-100 bg-white p-6 shadow-sm">
                <h3 className="font-semibold text-slate-900">{s.name}</h3>
                <p className="mt-2 text-sm text-slate-600">{s.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
