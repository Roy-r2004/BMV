/** DESIGN DRAFT — full menu page. See HomePage.tsx header for the extraction plan. */
import {
  FONT_LINK, IMG, SALON,
  Reveal, SectionHeading, PublicHeader, PublicFooter, GlobalStyles, THEME_VARS, PageBanner,
} from './_kit';

export default function ServicesPage() {
  return (
    <div style={THEME_VARS} className="relative bg-[#0c0b0a] font-sans text-white">
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />
      <PublicHeader active="/services" />
      <PageBanner
        image={IMG.bannerServices}
        eyebrow="The full menu"
        title={<>Every ritual<span className="italic text-[var(--color-brand)]"> — priced honestly.</span></>}
      />

      <div className="mx-auto max-w-6xl px-6 py-24">
        {SALON.categories.map((cat, ci) => (
          <section key={cat.id} className="mb-28 last:mb-0">
            <SectionHeading index={String(ci + 1).padStart(2, '0')}>{cat.label}</SectionHeading>
            <div className="mt-12 grid gap-10 lg:grid-cols-[minmax(0,20rem)_1fr]">
              <Reveal className="hidden overflow-hidden rounded-2xl lg:block">
                <img src={cat.image} alt={cat.label} className="aspect-[4/5] w-full object-cover" />
              </Reveal>
              <div className="border-y border-white/[0.09]">
                {cat.services.map((s, i) => (
                  <Reveal key={s.name} delay={i * 70}>
                    <div className="group grid gap-2 border-b border-white/[0.09] py-7 transition last:border-b-0 hover:bg-white/[0.02] md:grid-cols-[1fr_auto_auto] md:items-baseline md:gap-10">
                      <div>
                        <span className="font-display text-[1.6rem] font-light transition group-hover:text-[var(--color-brand)]">
                          {s.name}
                        </span>
                        <p className="mt-1.5 max-w-md text-sm leading-relaxed text-white/45">{s.desc}</p>
                      </div>
                      <span className="text-sm tabular-nums text-white/40">{s.dur}</span>
                      <span className="text-right font-display text-xl font-light tabular-nums">{s.price}</span>
                    </div>
                  </Reveal>
                ))}
              </div>
            </div>
          </section>
        ))}

        <Reveal className="mt-8 flex flex-col items-start gap-4 rounded-3xl border border-white/[0.1] bg-white/[0.03] p-10 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-display text-2xl font-light">Not sure what you need?</p>
            <p className="mt-1.5 text-sm text-white/50">Our AI front desk will ask a few questions and suggest the right ritual.</p>
          </div>
          <a
            href="/booking"
            className="rounded-full bg-[var(--color-brand)] px-6 py-3 text-sm font-semibold text-black transition hover:brightness-110"
          >
            Start booking →
          </a>
        </Reveal>
      </div>

      <PublicFooter />
    </div>
  );
}
