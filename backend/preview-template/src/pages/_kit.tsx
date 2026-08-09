/**
 * DESIGN DRAFT — shared kit for the "speechless" salon face (Maison Noor).
 *
 * Not a real UI-kit module: a dev-only helper so the draft pages (Home,
 * Services, Team, Booking) share one nav, footer, data set and animation
 * vocabulary instead of drifting apart. None of this ships — see the header
 * comment in HomePage.tsx for the extraction plan.
 */
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Heart, Users, Clock, CalendarCheck, Volume2, VolumeX, Camera, Globe, MessageCircle } from 'lucide-react';

export const FONT_LINK =
  'https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300..700;1,9..144,300..700&family=Inter:wght@400;500;600&display=swap';

export const IMG = {
  hero: 'https://images.unsplash.com/photo-1600948836101-f9ffda59d250?auto=format&fit=crop&w=2000&q=80',
  heroVideo: 'https://videos.pexels.com/video-files/3996900/3996900-hd_2048_1080_25fps.mp4',
  bannerServices: 'https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?auto=format&fit=crop&w=2000&q=80',
  bannerTeam: 'https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=2000&q=80',
  bannerBooking: 'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=crop&w=2000&q=80',
  bannerGallery: 'https://images.unsplash.com/photo-1595476108010-b4d1f102b1b1?auto=format&fit=crop&w=2000&q=80',
  bannerContact: 'https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=2000&q=80',
  gallery: [
    'https://images.unsplash.com/photo-1562322140-8baeececf3df?auto=format&fit=crop&w=1200&q=80',
    'https://images.unsplash.com/photo-1560869713-7d0a29430803?auto=format&fit=crop&w=900&q=80',
    'https://images.unsplash.com/photo-1522337094846-8a818192de1f?auto=format&fit=crop&w=900&q=80',
    'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=crop&w=900&q=80',
    'https://images.unsplash.com/photo-1519014816548-bf5fe059798b?auto=format&fit=crop&w=900&q=80',
    'https://images.unsplash.com/photo-1487412947147-5cebf100ffc2?auto=format&fit=crop&w=900&q=80',
    'https://images.unsplash.com/photo-1470259078422-826894b933aa?auto=format&fit=crop&w=1200&q=80',
    'https://images.unsplash.com/photo-1633681926022-84c23e8cb2d6?auto=format&fit=crop&w=900&q=80',
  ],
  team: [
    'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=640&q=80',
    'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=640&q=80',
    'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?auto=format&fit=crop&w=640&q=80',
  ],
};

export const SALON = {
  name: 'Maison Noor',
  eyebrow: 'Salon & Atelier — Gemmayze, Beirut',
  sub: 'Color, cuts and rituals by a team that remembers exactly how you like it — and an AI front desk that never lets a booking slip.',
  address: 'Rue Gouraud 44, Gemmayze, Beirut',
  hours: 'Tue–Sat 10:00–20:00',
  whatsapp: '+961',
  categories: [
    {
      id: 'color',
      label: 'Color & dimension',
      image: 'https://images.unsplash.com/photo-1562322140-8baeececf3df?auto=format&fit=crop&w=900&q=80',
      services: [
        { name: 'Balayage / Lived-in color', desc: 'Hand-painted dimension, gloss and care plan.', dur: '150 min', price: '$140' },
        { name: 'Full color / root refresh', desc: 'Single-process color, tone-matched to you.', dur: '90 min', price: '$85' },
        { name: 'Gloss & shine treatment', desc: 'Ten-minute color refresh between full sessions.', dur: '30 min', price: '$35' },
      ],
    },
    {
      id: 'cut',
      label: 'Cut & style',
      image: 'https://images.unsplash.com/photo-1522337660859-02fbefca4702?auto=format&fit=crop&w=900&q=80',
      services: [
        { name: 'Signature cut & finish', desc: 'Consultation, precision cut, styling ritual.', dur: '60 min', price: '$45' },
        { name: 'Fades & barbering', desc: 'Sharp lines, hot towel finish.', dur: '45 min', price: '$35' },
        { name: 'Blowout', desc: 'Wash, dry, finish — no cut.', dur: '40 min', price: '$30' },
      ],
    },
    {
      id: 'treatment',
      label: 'Treatments',
      image: 'https://images.unsplash.com/photo-1580618672591-eb180b1a973f?auto=format&fit=crop&w=900&q=80',
      services: [
        { name: 'Keratin smoothing', desc: 'Frizz control that survives Beirut humidity.', dur: '120 min', price: '$180' },
        { name: 'The Noor ritual', desc: 'Scalp treatment, massage, blowout. Our quiet hour.', dur: '75 min', price: '$95' },
      ],
    },
    {
      id: 'bridal',
      label: 'Bridal & occasion',
      image: 'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?auto=format&fit=crop&w=900&q=80',
      services: [
        { name: 'Bridal trial', desc: 'Full look trial, notes kept for the day.', dur: '90 min', price: '$120' },
        { name: 'Day-of styling', desc: 'On-location available for the bridal party.', dur: '90 min', price: 'from $220' },
      ],
    },
  ],
  team: [
    { name: 'Rania', role: 'Color Director', years: '10+ years', bio: 'Trained in Paris; Beirut’s go-to for lived-in balayage.', specialties: ['Balayage', 'Color correction', 'Gloss'] },
    { name: 'Maya', role: 'Senior Stylist', years: '8+ years', bio: 'Precision cuts and the calmest hands in the room.', specialties: ['Signature cuts', 'Blowouts', 'Bridal'] },
    { name: 'Karim', role: 'Barber & Fades', years: '12+ years', bio: 'Sharp fades, hot towel finishes, zero rush.', specialties: ['Fades', 'Beard sculpting'] },
  ],
  testimonials: [
    { quote: 'The best color I’ve ever had in Beirut. Rania just gets it.', name: 'Lea M.', for: 'Balayage / Lived-in color' },
    { quote: 'Booked at midnight over WhatsApp, chair was ready when I walked in.', name: 'Nour K.', for: 'Signature cut & finish' },
    { quote: 'The Noor ritual is the calmest hour of my week.', name: 'Sami H.', for: 'The Noor ritual' },
  ],
  slots: ['4:30', '5:15', '6:00'],
};

