/** DESIGN DRAFT — team page. See HomePage.tsx header for the extraction plan. */
import {
  FONT_LINK, IMG, SALON,
  Reveal, SectionHeading, PublicHeader, PublicFooter, GlobalStyles, THEME_VARS, PageBanner,
} from './_kit';

export default function TeamPage() {
  return (
    <div style={THEME_VARS} className="relative bg-[#0c0b0a] font-sans text-white">
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />
      <PublicHeader active="/team" />
      <PageBanner
        image={IMG.bannerTeam}
        eyebrow="The people"
        title={<>Three chairs<span className="italic text-[var(--color-brand)]"> — one standard.</span></>}
      />

      <div className="mx-auto max-w-6xl px-6 py-24">
        <SectionHeading index="01" note={`${SALON.team.length} specialists · book any of them directly`}>
          Your people<span className="text-[var(--color-brand)]">.</span>
        </SectionHeading>

        <div className="mt-16 space-y-24">
          {SALON.team.map((t, i) => (
            <Reveal key={t.name} delay={i * 90}>
              <div className={`grid items-center gap-10 md:grid-cols-2 ${i % 2 ? 'md:[&>*:first-child]:order-2' : ''}`}>
                <div className="overflow-hidden rounded-3xl">
                  <img
                    src={IMG.team[i]}
                    alt={t.name}
                    className="aspect-[4/5] w-full object-cover grayscale transition duration-700 hover:grayscale-0"
                  />
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.28em] text-[var(--color-brand)]">
                    {t.role} · {t.years}
                  </p>
                  <h3 className="mt-4 font-display text-4xl font-light md:text-5xl">{t.name}</h3>
                  <p className="mt-5 max-w-md leading-relaxed text-white/55">{t.bio}</p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    {t.specialties.map((s) => (
                      <span key={s} className="rounded-full border border-white/15 px-3.5 py-1.5 text-xs text-white/65">
                        {s}
                      </span>
                    ))}
                  </div>
                  <a
                    href="/booking"
                    className="mt-8 inline-flex items-center gap-2 rounded-full bg-[var(--color-brand)] px-6 py-3 text-sm font-semibold text-black transition hover:brightness-110"
                  >
                    Book with {t.name} →
                  </a>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>

      <PublicFooter />
    </div>
  );
}
