/** DESIGN DRAFT — gallery page. See HomePage.tsx header for the extraction plan. */
import {
  FONT_LINK, IMG,
  Reveal, SectionHeading, PublicHeader, PublicFooter, GlobalStyles, THEME_VARS, PageBanner,
} from './_kit';

const CAPTIONS = [
  'The color bar', 'Balayage in progress', 'Product wall', 'Finishing touches',
  'Wash & scalp ritual', 'Karim, fades', 'Golden hour', 'Quiet corner',
];

export default function GalleryPage() {
  return (
    <div style={THEME_VARS} className="relative bg-[#0c0b0a] font-sans text-white">
      <link rel="stylesheet" href={FONT_LINK} />
      <GlobalStyles />
      <PublicHeader active="/gallery" />
      <PageBanner
        image={IMG.bannerGallery}
        eyebrow="Inside Maison Noor"
        title={<>A calmer<span className="italic text-[var(--color-brand)]"> kind of salon.</span></>}
      />

      <div className="mx-auto max-w-7xl px-6 py-24">
        <SectionHeading index="01" note={`${IMG.gallery.length} photos`}>
          The space<span className="text-[var(--color-brand)]">.</span>
        </SectionHeading>

        <div className="mt-14 grid grid-cols-2 gap-5 md:grid-cols-4">
          {IMG.gallery.map((src, i) => (
            <Reveal key={src} delay={i * 70} className={i % 3 === 1 ? 'md:mt-14' : ''}>
              <figure className="group overflow-hidden rounded-2xl">
                <img
                  src={src}
                  alt={CAPTIONS[i] ?? ''}
                  className={
                    'w-full object-cover transition duration-700 group-hover:scale-105 ' +
                    (i % 5 === 0 ? 'aspect-square' : 'aspect-[3/4]')
                  }
                />
              </figure>
              <p className="mt-3 text-xs text-white/40">{CAPTIONS[i]}</p>
            </Reveal>
          ))}
        </div>

        <Reveal className="mt-20 flex flex-col items-start gap-4 rounded-3xl border border-white/[0.1] bg-white/[0.03] p-10 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-display text-2xl font-light">Seen enough?</p>
            <p className="mt-1.5 text-sm text-white/50">Your chair is a couple of taps away.</p>
          </div>
          <a
            href="/booking"
            className="rounded-full bg-[var(--color-brand)] px-6 py-3 text-sm font-semibold text-black transition hover:brightness-110"
          >
            Book now →
          </a>
        </Reveal>
      </div>

      <PublicFooter />
    </div>
  );
}