export const TRUST_POINTS = [
  { icon: Heart, label: 'Bespoke results', note: 'Tailored to your hair, your lifestyle.' },
  { icon: Users, label: 'Expert team', note: 'Specialists in color, cut and care.' },
  { icon: Clock, label: 'Calm, private space', note: 'Your time. Your ritual.' },
  { icon: CalendarCheck, label: 'Always on time', note: 'Run by precision — not chaos.' },
];

export const ICONS = { Instagram: Camera, Facebook: Globe, MessageCircle, Volume2, VolumeX };

/** Scroll-choreography: children slide up as their section enters the viewport. */
export function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          io.disconnect();
          setInView(true);
        }
      },
      { threshold: 0.18 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <div ref={ref} className={`rv ${inView ? 'rv-in' : ''} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

export function SectionHeading({ index, children, note }: { index: string; children: ReactNode; note?: string }) {
  return (
    <Reveal className="flex items-end justify-between gap-6">
      <div className="flex items-baseline gap-5">
        <span className="font-display text-sm italic text-[var(--color-brand)]">{index}</span>
        <h2 className="font-display text-5xl font-light tracking-tight md:text-6xl">{children}</h2>
      </div>
      {note ? <span className="hidden pb-2 text-sm text-white/35 md:block">{note}</span> : null}
    </Reveal>
  );
}

export function Marquee() {
  const items = ['Balayage', 'Keratin', 'Bridal', 'Color', 'The Noor ritual', 'Fades'];
  const row = items.map((s) => (
    <span key={s} className="mx-8 inline-flex items-center gap-8 font-display text-4xl font-light uppercase tracking-wide md:text-6xl">
      <span className="marquee-ghost">{s}</span>
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--color-brand)]" />
    </span>
  ));
  return (
    <div className="relative overflow-hidden border-y border-white/[0.07] bg-[#0a0908] py-6" aria-hidden>
      <div className="marquee flex w-max">
        <div className="flex shrink-0 items-center">{row}</div>
        <div className="flex shrink-0 items-center">{row}</div>
      </div>
    </div>
  );
}

const NAV_LINKS: { label: string; href: string }[] = [
  { label: 'Services', href: '/services' },
  { label: 'The team', href: '/team' },
  { label: 'Gallery', href: '/gallery' },
  { label: 'Contact', href: '/contact' },
];

/** `transparent` overlays a hero (Home); `solid` is for every interior page. */
export function PublicHeader({ active, variant = 'solid' }: { active: string; variant?: 'transparent' | 'solid' }) {
  return (
    <header
      className={
        variant === 'transparent'
          ? 'absolute inset-x-0 top-0 z-20'
          : 'sticky top-0 z-20 border-b border-white/[0.08] bg-[#0c0b0a]/85 backdrop-blur-xl'
      }
    >
      <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-7">
        <a href="/" className="font-display text-2xl italic tracking-tight">Maison Noor</a>
        <nav className="hidden items-center gap-9 text-sm md:flex">
          {NAV_LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className={
                'transition ' +
                (active === l.href ? 'text-[var(--color-brand)]' : 'text-white/60 hover:text-white')
              }
            >
              {l.label}
            </a>
          ))}
        </nav>
        <a
          href="/booking"
          className="rounded-full border border-white/25 px-5 py-2.5 text-sm font-semibold text-white transition hover:border-[var(--color-brand)] hover:bg-[var(--color-brand)] hover:text-black"
        >
          Book now
        </a>
      </div>
    </header>
  );
}

export function PublicFooter() {
  return (
    <footer className="relative overflow-hidden border-t border-white/[0.08] pb-16 pt-20">
      <span className="ghost-word bottom-[-6rem] left-1/2 -translate-x-1/2" aria-hidden>Maison Noor</span>
      <div className="relative mx-auto flex max-w-7xl flex-col items-start justify-between gap-8 px-6 md:flex-row md:items-end">
        <div>
          <p className="font-display text-3xl italic">Maison Noor</p>
          <p className="mt-3 max-w-xs text-sm leading-relaxed text-white/40">
            {SALON.address} · {SALON.hours}
          </p>
        </div>
        <div className="flex items-center gap-4 text-white/40">
          <ICONS.Instagram className="h-4 w-4" />
          <ICONS.Facebook className="h-4 w-4" />
          <ICONS.MessageCircle className="h-4 w-4" />
          <p className="text-xs text-white/30">
            Answered around the clock by our AI front desk · WhatsApp {SALON.whatsapp}
          </p>
        </div>
      </div>
    </footer>
  );
}

/** The full shared animation vocabulary — identical on every draft page. */
export function GlobalStyles() {
  return (
    <style>{`
      @keyframes fd-up { from { opacity: 0; transform: translateY(28px); } to { opacity: 1; transform: none; } }
      .fd { animation: fd-up 0.9s var(--ease-out) both; }
      .intro-wait .fd { animation-play-state: paused; }
      .fd-1 { animation-delay: 0.08s; } .fd-2 { animation-delay: 0.18s; } .fd-3 { animation-delay: 0.3s; }
      @keyframes pop-in { from { opacity: 0; transform: translateY(10px) scale(0.97); } to { opacity: 1; transform: none; } }
      .pop { animation: pop-in 0.4s var(--ease-out) both; }
      @keyframes chip-pop { 0% { opacity: 0; transform: scale(0.8); } 70% { transform: scale(1.04); } 100% { opacity: 1; transform: scale(1); } }
      .chip-pop { animation: chip-pop 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
      @keyframes dot-bounce { 0%, 60%, 100% { opacity: 0.25; transform: none; } 30% { opacity: 1; transform: translateY(-3px); } }
      .dot { animation: dot-bounce 1.2s infinite; }
      .dot2 { animation-delay: 0.15s; } .dot3 { animation-delay: 0.3s; }
      .rv { opacity: 0; transform: translateY(36px); transition: opacity 0.9s var(--ease-out), transform 0.9s var(--ease-out); }
      .rv-in { opacity: 1; transform: none; }
      @keyframes marquee-x { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      .marquee { animation: marquee-x 48s linear infinite; }
      .marquee-ghost { color: transparent; -webkit-text-stroke: 1px rgb(255 255 255 / 0.16); }
      .ghost-word {
        position: absolute; font-family: var(--font-display); font-style: italic;
        font-size: clamp(10rem, 24vw, 22rem); line-height: 1; color: rgb(255 255 255 / 0.028);
        pointer-events: none; user-select: none; white-space: nowrap;
      }
    `}</style>
  );
}

export const THEME_VARS = {
  '--font-display': '"Fraunces", Georgia, serif',
  '--font-sans': '"Inter", "Segoe UI", system-ui, sans-serif',
  '--color-brand': '#c9a464',
  '--color-brand-dark': '#b08d4f',
  '--ease-out': 'cubic-bezier(0.22, 0.61, 0.36, 1)',
} as CSSProperties;

/** A simple photo banner for interior pages that don't carry the full-bleed video hero. */
export function PageBanner({ image, eyebrow, title }: { image: string; eyebrow: string; title: ReactNode }) {
  return (
    <section className="relative flex h-[46vh] min-h-[22rem] items-end overflow-hidden">
      <img src={image} alt="" className="absolute inset-0 h-full w-full object-cover" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#0c0b0a] via-black/40 to-black/10" />
      <div className="relative mx-auto w-full max-w-7xl px-6 pb-14">
        <p className="fd text-[12px] font-semibold uppercase tracking-[0.32em] text-[var(--color-brand)]">{eyebrow}</p>
        <h1 className="fd fd-1 mt-4 font-display text-[clamp(2.4rem,6vw,4.5rem)] font-light leading-[1.02]">{title}</h1>
      </div>
    </section>
  );
}
