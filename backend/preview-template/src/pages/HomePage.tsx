/**
 * DESIGN DRAFT — "speechless" salon face, draft 5 (dark editorial mood).
 *
 * Dev-only vehicle: codegen overwrites `src/pages/HomePage.tsx` in every
 * generated workspace, so nothing here ships to a customer preview. Judge it
 * with `npm run dev` in `preview-template/`. Once the direction is approved,
 * the pieces get extracted into `src/ui/public/` skeletons and registered in
 * the catalogue — this file goes back to being a plain scaffold. Shared nav,
 * footer, data and animation vocabulary now live in `_kit.tsx` so Services,
 * Team and Booking stay one voice with Home.
 *
 * Draft 5 over draft 4: avatar photos + real date/time affordance on the
 * booking card, a trust-badge strip, a sound toggle on the video hero, menu
 * thumbnails, and working cross-links to the new interior pages.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { motion, useScroll, useTransform } from 'motion/react';
import {
  FONT_LINK, IMG, SALON, TRUST_POINTS, ICONS,
  Reveal, SectionHeading, Marquee, PublicHeader, PublicFooter, GlobalStyles, THEME_VARS,
} from './_kit';

/**
 * Film-title opening: black frame, the wordmark breathes open, the curtain
 * lifts. Plays once per mount; skipped entirely under reduced motion.
 */
function TitleSequence({ onReveal, onDone }: { onReveal: () => void; onDone: () => void }) {
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      onReveal();
      onDone();
      return;
    }
    const hold = setTimeout(() => { setLeaving(true); onReveal(); }, 1900);
    const done = setTimeout(onDone, 2900);
    return () => { clearTimeout(hold); clearTimeout(done); };
  }, [onReveal, onDone]);
  return (
    <motion.div
      className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-[#070605]"
      animate={leaving ? { y: '-100%' } : { y: 0 }}
      transition={{ duration: 0.9, ease: [0.76, 0, 0.24, 1] }}
    >
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.15 }}
        className="text-[10px] font-semibold uppercase tracking-[0.5em] text-[var(--color-brand)]"
      >
        Gemmayze · Beirut
      </motion.p>
      <motion.h1
        initial={{ opacity: 0, letterSpacing: '0.14em', y: 14 }}
        animate={{ opacity: 1, letterSpacing: '0em', y: 0 }}
        transition={{ duration: 1.3, delay: 0.35, ease: [0.22, 0.61, 0.36, 1] }}
        className="mt-5 font-display text-[clamp(3rem,8vw,6.5rem)] font-light italic leading-none"
      >
        Maison Noor
      </motion.h1>
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 1.1, delay: 0.7, ease: [0.22, 0.61, 0.36, 1] }}
        className="mt-8 h-px w-40 origin-center bg-[var(--color-brand)]/60"
      />
    </motion.div>
  );
}

