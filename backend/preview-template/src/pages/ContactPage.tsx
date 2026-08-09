/** DESIGN DRAFT — contact page. See HomePage.tsx header for the extraction plan. */
import { useState } from 'react';
import {
  FONT_LINK, IMG, SALON, ICONS,
  Reveal, PublicHeader, PublicFooter, GlobalStyles, THEME_VARS, PageBanner,
} from './_kit';

export default function ContactPage() {
  const [step, setStep] = useState<'idle' | 'typing' | 'sent'>('idle');
  const [msg, setMsg] = useState('');

  const send = () => {
    if (!msg.trim()) return;
    setStep('sent');
  };

  return (
    <div style={THEME_VARS} className="relative bg-[#0c0b0a] font-sans text-white">
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />
      <PublicHeader active="/contact" />
      <PageBanner
        image={IMG.bannerContact}
        eyebrow="Talk to us"
        title={<>We&rsquo;re a message<span className="italic text-[var(--color-brand)]"> away.</span></>}
      />

      <div className="mx-auto grid max-w-6xl gap-16 px-6 py-24 lg:grid-cols-2">
        <Reveal>
          <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">
            Message our AI front desk
          </p>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-white/50">
            No phone tag. Ask about availability, pricing, or anything else — it answers in seconds,
            in Arabic, French or English.
          </p>

          <div className="mt-8 rounded-3xl border border-white/[0.1] bg-black/30 p-6">
            <div className="mb-5 flex items-center gap-2.5 border-b border-white/[0.07] pb-4">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
              <span className="text-sm font-medium text-white/80">Maison Noor · WhatsApp Business</span>
              <span className="ml-auto text-xs text-white/35">online</span>
            </div>

            {step === 'sent' ? (
              <div className="space-y-3 py-2">
                <div className="pop ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-[var(--color-brand)] px-5 py-3.5 text-[15px] font-medium text-black">
                  {msg}
                </div>
                <div className="pop max-w-[88%] rounded-2xl rounded-bl-md bg-white/[0.08] px-5 py-3.5 text-[15px] text-white/85">
                  Got it — I&rsquo;ll have someone confirm shortly, or I can hold you a slot right now.
                  Want me to check tomorrow afternoon?
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <input
                  value={msg}
                  onChange={(e) => { setMsg(e.target.value); setStep('typing'); }}
                  onKeyDown={(e) => e.key === 'Enter' && send()}
                  placeholder="Type a message…"
                  className="flex-1 rounded-full border border-white/[0.15] bg-white/[0.04] px-5 py-3 text-sm text-white placeholder:text-white/30 focus:border-[var(--color-brand)] focus:outline-none"
                />
                <button
                  onClick={send}
                  className="rounded-full bg-[var(--color-brand)] px-5 py-3 text-sm font-semibold text-black transition hover:brightness-110"
                >
                  Send
                </button>
              </div>
            )}
          </div>
        </Reveal>

        <Reveal delay={100} className="space-y-8">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">Visit</p>
            <p className="mt-3 font-display text-2xl font-light">{SALON.address}</p>
            <p className="mt-1 text-sm text-white/45">{SALON.hours}</p>
          </div>
          <div className="overflow-hidden rounded-2xl border border-white/[0.1]">
            <img src={IMG.bannerContact} alt="" className="aspect-video w-full object-cover" />
          </div>
          <div className="flex items-center gap-5 text-white/50">
            <a href="#" className="transition hover:text-white"><ICONS.Instagram className="h-5 w-5" /></a>
            <a href="#" className="transition hover:text-white"><ICONS.Facebook className="h-5 w-5" /></a>
            <a href="#" className="flex items-center gap-2 transition hover:text-white">
              <ICONS.MessageCircle className="h-5 w-5" />
              <span className="text-sm">WhatsApp {SALON.whatsapp}</span>
            </a>
          </div>
        </Reveal>
      </div>

      <PublicFooter />
    </div>
  );
}
