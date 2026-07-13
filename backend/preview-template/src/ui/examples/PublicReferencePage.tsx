import { useMemo } from 'react';

import {
  BrandFooter,
  Button,
  CTABand,
  FeatureBento,
  MarketingHero,
  ProcessSection,
  ProductShowcase,
  PublicShell,
  SkeletonComposer,
  TestimonialRail,
  getSkeleton,
} from '@/ui';

const SKELETON_ID = 'public-home' as const;

/** Reference public site — structure driven by skeleton registry. */
export default function PublicReferencePage() {
  const skeleton = getSkeleton(SKELETON_ID);

  const slots = useMemo(
    () => ({
      hero: (
        <MarketingHero
          variant="cinematic"
          brandName="Lumina"
          headline="Quiet skin rituals, arranged around your life."
          subcopy="Clinical calm with a concierge that books, prepares, and follows up — so the visit feels as considered as the treatment."
          imageSrc="/catalogue-hero.svg"
          imageAlt="Soft light across a calm treatment suite"
          primaryCta={{ label: 'Book a consult', href: '#book' }}
          secondaryCta={{ label: 'View treatments', href: '#features' }}
        />
      ),
      trust: (
        <section className="border-b border-border-subtle bg-card px-6 py-10 lg:px-10" aria-label="Trust">
          <div className="mx-auto flex max-w-7xl flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <p className="max-w-xl text-sm leading-6 text-muted">
              Three studios. Board-led protocols. Returning members who stay for the rhythm — not the noise.
            </p>
            <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm font-semibold tracking-wide text-foreground/80">
              <span>Protocol-led care</span>
              <span>Same-day aftercare</span>
              <span>Membership cadence</span>
            </div>
          </div>
        </section>
      ),
      features: (
        <div id="features">
          <FeatureBento
            variant="bento"
            heading="Designed for how guests actually arrive."
            description="From first curiosity to aftercare, every step keeps the clinic’s voice intact."
            items={[
              {
                title: 'Concierge booking that feels like the front desk',
                description: 'Guided intake captures goals and timing without burying the hero in chat widgets.',
              },
              {
                title: 'Treatment clarity',
                description: 'One idea per surface — guests know what they are choosing.',
              },
              {
                title: 'Aftercare that continues the visit',
                description: 'Reminders stay clinical-calm, never promotional.',
              },
              {
                title: 'Membership pacing',
                description: 'Cadence that protects chairs and guest energy alike.',
              },
            ]}
          />
        </div>
      ),
      showcase: (
        <ProductShowcase
          heading="Signature experiences"
          description="A lead ritual with supporting treatments — hierarchy guests can feel."
          items={[
            {
              title: 'HydraGlow Ritual',
              description: 'Deep cleanse, infusion, and LED calm in one orchestrated visit.',
              imageSrc: '/catalogue-product.svg',
              imageAlt: 'HydraGlow treatment atmosphere',
            },
            {
              title: 'Precision Laser',
              description: 'Targeted clarity with measured downtime guidance.',
              imageSrc: '/catalogue-product-2.svg',
            },
            {
              title: 'Membership Reset',
              description: 'Monthly skin rhythm with concierge scheduling.',
              imageSrc: '/catalogue-product-2.svg',
            },
          ]}
        />
      ),
      process: (
        <ProcessSection
          heading="From curiosity to booked"
          description="Three calm steps. No detours."
          steps={[
            { title: 'Share goals', description: 'A short intake that captures skin goals and timing.' },
            { title: 'Match treatment', description: 'A clear path with transparent pricing and chair availability.' },
            { title: 'Confirm visit', description: 'Reminders and aftercare arrive in the same brand voice.' },
          ]}
        />
      ),
      testimonials: (
        <TestimonialRail
          heading="What returning guests notice"
          items={[
            {
              quote: 'The booking flow felt like the clinic itself — quiet, clear, and personal.',
              author: 'Maya R.',
              role: 'Hydrafacial guest',
            },
            {
              quote: 'Reminders arrived in the same brand voice. I never wondered what to do next.',
              author: 'Jordan K.',
              role: 'Membership client',
            },
            {
              quote: 'Premium without trying too hard. Exactly how Lumina feels in person.',
              author: 'Elena V.',
              role: 'First-time consult',
            },
          ]}
        />
      ),
      cta: (
        <div id="book">
          <CTABand
            heading="Ready for quieter confidence?"
            description="Reserve a consult. We’ll handle the orchestration."
            primaryCta={{ label: 'Book a consult', href: '#book' }}
            secondaryCta={{ label: 'Browse treatments', href: '#features' }}
          />
        </div>
      ),
      footer: (
        <BrandFooter
          brandName="Lumina"
          description="Clinical aesthetics with an AI concierge that books, follows up, and protects brand tone."
          links={[
            { label: 'Treatments', href: '#features' },
            { label: 'Book', href: '#book' },
            { label: 'Studios', href: '#features' },
          ]}
          meta={skeleton.id}
        />
      ),
    }),
    [skeleton.id]
  );

  return (
    <PublicShell
      brandName="Lumina"
      nav={
        <div className="flex items-center gap-5 text-sm text-muted">
          <a href="#features" className="hidden hover:text-foreground sm:inline">
            Treatments
          </a>
          <a href="#book" className="hidden hover:text-foreground sm:inline">
            Visit
          </a>
          <Button href="#book" size="sm">
            Book consult
          </Button>
        </div>
      }
    >
      <SkeletonComposer skeletonId={SKELETON_ID} slots={slots} />
    </PublicShell>
  );
}
