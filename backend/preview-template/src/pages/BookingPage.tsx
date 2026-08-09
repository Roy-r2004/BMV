/** DESIGN DRAFT — the booking flow. See HomePage.tsx header for the extraction plan. */
import { useMemo, useState } from 'react';
import {
  FONT_LINK, IMG, SALON,
  PublicHeader, PublicFooter, GlobalStyles, THEME_VARS, PageBanner,
} from './_kit';

const STEPS = ['Service', 'Stylist', 'Time', 'Confirm'] as const;
const DATES = ['Thu, Jul 24', 'Fri, Jul 25', 'Sat, Jul 26'];

type Service = { name: string; desc: string; dur: string; price: string; category: string };

export default function BookingPage() {
  const allServices: Service[] = useMemo(
    () => SALON.categories.flatMap((c) => c.services.map((s) => ({ ...s, category: c.label }))),
    []
  );
  const [step, setStep] = useState(0);
  const [service, setService] = useState<Service>(allServices[0]);
  const [staff, setStaff] = useState(SALON.team[0].name);
  const [date, setDate] = useState(DATES[0]);
  const [slot, setSlot] = useState(SALON.slots[1]);
  const [name, setName] = useState('');
  const [confirmed, setConfirmed] = useState(false);

  const canAdvance = step < STEPS.length - 1;
  const next = () => setStep((s) => Math.min(s + 1, STEPS.length - 1));
  const back = () => setStep((s) => Math.max(s - 1, 0));

  return (
    <div style={THEME_VARS} className="relative bg-[#0c0b0a] font-sans text-white">
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />
      <PublicHeader active="/booking" />
      <PageBanner
        image={IMG.bannerBooking}
        eyebrow="Book your chair"
        title={<>Two minutes<span className="italic text-[var(--color-brand)]"> — held instantly.</span></>}
      />

      <div className="mx-auto grid max-w-6xl gap-12 px-6 py-20 lg:grid-cols-[1fr_22rem]">
        <div>
          {/* Stepper */}
          <div className="mb-12 flex items-center gap-3">
            {STEPS.map((label, i) => (
              <div key={label} className="flex items-center gap-3">
                <button
                  onClick={() => setStep(i)}
                  disabled={confirmed}
                  className={
                    'flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold transition ' +
                    (i === step
                      ? 'bg-[var(--color-brand)] text-black'
                      : i < step
                        ? 'bg-white/15 text-white'
                        : 'border border-white/15 text-white/40')
                  }
                >
                  {i + 1}
                </button>
                <span className={'text-sm ' + (i === step ? 'text-white' : 'text-white/40')}>{label}</span>
                {i < STEPS.length - 1 && <span className="h-px w-8 bg-white/15" />}
              </div>
            ))}
          </div>

          {confirmed ? (
            <div className="chip-pop rounded-3xl border border-white/[0.12] bg-white/[0.03] p-12 text-center">
              <p className="text-5xl">✓</p>
              <p className="mt-6 font-display text-3xl font-light">
                Held — {date} at {slot} with {staff}
              </p>
              <p className="mx-auto mt-4 max-w-sm text-sm leading-relaxed text-white/50">
                Confirmed instantly on WhatsApp{name ? `, ${name}` : ''}. Our AI will send a reminder the evening
                before — no deposit needed today.
              </p>
              <a href="/" className="mt-8 inline-block text-sm font-medium text-[var(--color-brand)]">
                ← Back to Maison Noor
              </a>
            </div>
          ) : (
            <>
              {step === 0 && (
                <div className="space-y-3">
                  {allServices.map((s) => (
                    <button
                      key={s.name}
                      onClick={() => setService(s)}
                      className={
                        'flex w-full items-center justify-between rounded-2xl border px-6 py-5 text-left transition ' +
                        (service.name === s.name
                          ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/[0.08]'
                          : 'border-white/[0.1] hover:border-white/25')
                      }
                    >
                      <div>
                        <p className="font-display text-xl font-light">{s.name}</p>
                        <p className="mt-1 text-xs text-white/45">{s.category} · {s.dur}</p>
                      </div>
                      <span className="font-display text-lg tabular-nums text-white/80">{s.price}</span>
                    </button>
                  ))}
                </div>
              )}

              {step === 1 && (
                <div className="grid gap-4 sm:grid-cols-3">
                  {SALON.team.map((t, i) => (
                    <button
                      key={t.name}
                      onClick={() => setStaff(t.name)}
                      className={
                        'overflow-hidden rounded-2xl border text-left transition ' +
                        (staff === t.name ? 'border-[var(--color-brand)]' : 'border-white/[0.1] hover:border-white/25')
                      }
                    >
                      <img src={IMG.team[i]} alt={t.name} className="aspect-square w-full object-cover grayscale" />
                      <div className="p-4">
                        <p className="font-display text-lg">{t.name}</p>
                        <p className="text-xs text-white/45">{t.role}</p>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {step === 2 && (
                <div className="space-y-8">
                  <div>
                    <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">Date</p>
                    <div className="flex flex-wrap gap-2">
                      {DATES.map((d) => (
                        <button
                          key={d}
                          onClick={() => setDate(d)}
                          className={
                            'rounded-full px-4 py-2 text-sm transition ' +
                            (date === d ? 'bg-white font-semibold text-black' : 'border border-white/[0.15] text-white/60 hover:border-white/40')
                          }
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">Time</p>
                    <div className="flex flex-wrap gap-2">
                      {SALON.slots.map((s) => (
                        <button
                          key={s}
                          onClick={() => setSlot(s)}
                          className={
                            'rounded-full px-4 py-2 text-sm tabular-nums transition ' +
                            (slot === s ? 'bg-[var(--color-brand)] font-semibold text-black' : 'border border-white/[0.15] text-white/60 hover:border-white/40')
                          }
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {step === 3 && (
                <div className="max-w-sm space-y-4">
                  <div>
                    <label className="mb-2 block text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">
                      Your name
                    </label>
                    <input
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="e.g. Lea Matar"
                      className="w-full rounded-xl border border-white/[0.15] bg-white/[0.03] px-4 py-3 text-sm text-white placeholder:text-white/30 focus:border-[var(--color-brand)] focus:outline-none"
                    />
                  </div>
                  <p className="text-xs leading-relaxed text-white/40">
                    We&rsquo;ll confirm on WhatsApp and remind you the evening before. No deposit needed today.
                  </p>
                </div>
              )}

              <div className="mt-10 flex items-center gap-4">
                {step > 0 && (
                  <button onClick={back} className="text-sm text-white/50 transition hover:text-white">
                    ← Back
                  </button>
                )}
                <button
                  onClick={canAdvance ? next : () => setConfirmed(true)}
                  className="ml-auto rounded-full bg-[var(--color-brand)] px-7 py-3 text-sm font-semibold text-black transition hover:brightness-110"
                >
                  {canAdvance ? 'Continue →' : 'Confirm booking'}
                </button>
              </div>
            </>
          )}
        </div>

        {/* Summary sidebar */}
        {!confirmed && (
          <aside className="h-fit rounded-3xl border border-white/[0.1] bg-white/[0.03] p-7">
            <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]/90">Summary</p>
            <div className="mt-4 space-y-3 text-sm">
              <p className="font-display text-xl font-light text-white">{service.name}</p>
              <p className="text-white/45">{service.dur} · {service.price}</p>
              <div className="border-t border-white/[0.08] pt-3 text-white/70">With {staff}</div>
              {step >= 2 && <div className="text-white/70">{date} · {slot}</div>}
            </div>
          </aside>
        )}
      </div>

      <PublicFooter />
    </div>
  );
}