function BookingCard() {
  const [staff, setStaff] = useState(SALON.team[0].name);
  const [slot, setSlot] = useState('5:15');
  const [booked, setBooked] = useState(false);
  const label = (text: string) => (
    <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">{text}</p>
  );
  return (
    <aside className="fd fd-3 w-full max-w-sm overflow-hidden rounded-3xl border border-white/[0.12] bg-black/45 shadow-[0_60px_120px_-40px_rgba(0,0,0,0.9)] backdrop-blur-2xl">
      <div className="px-7 pb-5 pt-6">
        {label('Book your chair')}
        <p className="mt-2 font-display text-2xl">Balayage / Lived-in color</p>
        <p className="mt-1 text-sm text-white/45">150 min · $140 · gloss included</p>
      </div>
      <div className="border-t border-white/[0.08] px-7 py-5">
        {label('With')}
        <div className="mt-3 flex items-center gap-3">
          {SALON.team.map((t, i) => (
            <button
              key={t.name}
              onClick={() => { setStaff(t.name); setBooked(false); }}
              className="group flex flex-col items-center gap-1.5"
            >
              <span
                className={
                  'block h-11 w-11 overflow-hidden rounded-full ring-2 transition ' +
                  (staff === t.name ? 'ring-[var(--color-brand)]' : 'ring-transparent group-hover:ring-white/30')
                }
              >
                <img src={IMG.team[i]} alt={t.name} className="h-full w-full object-cover" />
              </span>
              <span className={'text-xs transition ' + (staff === t.name ? 'text-white' : 'text-white/50')}>
                {t.name}
              </span>
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 border-t border-white/[0.08] px-7 py-5">
        <div>
          {label('Date')}
          <div className="mt-2 flex items-center gap-2 rounded-lg border border-white/[0.1] bg-white/[0.03] px-3 py-2 text-sm text-white/85">
            <ICONS.MessageCircle className="h-3.5 w-3.5 text-white/35" />
            Thu, Jul 24
          </div>
        </div>
        <div>
          {label('Time')}
          <div className="mt-2 flex gap-1.5">
            {SALON.slots.map((s) => (
              <button
                key={s}
                onClick={() => { setSlot(s); setBooked(false); }}
                className={
                  'flex-1 rounded-lg px-2 py-2 text-xs tabular-nums transition ' +
                  (slot === s ? 'bg-white font-semibold text-black' : 'bg-white/[0.03] text-white/60 hover:bg-white/[0.08]')
                }
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="px-7 pb-7 pt-2">
        <button
          onClick={() => setBooked(true)}
          className={
            'w-full rounded-2xl py-4 font-semibold transition ' +
            (booked
              ? 'chip-pop bg-white text-black'
              : 'bg-[var(--color-brand)] text-black shadow-[0_18px_50px_-16px_var(--color-brand)] hover:brightness-110')
          }
        >
          {booked ? '✓ Chair held — confirmed on WhatsApp' : `Book Thursday ${slot} with ${staff}`}
        </button>
        <p className="mt-3 text-center text-xs leading-relaxed text-white/40">
          {booked
            ? `${staff} just got the heads-up. See you Thursday at ${slot}.`
            : 'Confirmed instantly by our AI — no deposit today.'}
        </p>
      </div>
    </aside>
  );
}

function TrustStrip() {
  return (
    <section className="border-b border-white/[0.06] bg-[#0c0b0a] py-14">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-6 md:grid-cols-4">
        {TRUST_POINTS.map((t, i) => (
          <Reveal key={t.label} delay={i * 80} className="flex items-start gap-3">
            <t.icon className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-brand)]" strokeWidth={1.5} />
            <div>
              <p className="text-sm font-medium text-white/85">{t.label}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-white/40">{t.note}</p>
            </div>
          </Reveal>
        ))}
      </div>
    </section>
  );
}

const AI_REPLY =
  'Saturday we’re fully booked until 4 — but Rania has 4:30 open. Want me to hold it for you? Balayage like last time?';

function TypingDots() {
  return (
    <div className="max-w-[85%] rounded-2xl rounded-bl-md bg-white/[0.08] px-5 py-4">
      <span className="dot inline-block h-1.5 w-1.5 rounded-full bg-white/60" />
      <span className="dot dot2 ml-1 inline-block h-1.5 w-1.5 rounded-full bg-white/60" />
      <span className="dot dot3 ml-1 inline-block h-1.5 w-1.5 rounded-full bg-white/60" />
    </div>
  );
}

/**
 * The conversation plays itself when scrolled into view: client asks, the AI
 * "types" its answer, the booking confirms, the money counters run. Reduced
 * motion (or a missing IntersectionObserver) jumps straight to the final frame.
 */
function AiReceptionBand() {
  const bandRef = useRef<HTMLElement | null>(null);
  const [step, setStep] = useState(0);
  const [typed, setTyped] = useState('');
  const [counts, setCounts] = useState({ booked: 0, recovered: 0 });

  useEffect(() => {
    const el = bandRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setStep(6);
      return;
    }
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        setStep(reduce ? 6 : 1);
      },
      { threshold: 0.35 }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (step === 1 || step === 2 || step === 4 || step === 5) {
      const delays: Record<number, number> = { 1: 900, 2: 1100, 4: 1000, 5: 900 };
      const t = setTimeout(() => setStep(step + 1), delays[step]);
      return () => clearTimeout(t);
    }
    if (step === 3) {
      let i = 0;
      const id = setInterval(() => {
        i += 2;
        setTyped(AI_REPLY.slice(0, i));
        if (i >= AI_REPLY.length) {
          clearInterval(id);
          setTimeout(() => setStep(4), 700);
        }
      }, 22);
      return () => clearInterval(id);
    }
  }, [step]);

  useEffect(() => {
    if (step !== 6) return;
    setTyped(AI_REPLY);
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / 1400);
      const ease = 1 - Math.pow(1 - p, 3);
      setCounts({ booked: Math.round(23 * ease), recovered: Math.round(220 * ease) });
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [step]);

  return (
    <section ref={bandRef} className="relative overflow-hidden bg-[#0a0908] py-32 text-white">
      <span className="ghost-word left-[-2rem] top-6" aria-hidden>Noor</span>
      <div className="relative mx-auto grid max-w-6xl gap-16 px-6 lg:grid-cols-2 lg:items-center">
        <Reveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.3em] text-[var(--color-brand)]">
            The front desk that never sleeps
          </p>
          <h2 className="mt-5 font-display text-5xl font-light leading-[1.02] md:text-6xl">
            It&rsquo;s 11 p.m.
            <br />
            Someone just booked
            <span className="italic text-[var(--color-brand)]"> — nobody was here.</span>
          </h2>
          <p className="mt-6 max-w-md leading-relaxed text-white/55">
            Maison Noor&rsquo;s AI receptionist answers every message, holds the right chair, and
            chases the no-shows — in Arabic, French or English.
          </p>
          <div className="mt-9 flex flex-wrap gap-3">
            <span className="rounded-full border border-white/12 px-4 py-1.5 text-sm text-white/70">
              Replies in ~4 seconds
            </span>
            <span className="rounded-full border border-white/12 px-4 py-1.5 text-sm tabular-nums text-white/70">
              Booked {counts.booked} this week
            </span>
            <span className="rounded-full border border-[var(--color-brand)]/40 px-4 py-1.5 text-sm tabular-nums text-[var(--color-brand)]">
              Recovered ${counts.recovered} in no-shows
            </span>
          </div>
        </Reveal>
        <div className="rounded-3xl border border-white/[0.09] bg-black/30 p-6">
          <div className="mb-5 flex items-center gap-2.5 border-b border-white/[0.07] pb-4">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
            <span className="text-sm font-medium text-white/80">Maison Noor · WhatsApp Business</span>
            <span className="ml-auto text-xs text-white/35">online</span>
          </div>
          <div className="min-h-[19rem] space-y-3">
            {step >= 1 && (
              <div className="pop max-w-[85%] rounded-2xl rounded-bl-md bg-white/[0.08] px-5 py-3.5 text-[15px] text-white/85">
                Do you take walk-ins on Saturday? 💇‍♀️
              </div>
            )}
            {step === 2 && <TypingDots />}
            {step >= 3 && (
              <div className="pop ml-auto max-w-[88%] rounded-2xl rounded-br-md bg-[var(--color-brand)] px-5 py-3.5 text-[15px] font-medium text-black">
                {typed}
                {step === 3 && <span className="ml-0.5 inline-block w-[2px] animate-pulse bg-black/70">&nbsp;</span>}
              </div>
            )}
            {step >= 4 && (
              <div className="pop max-w-[60%] rounded-2xl rounded-bl-md bg-white/[0.08] px-5 py-3.5 text-[15px] text-white/85">
                yes please!!
              </div>
            )}
            {step === 5 && <TypingDots />}
            {step >= 6 && (
              <div className="chip-pop ml-auto flex w-fit items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-black">
                ✓ Held — Saturday 4:30 with Rania · reminder set
              </div>
            )}
          </div>
          <p className="flex items-center gap-2 pt-4 text-xs uppercase tracking-wider text-white/35">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
            Live · answered by Maison Noor&rsquo;s AI
          </p>
        </div>
      </div>
    </section>
  );
}

export default function HomePage() {
  const [revealed, setRevealed] = useState(false);
  const [introGone, setIntroGone] = useState(false);
  const [muted, setMuted] = useState(true);
  const heroRef = useRef<HTMLElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const { scrollYProgress } = useScroll({ target: heroRef, offset: ['start start', 'end start'] });
  const heroImgY = useTransform(scrollYProgress, [0, 1], ['0%', '14%']);
  const heroImgScale = useTransform(scrollYProgress, [0, 1], [1.16, 1.02]);
  const heroTextY = useTransform(scrollYProgress, [0, 1], ['0%', '-22%']);
  const heroFade = useTransform(scrollYProgress, [0.55, 1], [1, 0.2]);

  const allServices = SALON.categories.flatMap((c) => c.services.map((s) => ({ ...s, category: c.label })));

  return (
    <div
      style={THEME_VARS}
      className={`relative bg-[#0c0b0a] font-sans text-white ${revealed ? '' : 'intro-wait'}`}
    >
      <link rel="stylesheet" href={FONT_LINK} />
      {!introGone && (
        <TitleSequence onReveal={() => setRevealed(true)} onDone={() => setIntroGone(true)} />
      )}
      <GlobalStyles />

      <PublicHeader active="/" variant="transparent" />

      {/* Hero — full-bleed editorial with floating booking card, scroll-driven depth */}
      <section ref={heroRef} className="relative flex min-h-[100svh] items-center overflow-hidden">
        <motion.video
          ref={videoRef}
          src={IMG.heroVideo}
          poster={IMG.hero}
          autoPlay
          muted={muted}
          loop
          playsInline
          style={{ y: heroImgY, scale: heroImgScale }}
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-gradient-to-r from-black/90 via-black/55 to-black/20" />
        <div className="absolute inset-x-0 bottom-0 h-44 bg-gradient-to-t from-[#0c0b0a] to-transparent" />
        <motion.div
          style={{ y: heroTextY, opacity: heroFade }}
          className="relative mx-auto grid w-full max-w-7xl gap-12 px-6 pb-28 pt-40 lg:grid-cols-[1.25fr_auto] lg:items-center"
        >
          <div>
            <p className="fd text-[12px] font-semibold uppercase tracking-[0.32em] text-[var(--color-brand)]">
              {SALON.eyebrow}
            </p>
            <h1 className="fd fd-1 mt-7 font-display text-[clamp(2.8rem,9.5vw,7rem)] font-light leading-[0.98] tracking-[-0.015em]">
              The calmest
              <br />
              <span className="italic">chair</span> in
              <span className="italic text-[var(--color-brand)]"> Beirut.</span>
            </h1>
            <p className="fd fd-2 mt-8 max-w-lg text-lg leading-relaxed text-white/65">{SALON.sub}</p>
            <div className="fd fd-2 mt-11 flex items-center gap-6">
              <span className="text-sm text-white/50">4.9 ★ — 312 reviews</span>
              <span className="h-px w-16 bg-white/20" />
              <span className="text-sm text-white/50">Since 2016</span>
              <button
                onClick={() => setMuted((m) => !m)}
                className="ml-2 flex items-center gap-2 rounded-full border border-white/20 px-3.5 py-1.5 text-xs text-white/70 transition hover:border-white/50 hover:text-white"
              >
                {muted ? <ICONS.VolumeX className="h-3.5 w-3.5" /> : <ICONS.Volume2 className="h-3.5 w-3.5" />}
                {muted ? 'Sound on' : 'Mute'}
              </button>
            </div>
          </div>
          <BookingCard />
        </motion.div>
        <div className="absolute bottom-7 left-6 z-10 hidden items-center gap-3 text-[11px] uppercase tracking-[0.3em] text-white/40 md:flex">
          <span className="animate-[ui-scroll-cue_2.2s_ease-in-out_infinite]">↓</span>
          Scroll
        </div>
      </section>

      <TrustStrip />
      <Marquee />

      {/* Services — editorial priced list with thumbnails, teaser of the full menu */}
      <section className="relative overflow-hidden">
        <span className="ghost-word right-[-4rem] top-[-2rem]" aria-hidden>Menu</span>
        <div className="relative mx-auto max-w-6xl px-6 py-32">
          <SectionHeading index="01" note="Prices include the ritual — never rushed">
            The menu<span className="text-[var(--color-brand)]">.</span>
          </SectionHeading>
          <div className="mt-14 border-y border-white/[0.09]">
            {allServices.slice(0, 5).map((s, i) => (
              <Reveal key={s.name} delay={i * 70}>
                <a
                  href="/services"
                  className="group grid grid-cols-[3.5rem_1fr_auto_auto] items-center gap-4 border-b border-white/[0.09] py-6 transition last:border-b-0 hover:bg-white/[0.02] md:grid-cols-[4rem_1fr_auto_auto] md:gap-6"
                >
                  <span className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-white/5 md:h-16 md:w-16">
                    <img
                      src={SALON.categories.find((c) => c.label === s.category)?.image}
                      alt=""
                      className="h-full w-full object-cover transition duration-500 group-hover:scale-110"
                    />
                  </span>
                  <div>
                    <span className="font-display text-[1.35rem] font-light transition group-hover:text-[var(--color-brand)] md:text-[1.7rem]">
                      {s.name}
                    </span>
                    <p className="mt-1 hidden max-w-md text-sm leading-relaxed text-white/45 md:block">{s.desc}</p>
                  </div>
                  <span className="text-sm tabular-nums text-white/40">{s.dur}</span>
                  <span className="text-right font-display text-xl font-light tabular-nums md:text-2xl">{s.price}</span>
                </a>
              </Reveal>
            ))}
          </div>
          <Reveal delay={80} className="mt-8">
            <a
              href="/services"
              className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-brand)] transition hover:gap-3"
            >
              See full menu →
            </a>
          </Reveal>
        </div>
      </section>

      {/* Team — staggered portraits that wake up on hover */}
      <section className="mx-auto max-w-6xl px-6 pb-24">
        <SectionHeading index="02">
          Your people<span className="text-[var(--color-brand)]">.</span>
        </SectionHeading>
        <div className="mt-14 grid gap-9 md:grid-cols-3">
          {SALON.team.map((t, i) => (
            <Reveal key={t.name} delay={i * 110} className={i === 1 ? 'md:mt-14' : ''}>
              <figure className="group">
                <div className="overflow-hidden rounded-2xl">
                  <img
                    src={IMG.team[i]}
                    alt={t.name}
                    className="aspect-[4/5] w-full object-cover grayscale transition duration-700 group-hover:scale-[1.04] group-hover:grayscale-0"
                  />
                </div>
                <figcaption className="mt-5 flex items-baseline justify-between">
                  <p className="font-display text-2xl font-light">{t.name}</p>
                  <p className="text-sm text-white/45">{t.role}</p>
                </figcaption>
              </figure>
            </Reveal>
          ))}
        </div>
        <Reveal delay={100} className="mt-10">
          <a
            href="/team"
            className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-brand)] transition hover:gap-3"
          >
            Meet the full team →
          </a>
        </Reveal>
      </section>

      <AiReceptionBand />

      {/* Gallery strip — staggered rhythm */}
      <section className="mx-auto max-w-7xl px-6 py-28">
        <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
          {IMG.gallery.map((src, i) => (
            <Reveal key={src} delay={i * 90} className={i % 2 ? 'md:mt-14' : ''}>
              <img
                src={src}
                alt=""
                className={'w-full rounded-2xl object-cover ' + (i % 2 ? 'aspect-[3/4]' : 'aspect-square')}
              />
            </Reveal>
          ))}
        </div>
      </section>

      <PublicFooter />
    </div>
  );
}
